"""Run one dead-man's-timer pass: alert on every monitor that has gone quiet.

Entry point for ``deploy/notifier-sweep.service``, which a systemd timer
starts every minute. Launched through ``scripts/sweep.sh``, never directly —
that script is where the database and the encryption key are checked.

Deliberately *not* a task inside the API process. An alerter that rides the
thing it watches stops reporting exactly when it is needed, which is the
argument #56 makes against the broker's in-process alternatives. This process
needs Postgres and outbound network and no part of the API to be up.

Usage (the unit's spelling, for reference — prefer ``scripts/sweep.sh``):
    . scripts/load_env.sh
    NOTIFIER_ALLOW_PROD_DB=1 uv run python scripts/sweep_monitors.py
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session_factory
from src.core.logging import configure_logging, get_logger
from src.core.monitors import SweepReport, sweep_monitors

logger = get_logger(__name__)


async def run_sweep(session: AsyncSession) -> SweepReport:
    """Sweep, commit, and log the outcome.

    The log line is emitted on every pass, including the quiet ones. An
    operator needs to be able to tell "nothing is overdue" from "the timer has
    not fired in a week", and only a line that appears either way does that.
    """
    report = await sweep_monitors(session)
    await session.commit()
    logger.info(
        "monitor sweep complete",
        extra={
            "checked": report.checked,
            "alerted": report.alerted,
            "undeliverable": report.undeliverable,
        },
    )
    return report


async def main() -> None:
    """Open a session, run one pass, close it."""
    factory = get_session_factory()
    async with factory() as session:
        await run_sweep(session)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
