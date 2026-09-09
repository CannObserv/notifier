"""Route-level tests for /api/v1/monitors and its check-in endpoint (#56).

A monitor is a dead-man's timer plus a place to send a report. The check-in
endpoint is deliberately consumer-agnostic: it takes a ``status`` and an
opaque ``variables`` bag, so a broker's ``finding_count``/``findings`` payload
travels through verbatim without any of that vocabulary entering notifier's
schema (AGENTS.md, API Boundary Principles).

Nothing is mocked. Delivery goes to the local sink or to a refused port.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from ulid import ULID

from src.core.models import ApiKey, Tenant
from src.core.models.monitor import Monitor

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
    return await _channel(client, headers, f"json://127.0.0.1:{sink_server.port}/ok")


@pytest.fixture
async def template(client, headers) -> str:
    """The broker's report template — a schema over the bag it actually sends."""
    response = await client.post(
        "/api/v1/templates",
        headers=headers,
        json={
            "name": f"t-{secrets.token_hex(4)}",
            "title_template": "{{ source }}: {{ finding_count }} finding(s)",
            "body_template": "{% for f in findings %}{{ f.check }}: {{ f.message }}\n{% endfor %}",
            "variables_schema": {
                "type": "object",
                "required": ["source", "finding_count"],
                "properties": {
                    "source": {"type": "string"},
                    "finding_count": {"type": "integer"},
                    "findings": {"type": "array"},
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create(client, headers, **overrides) -> dict:
    payload = {
        "name": f"m-{secrets.token_hex(4)}",
        "interval_seconds": 600,
        "grace_seconds": 1200,
        "channel_ids": overrides.pop("channel_ids", []),
        "title_template": "T {{ source }}",
        "body_template": "B",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/monitors", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def monitor(client, headers, good_channel) -> dict:
    return await _create(client, headers, channel_ids=[good_channel])


class TestCreate:
    async def test_creates_a_monitor_in_the_pending_state(self, client, headers, good_channel):
        created = await _create(client, headers, channel_ids=[good_channel])
        assert created["state"] == "pending"
        assert created["enabled"] is True
        assert created["last_checkin_at"] is None

    async def test_reports_the_deadline_it_will_be_judged_against(
        self, client, headers, good_channel
    ):
        """The consumer should not have to re-derive interval + grace."""
        created = await _create(client, headers, channel_ids=[good_channel])
        created_at = datetime.fromisoformat(created["created_at"])
        deadline = datetime.fromisoformat(created["next_deadline_at"])
        assert deadline - created_at == timedelta(seconds=1800)

    async def test_rejects_a_channel_the_tenant_does_not_own(self, client, headers):
        response = await client.post(
            "/api/v1/monitors",
            headers=headers,
            json={
                "name": f"m-{secrets.token_hex(4)}",
                "interval_seconds": 600,
                "channel_ids": [str(ULID())],
                "title_template": "T",
                "body_template": "B",
            },
        )
        assert response.status_code == 404
        assert "channel_ids" in str(response.json()["detail"])

    async def test_rejects_a_monitor_with_no_way_to_render_an_alert(
        self, client, headers, good_channel
    ):
        """Same rule as dispatch: a stored template or both inline halves.

        A monitor that cannot render is one whose alert fails at exactly the
        moment it matters.
        """
        response = await client.post(
            "/api/v1/monitors",
            headers=headers,
            json={
                "name": f"m-{secrets.token_hex(4)}",
                "interval_seconds": 600,
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422

    async def test_rejects_a_non_positive_interval(self, client, headers, good_channel):
        response = await client.post(
            "/api/v1/monitors",
            headers=headers,
            json={
                "name": f"m-{secrets.token_hex(4)}",
                "interval_seconds": 0,
                "channel_ids": [good_channel],
                "title_template": "T",
                "body_template": "B",
            },
        )
        assert response.status_code == 422

    async def test_rejects_a_duplicate_name_within_the_tenant(self, client, headers, good_channel):
        name = f"m-{secrets.token_hex(4)}"
        await _create(client, headers, name=name, channel_ids=[good_channel])
        response = await client.post(
            "/api/v1/monitors",
            headers=headers,
            json={
                "name": name,
                "interval_seconds": 600,
                "channel_ids": [good_channel],
                "title_template": "T",
                "body_template": "B",
            },
        )
        assert response.status_code == 409


class TestReadUpdateDelete:
    async def test_lists_only_the_calling_tenants_monitors(self, client, headers, monitor):
        response = await client.get("/api/v1/monitors", headers=headers)
        assert response.status_code == 200
        assert [m["id"] for m in response.json()] == [monitor["id"]]

    async def test_fetches_one(self, client, headers, monitor):
        response = await client.get(f"/api/v1/monitors/{monitor['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == monitor["id"]

    async def test_unknown_id_is_404(self, client, headers):
        response = await client.get(f"/api/v1/monitors/{ULID()}", headers=headers)
        assert response.status_code == 404

    async def test_malformed_id_is_422(self, client, headers):
        response = await client.get("/api/v1/monitors/not-a-ulid", headers=headers)
        assert response.status_code == 422

    async def test_can_be_paused_without_being_deleted(self, client, headers, monitor):
        """Planned downtime should not require destroying the configuration."""
        response = await client.patch(
            f"/api/v1/monitors/{monitor['id']}", headers=headers, json={"enabled": False}
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    async def test_update_rejects_an_unowned_channel(self, client, headers, monitor):
        response = await client.patch(
            f"/api/v1/monitors/{monitor['id']}",
            headers=headers,
            json={"channel_ids": [str(ULID())]},
        )
        assert response.status_code == 404

    async def test_deletes(self, client, headers, monitor):
        response = await client.delete(f"/api/v1/monitors/{monitor['id']}", headers=headers)
        assert response.status_code == 204
        follow_up = await client.get(f"/api/v1/monitors/{monitor['id']}", headers=headers)
        assert follow_up.status_code == 404


class TestCheckin:
    """Every tick, findings or not — the arrival is the signal."""

    async def test_a_clean_report_resets_the_timer_and_sends_nothing(
        self, client, headers, monitor, sink_server
    ):
        before = len(sink_server.received)
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "ok", "variables": {"source": "co-broker", "finding_count": 0}},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["state"] == "ok"
        assert payload["dispatches"] == []
        assert len(sink_server.received) == before

    async def test_status_defaults_to_ok(self, client, headers, monitor):
        """A bare heartbeat is a valid check-in; findings are the exception."""
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin", headers=headers, json={}
        )
        assert response.status_code == 202
        assert response.json()["state"] == "ok"

    async def test_the_checkin_advances_the_deadline(self, client, headers, monitor):
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin", headers=headers, json={}
        )
        body = response.json()
        checked_in = datetime.fromisoformat(body["last_checkin_at"])
        deadline = datetime.fromisoformat(body["next_deadline_at"])
        assert deadline - checked_in == timedelta(seconds=1800)

    async def test_an_alert_report_is_rendered_and_delivered(
        self, client, headers, monitor, sink_server
    ):
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "alert", "variables": {"source": "co-broker"}},
        )
        assert response.status_code == 202, response.text
        (dispatch,) = response.json()["dispatches"]
        assert dispatch["rendered_title"] == "T co-broker"
        assert dispatch["status"] == "succeeded"
        assert sink_server.received[-1]["title"] == "T co-broker"

    async def test_an_alert_still_counts_as_a_checkin(self, client, headers, monitor):
        """The report arrived. Findings say the broker is unwell; silence
        would have said something worse."""
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "alert", "variables": {"source": "co-broker"}},
        )
        assert response.json()["state"] == "ok"
        assert response.json()["last_checkin_at"] is not None

    async def test_the_whole_report_is_kept_verbatim(self, client, headers, monitor):
        """`findings`/`finding_count` are the consumer's vocabulary, stored
        opaquely and never interpreted here."""
        report = {
            "source": "co-broker",
            "finding_count": 1,
            "findings": [{"check": "dlq", "subject": "content.fetch.dlq", "message": "depth 12"}],
            "timestamp": "2026-09-08T21:58:44Z",
        }
        await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "alert", "variables": report},
        )
        fetched = await client.get(f"/api/v1/monitors/{monitor['id']}", headers=headers)
        assert fetched.json()["last_variables"] == report

    async def test_a_report_that_violates_the_template_schema_is_422(
        self, client, headers, good_channel, template
    ):
        created = await _create(
            client,
            headers,
            channel_ids=[good_channel],
            template_id=template,
            title_template=None,
            body_template=None,
        )
        response = await client.post(
            f"/api/v1/monitors/{created['id']}/checkin",
            headers=headers,
            json={"status": "alert", "variables": {"source": "co-broker"}},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["section"] == "variables"

    async def test_a_stored_template_renders_the_report(
        self, client, headers, good_channel, template
    ):
        created = await _create(
            client,
            headers,
            channel_ids=[good_channel],
            template_id=template,
            title_template=None,
            body_template=None,
        )
        response = await client.post(
            f"/api/v1/monitors/{created['id']}/checkin",
            headers=headers,
            json={
                "status": "alert",
                "variables": {"source": "co-broker", "finding_count": 2, "findings": []},
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["dispatches"][0]["rendered_title"] == "co-broker: 2 finding(s)"

    async def test_a_clean_report_is_not_schema_checked(
        self, client, headers, good_channel, template
    ):
        """Nothing is rendered, so nothing needs validating. Rejecting the
        heartbeat over its payload would silence the timer to protect a
        notification that was never going to be sent."""
        created = await _create(
            client,
            headers,
            channel_ids=[good_channel],
            template_id=template,
            title_template=None,
            body_template=None,
        )
        response = await client.post(
            f"/api/v1/monitors/{created['id']}/checkin",
            headers=headers,
            json={"status": "ok", "variables": {}},
        )
        assert response.status_code == 202

    async def test_checkin_on_an_unknown_monitor_is_404(self, client, headers):
        response = await client.post(f"/api/v1/monitors/{ULID()}/checkin", headers=headers, json={})
        assert response.status_code == 404

    async def test_rejects_an_unknown_status(self, client, headers, monitor):
        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "degraded"},
        )
        assert response.status_code == 422


class TestRecovery:
    async def test_a_missing_monitor_that_reports_again_announces_it(
        self, client, headers, monitor, db_session
    ):
        """Silence gets an alert; the end of silence gets one too, or the
        first alert stays the last word on a problem that is over."""
        row = (
            await db_session.execute(select(Monitor).where(Monitor.id == monitor["id"]))
        ).scalar_one()
        row.state = "missing"
        row.last_alert_at = datetime.now(UTC) - timedelta(hours=2)
        row.last_checkin_at = datetime.now(UTC) - timedelta(hours=3)
        await db_session.flush()

        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin", headers=headers, json={}
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["previous_state"] == "missing"
        assert body["state"] == "ok"
        (dispatch,) = body["dispatches"]
        assert "recovered" in dispatch["rendered_title"].lower()

    async def test_recovery_and_findings_are_two_separate_notifications(
        self, client, headers, monitor, db_session
    ):
        """Different facts, different audiences-in-time: 'it is back' and
        'here is what it found' should not be collapsed into one message."""
        row = (
            await db_session.execute(select(Monitor).where(Monitor.id == monitor["id"]))
        ).scalar_one()
        row.state = "missing"
        await db_session.flush()

        response = await client.post(
            f"/api/v1/monitors/{monitor['id']}/checkin",
            headers=headers,
            json={"status": "alert", "variables": {"source": "co-broker"}},
        )
        assert len(response.json()["dispatches"]) == 2


class TestTenantIsolation:
    async def test_another_tenant_cannot_see_or_check_in(
        self, client, headers, monitor, db_session
    ):
        """The check-in URL is guessable from a ULID; ownership is the guard."""
        other = Tenant(name=f"other-{secrets.token_hex(4)}")
        db_session.add(other)
        await db_session.flush()
        raw = "nk_" + secrets.token_urlsafe(16)
        db_session.add(
            ApiKey(
                tenant_id=other.id,
                label="other",
                key_prefix=raw[:8],
                key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            )
        )
        await db_session.flush()
        intruder = {HEADER: raw}

        assert (await client.get("/api/v1/monitors", headers=intruder)).json() == []
        assert (
            await client.get(f"/api/v1/monitors/{monitor['id']}", headers=intruder)
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/monitors/{monitor['id']}/checkin", headers=intruder, json={}
            )
        ).status_code == 404
