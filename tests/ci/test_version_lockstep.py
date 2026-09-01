"""One version, every site that mirrors it — the repo-wide half of the lockstep (#50).

The SDK and the server move together. That was already claimed in prose and
already false: three files said the SDK was "pinned 1:1 with the notifier
server" while the server sat at 0.1.0 and the SDK at 0.3.1, and the only test
enforcing anything read the SDK's three copies of *its own* version against
each other (#49). A rule that lives only in prose drifts, and the drift is
invisible until a consumer reads the sentence and believes it.

The sites that carry it — the server's, then the SDK's:

* ``pyproject.toml`` — the distribution version
* ``src/api/main.py`` — FastAPI's ``version=``, which becomes the OpenAPI
  spec's ``info.version`` and is the only copy a consumer can see at runtime
* ``clients/python/pyproject.toml`` — what a consumer resolves
* ``notifier_client.__version__`` — what a consumer introspects
* ``clients/python/CHANGELOG.md`` — the compatibility record

**This file reads; it never imports.** ``notifier_client`` is not a dependency
of the service and is not installed in this venv — it lives in its own tree
under its own lockfile. Reading ``__init__.py`` as text is not a workaround for
that: it is the only way to assert on the SDK's version from here without
making the service depend on its own client. ``src/api/main.py`` is read the
same way, by AST rather than by import, so the module stays a plain literal and
needs no ``importlib.metadata`` coupling to satisfy a test.

The SDK keeps its own ``tests/test_version_lockstep.py`` for the three-way
check among its internal copies. That is what a package shipped to consumers
should assert about itself; this file is what the repo asserts about the pair,
and it belongs here because ``clients/python`` must not read files above its
own root. ``test_dependencies.py`` already reaches into ``clients/python/``
from this directory for the same reason.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = REPO_ROOT / "clients" / "python"

MAIN = REPO_ROOT / "src" / "api" / "main.py"
SDK_INIT = SDK_ROOT / "src" / "notifier_client" / "__init__.py"
SDK_CHANGELOG = SDK_ROOT / "CHANGELOG.md"

HEADING = re.compile(r"^## (\d+\.\d+\.\d+)")


def _pyproject_version(path: Path) -> str:
    with path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _fastapi_version() -> str:
    """The ``version=`` literal passed to ``FastAPI(...)`` in ``main.py``.

    Every ``FastAPI(...)`` call is collected rather than the first one taken:
    ``ast.walk`` is breadth-first, not source order, so with a mounted
    sub-application "the first call" would be an arbitrary one of the two and
    this test would silently assert against whichever it happened to reach.
    More than one is an error to surface, not an ambiguity to resolve quietly.
    """
    tree = ast.parse(MAIN.read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None))
        == "FastAPI"
    ]
    if not calls:
        pytest.fail(f"{MAIN}: no FastAPI(...) call found")
    if len(calls) > 1:
        pytest.fail(
            f"{MAIN}: {len(calls)} FastAPI(...) calls found. This test asserts on the "
            "app's declared version and cannot tell which one is the service's — name "
            "the right one explicitly here."
        )
    for kw in calls[0].keywords:
        if kw.arg == "version" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    pytest.fail(f"{MAIN}: FastAPI(...) has no literal version= keyword")


def _sdk_dunder_version() -> str:
    """``__version__`` from the SDK's ``__init__.py``, read rather than imported."""
    tree = ast.parse(SDK_INIT.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    return node.value.value
    pytest.fail(f"{SDK_INIT}: no literal __version__ assignment found")


def _changelog_version() -> str:
    for line in SDK_CHANGELOG.read_text().splitlines():
        if m := HEADING.match(line):
            return m.group(1)
    pytest.fail(f"{SDK_CHANGELOG}: no released version heading found")


def sites() -> dict[str, str]:
    return {
        "pyproject.toml": _pyproject_version(REPO_ROOT / "pyproject.toml"),
        "src/api/main.py FastAPI(version=)": _fastapi_version(),
        "clients/python/pyproject.toml": _pyproject_version(SDK_ROOT / "pyproject.toml"),
        "notifier_client.__version__": _sdk_dunder_version(),
        "clients/python/CHANGELOG.md": _changelog_version(),
    }


def test_version_sites_agree():
    """Covers both pairs #49 named: the server/SDK split, and ``pyproject.toml``
    against ``src/api/main.py`` — the second lockstep, which nothing read before.
    A failure prints every site with its value, so the cause is legible from the
    message without a narrower assertion restating it.

    ``sites()`` is the only place the set is enumerated, and this name no longer
    counts them: a name carrying a cardinality goes stale the moment a site is
    added, and every doc repeating that number goes stale with it.
    """
    found = sites()
    distinct = set(found.values())
    assert len(distinct) == 1, "version sites disagree:\n" + "\n".join(
        f"  {site} = {version}" for site, version in found.items()
    )
