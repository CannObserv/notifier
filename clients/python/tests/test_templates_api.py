import json

import httpx
import pytest
import respx

from notifier_client import (
    NotifierClient,
    RetryConfig,
    ServerError,
    TemplateOut,
    TemplatePreviewResponse,
    ValidationError,
)


@pytest.fixture
def fast_retry():
    return RetryConfig(max_attempts=2, backoff_base=0.0)


_TEMPLATE_BODY = {
    "id": "01HT", "tenant_id": "t1", "name": "alert",
    "title_template": "T", "body_template": "B",
    "variables_schema": None, "sample_variables": None, "tags": None,
    "created_at": "2026-04-30T00:00:00Z",
    "updated_at": "2026-04-30T00:00:00Z",
}

_PREVIEW_BODY = {"title": "T", "body": "B", "error": None, "error_section": None}


@respx.mock
@pytest.mark.asyncio
async def test_templates_list_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/templates").mock(
        return_value=httpx.Response(200, json=[_TEMPLATE_BODY, _TEMPLATE_BODY])
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.list()
    assert len(result) == 2
    assert isinstance(result[0], TemplateOut)


@respx.mock
@pytest.mark.asyncio
async def test_templates_create_sends_body_and_returns_typed(fast_retry):
    route = respx.post("https://t.local/api/v1/templates").mock(
        return_value=httpx.Response(201, json=_TEMPLATE_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.create(
            name="alert", title_template="T", body_template="B",
        )
    body = route.calls.last.request.read().decode()
    assert "alert" in body
    assert "title_template" in body
    assert isinstance(result, TemplateOut)


@respx.mock
@pytest.mark.asyncio
async def test_templates_get_returns_typed(fast_retry):
    respx.get("https://t.local/api/v1/templates/01HT").mock(
        return_value=httpx.Response(200, json=_TEMPLATE_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.get("01HT")
    assert isinstance(result, TemplateOut)
    assert result.id == "01HT"


@respx.mock
@pytest.mark.asyncio
async def test_templates_update_patches_and_returns_typed(fast_retry):
    route = respx.patch("https://t.local/api/v1/templates/01HT").mock(
        return_value=httpx.Response(200, json={**_TEMPLATE_BODY, "name": "renamed"})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.update("01HT", name="renamed")
    body = route.calls.last.request.read().decode()
    assert "renamed" in body
    assert "title_template" not in body  # only supplied fields are sent
    assert isinstance(result, TemplateOut)
    assert result.name == "renamed"


@respx.mock
@pytest.mark.asyncio
async def test_templates_delete_returns_none(fast_retry):
    respx.delete("https://t.local/api/v1/templates/01HT").mock(
        return_value=httpx.Response(204)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.delete("01HT")
    assert result is None


@respx.mock
@pytest.mark.asyncio
async def test_templates_delete_not_auto_retried_on_5xx(fast_retry):
    route = respx.delete("https://t.local/api/v1/templates/01HT").mock(
        return_value=httpx.Response(503),
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ServerError):
            await c.templates.delete("01HT")
    # Single attempt — DELETE is not auto-retried.
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_templates_preview_with_variables(fast_retry):
    route = respx.post("https://t.local/api/v1/templates/01HT/preview").mock(
        return_value=httpx.Response(200, json=_PREVIEW_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.preview("01HT", variables={"who": "world"})
    sent = json.loads(route.calls.last.request.content.decode())
    assert sent.get("variables") == {"who": "world"}
    assert isinstance(result, TemplatePreviewResponse)
    assert result.title == "T"
    assert result.body == "B"


@respx.mock
@pytest.mark.asyncio
async def test_templates_preview_without_variables_uses_sample(fast_retry):
    route = respx.post("https://t.local/api/v1/templates/01HT/preview").mock(
        return_value=httpx.Response(200, json=_PREVIEW_BODY)
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        result = await c.templates.preview("01HT")
    sent = json.loads(route.calls.last.request.content.decode())
    assert "variables" not in sent
    assert isinstance(result, TemplatePreviewResponse)
    assert result.title == "T"


@respx.mock
@pytest.mark.asyncio
async def test_templates_create_validation_error(fast_retry):
    respx.post("https://t.local/api/v1/templates").mock(
        return_value=httpx.Response(422, json={"detail": [
            {"loc": ["body", "title_template"], "msg": "field required", "type": "missing"}
        ]})
    )
    async with NotifierClient(
        base_url="https://t.local", api_key="nk_x", retry_config=fast_retry
    ) as c:
        with pytest.raises(ValidationError) as exc:
            await c.templates.create(name="alert", title_template="", body_template="B")
    assert exc.value.field_path == "body.title_template"
