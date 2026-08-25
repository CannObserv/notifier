"""One tenant must never reach another tenant's rows.

Nothing tested this. Every ownership filter in the API — `Channel.tenant_id ==
tenant_id`, `Template.tenant_id == tenant_id` — was load-bearing and
unverified, and `channel_ids` arrive straight from consumer input. Dropping
one `.where()` clause would have let any tenant dispatch through any other
tenant's Slack webhook with a green suite behind it.

AGENTS.md puts it as a design rule: business logic never branches on tenant
identity, because tenancy is enforced at the boundary. These tests are what
makes that rule checkable.
"""

import hashlib
import secrets

import pytest

from src.core.models import ApiKey, Tenant

HEADER = "X-API-Key"


@pytest.fixture
async def intruder(db_session) -> str:
    """A second tenant's API key. Valid — just not the owner's."""
    other = Tenant(name=f"intruder-{secrets.token_hex(4)}")
    db_session.add(other)
    await db_session.flush()
    raw = "nk_" + secrets.token_urlsafe(16)
    db_session.add(
        ApiKey(
            tenant_id=other.id,
            label="intruder",
            key_prefix=raw[:8],
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
        )
    )
    await db_session.flush()
    return raw


@pytest.fixture
async def owned_channel(client, api_key, closed_port) -> str:
    raw_key, _ = api_key
    response = await client.post(
        "/api/v1/channels",
        headers={HEADER: raw_key},
        json={"name": "owned", "apprise_url": f"json://127.0.0.1:{closed_port}/x"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
async def owned_template(client, api_key) -> str:
    raw_key, _ = api_key
    response = await client.post(
        "/api/v1/templates",
        headers={HEADER: raw_key},
        json={
            "name": f"owned-{secrets.token_hex(4)}",
            "title_template": "T {{ n }}",
            "body_template": "B {{ n }}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestChannelIsolation:
    async def test_listing_shows_only_your_own(self, client, intruder, owned_channel):
        response = await client.get("/api/v1/channels", headers={HEADER: intruder})
        assert response.status_code == 200
        assert [c["id"] for c in response.json()] == []

    @pytest.mark.parametrize("method", ["get", "patch", "delete"])
    async def test_direct_access_is_404(self, client, intruder, owned_channel, method):
        """404, not 403 — a stranger's row should not be distinguishable from
        one that does not exist."""
        kwargs = {"json": {"name": "renamed"}} if method == "patch" else {}
        response = await getattr(client, method)(
            f"/api/v1/channels/{owned_channel}", headers={HEADER: intruder}, **kwargs
        )
        assert response.status_code == 404, response.text

    async def test_channel_test_endpoint_is_404(self, client, intruder, owned_channel):
        """POST /channels/{id}/test dispatches for real — the one that would
        actually deliver through someone else's credential."""
        response = await client.post(
            f"/api/v1/channels/{owned_channel}/test", headers={HEADER: intruder}, json={}
        )
        assert response.status_code == 404, response.text


class TestTemplateIsolation:
    async def test_listing_shows_only_your_own(self, client, intruder, owned_template):
        response = await client.get("/api/v1/templates", headers={HEADER: intruder})
        assert response.status_code == 200
        assert [t["id"] for t in response.json()] == []

    @pytest.mark.parametrize("method", ["get", "patch", "delete"])
    async def test_direct_access_is_404(self, client, intruder, owned_template, method):
        kwargs = {"json": {"name": "renamed"}} if method == "patch" else {}
        response = await getattr(client, method)(
            f"/api/v1/templates/{owned_template}", headers={HEADER: intruder}, **kwargs
        )
        assert response.status_code == 404, response.text

    async def test_preview_is_404(self, client, intruder, owned_template):
        response = await client.post(
            f"/api/v1/templates/{owned_template}/preview",
            headers={HEADER: intruder},
            json={"variables": {"n": 1}},
        )
        assert response.status_code == 404, response.text


class TestDispatchIsolation:
    async def test_cannot_dispatch_through_a_foreign_channel(self, client, intruder, owned_channel):
        """The one that delivers: a foreign channel_id must not resolve."""
        response = await client.post(
            "/api/v1/dispatch",
            headers={HEADER: intruder},
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [owned_channel],
            },
        )
        assert response.status_code == 404, response.text

    async def test_cannot_render_a_foreign_template(
        self, client, intruder, owned_template, api_key, closed_port
    ):
        """A channel of the intruder's own, so only the template is foreign."""
        own = await client.post(
            "/api/v1/channels",
            headers={HEADER: intruder},
            json={"name": "mine", "apprise_url": f"json://127.0.0.1:{closed_port}/y"},
        )
        assert own.status_code == 201, own.text
        response = await client.post(
            "/api/v1/dispatch",
            headers={HEADER: intruder},
            json={
                "template_id": owned_template,
                "variables": {"n": 1},
                "channel_ids": [own.json()["id"]],
            },
        )
        assert response.status_code == 404, response.text

    async def test_cannot_read_a_foreign_dispatch_log(
        self, client, api_key, intruder, owned_channel
    ):
        raw_key, _ = api_key
        created = await client.post(
            "/api/v1/dispatch",
            headers={HEADER: raw_key},
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "channel_ids": [owned_channel],
            },
        )
        assert created.status_code == 202, created.text
        dispatch_id = created.json()["id"]

        mine = await client.get(f"/api/v1/dispatch/{dispatch_id}", headers={HEADER: raw_key})
        assert mine.status_code == 200

        theirs = await client.get(f"/api/v1/dispatch/{dispatch_id}", headers={HEADER: intruder})
        assert theirs.status_code == 404, theirs.text
