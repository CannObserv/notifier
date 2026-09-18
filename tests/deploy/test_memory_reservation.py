"""Drift tests for the production memory reservation (#74).

This host is 3.8 GiB with no swap, and it runs the live service, the dev
endpoint, PostgreSQL and interactive agent sessions on the one kernel. The
failure that motivates this is not an OOM kill — it is the *absence* of one.
Past the ceiling the kernel fails atomic allocations in whatever asks next
(`tailscaled`, `ksoftirqd`) and the production service is what goes down,
which is how CannObserv/broker lost its bus for 57m 48s on 2026-09-16
(gregoryfoster/skills#295, `references/troubleshooting.md` row U).

Three settings, none of which substitutes for another:

* ``MemoryLow=`` — a soft floor the kernel will not reclaim below under
  pressure. It protects the *working set*, which is what a stall eats.
* ``OOMScoreAdjust=`` — makes the killer prefer almost anything else. On this
  host agent sessions sit at adj 0 (only `sshd` and `exe-init` carry -1000),
  so a negative score here is what puts production last in line.
* ``vm.min_free_kbytes`` — the reserve the *atomic* allocations draw on. The
  other two are per-cgroup and cannot help an allocation in `ksoftirqd`.

The dev units deliberately carry none of it: a reservation everything holds is
a reservation nobody holds, and dev losing memory to production is the
outcome this is choosing.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"

PROD_UNIT = DEPLOY / "notifier.service"
PROD_SWEEP = DEPLOY / "notifier-sweep.service"
DEV_UNIT = DEPLOY / "notifier-dev.service"
DEV_SWEEP = DEPLOY / "notifier-sweep-dev.service"

SYSCTL = DEPLOY / "99-notifier-memory.conf"
EARLYOOM = DEPLOY / "earlyoom.default"

#: Live peaks measured on this host, 2026-09-18: notifier.service 90 MiB,
#: notifier-dev.service 69 MiB, PostgreSQL 121 MiB. The floor must clear the
#: service's own peak with room, or it reserves less than the service uses.
MEASURED_PROD_PEAK_MIB = 90


def directives(unit: Path) -> str:
    """The lines systemd acts on, with comments and blanks dropped.

    Same helper the other three unit drift tests use: the absence checks are
    about what a unit *does*, and these units explain their reasoning at
    length in comments that would otherwise fail the tests they document.
    """
    return "\n".join(
        line
        for line in unit.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def setting(unit: Path, key: str) -> str | None:
    """The value of a ``Key=value`` directive, or None when unset."""
    for line in directives(unit).splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return None


def _mib(value: str) -> int:
    """Parse a systemd memory value into whole MiB."""
    match = re.fullmatch(r"(\d+)([KMG]?)", value)
    assert match, f"unparseable memory value {value!r}"
    amount, suffix = int(match.group(1)), match.group(2)
    return {"": amount // (1024 * 1024), "K": amount // 1024, "M": amount, "G": amount * 1024}[
        suffix
    ]


# ── the production units take the reservation ────────────────────────────────


def test_production_unit_reserves_a_memory_floor():
    """MemoryLow=, not MemoryMax=.

    A cap is the wrong tool twice over: it bounds the service that is the
    victim here rather than the launch that is the cause, and on a process the
    killer will not pick a cap stalls rather than kills.
    """
    value = setting(PROD_UNIT, "MemoryLow")
    assert value is not None, "notifier.service declares no MemoryLow= floor"
    assert _mib(value) > MEASURED_PROD_PEAK_MIB, (
        f"MemoryLow={value} is at or under the {MEASURED_PROD_PEAK_MIB} MiB this "
        f"service actually peaked at, so it reserves less than the working set"
    )


def test_production_unit_is_not_capped():
    """MemoryMax= here would bound the victim, not the cause.

    The cap belongs on the SocratiCode pre-install, which is a deliberate
    one-off run, never on the always-on service it was starving.
    """
    assert setting(PROD_UNIT, "MemoryMax") is None, (
        "notifier.service must not cap itself; cap the install that starves it"
    )


@pytest.mark.parametrize("unit", [PROD_UNIT, PROD_SWEEP], ids=["api", "sweep"])
def test_production_units_are_deprioritised_for_the_killer(unit):
    """Negative, but never -1000.

    -1000 makes a unit unkillable, so a leak in it wedges the host with no
    kill and no report — trading this failure mode for a worse one. The sweep
    is included because it is the only thing watching for consumer silence:
    losing it is a silent outage of the outage detector.
    """
    value = setting(unit, "OOMScoreAdjust")
    assert value is not None, f"{unit.name} declares no OOMScoreAdjust="
    score = int(value)
    assert -1000 < score < 0, (
        f"{unit.name} sets OOMScoreAdjust={score}; it must be negative to sit "
        f"below the agent sessions at adj 0, and above -1000 to stay killable"
    )


# ── the dev units deliberately take none of it ───────────────────────────────


@pytest.mark.parametrize("unit", [DEV_UNIT, DEV_SWEEP], ids=["api", "sweep"])
@pytest.mark.parametrize("key", ["MemoryLow", "OOMScoreAdjust"])
def test_dev_units_never_take_the_reservation(unit, key):
    """The mirror of the two tests above, and the same rule as the prod opt-in.

    Under pressure something has to lose. This picks dev on purpose; a
    reservation on every unit would reserve nothing.
    """
    assert setting(unit, key) is None, (
        f"{unit.name} sets {key}=; the reservation belongs to the production "
        f"units alone, or it stops being a reservation"
    )


# ── the half a cgroup cannot do ──────────────────────────────────────────────


def test_sysctl_drop_in_raises_the_atomic_allocation_reserve():
    """`vm.min_free_kbytes`, the one setting that is not per-cgroup.

    Both settings above are cgroup properties and can do nothing for an
    atomic allocation in `ksoftirqd` — which is precisely what failed on
    broker. The kernel default scales off RAM and lands near 8 MiB here,
    far too thin for a no-swap host to absorb a 1.2 G spike.
    """
    assert SYSCTL.is_file(), f"{SYSCTL.name} is missing from deploy/"
    body = SYSCTL.read_text()
    match = re.search(r"^vm\.min_free_kbytes\s*=\s*(\d+)", body, re.MULTILINE)
    assert match, "the drop-in does not set vm.min_free_kbytes"
    assert int(match.group(1)) >= 65536, (
        "a reserve under 64 MiB leaves this no-swap host where it started"
    )


# ── the killer that acts before the kernel's does ────────────────────────────


def _earlyoom_args() -> str:
    match = re.search(r'^EARLYOOM_ARGS="([^"]*)"', EARLYOOM.read_text(), re.MULTILINE)
    assert match, "no EARLYOOM_ARGS= assignment in the drop-in"
    return match.group(1)


def test_earlyoom_config_exists():
    """The kernel's own killer is the last resort, and on this host it is late.

    With no swap there is no slow path into pressure, so by the time the
    kernel acts the allocation failures row U describes have already landed.
    earlyoom watches available memory and acts while the host is still
    responsive.
    """
    assert EARLYOOM.is_file(), f"{EARLYOOM.name} is missing from deploy/"


def test_earlyoom_prefers_the_session_processes_that_cause_this():
    """Agent sessions and the servers they launch, which is the measured cause.

    Losing an agent session costs a session; losing the production service
    costs the bus. This picks the session on purpose.
    """
    assert "--prefer" in _earlyoom_args()


def test_earlyoom_avoids_the_production_processes():
    """Belt and braces over OOMScoreAdjust=, which earlyoom already honours."""
    args = _earlyoom_args()
    assert "--avoid" in args
    for name in ("uv", "postgres", "tailscaled"):
        assert re.search(rf"\b{name}\b", args.split("--avoid", 1)[1]), (
            f"earlyoom is not told to avoid {name}"
        )


def test_earlyoom_regexes_contain_no_spaces():
    """systemd word-splits an unquoted $EARLYOOM_ARGS.

    `ExecStart=/usr/bin/earlyoom $EARLYOOM_ARGS` splits on whitespace with no
    shell quoting, so a space inside a regex silently becomes two arguments
    and earlyoom exits on the stray one — leaving the host with no early
    killer and an active-looking unit. The socraticode server's `comm` is
    literally `npm exec socrat`, so this is a live trap, not a hypothetical:
    match it with a start-anchored `^npm` instead.
    """
    args = _earlyoom_args()
    regexes = re.findall(r"--(?:prefer|avoid)\s+('[^']*'|\"[^\"]*\"|\S+)", args)
    assert len(regexes) == 2, (
        f"expected one regex each for --prefer and --avoid, found {regexes!r}; "
        f"a regex split across arguments is exactly the bug this test is for"
    )
    for regex in regexes:
        assert " " not in regex.strip("'\""), (
            f"regex {regex!r} contains a space and would be split into two arguments"
        )


def test_earlyoom_args_survive_systemd_word_splitting():
    """End-to-end on the value itself: split it the way systemd will.

    The test above reads the regexes; this one asserts the whole argument
    vector comes out the length it should, so a stray quote or space anywhere
    in the line is caught rather than just inside the two regexes.
    """
    argv = _earlyoom_args().split()
    assert argv.count("--avoid") == 1 and argv.count("--prefer") == 1
    for flag in ("--avoid", "--prefer"):
        value = argv[argv.index(flag) + 1]
        assert not value.startswith("-"), (
            f"{flag} is followed by {value!r}, not a regex — the regex was split"
        )
        re.compile(value)  # earlyoom would reject an unparseable one at startup
