"""Direct tests for the schema-lifecycle primitives in conftest.

The happy path is covered transitively — every integration test depends on
`_heal_test_db → _test_db_schema` having built the schema. What is *not*
covered transitively is `_run_schema`'s error handling, and the rule that
nothing may drop the schema while the server is serving it.

That rule used to be convention, and the convention broke: a round-trip test
here called `drop_all` mid-session, wiping the tables (and the seeded tenant)
out from under the running uvicorn subprocess. The only symptom was a smoke
test asserting 404 and receiving 500 (issue #23). It is now enforced in
`_run_schema` itself, so recurrence fails loudly at the call rather than
silently three tests later.
"""

import pytest

from tests import conftest as ct
from tests.conftest import _run_schema

pytestmark = pytest.mark.integration


def test_drop_is_refused_while_the_server_is_serving(notifier_url, _server_env):
    """The guard that makes issue #23 structurally impossible."""
    with pytest.raises(RuntimeError, match="while the server is running"):
        _run_schema("drop_all", _server_env)


def test_create_is_also_refused_while_the_server_is_serving(notifier_url, _server_env):
    """`create_all` is not destructive, but it masks model drift mid-session."""
    with pytest.raises(RuntimeError, match="while the server is running"):
        _run_schema("create_all", _server_env)


def test_schema_survives_a_refused_drop(notifier_url, tenant_credentials):
    """The refusal must not be cosmetic — the schema and seed are still there."""
    import httpx

    _, api_key = tenant_credentials
    response = httpx.get(
        f"{notifier_url}/api/v1/templates",
        headers={"X-API-Key": api_key},
        timeout=10.0,
    )
    assert response.status_code == 200


def test_run_schema_surfaces_a_subprocess_failure(_server_env):
    """An unreachable database must fail the test, not pass silently."""
    broken = {**_server_env, "DATABASE_URL": "postgresql+asyncpg://u@localhost:1/x_test"}
    with pytest.raises(pytest.fail.Exception, match="schema create_all failed"):
        _run_schema("create_all", broken)


def test_run_schema_surfaces_a_timeout(monkeypatch, _server_env):
    """Points at another database — the served one is guarded, by design."""
    monkeypatch.setattr(ct, "SCHEMA_TIMEOUT_SECONDS", 0.001)
    elsewhere = {**_server_env, "DATABASE_URL": "postgresql+asyncpg://u@localhost:1/y_test"}
    with pytest.raises(pytest.fail.Exception, match="timed out"):
        _run_schema("create_all", elsewhere)


def test_heal_test_db_runs_drop(_heal_test_db):
    """`_heal_test_db` runs before the server exists and yields no value."""
    assert _heal_test_db is None
