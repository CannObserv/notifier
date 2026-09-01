"""A released version must be reachable — the tag-presence gate (#50).

``sdk-staleness.yml`` proves the SDK matches the schema. Nothing proved a
consumer could *obtain* it, and the gap was not hypothetical: 0.3.0 and 0.3.1
were both released — version bumped, CHANGELOG rolled, committed to main — and
neither was ever tagged. ``git ls-remote --tags`` returned ``v0.2.0`` and
``v0.2.1`` and nothing else, so the install line every consumer is handed
(``@vX.Y.Z``) could not resolve either release, and watcher stayed pinned two
versions back because that was the newest pin that existed.

The rule: **the current version has a tag.** With exactly one exception — HEAD
is the commit that introduced it, which is the release commit itself, before
its tag is pushed. One commit of grace, so the runbook's
``git commit`` → ``git tag`` → ``git push --follow-tags`` sequence is not
racing its own gate, and nothing beyond it is. Under this rule 0.3.0 would have
failed at the very next merge to main rather than going unnoticed through an
entire further release.

This is a test rather than a workflow so that ``permissions: contents: read``
holds across every workflow in the repo. An auto-tagging job would need
``contents: write`` — one grant, in the one place that also holds the release
decision, to save a line of a runbook.

**It needs tags and history.** A shallow clone has neither, and would pass this
file vacuously: no tag found, no ``HEAD~1`` to compare against, and the gate
quietly stops being one. ``test_workflows.py`` asserts the CI job that runs it
checks out with ``fetch-depth: 0``; this file refuses to run at all against a
shallow checkout rather than reporting green from an empty tag list.
"""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ("git", *args), cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )


def current_version() -> str:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def version_at(rev: str) -> str | None:
    """The declared version at ``rev``, or None when the revision has no pyproject."""
    result = git("show", f"{rev}:pyproject.toml")
    if result.returncode != 0:
        return None
    m = VERSION_LINE.search(result.stdout)
    return m.group(1) if m else None


@pytest.fixture(scope="module", autouse=True)
def requires_full_history():
    """Refuse to report green from a checkout that cannot answer the question."""
    if git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    shallow = git("rev-parse", "--is-shallow-repository").stdout.strip()
    assert shallow == "false", (
        "shallow checkout: this gate needs full history and tags. "
        "In CI, actions/checkout must set fetch-depth: 0; locally, "
        "run `git fetch --unshallow --tags`."
    )


def test_current_version_is_tagged_or_head_introduced_it():
    version = current_version()
    tag = f"v{version}"

    if git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode == 0:
        return

    previous = version_at("HEAD~1")
    assert previous != version, (
        f"version {version} is declared but `{tag}` does not exist, and HEAD is not "
        f"the commit that introduced it. Cut the tag and push it:\n"
        f"    git tag {tag} && git push --follow-tags\n"
        f"See docs/RELEASING.md. This is the failure that lost v0.3.0 and v0.3.1."
    )


def test_tag_names_the_commit_that_declares_its_version():
    """A tag that exists must point at a commit declaring that same version.

    Equality alone would accept ``v0.3.1`` pointing anywhere in history — which
    is how a mis-tagged release publishes an unrelated tree under a version
    consumers then pin. cannobserv guards the same hazard with
    ``bump_version.py --check-tag``.
    """
    version = current_version()
    tag = f"v{version}"
    if git("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}").returncode != 0:
        pytest.skip(f"{tag} not cut yet; the release-commit grace case is tested above")

    tagged = version_at(tag)
    assert tagged == version, (
        f"{tag} points at a commit declaring version {tagged}, not {version}. "
        "Tags are immutable — a mis-tagged release gets a new patch tag, never a "
        "moved one."
    )
