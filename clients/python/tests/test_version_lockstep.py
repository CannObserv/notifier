"""The SDK version is mirrored in three places; they must agree.

`pyproject.toml`, `notifier_client.__version__`, and the top entry of
CHANGELOG.md drift silently otherwise — nothing else reads all three.
"""

import re
import tomllib
from pathlib import Path

import notifier_client

SDK_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    with (SDK_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _changelog_version() -> str:
    for line in (SDK_ROOT / "CHANGELOG.md").read_text().splitlines():
        match = re.match(r"^## (\d+\.\d+\.\d+)", line)
        if match:
            return match.group(1)
    raise AssertionError("no released version heading found in CHANGELOG.md")


def test_dunder_version_matches_pyproject():
    assert notifier_client.__version__ == _pyproject_version()


def test_changelog_documents_the_current_version():
    assert _changelog_version() == _pyproject_version()
