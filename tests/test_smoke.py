"""Smoke tests — exercise the v0 API surface end-to-end against a real DB."""


async def test_health_endpoint(client):
    """/health returns ok without authentication."""
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


async def test_ready_endpoint(client):
    """/ready returns 200 when the DB is reachable."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["db"] is True


async def test_v1_requires_api_key(client):
    """Hitting a v1 route without X-API-Key returns 403."""
    response = await client.get("/api/v1/templates")
    assert response.status_code == 403


async def test_v1_invalid_api_key(client):
    """A non-matching key returns 401."""
    response = await client.get("/api/v1/templates", headers={"X-API-Key": "nk_unknown"})
    assert response.status_code == 401


async def test_apprise_plugins_list_authenticated(client, api_key):
    """Authenticated /apprise/plugins returns a sorted list of plugin items."""
    raw_key, _ = api_key
    response = await client.get("/api/v1/apprise/plugins", headers={"X-API-Key": raw_key})
    assert response.status_code == 200
    plugins = response.json()
    assert len(plugins) > 0
    assert all("plugin_schema" in p and "service_name" in p for p in plugins)
    names = [p["service_name"].lower() for p in plugins]
    assert names == sorted(names)


async def test_template_crud_and_preview(client, api_key):
    """Create → fetch → preview → delete a template."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    create_payload = {
        "name": "smoke-test-template",
        "title_template": "Hello {{ name }}",
        "body_template": "Body for {{ name }}: {{ message }}",
        "variables_schema": {
            "type": "object",
            "required": ["name", "message"],
            "properties": {"name": {"type": "string"}, "message": {"type": "string"}},
        },
        "sample_variables": {"name": "World", "message": "smoke test"},
        "tags": ["smoke"],
    }
    response = await client.post("/api/v1/templates", headers=headers, json=create_payload)
    assert response.status_code == 201, response.text
    template = response.json()
    template_id = template["id"]

    response = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["name"] == "smoke-test-template"

    # Preview with sample variables (omits explicit variables in body)
    response = await client.post(
        f"/api/v1/templates/{template_id}/preview", headers=headers, json={}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is None
    assert body["title"] == "Hello World"
    assert "smoke test" in body["body"]

    # Preview with bad variables — schema rejects missing 'message'
    response = await client.post(
        f"/api/v1/templates/{template_id}/preview",
        headers=headers,
        json={"variables": {"name": "X"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error_section"] == "variables"
    assert body["title"] is None

    response = await client.delete(f"/api/v1/templates/{template_id}", headers=headers)
    assert response.status_code == 204


async def test_channel_create_round_trips_masked_url(client, api_key):
    """Channel URL is encrypted at rest and returned masked on read."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    response = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": "smoke-channel", "apprise_url": "json://example.com/path"},
    )
    assert response.status_code == 201, response.text
    channel = response.json()
    assert channel["apprise_url_masked"] == "json://***"

    response = await client.get(f"/api/v1/channels/{channel['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json()["apprise_url_masked"] == "json://***"


async def test_preview_endpoint_renders_inline(client, api_key):
    """/preview renders inline templates statelessly."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    response = await client.post(
        "/api/v1/preview",
        headers=headers,
        json={
            "title_template": "{{ subject }}",
            "body_template": "Hi {{ name }}",
            "variables": {"subject": "T", "name": "N"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["title"] == "T"
    assert body["body"] == "Hi N"


async def test_preview_endpoint_reports_undefined(client, api_key):
    """StrictUndefined surfaces as a body-section render error."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    response = await client.post(
        "/api/v1/preview",
        headers=headers,
        json={
            "title_template": "ok",
            "body_template": "Hi {{ unknown }}",
            "variables": {},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error_section"] == "body"
    assert body["title"] is None


async def test_dispatch_malformed_channel_id_returns_422(client, api_key):
    """Malformed (non-ULID) channel_id in body produces 422 with field path."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}
    response = await client.post(
        "/api/v1/dispatch",
        headers=headers,
        json={
            "title_template": "hello",
            "body_template": "body",
            "variables": {},
            "channel_ids": ["not-a-valid-ulid"],
        },
    )
    assert response.status_code == 422
    locs = [str(e.get("loc", [])) for e in response.json()["detail"]]
    assert any("channel_ids" in loc for loc in locs)


async def test_dispatch_malformed_template_id_returns_422(client, api_key):
    """Malformed (non-ULID) template_id in body produces 422 with field path."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}
    response = await client.post(
        "/api/v1/dispatch",
        headers=headers,
        json={
            "template_id": "550e8400-e29b-41d4-a716-446655440000",
            "variables": {},
            "channel_ids": ["00000000000000000000000000"],
        },
    )
    assert response.status_code == 422
    locs = [str(e.get("loc", [])) for e in response.json()["detail"]]
    assert any("template_id" in loc for loc in locs)


async def test_channel_malformed_path_param_returns_422(client, api_key):
    """Any verb on /channels/<bad-id> returns 422 — ULIDStr covers GET/PATCH/DELETE/test."""
    raw_key, _ = api_key
    response = await client.get(
        "/api/v1/channels/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_template_malformed_path_param_returns_422(client, api_key):
    """Any verb on /templates/<bad-id> returns 422 — ULIDStr covers GET/PATCH/DELETE/preview."""
    raw_key, _ = api_key
    response = await client.get(
        "/api/v1/templates/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_dispatch_log_malformed_path_param_returns_422(client, api_key):
    """GET /dispatch/<bad-id> returns 422 — ULIDStr annotation on dispatch_id path param."""
    raw_key, _ = api_key
    response = await client.get(
        "/api/v1/dispatch/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_channel_malformed_patch_param_returns_422(client, api_key):
    """PATCH /channels/<bad-id> returns 422 — ULIDStr annotation shared across all verbs."""
    raw_key, _ = api_key
    response = await client.patch(
        "/api/v1/channels/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
        json={"name": "x"},
    )
    assert response.status_code == 422


async def test_channel_malformed_delete_param_returns_422(client, api_key):
    """DELETE /channels/<bad-id> returns 422 — ULIDStr annotation shared across all verbs."""
    raw_key, _ = api_key
    response = await client.delete(
        "/api/v1/channels/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_template_malformed_patch_param_returns_422(client, api_key):
    """PATCH /templates/<bad-id> returns 422 — ULIDStr annotation shared across all verbs."""
    raw_key, _ = api_key
    response = await client.patch(
        "/api/v1/templates/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
        json={"name": "x"},
    )
    assert response.status_code == 422


async def test_template_malformed_delete_param_returns_422(client, api_key):
    """DELETE /templates/<bad-id> returns 422 — ULIDStr annotation shared across all verbs."""
    raw_key, _ = api_key
    response = await client.delete(
        "/api/v1/templates/not-a-valid-ulid",
        headers={"X-API-Key": raw_key},
    )
    assert response.status_code == 422


async def test_inline_dispatch_with_auto_idempotency(client, api_key):
    """Second inline dispatch with the same idempotency_key replays the original."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    ch = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": "idem-channel", "apprise_url": "json://example.com"},
    )
    assert ch.status_code == 201
    channel_id = ch.json()["id"]

    payload = {
        "title_template": "Hello {{ name }}",
        "body_template": "Body for {{ name }}",
        "variables": {"name": "World"},
        "channel_ids": [channel_id],
        "idempotency_key": "smoke-idem-001",
    }

    r1 = await client.post("/api/v1/dispatch", headers=headers, json=payload)
    assert r1.status_code == 202
    d1 = r1.json()

    r2 = await client.post("/api/v1/dispatch", headers=headers, json=payload)
    assert r2.status_code == 202
    d2 = r2.json()

    assert d2["id"] == d1["id"]
    assert d2["created_at"] == d1["created_at"]
    assert d2["rendered_title"] == "Hello World"
    assert d2["rendered_body"] == "Body for World"
    assert d2["attempts"] == d1["attempts"]


async def test_delete_channel_with_dispatch_attempts_returns_409(client, api_key):
    """DELETE a channel that has dispatch attempts must return 409, not 500."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    ch = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": "busy-channel", "apprise_url": "json://example.com"},
    )
    assert ch.status_code == 201
    channel_id = ch.json()["id"]

    dispatch_response = await client.post(
        "/api/v1/dispatch",
        headers=headers,
        json={
            "title_template": "t",
            "body_template": "b",
            "variables": {},
            "channel_ids": [channel_id],
        },
    )
    assert dispatch_response.status_code == 202, dispatch_response.text

    response = await client.delete(f"/api/v1/channels/{channel_id}", headers=headers)
    assert response.status_code == 409
    assert "dispatch" in response.json()["detail"].lower()


async def test_delete_channel_without_attempts_returns_204(client, api_key):
    """DELETE a channel with no dispatch attempts still returns 204."""
    raw_key, _ = api_key
    headers = {"X-API-Key": raw_key}

    ch = await client.post(
        "/api/v1/channels",
        headers=headers,
        json={"name": "idle-channel", "apprise_url": "json://example.com"},
    )
    assert ch.status_code == 201
    channel_id = ch.json()["id"]

    response = await client.delete(f"/api/v1/channels/{channel_id}", headers=headers)
    assert response.status_code == 204
