"""One version, five sites — the repo-wide half of the lockstep (#50).

The SDK and the server move together. That was already claimed in prose and
already false: three files said the SDK was "pinned 1:1 with the notifier
server" while the server sat at 0.1.0 and the SDK at 0.3.1, and the only test
enforcing anything read the SDK's three copies of *its own* version against
each other (#49). A rule that lives only in prose drifts, and the drift is
invisible until a consumer reads the sentence and believes it.

Five sites carry the version. Two are the server's, three are the SDK's:

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
    """The ``version=`` literal passed to ``FastAPI(...)`` in ``main.py``."""
    tree = ast.parse(MAIN.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "FastAPI":
            continue
        for kw in node.keywords:
            if kw.arg == "version" and isinstance(kw.value, ast.Constant):
                return kw.value.value
        pytest.fail(f"{MAIN}: FastAPI(...) has no literal version= keyword")
    pytest.fail(f"{MAIN}: no FastAPI(...) call found")


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


def test_all_five_version_sites_agree():
    found = sites()
    distinct = set(found.values())
    assert len(distinct) == 1, "version sites disagree:\n" + "\n".join(
        f"  {site} = {version}" for site, version in found.items()
    )


def test_server_pyproject_and_fastapi_agree():
    """The pair #49 flagged as unguarded in either direction.

    Called out on its own because a failure here has a different cause than a
    server/SDK split: it means the release bumped the distribution but not the
    version the OpenAPI spec advertises, so consumers regenerate against a spec
    that names the wrong version.
    """
    assert _pyproject_version(REPO_ROOT / "pyproject.toml") == _fastapi_version()
