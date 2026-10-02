"""exe.dev's setup unit stays off, and its script stays root-only (#93, #99).

exe.dev ships ``exe-setup.service`` to run a VM's creation-time
``--setup-script`` from ``/exe.dev/setup``. This VM was created with one. It
holds an inline Tailscale auth key (expired, per the operator) and still
provisions things: the Tailscale installer, ``apt-get install`` PostgreSQL 16,
``systemctl enable --now postgresql``. Line 3 fails as ``exedev``, so the
unit's ``ExecStartPost=`` ``rm`` never runs. It failed at every boot before
the fix (all four journald kept), and the file stayed ``root:root`` 0755.

#93 shredded the file. The platform delivered it again at the next boot: its
mtime matched boot 0's start, 2026-09-29T12:27:10Z. Shredding doesn't last. The
fix that holds comes from CannObserv/provisioner#4:

* the unit is **disabled**, so a re-delivered file no longer means a run. Its
  preset is ``enabled``, so ``systemctl preset`` or ``preset-all`` turns it back
  on;
* the file is **left in place at 0600**. The platform leaves a present copy
  alone, mode included, at an in-guest reboot and at ``ssh exe.dev restart``.
  A missing one it delivers again at 0755 (measured in provisioner#4), and
  with the unit disabled nothing removes that copy.

All four tests read live systemd and file state, so they skip anywhere but
this host, CI included. They never read the file's contents: it holds a key.
"""

import socket
import stat
import subprocess
from pathlib import Path

import pytest

HOST = "notifier"
pytestmark = pytest.mark.skipif(
    socket.gethostname() != HOST, reason=f"reads {HOST}'s live systemd state"
)

UNIT = "exe-setup.service"
SCRIPT = Path("/exe.dev/setup")


def unit_properties(*names: str) -> dict[str, str]:
    """Return ``systemctl show`` values for ``UNIT``, skipping where it is absent."""
    out = subprocess.run(
        ["systemctl", "show", UNIT, *(f"--property={n}" for n in names)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    props = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if props.get("LoadState") == "not-found":
        pytest.skip(f"{UNIT} is not installed on this host")
    return props


def test_setup_unit_is_disabled() -> None:
    props = unit_properties("LoadState", "UnitFileState")
    assert props["UnitFileState"] == "disabled", (
        f"{UNIT} is {props['UnitFileState']!r}: {SCRIPT} stays on disk, so the "
        f"unit runs it again at every boot. Its preset is "
        f"`enabled`, so a `systemctl preset` or `preset-all` is the likely cause. "
        f"`sudo systemctl disable {UNIT}` (#99)"
    )


def test_setup_unit_is_not_failed() -> None:
    """The health baseline expects ``systemctl --failed`` to be empty again (#91)."""
    props = unit_properties("LoadState", "ActiveState", "Result")
    assert props["ActiveState"] != "failed", (
        f"{UNIT} failed ({props['Result']}): it ran this boot. Check "
        f"`sudo journalctl -b -u {UNIT}`, then `sudo systemctl reset-failed {UNIT}`"
    )


def test_setup_unit_was_not_started_this_boot() -> None:
    """A disabled unit never reaches its condition check, so systemd never stamps it.

    ``ConditionTimestamp`` is set by any start attempt, condition met or not,
    and resets at boot. That makes it stronger than ``ConditionResult=no``, which
    an unstarted unit also reads (provisioner#1), and it catches a run that
    succeeded, which the failed-state test above cannot. It is #99's
    "0 ``Starting`` this boot" without the privileges the journal needs.
    """
    props = unit_properties("LoadState", "ConditionTimestampMonotonic")
    assert props["ConditionTimestampMonotonic"] == "0", (
        f"systemd tried to start {UNIT} this boot. Check "
        f"`sudo journalctl -b -u {UNIT}` and `systemctl is-enabled {UNIT}` (#99)"
    )


def test_setup_script_is_root_only() -> None:
    unit_properties("LoadState")
    try:
        st = SCRIPT.stat()
    except FileNotFoundError:
        pytest.skip(
            f"{SCRIPT} is absent: the next boot delivers it again at 0755 and "
            f"this test fails then. Don't shred it; leave it at 0600 (#99)"
        )
    mode = stat.S_IMODE(st.st_mode)
    assert (st.st_uid, st.st_gid) == (0, 0), f"{SCRIPT} is not root:root"
    assert mode & 0o077 == 0, (
        f"{SCRIPT} is {mode:04o}: any local user can read the Tailscale key in it. "
        f"`sudo chmod 600 {SCRIPT}`, and never print it (#99)"
    )
