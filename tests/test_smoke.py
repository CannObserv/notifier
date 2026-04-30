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
