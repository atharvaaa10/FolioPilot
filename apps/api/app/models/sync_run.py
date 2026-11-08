"""Audit and execution runs for AMFI sync and mfapi backfills."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.fund import Fund


class NavSyncRun(Base, UUIDPrimaryKeyMixin):
    """Audit record for a NAV sync or history backfill operation."""

    __tablename__ = "nav_sync_runs"

    source: Mapped[str] = mapped_column(String(50), nullable=False)
    fund_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("funds.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schemes_parsed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    funds_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    funds_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nav_rows_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fund: Mapped["Fund | None"] = relationship("Fund")
