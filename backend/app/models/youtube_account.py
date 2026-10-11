"""YouTubeAccount model — authorized channels (guide §12).

OAuth tokens never live in the database: oauth_reference points at a token
file outside version control, per the "never commit credentials" rule.
"""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base


class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(200), default="")
    oauth_reference: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="active")
    scopes: Mapped[str] = mapped_column(Text, default="")
    last_sync: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
