"""Publication policy — what may be published and what still blocks it (Sprint 7.4).

Official API first (architecture §5.8/§17). Public automated uploads require:
1. publishing_mode == "public_api"
2. the connected account holds the youtube.upload scope
3. the Google API audit is recorded as approved
Anything else keeps MVP publishing private + human-approved.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models.audit_status import AuditStatus
from ..models.youtube_account import YouTubeAccount

VALID_STATUSES = ("not_submitted", "in_review", "more_info", "approved", "denied")


def record_audit_status(db: Session, status: str, notes: str = "", project_name: str | None = None) -> AuditStatus:
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {list(VALID_STATUSES)}")
    row = db.query(AuditStatus).first()
    if row is None:
        row = AuditStatus(status=status, notes=notes, project_name=project_name or "CreatorLab")
        db.add(row)
    else:
        row.status = status
        if notes:
            row.notes = notes
        if project_name:
            row.project_name = project_name
    db.commit()
    db.refresh(row)
    return row


def get_audit_status(db: Session) -> AuditStatus:
    row = db.query(AuditStatus).first()
    if row is None:
        row = AuditStatus(status="not_submitted")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def publication_mode() -> str:
    from ..core.config import settings

    return settings.publishing_mode


def public_blockers(account: YouTubeAccount | None, audit: AuditStatus) -> list[str]:
    """Why public automated publishing is not available right now."""
    blockers: list[str] = []
    if publication_mode() != "public_api":
        blockers.append(
            f"publishing_mode is {publication_mode()!r}; set PUBLISHING_MODE=public_api when ready"
        )
    if audit.status != "approved":
        blockers.append(f"audit status is {audit.status!r}; approval required")
    if account is None:
        blockers.append("no active connected channel")
    elif "youtube.upload" not in (account.scopes or ""):
        blockers.append("connected channel lacks the youtube.upload scope")
    return blockers


def policy(db: Session) -> dict:
    audit = get_audit_status(db)
    account = (
        db.query(YouTubeAccount).filter_by(status="active").first()
    )
    blockers = public_blockers(account, audit)
    return {
        "mode": publication_mode(),
        "public_automated_uploads_allowed": not blockers,
        "blockers": blockers,
        "audit": {
            "project_name": audit.project_name,
            "status": audit.status,
            "notes": audit.notes,
            "scopes_requested": audit.scopes_requested,
            "updated_at": audit.updated_at.isoformat(),
        },
        "fallback": (
            "manual publishing: human downloads the private render and uploads it"
        ),
    }
