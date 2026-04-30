"""Dispatch + DispatchAttempt models — log of every dispatch and per-channel attempt."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, ULIDType, generate_ulid


class Dispatch(Base):
    """One ``POST /dispatch`` call. Renders a template (or inline pair) and fans
    out to one or more channels; per-channel results live in DispatchAttempt.
    """

    __tablename__ = "dispatches"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_dispatches_tenant_idempotency"
        ),
        Index("ix_dispatches_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    tenant_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[str | None] = mapped_column(
        ULIDType, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # Snapshot of the request — useful for replay, debugging, and audits.
    rendered_title: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_body: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    request_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Aggregate status across all channel attempts.
    # one of: "succeeded", "partial", "failed"
    status: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


class DispatchAttempt(Base):
    """Per-channel result for a single Dispatch."""

    __tablename__ = "dispatch_attempts"
    __table_args__ = (
        UniqueConstraint(
            "dispatch_id", "channel_id", "attempt", name="uq_attempts_dispatch_channel_attempt"
        ),
    )

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    dispatch_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("dispatches.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)
    # one of: "succeeded", "failed"
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
