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

import asyncio
import http.server
import secrets
import threading
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass, field

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from src.api.deps import get_db_session
from src.api.main import app
from src.core.api_keys import mint
from src.core.crypto import encrypt_apprise_url
from src.core.models import Channel, Dispatch, Tenant
from src.core.models.template import Template
from src.core.notifications.constants import MAX_ATTEMPTS_PER_CHANNEL, DispatchStatus
from src.core.notifications.validate import VariablesValidationError, validate_variables
from src.core.tenants import delete_tenant

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
    return await _channel(client, headers, f"json://127.0.0.1:{sink_server.port}/ok")


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

    async def test_a_malformed_stored_schema_is_422_not_500(
        self, client, headers, good_channel, db_session, tenant
    ):
        """The dispatch-time backstop, for a row the write-time guard never saw.

        Templates once stored `variables_schema` unvalidated, so a consumer
        could save a broken one and get a 201; every dispatch through that
        template then raised jsonschema's UnknownType straight out of the
        route — a 500 on consumer-supplied input. Found by writing this test.

        POST /templates refuses that schema now (#28), so the row is inserted
        through the ORM instead — which is exactly the case the backstop still
        has to cover: a template written before the guard landed.
        """
        stored = Template(
            tenant_id=tenant.id,
            name=f"bad-{secrets.token_hex(4)}",
            title_template="x",
            body_template="y",
            variables_schema={"type": "not-a-json-schema-type"},
        )
        db_session.add(stored)
        await db_session.flush()

        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": str(stored.id),
                "variables": {"n": 1},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422, response.text
        assert "not a valid JSON Schema" in response.json()["detail"]["message"]

    async def test_an_unresolvable_ref_in_a_stored_schema_is_422_not_500(
        self, client, headers, good_channel, db_session, tenant
    ):
        """`check_schema` passes a `$ref` that resolves to nothing, so this
        schema reached storage looking valid. `iter_errors` then raised
        `Unresolvable` — not a SchemaError, caught by nobody — straight out of
        the route. Same 500-on-consumer-input as the malformed-type case above,
        which is why the dispatch guard has to catch both."""
        stored = Template(
            tenant_id=tenant.id,
            name=f"ref-{secrets.token_hex(4)}",
            title_template="x",
            body_template="y",
            variables_schema={"$ref": "https://example.com/schema.json"},
        )
        db_session.add(stored)
        await db_session.flush()

        response = await client.post(
            "/api/v1/dispatch",
            headers=headers,
            json={
                "template_id": str(stored.id),
                "variables": {"n": 1},
                "channel_ids": [good_channel],
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "variables_schema"

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
        second = await _channel(client, headers, f"json://127.0.0.1:{sink_server.port}/two")
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

    async def test_a_channel_listed_twice_is_sent_once(
        self, client, headers, good_channel, sink_server
    ):
        """CR 1: `[A, A]` sent twice, then hit the attempt unique constraint —
        a 500 whose rollback left no record, so replaying the key sent twice
        more."""
        delivered = len(sink_server.received)

        payload = await _dispatch(client, headers, [good_channel, good_channel])

        assert _trail(payload) == [(good_channel, 1, "succeeded")]
        assert len(sink_server.received) == delivered + 1

    async def test_reading_an_unknown_dispatch_is_404(self, client, headers):
        response = await client.get(f"/api/v1/dispatch/{ULID()}", headers=headers)
        assert response.status_code == 404, response.text


async def _dispatch(client, headers, channel_ids: list[str], **extra) -> dict:
    response = await client.post(
        "/api/v1/dispatch",
        headers=headers,
        json={
            "title_template": "Retry {{ n }}",
            "body_template": "Body {{ n }}",
            "variables": {"n": 7},
            "channel_ids": channel_ids,
            **extra,
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _redeliver(client, headers, dispatch_id: str):
    return await client.post(f"/api/v1/dispatch/{dispatch_id}/redeliver", headers=headers)


def _trail(payload: dict) -> list[tuple[str, int, str]]:
    """Every attempt as (channel_id, attempt, status), in the order made."""
    return [(a["channel_id"], a["attempt"], a["status"]) for a in payload["attempts"]]


class TestRedelivery:
    """POST /dispatch/{id}/redeliver retries failed channels, and only those (#96).

    Before this a transient failure was final: replaying the idempotency key
    returns the stored `failed` record, and a new key resends to every
    channel — twice over for the ones that already succeeded.
    """

    async def test_a_failed_channel_is_retried_as_the_next_attempt(
        self, client, headers, bad_channel, sink_server
    ):
        created = await _dispatch(client, headers, [bad_channel])
        assert created["status"] == "failed"
        # The failure was transient — the target answers now.
        fixed = await client.patch(
            f"/api/v1/channels/{bad_channel}",
            headers=headers,
            json={"apprise_url": f"json://127.0.0.1:{sink_server.port}/fixed"},
        )
        assert fixed.status_code == 200, fixed.text

        response = await _redeliver(client, headers, created["id"])

        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["id"] == created["id"]
        assert payload["status"] == "succeeded"
        assert _trail(payload) == [(bad_channel, 1, "failed"), (bad_channel, 2, "succeeded")]

    async def test_redelivery_resends_the_stored_render(
        self, client, headers, bad_channel, sink_server
    ):
        """No re-render: what goes out is what the original dispatch rendered."""
        created = await _dispatch(client, headers, [bad_channel])
        await client.patch(
            f"/api/v1/channels/{bad_channel}",
            headers=headers,
            json={"apprise_url": f"json://127.0.0.1:{sink_server.port}/render"},
        )

        await _redeliver(client, headers, created["id"])

        assert sink_server.received[-1]["title"] == "Retry 7"
        assert sink_server.received[-1]["message"] == "Body 7"

    async def test_channels_that_succeeded_are_not_sent_again(
        self, client, headers, good_channel, bad_channel, sink_server
    ):
        created = await _dispatch(client, headers, [good_channel, bad_channel])
        assert created["status"] == "partial"
        delivered = len(sink_server.received)

        response = await _redeliver(client, headers, created["id"])

        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert _trail(payload) == [
            (good_channel, 1, "succeeded"),
            (bad_channel, 1, "failed"),
            (bad_channel, 2, "failed"),
        ]
        assert len(sink_server.received) == delivered

    async def test_a_succeeded_dispatch_is_returned_unchanged(
        self, client, headers, good_channel, sink_server
    ):
        created = await _dispatch(client, headers, [good_channel])
        delivered = len(sink_server.received)

        response = await _redeliver(client, headers, created["id"])

        assert response.status_code == 202, response.text
        assert response.json() == created
        assert len(sink_server.received) == delivered

    async def test_the_attempt_cap_is_409_naming_the_channels(self, client, headers, bad_channel):
        """Apprise answers a bool, so a revoked webhook fails forever; the cap
        is what bounds the attempt log, not error classification."""
        created = await _dispatch(client, headers, [bad_channel])
        for _ in range(MAX_ATTEMPTS_PER_CHANNEL - 1):
            assert (await _redeliver(client, headers, created["id"])).status_code == 202

        response = await _redeliver(client, headers, created["id"])

        assert response.status_code == 409, response.text
        assert response.json()["detail"]["channel_ids"] == [bad_channel]
        fetched = await client.get(f"/api/v1/dispatch/{created['id']}", headers=headers)
        assert len(fetched.json()["attempts"]) == MAX_ATTEMPTS_PER_CHANNEL

    async def test_the_redelivered_record_is_what_get_and_replay_return(
        self, client, headers, bad_channel, sink_server
    ):
        """Replaying the key hands back the current record, so a caller that
        only ever replays sees the retry land without learning a new call."""
        created = await _dispatch(client, headers, [bad_channel], idempotency_key="evt-96")
        await client.patch(
            f"/api/v1/channels/{bad_channel}",
            headers=headers,
            json={"apprise_url": f"json://127.0.0.1:{sink_server.port}/replay"},
        )
        await _redeliver(client, headers, created["id"])

        fetched = await client.get(f"/api/v1/dispatch/{created['id']}", headers=headers)
        replayed = await _dispatch(client, headers, [bad_channel], idempotency_key="evt-96")

        for payload in (fetched.json(), replayed):
            assert payload["status"] == "succeeded"
            assert [a["attempt"] for a in payload["attempts"]] == [1, 2]

    async def test_redelivering_an_unknown_dispatch_is_404(self, client, headers):
        response = await _redeliver(client, headers, str(ULID()))
        assert response.status_code == 404, response.text

    def test_the_repeated_attempts_rule_is_in_the_openapi_schema(self):
        """CR 3: `/docs` is the contract for callers without the SDK, and a
        client counting `attempts` entries as channels miscounts after one
        redelivery."""
        spec = app.openapi()
        attempts = spec["components"]["schemas"]["DispatchOut"]["properties"]["attempts"]
        assert "highest `attempt`" in attempts["description"]


@dataclass
class HeldSink:
    """A delivery target that answers only once `release` is set.

    Holding the first send open is what holds its dispatch's transaction
    open, with the Dispatch row flushed and uncommitted — the window a
    retrying client lands in. Records each request's path, so a test can
    count sends per channel.
    """

    port: int
    release: threading.Event
    arrived: threading.Event
    paths: list[str] = field(default_factory=list)


@pytest.fixture
def held_sink() -> Iterator[HeldSink]:
    release, arrived = threading.Event(), threading.Event()
    paths: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            paths.append(self.path)
            arrived.set()
            release.wait(timeout=30)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args) -> None:
            """Silence the default stderr access log."""

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield HeldSink(port=server.server_address[1], release=release, arrived=arrived, paths=paths)
    release.set()
    server.shutdown()
    server.server_close()


@dataclass(frozen=True)
class LiveTenant:
    """A committed tenant, its raw key, and channels on the held sink."""

    id: str
    headers: dict[str, str]
    channel_ids: list[str]


@pytest.fixture
async def live_tenant(test_engine, held_sink) -> AsyncGenerator[LiveTenant]:
    """Committed rows, because each concurrent request gets its own session.

    The savepointed `db_session` serialises every request through one
    connection, so two dispatches never overlap — the very thing #115 needs.
    """
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        tenant = Tenant(name=f"race-{secrets.token_hex(4)}")
        session.add(tenant)
        await session.flush()
        _, raw = await mint(session, tenant.id, "race", "production")
        channels = [
            Channel(
                tenant_id=tenant.id,
                name=f"held-{n}",
                # rto: Apprise's 4 s read timeout would otherwise fail the held send.
                apprise_url_encrypted=encrypt_apprise_url(
                    f"json://127.0.0.1:{held_sink.port}/c{n}?rto=30"
                ),
            )
            for n in range(2)
        ]
        session.add_all(channels)
        await session.commit()
        tenant_id = str(tenant.id)
        yield LiveTenant(
            id=tenant_id,
            headers={HEADER: raw},
            channel_ids=[str(c.id) for c in channels],
        )
        await delete_tenant(session, tenant_id, dry_run=False)


@pytest.fixture
async def live_client(test_engine) -> AsyncGenerator[AsyncClient]:
    """An AsyncClient whose every request opens its own committing session."""

    async def own_session() -> AsyncGenerator[AsyncSession]:
        async with AsyncSession(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db_session] = own_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _until_a_backend_waits_on_a_lock(test_engine) -> None:
    """Return once some session in this database is blocked on a lock.

    Proof that the second request has reached its INSERT and is queued behind
    the first's uncommitted row — without it, releasing the first early lets
    the second take the plain sequential replay, and the test passes having
    exercised nothing.
    """
    query = text(
        "SELECT count(*) FROM pg_stat_activity "
        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    async with asyncio.timeout(10), test_engine.connect() as conn:
        while (await conn.execute(query)).scalar_one() == 0:
            await conn.rollback()
            await asyncio.sleep(0.05)


async def _rows_with_key(test_engine, tenant_id: str, key: str) -> int:
    async with AsyncSession(test_engine) as session:
        return await session.scalar(
            select(func.count())
            .select_from(Dispatch)
            .where(Dispatch.tenant_id == tenant_id, Dispatch.idempotency_key == key)
        )


class TestConcurrentIdempotency:
    """#115: a retry that lands while the first call is still sending.

    Sequential replay was always safe; concurrent replay gave the second
    caller a 500 once the first committed.
    """

    @staticmethod
    def _post(client: AsyncClient, tenant: LiveTenant, key: str):
        return client.post(
            "/api/v1/dispatch",
            headers=tenant.headers,
            json={
                "title_template": "Race",
                "body_template": "Body",
                "channel_ids": tenant.channel_ids,
                "idempotency_key": key,
            },
        )

    async def test_the_second_request_gets_the_first_ones_dispatch(
        self, live_client, live_tenant, held_sink, test_engine
    ):
        first = asyncio.create_task(self._post(live_client, live_tenant, "evt-115"))
        assert await asyncio.to_thread(held_sink.arrived.wait, 10), "first send never arrived"
        second = asyncio.create_task(self._post(live_client, live_tenant, "evt-115"))
        await _until_a_backend_waits_on_a_lock(test_engine)
        held_sink.release.set()

        a, b = await asyncio.gather(first, second)

        assert a.status_code == 202, a.text
        assert b.status_code == 202, b.text
        assert b.json()["id"] == a.json()["id"]
        assert b.json()["status"] == DispatchStatus.SUCCEEDED
        assert len(b.json()["attempts"]) == 2
        assert sorted(held_sink.paths) == ["/c0", "/c1"]
        assert await _rows_with_key(test_engine, live_tenant.id, "evt-115") == 1

    async def test_a_rolled_back_first_request_leaves_the_key_to_the_second(
        self, live_client, live_tenant, held_sink, test_engine
    ):
        """The first holder never commits, so the key was never taken: the
        second request must deliver, not replay a row that does not exist."""
        held_sink.release.set()
        async with AsyncSession(test_engine) as holder:
            holder.add(
                Dispatch(
                    tenant_id=live_tenant.id,
                    idempotency_key="evt-115",
                    rendered_title="t",
                    rendered_body="b",
                    status=DispatchStatus.FAILED,
                )
            )
            await holder.flush()
            second = asyncio.create_task(self._post(live_client, live_tenant, "evt-115"))
            await _until_a_backend_waits_on_a_lock(test_engine)
            await holder.rollback()

        b = await second

        assert b.status_code == 202, b.text
        assert b.json()["status"] == DispatchStatus.SUCCEEDED
        assert sorted(held_sink.paths) == ["/c0", "/c1"]
        assert await _rows_with_key(test_engine, live_tenant.id, "evt-115") == 1
