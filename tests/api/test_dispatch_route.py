"""Route-level tests for POST /api/v1/dispatch.

This is the endpoint the service exists to serve, and it was the least covered
code in `src/` — 53%, with the entire stored-template path, both 404s, the
per-channel attempt loop, and the `partial` aggregation never executed. The
smoke suite reached the inline happy path and malformed-ULID rejection and
stopped there.

Nothing here is mocked. Delivery goes to a local sink that returns 200 or to a
port where the connection is refused, so success and failure are both real
outcomes of the real dispatcher.
"""

import secrets

import pytest
from ulid import ULID

from src.core.notifications.validate import VariablesValidationError, validate_variables

HEADER = "X-API-Key"


@pytest.fixture
def headers(api_key) -> dict[str, str]:
    raw_key, _ = api_key
    return {HEADER: raw_key}


async def _channel(client, headers, url: str) -> str:
    response = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": f"c-{secrets.token_hex(4)}", "apprise_url": url},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
async def good_channel(client, headers, sink_server) -> str:
    """Delivers successfully — a local HTTP sink that answers 200."""
    return await _channel(client, headers, f"json://127.0.0.1:{sink_server}/ok")


@pytest.fixture
async def bad_channel(client, headers, closed_port) -> str:
    """Fails to deliver — nothing is listening."""
    return await _channel(client, headers, f"json://127.0.0.1:{closed_port}/nope")


@pytest.fixture
async def template(client, headers) -> str:
    response = await client.post(
        "/api/v1/templates",
        headers=headers,
        json={
            "name": f"t-{secrets.token_hex(4)}",
            "title_template": "Hello {{ name }}",
            "body_template": "Body for {{ name }}",
            "variables_schema": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestStoredTemplateDispatch:
    """The primary documented workflow, and it had never run in a test."""

    async def test_renders_from_the_stored_template(self, client, headers, template, good_channel):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": template,
                "variables": {"name": "World"},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["rendered_title"] == "Hello World"
        assert payload["rendered_body"] == "Body for World"
        assert payload["template_id"] == template

    async def test_inline_templates_take_precedence(self, client, headers, template, good_channel):
        """Documented on DispatchRequest: inline wins, for stage rollouts."""
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": template,
                "title_template": "Inline {{ name }}",
                "body_template": "Inline body",
                "variables": {"name": "World"},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["rendered_title"] == "Inline World"

    async def test_unknown_template_is_404(self, client, headers, good_channel):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": str(ULID()),
                "variables": {"name": "x"},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 404, response.text

    async def test_unknown_channel_is_404_and_names_the_id(self, client, headers):
        missing = str(ULID())
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [missing],
            },
        )
        assert response.status_code == 404, response.text
        assert missing in response.json()["detail"]["channel_ids"]


class TestVariableValidation:
    """AGENTS.md: reject 422 with a clear field path on miss.

    A named API-boundary guarantee that nothing verified. `validate.py` looked
    covered only because the *preview* route exercises it — and preview
    answers 200 with an `error_section`, never a 422.
    """

    async def test_missing_required_variable_is_422_with_a_path(
        self, client, headers, template, good_channel
    ):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={"template_id": template, "variables": {}, "channel_ids": [good_channel]},
        )
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["section"] == "variables"
        assert "path" in detail
        assert "name" in detail["message"]

    async def test_wrong_type_is_422(self, client, headers, template, good_channel):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": template,
                "variables": {"name": 42},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "variables"

    async def test_undefined_reference_is_422_naming_the_section(
        self, client, headers, good_channel
    ):
        """StrictUndefined: an unbound reference fails loudly, per AGENTS.md."""
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "{{ never_bound }}",
                "body_template": "b",
                "variables": {},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "title"

    async def test_a_malformed_stored_schema_is_422_not_500(self, client, headers, good_channel):
        """Templates store `variables_schema` unvalidated, so a consumer can
        save a broken one and get a 201. Every dispatch through that template
        then raised jsonschema's UnknownType straight out of the route — a 500
        on consumer-supplied input. Found by writing this test."""
        created = await client.post(
            "/api/v1/templates",
            headers=headers,
            json={
                "name": f"bad-{secrets.token_hex(4)}",
                "title_template": "x",
                "body_template": "y",
                "variables_schema": {"type": "not-a-json-schema-type"},
            },
        )
        assert created.status_code == 201, created.text

        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": created.json()["id"],
                "variables": {"n": 1},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422, response.text
        assert "not a valid JSON Schema" in response.json()["detail"]["message"]

    def test_a_malformed_schema_is_reported_separately(self):
        """Unreachable through the API — templates validate their schema on
        write — so it is pinned here rather than left as the module's only
        uncovered branch."""
        with pytest.raises(VariablesValidationError) as exc:
            validate_variables({"n": 1}, {"type": "not-a-json-schema-type"})
        assert "not a valid JSON Schema" in exc.value.message


class TestStatusAggregation:
    """`partial` was asserted to exist as a string and never once produced."""

    async def test_all_channels_succeed(self, client, headers, good_channel, sink_server):
        second = await _channel(client, headers, f"json://127.0.0.1:{sink_server}/two")
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [good_channel, second],
            },
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["status"] == "succeeded"
        assert [a["status"] for a in payload["attempts"]] == ["succeeded", "succeeded"]

    async def test_mixed_outcomes_report_partial(self, client, headers, good_channel, bad_channel):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [good_channel, bad_channel],
            },
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert {a["status"] for a in payload["attempts"]} == {"succeeded", "failed"}

    async def test_all_channels_fail(self, client, headers, bad_channel):
        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [bad_channel],
            },
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["status"] == "failed"
        # The #25 fix, seen from the API: a real reason, not a placeholder.
        assert "no detail captured" not in payload["attempts"][0]["reason"]

    async def test_the_attempt_log_is_readable_afterwards(
        self, client, headers, good_channel, bad_channel
    ):
        created = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [good_channel, bad_channel],
            },
        )
        assert created.status_code == 202, created.text
        fetched = await client.get(f"/api/v1/dispatch/{created.json()['id']}", headers=headers)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["status"] == "partial"
        assert len(fetched.json()["attempts"]) == 2

    async def test_reading_an_unknown_dispatch_is_404(self, client, headers):
        response = await client.get(f"/api/v1/dispatch/{ULID()}", headers=headers)
        assert response.status_code == 404, response.text
