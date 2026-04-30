from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.plugin_detail import PluginDetail
from ...types import Response


def _get_kwargs(
    schema: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/apprise/plugins/{schema}".format(
            schema=quote(str(schema), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PluginDetail | None:
    if response.status_code == 200:
        response_200 = PluginDetail.from_dict(response.json())

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
) -> Response[HTTPValidationError | PluginDetail]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    schema: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | PluginDetail]:
    """Get Apprise Plugin

     Return token definitions and variant info for an Apprise plugin.

    Args:
        schema (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PluginDetail]
    """

    kwargs = _get_kwargs(
        schema=schema,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    schema: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | PluginDetail | None:
    """Get Apprise Plugin

     Return token definitions and variant info for an Apprise plugin.

    Args:
        schema (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PluginDetail
    """

    return sync_detailed(
        schema=schema,
        client=client,
    ).parsed


async def asyncio_detailed(
    schema: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | PluginDetail]:
    """Get Apprise Plugin

     Return token definitions and variant info for an Apprise plugin.

    Args:
        schema (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PluginDetail]
    """

    kwargs = _get_kwargs(
        schema=schema,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    schema: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | PluginDetail | None:
    """Get Apprise Plugin

     Return token definitions and variant info for an Apprise plugin.

    Args:
        schema (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PluginDetail
    """

    return (
        await asyncio_detailed(
            schema=schema,
            client=client,
        )
    ).parsed
