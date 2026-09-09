"""Monitor model — a dead-man's timer over a consumer's periodic check-ins.

A consumer that only reports *findings* is silent in exactly the cases that
matter: a stopped timer, a wedged process, or a dead node all produce zero
findings and zero traffic, which is indistinguishable from health.
CannObserv/observo#473 is what that cost — a crash-looped Redis left a cluster
starved for two weeks because nothing was watching for silence.

So a consumer checks in every tick regardless, and this row records when it
last did. ``src/core/monitors.py`` compares that against
``interval_seconds + grace_seconds`` and treats the *absence* of a check-in as
the alert (#56).
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, TimestampMixin, ULIDType, generate_ulid


class Monitor(Base, TimestampMixin):
    """One reporting source, its expected cadence, and where to alert.

    ``title_template``/``body_template``/``template_id`` render the *report*
    a check-in carries when the consumer marks it ``alert``. The missing and
    recovery notifications are built in rather than configurable: a consumer
    that has stopped reporting cannot supply a template for the fact that it
    stopped reporting.

    ``channel_ids`` is a plain array, not a join table — it mirrors the
    ``channel_ids`` a dispatch request carries, and ownership is re-checked on
    every write. The cost is that ids can go stale when a channel is deleted;
    the sweep treats an unresolvable id as an undeliverable monitor rather
    than an exception (see ``sweep_monitors``).
    """

    __tablename__ = "monitors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_monitors_tenant_name"),
        CheckConstraint(
            "state IN ('pending', 'ok', 'missing')",
            name="ck_monitors_state",
        ),
        CheckConstraint("interval_seconds > 0", name="ck_monitors_interval_positive"),
        CheckConstraint("grace_seconds >= 0", name="ck_monitors_grace_non_negative"),
        CheckConstraint(
            "renotify_seconds IS NULL OR renotify_seconds > 0",
            name="ck_monitors_renotify_positive",
        ),
        # The sweep's only query: every enabled monitor, every minute.
        Index("ix_monitors_enabled", "enabled"),
    )

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    tenant_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    #: False pauses the timer without destroying the configuration — planned
    #: downtime should not require deleting and re-creating the monitor.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    #: How often the consumer promises to check in.
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Slack on top of the cadence before silence counts as an outage. A
    #: ten-minute probe with 1200s of grace may lose two ticks to a slow run
    #: or a reboot without paging anyone.
    grace_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: None alerts once per outage. A value re-alerts every N seconds while
    #: the monitor stays missing — for the case where the first alert is the
    #: one nobody saw.
    renotify_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    channel_ids: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    template_id: Mapped[str | None] = mapped_column(
        ULIDType, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    title_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: "pending" until the first check-in ever arrives, then "ok" or "missing".
    state: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", server_default="pending"
    )
    last_checkin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The ``status`` the consumer reported on its last check-in.
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The last report, stored verbatim. Notifier never reads inside it —
    #: whatever taxonomy the consumer uses is the consumer's business.
    last_variables: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    last_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
