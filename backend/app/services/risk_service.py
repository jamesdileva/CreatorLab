"""Risk-based approval classifier (roadmap Sprint 21.2).

Classifies pending content as LOW / MEDIUM / HIGH using the existing
deterministic screens (`review_service`) plus simulation signals, so reviewers
can prioritise and low-risk items can take a faster — still explicit, human —
approval path.

Oversight is never eliminated: classification only recommends; every approval
(including the fast lane) is a human action, and publishing remains a separate,
explicit human step (architecture §5.6, §20). No artificial engagement, no
autonomous publishing.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.episode import Episode
from ..models.risk import RiskAssessment
from .review_service import PENDING_STATUSES, ReviewPayload, review_payload

CLASSIFIER_VERSION = "risk-v1"
RISK_LEVELS = ("LOW", "MEDIUM", "HIGH")
_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

# Simulation reason codes that signal genuine audience risk (never fast-lane).
RISKY_SIM_CODES = {"controversy", "outrage", "clickbait", "misleading", "rage", "rage_bait"}
# Below this mean simulated watch probability the content looks weak.
LOW_WATCH_THRESHOLD = 0.35
# REVIEW-severity codes that never escalate on their own (always required).
_NON_ESCALATING = {"clean", "synthetic_media_disclosure"}


@dataclass
class RiskVerdict:
    level: str
    fast_lane: bool
    reasons: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    classifier_version: str = CLASSIFIER_VERSION


def _classify_payload(payload: ReviewPayload) -> RiskVerdict:
    reasons: list[str] = []
    signals: dict = {"risk_codes": sorted({r.code for r in payload.risks})}
    level = "LOW"

    def escalate(to: str) -> None:
        nonlocal level
        if _RANK[to] > _RANK[level]:
            level = to

    for risk in payload.risks:
        if risk.severity == "BLOCK":
            escalate("HIGH")
            reasons.append(f"hard block ({risk.code}): {risk.detail}")
        elif risk.code == "sensitive_topic":
            escalate("HIGH")
            reasons.append(f"sensitive topic requires close human judgment: {risk.detail}")
        elif risk.severity == "REVIEW" and risk.code not in _NON_ESCALATING:
            escalate("MEDIUM")
            reasons.append(f"needs review ({risk.code}): {risk.detail}")

    sim = payload.simulation
    if sim is None:
        escalate("MEDIUM")
        reasons.append("no simulated-audience run — reception unverified")
    else:
        agg = sim.get("aggregate", {})
        means = agg.get("means", {})
        counts = agg.get("reason_counts", {}) or {}
        watch = means.get("watch_probability")
        signals["watch_probability"] = watch
        signals["reason_counts"] = counts
        flags = sorted(set(counts) & RISKY_SIM_CODES)
        if flags:
            escalate("HIGH")
            reasons.append(f"simulation flags risky reception: {flags}")
        if watch is not None and watch < LOW_WATCH_THRESHOLD:
            escalate("MEDIUM")
            reasons.append(f"low simulated watch probability ({watch:.2f})")

    fast_lane = level == "LOW"
    if not reasons:
        reasons.append("no material risk detected")
    reasons.append("human approval still required to publish")
    return RiskVerdict(level=level, fast_lane=fast_lane, reasons=reasons, signals=signals)


def classify_episode(db: Session, episode: Episode) -> RiskVerdict:
    return _classify_payload(review_payload(db, episode))


def record_assessment(
    db: Session,
    episode: Episode,
    verdict: RiskVerdict,
    actor: str = "human",
    note: str = "",
) -> RiskAssessment:
    row = RiskAssessment(
        episode_id=episode.id,
        level=verdict.level,
        fast_lane=verdict.fast_lane,
        reasons=verdict.reasons,
        signals=verdict.signals,
        classifier_version=verdict.classifier_version,
        actor=actor,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_assessment(db: Session, episode_id: int) -> RiskAssessment | None:
    return (
        db.query(RiskAssessment)
        .filter(RiskAssessment.episode_id == episode_id)
        .order_by(RiskAssessment.id.desc())
        .first()
    )


def risk_queue(db: Session) -> list[dict]:
    """Pending episodes with their verdict, HIGH risk first."""
    from ..models.episode import Episode as _Episode

    episodes = (
        db.query(_Episode)
        .filter(_Episode.status.in_(PENDING_STATUSES))
        .all()
    )
    rows = []
    for episode in episodes:
        verdict = classify_episode(db, episode)
        rows.append(
            {
                "episode_id": episode.id,
                "title": episode.title,
                "episode_number": episode.episode_number,
                "status": episode.status.value,
                "series_id": episode.series_id,
                "level": verdict.level,
                "fast_lane": verdict.fast_lane,
                "reasons": verdict.reasons,
                "classifier_version": verdict.classifier_version,
            }
        )
    rows.sort(key=lambda r: (-_RANK[r["level"]], -r["episode_id"]))
    return rows


def fast_lane_episodes(db: Session) -> list[Episode]:
    from ..models.episode import Episode as _Episode

    episodes = (
        db.query(_Episode)
        .filter(_Episode.status.in_(PENDING_STATUSES))
        .order_by(_Episode.id.desc())
        .all()
    )
    return [e for e in episodes if classify_episode(db, e).fast_lane]
