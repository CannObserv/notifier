"""Drift test for ``[tool.ruff.lint] select`` — the whole static-analysis surface.

``pre-commit`` runs ruff and never pytest, and CI's ``lint`` job runs the same
two ruff commands. So the selector list *is* every automated check standing
between a commit and review; a family dropped from it goes quiet without
failing anything.

``ASYNC`` is asserted by name rather than left to "ruff check is clean"
because that is exactly the evidence it cannot provide: the family reported
zero findings on this tree the day it was adopted (#66), so a clean run looks
identical whether the rules are selected or not.
"""

import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def selectors() -> list[str]:
    config = tomllib.loads(PYPROJECT.read_text())
    return config["tool"]["ruff"]["lint"]["select"]


def test_async_family_is_selected(selectors):
    """Every route handler in src/api/routes/ is ``async def`` on one shared
    event loop, so a blocking call there is a latency bug nothing else catches.
    """
    assert "ASYNC" in selectors, (
        "ASYNC reports 0 findings on this tree, so a clean `ruff check .` is "
        "not evidence it is still selected — this assertion is (#66)"
    )


def test_fast_family_is_selected(selectors):
    """FastAPI-specific rules, adopted in two commits after their 62 findings
    were cleared (#66). Asserted as the family: narrowing it back to a single
    code (``FAST001``, the intermediate state) leaves a green ``ruff check .``
    while the other half stops being checked.
    """
    assert "FAST" in selectors, (
        "FAST001 and FAST002 are both clean; selecting the family is what "
        "keeps the next violation from landing (#66)"
    )


def test_baseline_families_are_still_selected(selectors):
    """The five families predating #66. Named so a rewrite of the list has to
    be deliberate about dropping one.
    """
    assert {"E", "F", "I", "W", "UP"} <= set(selectors)
