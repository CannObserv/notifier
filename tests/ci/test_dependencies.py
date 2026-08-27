"""Drift tests for pyproject.toml's dependency table.

Two invariants that `uv sync --locked` cannot express, both from #30.

* **Every specifier carries an upper bound.** A resolver takes what the
  specifier permits: `cryptography>=46.0.6` let 47.0.0 into the lock with no
  diff and no review. Build-time breaks are cheap; the expensive majors are
  the ones that move behavior on the dispatch path (`apprise`'s URL grammar,
  Fernet's backing API) where a green suite is not evidence.
* **Every declared runtime dependency has an importer under `src/`.** The
  lock is indifferent to a dependency nothing uses — which is how
  `procrastinate` sat unimported for months (#29). The exceptions are real
  but few, so `IMPORT_LESS` states each one once instead of leaving it to be
  re-derived; a stale entry there fails as loudly as a missing one.

The importer check covers `[project.dependencies]` only. Dev-group tools are
run as commands or imported from `tests/`, so "unimported by `src/`" is their
normal condition and says nothing.
"""

import re
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SRC = REPO_ROOT / "src"

# Operators that put a ceiling on what a resolver may take. `~=` and `==`
# bound from above as surely as `<` does, so a pin is not a violation.
BOUNDING_OPERATORS = {"<", "<=", "==", "===", "~="}

# Runtime dependencies that nothing under src/ imports, and why each is
# nonetheless required at runtime. Reached by name — a command line, a URL
# scheme, a framework's transport — rather than by `import`.
IMPORT_LESS = {
    "uvicorn": (
        "ASGI server, invoked as a command by scripts/dev_server.sh and the "
        "systemd units in deploy/"
    ),
    "asyncpg": (
        "SQLAlchemy's async driver, selected by the postgresql+asyncpg:// URL "
        "scheme rather than by import"
    ),
    "alembic": (
        "migration CLI; the only module that imports it is alembic/env.py, "
        "which alembic itself loads"
    ),
    "httpx": (
        "transport behind fastapi.testclient.TestClient, imported by "
        "tests/conftest.py; declared at runtime because the client the SDK "
        "ships depends on it too"
    ),
}


def pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def runtime_requirements() -> list[Requirement]:
    return [Requirement(dep) for dep in pyproject()["project"]["dependencies"]]


def all_requirements() -> list[Requirement]:
    groups = pyproject().get("dependency-groups", {})
    grouped = [Requirement(dep) for deps in groups.values() for dep in deps]
    return runtime_requirements() + grouped


def import_names(distribution: str) -> set[str]:
    """Top-level modules a distribution installs.

    Read from installed metadata, so `python-json-logger` resolves to
    `pythonjsonlogger` without a hand-kept name map. Falls back to the
    distribution name for anything the metadata does not describe.
    """
    name = canonicalize_name(distribution)
    modules = {
        module
        for module, dists in packages_distributions().items()
        if any(canonicalize_name(dist) == name for dist in dists)
    }
    return modules or {distribution.replace("-", "_")}


def importers(distribution: str) -> list[str]:
    """Paths under src/ importing any module the distribution installs."""
    alternatives = "|".join(re.escape(module) for module in sorted(import_names(distribution)))
    pattern = re.compile(rf"^\s*(?:from|import)\s+(?:{alternatives})\b", re.MULTILINE)
    return [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(SRC.rglob("*.py"))
        if pattern.search(path.read_text())
    ]


@pytest.mark.parametrize("requirement", all_requirements(), ids=str)
def test_every_dependency_carries_an_upper_bound(requirement):
    """A floor alone delegates the next major to whoever runs the resolver."""
    assert any(spec.operator in BOUNDING_OPERATORS for spec in requirement.specifier), (
        f"{requirement} may resolve to any future major. Add a cap "
        f"(house style is <next-major) so crossing one takes a reviewed diff."
    )


@pytest.mark.parametrize(
    "requirement",
    [req for req in runtime_requirements() if canonicalize_name(req.name) not in IMPORT_LESS],
    ids=str,
)
def test_every_runtime_dependency_has_an_importer(requirement):
    """Declared and unimported is how procrastinate survived to #29."""
    assert importers(requirement.name), (
        f"nothing under src/ imports {requirement.name}. Drop it, or add it "
        f"to IMPORT_LESS in this file with the reason it is needed anyway."
    )


@pytest.mark.parametrize("distribution", sorted(IMPORT_LESS), ids=str)
def test_import_less_allowlist_names_a_declared_dependency(distribution):
    """An exception outliving its dependency is a claim nobody rechecks."""
    declared = {canonicalize_name(req.name) for req in runtime_requirements()}
    assert distribution in declared, (
        f"IMPORT_LESS excuses {distribution}, which pyproject.toml no longer "
        f"declares; remove the entry."
    )


@pytest.mark.parametrize("distribution", sorted(IMPORT_LESS), ids=str)
def test_import_less_allowlist_has_no_entry_that_is_imported(distribution):
    """Once src/ imports it, the ordinary check covers it — and an allowlist
    entry would then hide a later removal."""
    found = importers(distribution)
    assert not found, (
        f"src/ now imports {distribution} ({', '.join(found)}); remove its "
        f"IMPORT_LESS entry so the importer check applies."
    )
