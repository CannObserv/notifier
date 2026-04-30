from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.template_preview_request import TemplatePreviewRequest
from ...models.template_preview_response import TemplatePreviewResponse
from ...types import Response


def _get_kwargs(
    template_id: str,
    *,
    body: TemplatePreviewRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/templates/{template_id}/preview".format(
            template_id=quote(str(template_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TemplatePreviewResponse | None:
    if response.status_code == 200:
        response_200 = TemplatePreviewResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | TemplatePreviewResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: TemplatePreviewRequest,
) -> Response[HTTPValidationError | TemplatePreviewResponse]:
    """Preview Template

     Render a template against supplied or sample variables; never dispatches.

    Args:
        template_id (str):
        body (TemplatePreviewRequest): Request body for POST /templates/{id}/preview.

            If ``variables`` is omitted, the template's stored ``sample_variables``
            are used (handy for "preview as it would look out of the box").

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplatePreviewResponse]
    """

    kwargs = _get_kwargs(
        template_id=template_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: TemplatePreviewRequest,
) -> HTTPValidationError | TemplatePreviewResponse | None:
    """Preview Template

     Render a template against supplied or sample variables; never dispatches.

    Args:
        template_id (str):
        body (TemplatePreviewRequest): Request body for POST /templates/{id}/preview.

            If ``variables`` is omitted, the template's stored ``sample_variables``
            are used (handy for "preview as it would look out of the box").

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplatePreviewResponse
    """

    return sync_detailed(
        template_id=template_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: TemplatePreviewRequest,
) -> Response[HTTPValidationError | TemplatePreviewResponse]:
    """Preview Template

     Render a template against supplied or sample variables; never dispatches.

    Args:
        template_id (str):
        body (TemplatePreviewRequest): Request body for POST /templates/{id}/preview.

            If ``variables`` is omitted, the template's stored ``sample_variables``
            are used (handy for "preview as it would look out of the box").

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplatePreviewResponse]
    """

    kwargs = _get_kwargs(
        template_id=template_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: TemplatePreviewRequest,
) -> HTTPValidationError | TemplatePreviewResponse | None:
    """Preview Template

     Render a template against supplied or sample variables; never dispatches.

    Args:
        template_id (str):
        body (TemplatePreviewRequest): Request body for POST /templates/{id}/preview.

            If ``variables`` is omitted, the template's stored ``sample_variables``
            are used (handy for "preview as it would look out of the box").

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplatePreviewResponse
    """

    return (
        await asyncio_detailed(
            template_id=template_id,
            client=client,
            body=body,
        )
    ).parsed
