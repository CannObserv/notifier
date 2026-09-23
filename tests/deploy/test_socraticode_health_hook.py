"""Drift test for the SocratiCode health hook's SessionStart budget (#75).

`.claude/hooks/socraticode-health.sh` stamps its once-per-UTC-day lock before
it runs the check, so a harness kill consumes the day's only attempt and
reports nothing — the silent-when-clean hook becomes silent-when-killed.
Upstream's manifest sets 120s: the 60s driver ceiling the hook exports
(`HEALTH_TIMEOUT_MS`) plus process start, which is a package download when the
pinned pre-install (#74) is absent and the driver falls back to `npx -y`.

This repo carried 90s. The installer cannot repair it — gregoryfoster/skills#259
made preserve beat prescribe, so a timeout already on the entry wins over
`--timeout` — which is why the value is pinned here.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

#: The vendored skills repo. Uninitialized in CI, which checks out without
#: submodules.
SUBMODULE = REPO_ROOT / "skills-vendor" / "gregoryfoster-skills"

#: The upstream manifest that prescribes the constant.
MANIFEST = SUBMODULE / "skills" / "init-socraticode" / "scripts" / "socraticode-health.install"

#: The hook script, matched on its basename inside the registered command —
#: the same `contains` the installer's own dedupe uses.
HEALTH_HOOK = "socraticode-health.sh"

#: `--timeout 120` in `socraticode-health.install`.
HEALTH_TIMEOUT = 120


@pytest.fixture(scope="module")
def health_entries() -> list[dict]:
    """Every SessionStart hook entry whose command runs the health script."""
    settings = json.loads(SETTINGS.read_text())
    return [
        hook
        for group in settings.get("hooks", {}).get("SessionStart", [])
        for hook in group.get("hooks", [])
        if HEALTH_HOOK in str(hook.get("command", ""))
    ]


@pytest.fixture(scope="module")
def health_entry(health_entries) -> dict:
    """The single registered entry, or a named failure rather than an unpack error."""
    assert len(health_entries) == 1, (
        f"expected exactly one SessionStart entry running {HEALTH_HOOK}, "
        f"found {len(health_entries)}"
    )
    return health_entries[0]


def test_health_hook_is_registered(health_entries):
    """The negative control: without it the timeout assertions pass vacuously."""
    assert len(health_entries) == 1, (
        f"expected exactly one SessionStart entry running {HEALTH_HOOK}, "
        f"found {len(health_entries)}"
    )


def test_health_hook_declares_a_timeout(health_entry):
    """Absent and wrong are different states; asserted apart so the failure says which."""
    assert "timeout" in health_entry, (
        f"{HEALTH_HOOK} runs under the harness default; "
        f"re-run its installer to register {HEALTH_TIMEOUT}"
    )


def test_health_hook_timeout_is_the_constant(health_entry):
    """120, written as a bare integer; `bool` excluded since it passes `isinstance(int)`."""
    timeout = health_entry["timeout"]
    assert isinstance(timeout, int) and not isinstance(timeout, bool), (
        f"timeout is {type(timeout).__name__}, not a bare integer"
    )
    assert timeout == HEALTH_TIMEOUT, (
        f"{HEALTH_HOOK} is registered with a {timeout}s budget; its manifest sets "
        f"{HEALTH_TIMEOUT}s — the 60s driver ceiling plus process start, and a "
        f"kill consumes the day's lock"
    )


def test_constant_matches_the_upstream_manifest():
    """The pinned constant tracks upstream, so a vendor bump that moves it fails here.

    Skipped where the submodule is not initialized (CI); the refresh that would
    move the constant happens on this VM, where it is. The skip keys on the
    submodule, not the manifest: an upstream rename must fail here, not skip.
    """
    if not (SUBMODULE / ".git").exists():
        pytest.skip("gregoryfoster-skills submodule not initialized")
    assert MANIFEST.is_file(), f"upstream moved or removed {MANIFEST.relative_to(REPO_ROOT)}"
    args = next(
        line
        for line in MANIFEST.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    match = re.search(r"--timeout\s+(\d+)", args)
    assert match, f"{MANIFEST.name} prescribes no --timeout: {args!r}"
    assert int(match.group(1)) == HEALTH_TIMEOUT, (
        f"upstream now prescribes --timeout {match.group(1)}; update HEALTH_TIMEOUT "
        f"and the entry in .claude/settings.json by hand (skills#259 preserves it)"
    )
