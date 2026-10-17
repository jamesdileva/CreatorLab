"""Human baseline — synthetic audience vs human panel vs real viewers (17.1).

Phase 17 experiment: a human panel ranks the same candidate videos that the
synthetic audience scores and the real YouTube audience watches. The comparison
reports all three pairwise agreements:

- synthetic ↔ human (does the simulator resemble human judgment?)
- synthetic ↔ reality (does it resemble the real audience?)
- human ↔ reality (how reliable is human judgment as a baseline?)

Only candidates that all three judges scored enter the comparison, so every
pair is computed over the same items. Interpretation is gated (guide §15).
"""
from sqlalchemy.orm import Session

from ..core.metrics import directional_accuracy, kendall_tau, spearman, top_k_agreement
from ..models.episode import Episode
from ..models.human_panel import HumanPanelRanking
from ..models.published_video import PublishedVideo
from ..models.simulation import ViewerReaction
from ..models.video_metrics import VideoMetrics
from .review_service import latest_simulation_for
from .simulation_service import aggregate_reactions

MIN_PANEL = 2  # a ranking ranks at least two candidates
MIN_CANDIDATES = 5
RESEMBLES_THRESHOLD = 0.6  # directional accuracy at/above this counts as resemblance


class PanelError(ValueError):
    pass


def record_panel_ranking(
    db: Session, candidate_type: str, order: list[int], note: str = ""
) -> HumanPanelRanking:
    """Validate and store one panel ranking (best-first candidate ids)."""
    if candidate_type != "episode":
        raise PanelError("candidate_type must be 'episode' in Sprint 17.1")
    ids = list(dict.fromkeys(int(v) for v in order))
    if len(ids) < MIN_PANEL:
        raise PanelError(f"a ranking needs at least {MIN_PANEL} distinct candidates")
    if len(ids) != len(order):
        raise PanelError("candidate ids must be unique and integers")
    unknown = [cid for cid in ids if db.get(Episode, cid) is None]
    if unknown:
        raise PanelError(f"unknown episode ids: {unknown}")
    row = HumanPanelRanking(candidate_type=candidate_type, order=ids, note=note.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _sim_watch(db: Session, episode_id: int) -> float | None:
    run = latest_simulation_for(db, episode_id)
    if run is None:
        return None
    reactions = db.query(ViewerReaction).filter(ViewerReaction.run_id == run.id).all()
    if not reactions:
        return None
    return aggregate_reactions(reactions)["means"]["watch_probability"]


def _real_views(db: Session, episode_id: int) -> int | None:
    video = (
        db.query(PublishedVideo)
        .filter(PublishedVideo.episode_id == episode_id)
        .order_by(PublishedVideo.id.desc())
        .first()
    )
    if video is None:
        return None
    snap = (
        db.query(VideoMetrics)
        .filter(VideoMetrics.published_video_id == video.id)
        .order_by(VideoMetrics.id.desc())
        .first()
    )
    return snap.views if snap is not None else None


def _pair(order_a: list[int], order_b: list[int]) -> dict:
    """Agreement stats for two best-first orders over the same items."""
    ids = order_a
    pos_a = {cid: i for i, cid in enumerate(order_a)}
    pos_b = {cid: i for i, cid in enumerate(order_b)}
    values_a = [float(pos_a[cid]) for cid in ids]
    values_b = [float(pos_b[cid]) for cid in ids]
    return {
        "top_1_match": order_a[0] == order_b[0],
        "top_3_overlap": round(top_k_agreement(order_a, order_b, 3), 3),
        "directional_accuracy": round(directional_accuracy(order_a, order_b), 3),
        "spearman": round(spearman(values_a, values_b), 3),
        "kendall_tau": round(kendall_tau(values_a, values_b), 3),
        "candidates": len(ids),
    }


def judge_comparison(db: Session, series_id: int | None = None) -> dict:
    """Three-way comparison over candidates all three judges scored."""
    query = db.query(Episode).order_by(Episode.id)
    if series_id is not None:
        query = query.filter(Episode.series_id == series_id)
    episodes = query.all()

    panel = (
        db.query(HumanPanelRanking)
        .filter(HumanPanelRanking.candidate_type == "episode")
        .order_by(HumanPanelRanking.id.desc())
        .first()
    )

    rows = []
    for episode in episodes:
        sim_watch = _sim_watch(db, episode.id)
        real_views = _real_views(db, episode.id)
        human_pos = panel.order.index(episode.id) if panel and episode.id in panel.order else None
        complete = sim_watch is not None and real_views is not None and human_pos is not None
        rows.append(
            {
                "episode_id": episode.id,
                "sim_watch": sim_watch,
                "human_position": human_pos,
                "real_views": real_views,
                "judged_by_all_three": complete,
            }
        )

    scored = {r["episode_id"]: r for r in rows}
    common = [r["episode_id"] for r in rows if r["judged_by_all_three"]]
    pairs: dict[str, dict] = {}
    orders: dict[str, list[int]] = {}
    if len(common) >= 2:
        synthetic = sorted(common, key=lambda cid: (-scored[cid]["sim_watch"], cid))
        human = [cid for cid in panel.order if cid in common]
        reality = sorted(common, key=lambda cid: (-scored[cid]["real_views"], cid))
        orders = {
            "synthetic": synthetic,
            "human": human,
            "reality": reality,
            "candidate_ids": common,
        }
        pairs = {
            "synthetic_vs_human": _pair(synthetic, human),
            "synthetic_vs_reality": _pair(synthetic, reality),
            "human_vs_reality": _pair(human, reality),
        }

    interpretation_allowed = len(common) >= MIN_CANDIDATES
    sim_human = pairs.get("synthetic_vs_human")
    sim_reality = pairs.get("synthetic_vs_reality")

    if not interpretation_allowed:
        verdict = "insufficient data — no interpretation (guide §15)"
    elif sim_human and sim_reality:
        resembles_human = sim_human["directional_accuracy"] >= RESEMBLES_THRESHOLD
        resembles_reality = sim_reality["directional_accuracy"] >= RESEMBLES_THRESHOLD
        if resembles_human and resembles_reality:
            verdict = "simulator resembles human judgment and the real audience"
        elif resembles_human:
            verdict = "simulator resembles human judgment, but not the real audience"
        elif resembles_reality:
            verdict = "simulator matches the real audience, but not human judgment"
        else:
            verdict = "simulator resembles neither human judgment nor the real audience"
    else:
        verdict = "comparison incomplete"

    return {
        "min_candidates": MIN_CANDIDATES,
        "panel_rankings_recorded": panel.id if panel else 0,
        "panel_note": panel.note if panel else "",
        "candidates": len(common),
        "interpretation_allowed": interpretation_allowed,
        "resembles_threshold": RESEMBLES_THRESHOLD,
        "candidates_scored": rows,
        "orders": orders,
        "pairs": pairs,
        "verdict": verdict,
    }
