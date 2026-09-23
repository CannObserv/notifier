"""Give a tenant copies of another tenant's channels without handling the URL.

Onboarding a consumer onto the cohort's existing Slack and Mailgun
destinations used to mean pasting a live Apprise URL into ``POST /channels``.
This script copies the stored ciphertext instead, so the URL is never
decrypted, printed or pasted. Why that is sound, and what the refusals are:
``src/core/channels.py``.

Usage (production — deliberate, opt-in)::

    . scripts/load_env.sh

    # Rehearse first: every refusal fires, nothing is written
    NOTIFIER_ALLOW_PROD_DB=1 uv run python scripts/copy_channels.py \\
        --to-tenant <target id> --expect-name <target name> \\
        --channel <source channel id>=<new name> [--channel ...] --dry-run

    # Then the same command line without --dry-run

For the dev database, swap the opt-in for ``DATABASE_URL="$DEV_DATABASE_URL"``.
Copying a production channel into ``notifier_dev`` is a different operation
and a dangerous one: see docs/COMMANDS.md, "Dev channels are sink channels by
construction". It is not reachable here, because the source and target share
one database.

``--expect-name`` is required. The target id is the whole of who receives the
grant, and a typo that happens to name another consumer would hand that
consumer the destination instead. It's the same guard as ``delete_tenant.py``'s,
but it has no prompt to stand in for, so it is never optional.

Every copy is recorded on the credential audit channel
(``journalctl -t notifier-keys``), naming both ends and never the URL.
"""

import argparse
import asyncio
import sys

from src.core.channels import ChannelCopy, copy_channels
from src.core.database import get_session_factory
from src.core.logging import AUDIT_IDENT, configure_script_logging
from src.core.models import Tenant

#: Exit codes, spelled as in ``delete_tenant.py`` and ``rotate_key.py``.
OK = 0
REFUSED = 2


def _channel_spec(value: str) -> tuple[str, str]:
    """Parse ``SOURCE_CHANNEL_ID=NEW_NAME``."""
    source, sep, name = value.partition("=")
    if not sep or not source.strip() or not name.strip():
        raise argparse.ArgumentTypeError(f"expected SOURCE_CHANNEL_ID=NEW_NAME, got {value!r}")
    return source.strip(), name.strip()


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser. Split out so tests can read its help."""
    parser = argparse.ArgumentParser(
        prog="copy_channels.py",
        description=(
            "Copy channels into a tenant by copying their encrypted Apprise URL, "
            "never decrypting it. Every copy is recorded on the audit channel."
        ),
    )
    parser.add_argument("--to-tenant", required=True, help="the tenant receiving the copies (id)")
    parser.add_argument(
        "--expect-name",
        required=True,
        help="the name you believe --to-tenant belongs to; the run refuses if it does not match",
    )
    parser.add_argument(
        "--channel",
        action="append",
        required=True,
        type=_channel_spec,
        metavar="SOURCE_CHANNEL_ID=NEW_NAME",
        help="a channel to copy and the name its copy takes. Repeat for several",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="rehearse the whole operation, refusals included, and roll back",
    )
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse *argv*."""
    return build_parser().parse_args(argv)


def render(copies: list[ChannelCopy], dry_run: bool) -> list[str]:
    """Return the lines to print. Never the URL, which this script never holds."""
    lines = ["DRY RUN — nothing was written"] if dry_run else []
    for copy in copies:
        lines.append(f"channel_id={copy.channel_id}")
        lines.append(f"  name={copy.name}")
        lines.append(f"  channel_hint={copy.channel_hint}")
        lines.append(f"  tenant_id={copy.tenant_id}")
        lines.append(f"  source_channel_id={copy.source_channel_id}")
        lines.append(f"  source_tenant_id={copy.source_tenant_id}")
    return lines


async def main(args: argparse.Namespace) -> int:
    """Run the copy and print the result. Returns an exit code."""
    try:
        factory = get_session_factory()
    except RuntimeError as exc:  # ProductionDatabaseError is one of these
        print(f"refused: {exc}", file=sys.stderr)
        return REFUSED

    try:
        async with factory() as session:
            tenant = await session.get(Tenant, args.to_tenant)
            if tenant is not None and tenant.name != args.expect_name:
                raise LookupError(
                    f"tenant {args.to_tenant} is named {tenant.name!r}, "
                    f"not {args.expect_name!r} — check the id before granting anything"
                )
            copies = await copy_channels(
                session, args.to_tenant, args.channel, dry_run=args.dry_run
            )
    except (LookupError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        print("Nothing was written.", file=sys.stderr)
        return REFUSED

    for line in render(copies, args.dry_run):
        print(line)
    if args.dry_run:
        print("Re-run without --dry-run to perform it.")
    else:
        print(f"Recorded on the credential audit channel: journalctl -t {AUDIT_IDENT}")
    return OK


if __name__ == "__main__":
    _args = parse_args(sys.argv[1:])
    configure_script_logging()
    raise SystemExit(asyncio.run(main(_args)))
