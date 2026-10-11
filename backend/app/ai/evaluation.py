"""Draft evaluation — every episode passes gates before it can continue (guide §19).

PASS: safe and consistent -> normal flow
REVIEW: usable but suspicious -> persisted, but flagged for the human approval queue
BLOCK: never persisted
"""
import re
from dataclasses import dataclass, field
from enum import Enum

from .structured_output import EpisodeDraft


class Severity(str, Enum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass
class Issue:
    code: str
    severity: Severity
    detail: str


@dataclass
class Evaluation:
    issues: list[Issue] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(i.severity is Severity.BLOCK for i in self.issues):
            return "BLOCK"
        if any(i.severity is Severity.REVIEW for i in self.issues):
            return "REVIEW"
        return "PASS"


# Terms that are never acceptable regardless of context (architecture §20).
BANNED_TERMS = [
    "impersonate",
    "deepfake",
    "buy views",
    "buy subscribers",
    "engagement farm",
    "manipulate the algorithm",
    "real person ",
]

_NEGATORS = [
    "does not",
    "doesn't",
    "did not",
    "didn't",
    "no longer",
    "stopped owning",
    "gave up",
    "sold his",
    "sold her",
]

_STOPWORDS = {
    "the",
    "and",
    "his",
    "her",
    "that",
    "with",
    "from",
    "this",
    "have",
    "has",
    "was",
    "for",
    "are",
    "not",
}


def _keywords(statement: str) -> set[str]:
    return {
        w.strip(".,;:!?\"'()").lower()
        for w in statement.split()
        if len(w.strip(".,;:!?\"'()")) > 4
    } - _STOPWORDS


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]


def _overlap(a: str, b: str) -> float:
    wa = set(w.lower() for w in re.findall(r"\w+", a) if len(w) > 2)
    wb = set(w.lower() for w in re.findall(r"\w+", b) if len(w) > 2)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def evaluate_draft(
    draft: EpisodeDraft,
    canon: list[str] | None = None,
    previous_premises: list[str] | None = None,
    open_threads: list[str] | None = None,
) -> Evaluation:
    issues: list[Issue] = []
    canon = canon or []
    previous_premises = previous_premises or []
    open_threads = open_threads or []

    full_text = " ".join(
        [draft.premise, draft.synopsis, draft.script, *[s.title for s in draft.scenes]]
    ).lower()

    # 1. Hard safety terms (architecture §20)
    for term in BANNED_TERMS:
        if term in full_text:
            issues.append(
                Issue(
                    code="safety_violation",
                    severity=Severity.BLOCK,
                    detail=f"draft contains banned term: {term!r}",
                )
            )

    # 2. Canon contradiction: negated statements about canon keywords
    for statement in canon:
        keywords = _keywords(statement)
        if not keywords:
            continue
        for sentence in _sentences(full_text):
            sentence_keywords = _keywords(sentence) & keywords
            if not sentence_keywords:
                continue
            if _overlap(sentence, statement) > 0.6:
                continue  # near-verbatim canon echo, not a contradiction
            lowered = sentence.lower()
            if any(neg in lowered for neg in _NEGATORS):
                issues.append(
                    Issue(
                        code="canon_contradiction",
                        severity=Severity.REVIEW,
                        detail=(
                            f"possible contradiction of canon {statement!r} "
                            f"in sentence {sentence!r}"
                        ),
                    )
                )

    # 3. Canon awareness: canon exists but draft never references it
    if canon and not any(
        (_keywords(statement) & _keywords(full_text)) for statement in canon
    ):
        issues.append(
            Issue(
                code="canon_not_referenced",
                severity=Severity.REVIEW,
                detail="draft does not reference any established canon",
            )
        )

    # 4. Repetition vs previous episodes (architecture §5.5)
    for old in previous_premises:
        if _overlap(draft.premise, old) > 0.6:
            issues.append(
                Issue(
                    code="repetition",
                    severity=Severity.REVIEW,
                    detail=f"premise too similar to existing episode: {old!r}",
                )
            )

    # 5. Thread resolution claims must reference a real open thread (Sprint 2.3)
    if getattr(draft, "resolves_thread", None):
        titles = {t.strip().lower() for t in open_threads}
        if draft.resolves_thread.strip().lower() not in titles:
            issues.append(
                Issue(
                    code="thread_not_found",
                    severity=Severity.REVIEW,
                    detail=f"draft claims to resolve unknown thread: {draft.resolves_thread!r}",
                )
            )

    return Evaluation(issues=issues)
