"""Drift tests for the SocratiCode server pin: the driver's and the session's (#74, #87).

Two things launch a SocratiCode server on this host. The driver — the daily
health hook, `index`, `verify` — prefers the pre-install under
``~/.socraticode/pin`` (#74). The session's server is the plugin's, which
launches ``npx -y --prefer-online ${SOCRATICODE_SPEC:-socraticode@latest}``
since upstream giancarloerra/socraticode@0c33776 (#87). The settings ``env``
block declares that spec but never reaches the launch: Claude Code expands the
plugin's args before it merges the block (gregoryfoster/skills#332). VS Code's
machine-scoped ``claudeCode.environmentVariables`` delivers it, being in
``claude``'s environment from the start.

A spec that floats installs at session start on any day the package moves:
the ~1.2 G peak a 3.8 GiB no-swap host running production cannot afford
(gregoryfoster/skills#295). One that differs from the pre-install puts two
builds on one shared store. Re-pinning means changing all four — the
pre-install, the block, the machine setting and docs/SOCRATICODE.md — and these
fail until all four agree. The pre-install and the machine setting are
VM-local, so CI, which has neither, holds only the block and the doc; the rest
is compared here.
"""

import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
SOCRATICODE_DOC = REPO_ROOT / "docs" / "SOCRATICODE.md"

#: The plugin's live launch expands this; unset, it resolves to @latest.
SPEC_VARIABLE = "SOCRATICODE_SPEC"

#: A literal release. `latest`, a range or a bare name all float.
EXACT_SPEC = re.compile(r"socraticode@(\d+\.\d+\.\d+)")

#: VS Code's machine-scoped settings on this remote host. The extension sets
#: `claudeCode.environmentVariables` in `claude`'s environment at startup, which
#: is when the plugin's args are expanded.
VSCODE_SERVER = Path.home() / ".vscode-server"
VSCODE_MACHINE_SETTINGS = VSCODE_SERVER / "data" / "Machine" / "settings.json"
VSCODE_ENV_SETTING = "claudeCode.environmentVariables"


def pinned_install_version() -> str | None:
    """The pre-install's version, found where mcp-driver.mjs looks; None if absent.

    VM-local, like the driver's own lookup: SOCRATICODE_PIN_DIR, else
    ~/.socraticode/pin — an empty value falls back too, as the driver's `||` does.
    """
    pin_dir = Path(os.environ.get("SOCRATICODE_PIN_DIR") or "~/.socraticode/pin").expanduser()
    manifest = pin_dir / "node_modules" / "socraticode" / "package.json"
    if not manifest.exists():
        return None
    return json.loads(manifest.read_text())["version"]


def vscode_launch_spec() -> str | None:
    """SOCRATICODE_SPEC as the extension hands it to `claude` at startup; None if unset."""
    if not VSCODE_MACHINE_SETTINGS.exists():
        return None
    variables = json.loads(VSCODE_MACHINE_SETTINGS.read_text()).get(VSCODE_ENV_SETTING, [])
    return next((v["value"] for v in variables if v.get("name") == SPEC_VARIABLE), None)


@pytest.fixture(scope="module")
def session_spec() -> str | None:
    return json.loads(SETTINGS.read_text()).get("env", {}).get(SPEC_VARIABLE)


def test_session_spec_is_an_exact_version(session_spec):
    """`--prefer-online` revalidates every launch, so anything but a literal installs on a move."""
    assert session_spec is not None, (
        f"{SETTINGS.name} does not set {SPEC_VARIABLE}: the session's server floats on @latest"
    )
    assert EXACT_SPEC.fullmatch(session_spec), (
        f"{SPEC_VARIABLE}={session_spec!r} is not socraticode@<major>.<minor>.<patch>"
    )


def test_session_spec_matches_the_driver_pin(session_spec):
    """One build per host: the session and the driver write the same shared store."""
    pinned = pinned_install_version()
    if pinned is None:
        pytest.skip("no SocratiCode pre-install on this machine")
    assert session_spec == f"socraticode@{pinned}", (
        f"{SPEC_VARIABLE}={session_spec!r} but the driver's pre-install is {pinned}"
    )


def test_socraticode_doc_names_only_the_session_spec(session_spec):
    """The doc says what the session launches; a re-pin that skips it leaves it lying.

    Every literal spec in it, not one: a re-pin that updates the first mention
    and misses a later one would otherwise pass.
    """
    doc = SOCRATICODE_DOC.read_text()
    assert SPEC_VARIABLE in doc, f"{SOCRATICODE_DOC.name} does not name {SPEC_VARIABLE}"
    named = {match.group(0) for match in EXACT_SPEC.finditer(doc)}
    assert named == {session_spec}, (
        f"{SOCRATICODE_DOC.name} names {sorted(named)}; the session launches {session_spec}"
    )


def test_vscode_launches_claude_with_the_session_spec(session_spec):
    """The block declares the pin; this is what delivers it (#87, gregoryfoster/skills#332).

    Measured 2026-09-24 on 2.1.280, after a full reconnect: with the block
    alone, the session's server carried the variable in its environment and was
    still launched @latest. VM-local: skips only where no VS Code server is
    installed, as in CI — on this VM a missing setting is the defect.
    """
    if not VSCODE_SERVER.exists():
        pytest.skip("no VS Code server on this machine")
    delivered = vscode_launch_spec()
    assert delivered == session_spec, (
        f"{VSCODE_MACHINE_SETTINGS} gives claude {SPEC_VARIABLE}={delivered!r} at startup; "
        f"{SETTINGS.name} declares {session_spec!r}"
    )
