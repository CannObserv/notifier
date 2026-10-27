"""Readers for the systemd units in deploy/, shared by both units' drift tests.

Not a test module. test_systemd_unit.py and test_dev_systemd_unit.py assert
the same arithmetic over each unit's start-limit bound (#143), and that
arithmetic needs the tailnet wait from scripts/tailnet_bind.sh as well as the
unit's own values.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TAILNET_BIND = REPO_ROOT / "scripts" / "tailnet_bind.sh"


def directives(unit: Path) -> str:
    """The lines systemd acts on, with comments and blanks dropped.

    The absence checks are about what a unit *does*, and both units explain at
    length what they omit and why ExecStart is not a uvicorn line. Matching raw
    text would make those comments fail the tests they document.
    """
    return "\n".join(
        line
        for line in unit.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def values(unit: Path, key: str) -> list[str]:
    """Every value ``key`` is set to, in file order.

    A list rather than the last value: systemd keeps the last assignment of a
    single-valued setting, so a stray second ``Restart=`` further down would
    silently win. Asserting the whole list catches it.
    """
    found = []
    for line in directives(unit).splitlines():
        name, _, value = line.partition("=")
        if name.strip() == key:
            found.append(value.strip())
    return found


def seconds(unit: Path, key: str) -> int:
    """Read a systemd time-valued setting as whole seconds.

    Accepts a bare integer or an explicit ``s`` suffix, both of which systemd
    takes. Anything else — ``1min``, ``2h`` — is rejected with a message
    naming the parser rather than raising ValueError from int(), so the
    failure points at this helper instead of looking like a broken test.
    """
    found = values(unit, key)
    assert found, f"{key} not set in {unit.name}"
    raw = found[-1].removesuffix("s")
    assert raw.isdigit(), (
        f"{key}={found[-1]} in {unit.name} is a systemd time span this "
        f"helper does not parse — express it in seconds, or teach seconds() the unit"
    )
    return int(raw)


def tailnet_wait_seconds() -> int:
    """The default wait tailnet_bind.sh spends before failing a start.

    Read from the script rather than restated, so a longer wait there fails the
    start-limit arithmetic here instead of quietly outgrowing it.
    """
    match = re.search(r"NOTIFIER_TAILNET_WAIT_SECONDS:-(\d+)", TAILNET_BIND.read_text())
    assert match, f"no NOTIFIER_TAILNET_WAIT_SECONDS default in {TAILNET_BIND.name}"
    return int(match.group(1))
