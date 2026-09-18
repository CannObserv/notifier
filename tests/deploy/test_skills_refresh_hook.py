"""Drift test for the auto-refresh hook's SessionStart budget (#71).

`.claude/hooks/skills-submodule-update.sh` fetches every vendored skills repo
and, since gregoryfoster/skills#293, pushes the pointer bump it commits — one
network round trip per submodule plus a push, all inside a single SessionStart
entry. skills#259 set 120s as that hook's constant for exactly that reason: it
is the slowest hook a consumer installs, and a kill lands *between* the commit
and the push, leaving `main` ahead of `origin/main` on one machine and nowhere
else.

This repo carried 60s, and the installer cannot repair it. skills#259 made
preserve beat prescribe — a timeout already on the entry wins over `--timeout`,
so an operator's hand-chosen figure survives the tool that prescribed one (see
`install-hook.sh`, `resolve_timeout`). `install-refresh.sh` therefore reports
the disagreement and changes nothing, which is why the value is pinned here
rather than left to the next install run.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

#: The hook script, matched on its basename inside the registered command —
#: the same `contains` the installer's own dedupe uses, so a re-anchored or
#: `${CLAUDE_PROJECT_DIR}`-prefixed command still resolves.
REFRESH_HOOK = "skills-submodule-update.sh"

#: gregoryfoster/skills#259, duplicated in `install-refresh.sh` (--timeout 120)
#: and in `skills-submodule-update.install`.
REFRESH_TIMEOUT = 120


@pytest.fixture(scope="module")
def refresh_entries() -> list[dict]:
    """Every SessionStart hook entry whose command runs the refresh script."""
    settings = json.loads(SETTINGS.read_text())
    return [
        hook
        for group in settings.get("hooks", {}).get("SessionStart", [])
        for hook in group.get("hooks", [])
        if REFRESH_HOOK in str(hook.get("command", ""))
    ]


@pytest.fixture(scope="module")
def refresh_entry(refresh_entries) -> dict:
    """The single registered entry, or a named failure rather than an unpack error.

    `(entry,) = refresh_entries` raises ValueError in exactly the state this
    file exists to diagnose — a missing or duplicated registration — and the
    two tests below would then read as a broken test file rather than a broken
    settings file.
    """
    assert len(refresh_entries) == 1, (
        f"expected exactly one SessionStart entry running {REFRESH_HOOK}, "
        f"found {len(refresh_entries)}"
    )
    return refresh_entries[0]


def test_refresh_hook_is_registered(refresh_entries):
    """The negative control: without it the timeout assertions pass vacuously."""
    assert len(refresh_entries) == 1, (
        f"expected exactly one SessionStart entry running {REFRESH_HOOK}, "
        f"found {len(refresh_entries)}"
    )


def test_refresh_hook_declares_a_timeout(refresh_entry):
    """Absent is the eight-sibling defect; here it would also re-arm the installer.

    An entry with no timeout takes `--timeout` on the next install run, so a
    missing value is self-healing and a wrong one is not. Asserted separately
    from the value so the failure says which of the two states it is in.
    """
    assert "timeout" in refresh_entry, (
        f"{REFRESH_HOOK} runs under the harness default; "
        f"re-run install-refresh.sh to register {REFRESH_TIMEOUT}"
    )


def test_refresh_hook_timeout_is_the_constant(refresh_entry):
    """120, written as a bare integer the way every other entry in the file is.

    The type assertion is a spelling guard, not a claim about the harness:
    `"120"` and `120.0` are both things a hand edit or a jq recipe can leave
    behind, and neither is what the surrounding entries carry. `bool` is
    excluded because it satisfies `isinstance(x, int)`.

    If 60 were deliberate for this VM the fix is to say so on #71 and delete
    this test, not to loosen it: skills#259 exists to protect a chosen figure,
    and the point is that it be a decision rather than a leftover.
    """
    timeout = refresh_entry["timeout"]
    assert isinstance(timeout, int) and not isinstance(timeout, bool), (
        f"timeout is {type(timeout).__name__}, not a bare integer"
    )
    assert timeout == REFRESH_TIMEOUT, (
        f"{REFRESH_HOOK} is registered with a {timeout}s budget; skills#259 sets "
        f"{REFRESH_TIMEOUT}s because the run now fetches every vendored repo "
        f"and pushes the commit it writes"
    )
