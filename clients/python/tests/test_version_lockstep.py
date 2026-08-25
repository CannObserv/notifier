"""The SDK version is mirrored in three places; they must agree.

`pyproject.toml`, `notifier_client.__version__`, and the CHANGELOG headings
drift silently otherwise — nothing else reads all three. The changelog checks
go past equality: a duplicated or out-of-order heading means a release was
half-edited, and equality alone reads that as green.
"""

import re
import tomllib
from pathlib import Path

import notifier_client

SDK_ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## (\d+\.\d+\.\d+)")


def _pyproject_version() -> str:
    with (SDK_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _changelog_versions() -> list[str]:
    text = (SDK_ROOT / "CHANGELOG.md").read_text()
    versions = [m.group(1) for line in text.splitlines() if (m := HEADING.match(line))]
    assert versions, "no released version heading found in CHANGELOG.md"
    return versions


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_dunder_version_matches_pyproject():
    assert notifier_client.__version__ == _pyproject_version()


def test_changelog_documents_the_current_version_at_the_top():
    assert _changelog_versions()[0] == _pyproject_version()


def test_changelog_headings_are_unique():
    versions = _changelog_versions()
    assert len(versions) == len(set(versions)), f"duplicate headings: {versions}"


def test_changelog_headings_are_newest_first():
    versions = _changelog_versions()
    keys = [_key(v) for v in versions]
    assert keys == sorted(keys, reverse=True), f"out of order: {versions}"
