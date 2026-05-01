"""Direct tests for the schema-lifecycle primitives in conftest.

The smoke tests exercise the integrated `_heal_test_db → _test_db_schema`
chain transitively. These tests cover the primitives in isolation so a
regression in either step surfaces with a precise failure rather than
breaking the smoke run.
"""

import pytest

from tests.conftest import _run_schema

pytestmark = pytest.mark.integration


def test_run_schema_round_trip(_server_env):
    """create_all → drop_all → drop_all is the full primitive cycle.

    Validates each branch of `_run_schema` and the heal-on-empty case
    (the second `drop_all`). Leaves the DB empty so any session-scoped
    fixtures requested later see a clean slate.
    """
    _run_schema("create_all", _server_env)
    _run_schema("drop_all", _server_env)
    _run_schema("drop_all", _server_env)


def test_heal_test_db_runs_drop(_heal_test_db):
    """`_heal_test_db` runs without raising and yields no value.

    The fixture is exercised transitively via every smoke test that
    requests `_test_db_schema`; this test pins it as a directly-named
    dependency so a future refactor that breaks the heal step fails
    here independently of the smoke chain.
    """
    assert _heal_test_db is None
