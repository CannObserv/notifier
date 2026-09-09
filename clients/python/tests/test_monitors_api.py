"""``client.monitors.*`` — dead-man's-timer CRUD and check-in (#56).

The check-in is the method that matters: a consumer calls it every tick,
findings or not, and its arrival is what keeps notifier from alerting on the
consumer's silence. Alone among the write methods it *is* auto-retried — see
the last test for why that is safe here and not elsewhere.
"""

import httpx
import pytest
import respx

from notifier_client import (
    CheckinResponse,
    MonitorOut,
    NotifierClient,
    RetryConfig,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


_MONITOR_BODY = {
    "id": "01HM",
    "tenant_id": "t1",
    "name": "co-broker",
    "enabled": True,
    "interval_seconds": 600,
    "grace_seconds": 1200,
    "renotify_seconds": None,
    "channel_ids": ["01HC"],
    "template_id": None,
    "title_template": "T",
    "body_template": "B",
    "state": "ok",
    "last_checkin_at": "2026-09-09T12:00:00Z",
    "last_status": "ok",
    "last_variables": {"source": "co-broker", "finding_count": 0},
    "last_alert_at": None,
    "next_deadline_at": "2026-09-09T12:30:00Z",
    "created_at": "2026-09-01T00:00:00Z",
    "updated_at": "2026-09-09T12:00:00Z",
}

_CHECKIN_BODY = {
    "monitor_id": "01HM",
    "previous_state": "ok",
    "state": "ok",
    "last_checkin_at": "2026-09-09T12:00:00Z",
    "next_deadline_at": "2026-09-09T12:30:00Z",
    "dispatches": [],
}


@respx.mock
@pytest.mark.asyncio
async def test_monitors_list_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/monitors").mock(
        return_value=httpx.Response(200, json=[_MONITOR_BODY])
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.monitors.list()
    assert len(result) == 1
    assert isinstance(result[0], MonitorOut)
    assert result[0].name == "co-broker"


@respx.mock
@pytest.mark.asyncio
async def test_monitors_create_sends_body_and_returns_typed(fast_retry):
    route = respx.post("https://t.local/api/v1/monitors").mock(
        return_value=httpx.Response(201, json=_MONITOR_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.monitors.create(
            name="co-broker",
            interval_seconds=600,
            grace_seconds=1200,
            channel_ids=["01HC"],
            title_template="T",
            body_template="B",
        )
    body = route.calls.last.request.read().decode()
    assert '"interval_seconds":600' in body
    assert isinstance(result, MonitorOut)


@respx.mock
@pytest.mark.asyncio
async def test_monitors_get_and_update(fast_retry):
    respx.get("https://t.local/api/v1/monitors/01HM").mock(
        return_value=httpx.Response(200, json=_MONITOR_BODY)
    )
    route = respx.patch("https://t.local/api/v1/monitors/01HM").mock(
        return_value=httpx.Response(200, json={**_MONITOR_BODY, "enabled": False})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        assert (await c.monitors.get("01HM")).name == "co-broker"
        paused = await c.monitors.update("01HM", enabled=False)
    assert paused.enabled is False
    # Only the supplied field is sent, so a PATCH never resets the cadence.
    assert "interval_seconds" not in route.calls.last.request.read().decode()


@respx.mock
@pytest.mark.asyncio
async def test_monitors_delete(fast_retry):
    respx.delete("https://t.local/api/v1/monitors/01HM").mock(return_value=httpx.Response(204))
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        assert await c.monitors.delete("01HM") is None


@respx.mock
@pytest.mark.asyncio
async def test_checkin_defaults_to_a_clean_heartbeat(fast_retry):
    route = respx.post("https://t.local/api/v1/monitors/01HM/checkin").mock(
        return_value=httpx.Response(202, json=_CHECKIN_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.monitors.checkin("01HM")
    assert '"status":"ok"' in route.calls.last.request.read().decode()
    assert isinstance(result, CheckinResponse)
    assert result.state == "ok"


@respx.mock
@pytest.mark.asyncio
async def test_checkin_carries_the_report_verbatim(fast_retry):
    """The consumer's own vocabulary passes straight through ``variables``."""
    route = respx.post("https://t.local/api/v1/monitors/01HM/checkin").mock(
        return_value=httpx.Response(202, json=_CHECKIN_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        await c.monitors.checkin(
            "01HM",
            status="alert",
            variables={"source": "co-broker", "finding_count": 1},
        )
    body = route.calls.last.request.read().decode()
    assert '"status":"alert"' in body
    assert '"finding_count":1' in body


@respx.mock
@pytest.mark.asyncio
async def test_checkin_is_retried_on_a_server_error(fast_retry):
    """A dropped heartbeat is indistinguishable from a dead consumer, and a
    retry cannot double-notify: the second check-in overwrites the first."""
    route = respx.post("https://t.local/api/v1/monitors/01HM/checkin").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(202, json=_CHECKIN_BODY),
        ]
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.monitors.checkin("01HM")
    assert route.call_count == 2
    assert isinstance(result, CheckinResponse)
