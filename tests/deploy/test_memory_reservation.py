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
  pressure. It protects the *working set*, which is what a stall eats — the
  service's and its database's. Inert unless every slice above it grants it
  too (#85).
* ``OOMScoreAdjust=`` — makes the killer prefer almost anything else. On this
  host agent sessions sit at adj 0 (only `sshd` and `exe-init` carry -1000),
  so a negative score here is what puts production last in line.
* ``vm.min_free_kbytes`` — the reserve the *atomic* allocations draw on. The
  other two are per-cgroup and cannot help an allocation in `ksoftirqd`.

The dev units deliberately carry none of it: a reservation everything holds is
a reservation nobody holds, and dev losing memory to production is the
outcome this is choosing.

One premise here is the host's rather than the repo's — what the kernel
actually grants — so that test reads the live host and skips everywhere else,
CI included.
"""

import math
import re
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = REPO_ROOT / "deploy"

PROD_UNIT = DEPLOY / "notifier.service"
PROD_SWEEP = DEPLOY / "notifier-sweep.service"
DEV_UNIT = DEPLOY / "notifier-dev.service"
DEV_SWEEP = DEPLOY / "notifier-sweep-dev.service"

POSTGRES_UNIT = DEPLOY / "postgresql@16-main.service.d" / "10-memory.conf"
POSTGRES_SLICE = DEPLOY / "system-postgresql.slice.d" / "10-memory-protection.conf"
SYSTEM_SLICE = DEPLOY / "system.slice.d" / "10-memory-protection.conf"

#: co-index's units (#57), which run on that host's slices, not this one's.
OTHER_HOST_UNITS = DEPLOY / "index"

SYSCTL = DEPLOY / "99-notifier-memory.conf"
EARLYOOM = DEPLOY / "earlyoom.default"

#: Live peaks measured on this host, 2026-09-18: notifier.service 90 MiB,
#: notifier-dev.service 69 MiB, PostgreSQL 121 MiB. A floor must clear its
#: unit's own peak with room, or it reserves less than the unit uses.
MEASURED_PROD_PEAK_MIB = 90
MEASURED_POSTGRES_PEAK_MIB = 121

MIB = 1024 * 1024

#: The host this repo deploys to. The live tests read its kernel, so anywhere
#: else — CI, a laptop — they have nothing to read.
HOST = "notifier"
live_host_only = pytest.mark.skipif(
    socket.gethostname() != HOST, reason=f"reads {HOST}'s live kernel state"
)

CGROUP_FS = Path("/sys/fs/cgroup")


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


def section_of(unit: Path, key: str) -> str | None:
    """The ``[Section]`` a ``Key=`` directive sits in, or None when unset."""
    section = None
    for line in directives(unit).splitlines():
        if line.startswith("["):
            section = line.strip("[] ")
        elif line.startswith(f"{key}="):
            return section
    return None


def _mib(value: str) -> int:
    """Parse a systemd memory value into whole MiB."""
    match = re.fullmatch(r"(\d+)([KMG]?)", value)
    assert match, f"unparseable memory value {value!r}"
    amount, suffix = int(match.group(1)), match.group(2)
    return {"": amount // (1024 * 1024), "K": amount // 1024, "M": amount, "G": amount * 1024}[
        suffix
    ]


def unit_of(path: Path) -> str:
    """The unit a deploy file configures: its own name, or its drop-in directory's."""
    parent = path.parent.name
    return parent.removesuffix(".d") if parent.endswith(".d") else path.name


def claiming_files() -> list[Path]:
    """This host's deploy files that set ``MemoryLow=``."""
    return [
        path
        for path in sorted(DEPLOY.rglob("*"))
        if path.is_file()
        and OTHER_HOST_UNITS not in path.parents
        and setting(path, "MemoryLow") is not None
    ]


def declared_lows() -> dict[str, int]:
    """Every ``MemoryLow=`` this host's deploy files set, in MiB, by unit."""
    lows: dict[str, int] = {}
    for path in claiming_files():
        unit = unit_of(path)
        assert unit not in lows, f"{unit} sets MemoryLow= in two deploy files"
        lows[unit] = _mib(setting(path, "MemoryLow"))
    return lows


def parent_slice(unit: str) -> str | None:
    """The slice systemd puts a system unit in by default; None above system.slice.

    A plain unit lands in ``system.slice``. A template instance
    ``foo@bar.service`` lands in the implicit ``system-foo.slice``, which
    systemd creates with no settings — so it grants 0 like any other link.
    A slice ``a-b.slice`` sits in ``a.slice``. No unit here sets ``Slice=``;
    the live test checks this derivation against the real ``ControlGroup``.
    """
    name, _, kind = unit.rpartition(".")
    if kind == "slice":
        prefix = name.rpartition("-")[0]
        return f"{prefix}.slice" if prefix else None
    if "@" in name:
        return f"system-{name.split('@')[0]}.slice"
    return "system.slice"


def cgroup_of(unit: str) -> str:
    """The cgroup path ``parent_slice`` places ``unit`` at, as ``ControlGroup=`` spells it."""
    chain = [unit]
    while (parent := parent_slice(chain[-1])) is not None:
        chain.append(parent)
    return "/" + "/".join(reversed(chain))


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


def test_postgres_reserves_a_memory_floor():
    """The API is only as protected as its database (#85).

    The service's floor keeps its own working set resident; a request still
    stalls on a reclaimed page of the cluster behind it. Same rule as the
    service's floor, against the cluster's own measured peak.
    """
    assert POSTGRES_UNIT.is_file(), f"{POSTGRES_UNIT.relative_to(DEPLOY)} is missing"
    value = setting(POSTGRES_UNIT, "MemoryLow")
    assert value is not None, "the PostgreSQL drop-in declares no MemoryLow= floor"
    assert _mib(value) > MEASURED_POSTGRES_PEAK_MIB, (
        f"MemoryLow={value} is at or under the {MEASURED_POSTGRES_PEAK_MIB} MiB "
        f"PostgreSQL actually peaked at, so it reserves less than the working set"
    )
    assert setting(POSTGRES_UNIT, "MemoryMax") is None, "a cap bounds the victim"


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


# ── every slice above a floor grants it (#85) ────────────────────────────────


def test_every_slice_above_a_floor_grants_exactly_what_its_children_claim():
    """cgroup v2 caps a unit's protection at what every ancestor grants.

    ``system.slice`` ships ``memory.low`` 0, so notifier.service's
    ``MemoryLow=192M`` protected nothing from #74 to #85, while every check —
    this module's included — read the unit's own value and passed. A template
    instance adds a link: ``postgresql@16-main`` sits in an implicit
    ``system-postgresql.slice`` that grants 0 as well.

    Exactly the sum, not at least it. Less and each child keeps only a
    usage-proportional share. More is protection nothing here claims, and on a
    mount that gains ``memory_recursiveprot`` it would shield unclaimed daemons
    from the sessions.
    """
    lows = declared_lows()
    children: dict[str, set[str]] = {}
    for unit in lows:
        child = unit
        while (parent := parent_slice(child)) is not None:
            children.setdefault(parent, set()).add(child)
            child = parent
    assert "system.slice" in children, "no floor under deploy/ to grant — the test is vacuous"
    for slice_, members in sorted(children.items()):
        claimed = sum(lows.get(member, 0) for member in members)
        assert slice_ in lows, (
            f"{slice_} grants nothing, so {sorted(members)} keep no protection at "
            f"all: add deploy/{slice_}.d/10-memory-protection.conf"
        )
        assert lows[slice_] == claimed, (
            f"{slice_} grants MemoryLow={lows[slice_]}M but its children "
            f"{sorted(members)} claim {claimed}M; grant exactly the sum"
        )


def test_every_floor_sits_in_the_section_its_unit_type_reads():
    """``[Slice]`` in a slice drop-in, ``[Service]`` in a service's.

    systemd skips a section its unit type does not read, with one line in the
    journal: the drop-in loads, ``daemon-reload`` succeeds, and the floor is
    as inert as #85's was.
    """
    expected = {"service": "Service", "slice": "Slice"}
    for path in claiming_files():
        kind = unit_of(path).rpartition(".")[2]
        assert section_of(path, "MemoryLow") == expected[kind], (
            f"{path.relative_to(DEPLOY)} sets MemoryLow= outside [{expected[kind]}]"
        )


def _memory_low(cgroup: Path) -> float:
    """A cgroup's ``memory.low`` in bytes; ``max`` is unbounded."""
    value = (cgroup / "memory.low").read_text().strip()
    return math.inf if value == "max" else int(value)


def weakest_link(fs: Path, cgroup: str) -> tuple[str, float]:
    """The lowest ``memory.low`` from ``cgroup`` up, and the cgroup that sets it.

    The unit keeps at most this: the kernel scales a child's protection by its
    parent's effective protection (``effective_protection()`` in
    ``mm/page_counter.c``). The root has no ``memory.low`` and is no link.
    """
    links = []
    while cgroup not in ("", "/"):
        links.append((cgroup, _memory_low(fs / cgroup.lstrip("/"))))
        cgroup = cgroup.rpartition("/")[0]
    return min(links, key=lambda link: link[1])


def oversubscribed(fs: Path, cgroup: str) -> list[tuple[str, float, float]]:
    """``(slice, grant, claimed)`` for each slice above ``cgroup`` its children overdraw.

    Read from the kernel rather than ``deploy/``, since a unit installed from
    anywhere else can claim a share of the same grant.
    """
    found = []
    cgroup = cgroup.rpartition("/")[0]
    while cgroup not in ("", "/"):
        node = fs / cgroup.lstrip("/")
        claimed = sum(
            _memory_low(child) for child in node.iterdir() if (child / "memory.low").is_file()
        )
        if claimed > _memory_low(node):
            found.append((cgroup, _memory_low(node), claimed))
        cgroup = cgroup.rpartition("/")[0]
    return found


def _fake_cgroup(fs: Path, cgroup: str, low_mib: int) -> None:
    node = fs / cgroup.lstrip("/")
    node.mkdir(parents=True, exist_ok=True)
    (node / "memory.low").write_text(f"{low_mib * MIB}\n")


def test_a_slice_at_zero_clamps_the_unit_below_it(tmp_path):
    """#85 as found: the unit's own 192M, under a system.slice granting 0."""
    _fake_cgroup(tmp_path, "/system.slice", 0)
    _fake_cgroup(tmp_path, "/system.slice/notifier.service", 192)
    assert weakest_link(tmp_path, "/system.slice/notifier.service") == ("/system.slice", 0)


def test_a_granted_chain_keeps_the_templated_units_floor(tmp_path):
    """The fixed shape, three links deep for the template instance."""
    pg = "/system.slice/system-postgresql.slice/postgresql@16-main.service"
    _fake_cgroup(tmp_path, "/system.slice", 384)
    _fake_cgroup(tmp_path, "/system.slice/notifier.service", 192)
    _fake_cgroup(tmp_path, "/system.slice/system-postgresql.slice", 192)
    _fake_cgroup(tmp_path, pg, 192)
    assert weakest_link(tmp_path, pg)[1] == 192 * MIB
    assert oversubscribed(tmp_path, pg) == []


def test_children_claiming_past_the_grant_are_oversubscribed(tmp_path):
    """Both children pass the weakest-link walk; together they overdraw the slice."""
    _fake_cgroup(tmp_path, "/system.slice", 192)
    _fake_cgroup(tmp_path, "/system.slice/notifier.service", 192)
    _fake_cgroup(tmp_path, "/system.slice/system-postgresql.slice", 192)
    assert weakest_link(tmp_path, "/system.slice/notifier.service")[1] == 192 * MIB
    assert oversubscribed(tmp_path, "/system.slice/notifier.service") == [
        ("/system.slice", 192 * MIB, 384 * MIB)
    ]


@live_host_only
@pytest.mark.parametrize("unit", sorted(u for u in declared_lows() if u.endswith(".service")))
def test_the_live_floor_takes_effect(unit):
    """The effective protection, which is the only evidence (#85).

    ``systemctl show -p MemoryLow``, the unit's own ``memory.low``, a clean
    ``daemon-reload`` and a healthy service all agreed the floor worked while
    it protected nothing — here and on wslcb-licensing-tracker
    (gregoryfoster/skills#303). Walks the real ``ControlGroup``, which also
    checks ``parent_slice`` against the one systemd chose.
    """
    cgroup = subprocess.run(
        ["systemctl", "show", unit, "-p", "ControlGroup", "--value"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not cgroup:
        pytest.skip(f"{unit} is not running")
    assert cgroup == cgroup_of(unit), f"{unit} runs in {cgroup}, not {cgroup_of(unit)}"
    link, low = weakest_link(CGROUP_FS, cgroup)
    claimed = declared_lows()[unit]
    assert low >= claimed * MIB, (
        f"{unit} claims {claimed} MiB but keeps at most {low / MIB:.0f}: {link} grants "
        f"no more. Install deploy/'s slice drop-ins and daemon-reload (docs/DEPLOYMENT.md)"
    )
    assert oversubscribed(CGROUP_FS, cgroup) == [], (
        "a slice above this unit grants less than its children claim, so each keeps only a share"
    )


# ── the dev units deliberately take none of it ───────────────────────────────


@pytest.mark.parametrize("unit", [DEV_UNIT, DEV_SWEEP], ids=["api", "sweep"])
@pytest.mark.parametrize("key", ["MemoryLow", "OOMScoreAdjust"])
def test_dev_units_never_take_the_reservation(unit, key):
    """The mirror of the production floor and score, and the same rule as the prod opt-in.

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
