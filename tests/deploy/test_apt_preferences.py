"""Tailscale's apt origin is scoped to the packages it was added for (#113).

``pkgs.tailscale.com`` sits at apt's default priority, 500, which ties
Ubuntu's: any package it serves under an Ubuntu name, at a higher version,
would replace Ubuntu's in the maintenance lane. The ``patching-hosts`` skill
reports that as ``unscoped:Tailscale`` and each package it serves that no pin
names as ``unpinned:<package>`` (its ``references/policy.md``, Two lanes). The
fix is its shape: a ``Package: *`` pin for the site below 500, and a package
pin above 500 for each package the origin was added for. co-index took the
same file (CannObserv/index#9).

Tracked in ``deploy/``, installed as:

- ``apt-preferences.d/tailscale.pref`` -> ``/etc/apt/preferences.d/``

Pure assertions on the tracked copy run everywhere; installed-parity and live
assertions skip where the node is not this one, CI included.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PREFS = REPO_ROOT / "deploy" / "apt-preferences.d" / "tailscale.pref"
INSTALLED = Path("/etc/apt/preferences.d/tailscale.pref")
SITE = "pkgs.tailscale.com"
#: What the origin was added for: the daemon and the key that signs its repo.
PACKAGES = ("tailscale", "tailscale-archive-keyring")


def _stanzas(text: str) -> list[dict[str, str]]:
    """Parse apt preferences into one dict per blank-line-separated stanza."""
    stanzas: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        fields = {}
        for line in block.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        if fields:
            stanzas.append(fields)
    return stanzas


def _priority(package: str) -> int:
    """The tracked priority for ``package`` from the Tailscale site."""
    hits = [
        int(s["Pin-Priority"])
        for s in _stanzas(PREFS.read_text())
        if s.get("Package") == package and s.get("Pin") == f"origin {SITE}"
    ]
    assert len(hits) == 1, f"expected one pin for {package}, got {hits}"
    return hits[0]


def test_every_stanza_pins_the_tailscale_site() -> None:
    """Nothing else rides along in a file named for one origin."""
    stanzas = _stanzas(PREFS.read_text())
    assert stanzas
    for s in stanzas:
        assert set(s) == {"Package", "Pin", "Pin-Priority"}
        assert s["Pin"] == f"origin {SITE}"


def test_catch_all_is_below_ubuntu() -> None:
    assert _priority("*") < 500


@pytest.mark.parametrize("package", PACKAGES)
def test_each_package_it_was_added_for_is_above_ubuntu(package: str) -> None:
    assert _priority(package) > 500


def test_installed_copy_matches_tracked() -> None:
    try:
        installed = INSTALLED.read_text()
    except FileNotFoundError:
        pytest.skip(f"{INSTALLED} not installed on this host")
    assert installed == PREFS.read_text()


def test_live_policy_reads_the_pins() -> None:
    """apt itself, not the parser above, has the last word: the site's
    release lines read the catch-all, and each package's candidate carries
    its package pin."""
    if shutil.which("apt-cache") is None:
        pytest.skip("apt not available on this host")
    if not INSTALLED.exists():
        pytest.skip(f"{INSTALLED} not installed on this host")
    out = _policy()
    releases = re.findall(rf"^\s*(\d+) https://{re.escape(SITE)}/", out, re.M)
    assert releases
    assert set(releases) == {str(_priority("*"))}
    for package in PACKAGES:
        out = _policy(package)
        candidate = re.search(r"^\s*Candidate: (\S+)$", out, re.M)
        assert candidate, out
        line = rf"^\s*(\*\*\* )?{re.escape(candidate[1])} (\d+)$"
        hit = re.search(line, out, re.M)
        assert hit and int(hit[2]) == _priority(package)


def _policy(*packages: str) -> str:
    """``apt-cache policy`` for ``packages``, or for every source."""
    return subprocess.run(
        ["apt-cache", "policy", *packages],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
