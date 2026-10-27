"""PID 1's own lines stay in the journal after a ``daemon-reload`` (#145).

exe.dev's image ships ``/etc/systemd/system.conf.d/container-overrides.conf``
with ``LogTarget=console``. Boot runs on exe-init's ``--log-target=syslog``,
but the first reload applies the drop-in, and from then until the next boot
PID 1 writes only to ``hvc0``: ``Started``, ``Failed with result``,
``Scheduled restart job`` and ``start-limit-hit`` all vanish from
``journalctl -u``, which is what Routine ops reads after a deploy.

The fix is co-image-base's own file (CannObserv/provisioner#62), installed
host-locally until this host migrates (CannObserv/provisioner#16), as
CannObserv/usa-wa#521 did. It is pinned **byte-identical** to provisioner at
``14597bc2``, comment included, so the image's copy at the same path later
supersedes it and nothing changes.

Tracked in ``deploy/``, installed as:

- ``system.conf.d/zz-cannobserv-log-target.conf`` -> ``/etc/systemd/system.conf.d/``

Pure assertions on the tracked copy run everywhere; installed-parity and live
assertions skip where the node is not this one, CI included.
"""

import hashlib
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
NAME = "zz-cannobserv-log-target.conf"
DROPIN = REPO_ROOT / "deploy" / "system.conf.d" / NAME
INSTALLED = Path("/etc/systemd/system.conf.d") / NAME
#: The image's drop-in this one must sort after: systemd reads drop-ins in
#: filename order across every ``system.conf.d``, and the last one wins.
IMAGE_DROPIN = "container-overrides.conf"
TARGET = "journal-or-kmsg"

#: sha256 of ``image/rootfs/etc/systemd/system.conf.d/zz-cannobserv-log-target.conf``
#: in CannObserv/provisioner at ``14597bc2``. A local edit, even to the
#: comment, makes this a different file from the one the image ships.
PROVISIONER_SHA256 = "0f16a1e6986d15ebb8d40999e05980ce0ce386d0cb8c1b8efa55881b478cb54d"

HOST = "notifier"
live_host_only = pytest.mark.skipif(
    socket.gethostname() != HOST, reason=f"reads {HOST}'s live systemd state"
)


def _directives(text: str) -> list[str]:
    """The lines systemd acts on, with comments and blanks dropped."""
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith(("#", ";"))
    ]


def _installed() -> str:
    try:
        return INSTALLED.read_text()
    except FileNotFoundError:
        pytest.skip(f"{INSTALLED} not installed on this host")


def test_tracked_copy_is_provisioners_byte_for_byte() -> None:
    assert hashlib.sha256(DROPIN.read_bytes()).hexdigest() == PROVISIONER_SHA256


def test_dropin_sets_only_the_log_target() -> None:
    """One key, so the image's other ``[Manager]`` settings stay its own."""
    assert _directives(DROPIN.read_text()) == ["[Manager]", f"LogTarget={TARGET}"]


def test_dropin_sorts_after_the_images() -> None:
    assert sorted([IMAGE_DROPIN, NAME])[-1] == NAME


def test_installed_copy_matches_tracked() -> None:
    assert _installed() == DROPIN.read_text()


@live_host_only
def test_live_config_chain_ends_on_journal() -> None:
    """``cat-config`` prints the chain in systemd's own order, so a later
    drop-in from any ``system.conf.d`` would show here and nowhere else."""
    _installed()
    chain = subprocess.run(
        ["systemd-analyze", "cat-config", "systemd/system.conf"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    targets = [ln for ln in _directives(chain) if ln.startswith("LogTarget=")]
    assert targets[-1] == f"LogTarget={TARGET}"


@live_host_only
def test_live_log_target_is_journal() -> None:
    """The running target, which the chain alone cannot show: a runtime
    ``systemctl log-target`` holds across every reload until boot. This reads
    the same while such an override names ``journal-or-kmsg``, so it proves
    the drop-in took only once the override is cleared (#145)."""
    _installed()
    live = subprocess.run(
        ["systemd-analyze", "get-log-target"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert live == TARGET
