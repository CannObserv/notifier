from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.health_response import HealthResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HealthResponse | None:
    if response.status_code == 200:
        response_200 = HealthResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HealthResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[HealthResponse]:
    """Health

     Liveness probe — confirms the app process is running. No DB call.

    Unauthenticated, so a consumer can establish which deployment it is
    talking to before it has a key that works. ``build`` cannot answer that:
    both endpoints serve one working tree, so the commit agrees on either.

    ``database`` and ``environment`` are read from the configured URL, which
    is what keeps this a no-DB probe; ``/ready`` reports the database actually
    connected. Why it is safe for this to be unauthenticated:
    docs/DEPLOYMENT.md § Health checks.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> HealthResponse | None:
    """Health

     Liveness probe — confirms the app process is running. No DB call.

    Unauthenticated, so a consumer can establish which deployment it is
    talking to before it has a key that works. ``build`` cannot answer that:
    both endpoints serve one working tree, so the commit agrees on either.

    ``database`` and ``environment`` are read from the configured URL, which
    is what keeps this a no-DB probe; ``/ready`` reports the database actually
    connected. Why it is safe for this to be unauthenticated:
    docs/DEPLOYMENT.md § Health checks.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[HealthResponse]:
    """Health

     Liveness probe — confirms the app process is running. No DB call.

    Unauthenticated, so a consumer can establish which deployment it is
    talking to before it has a key that works. ``build`` cannot answer that:
    both endpoints serve one working tree, so the commit agrees on either.

    ``database`` and ``environment`` are read from the configured URL, which
    is what keeps this a no-DB probe; ``/ready`` reports the database actually
    connected. Why it is safe for this to be unauthenticated:
    docs/DEPLOYMENT.md § Health checks.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HealthResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> HealthResponse | None:
    """Health

     Liveness probe — confirms the app process is running. No DB call.

    Unauthenticated, so a consumer can establish which deployment it is
    talking to before it has a key that works. ``build`` cannot answer that:
    both endpoints serve one working tree, so the commit agrees on either.

    ``database`` and ``environment`` are read from the configured URL, which
    is what keeps this a no-DB probe; ``/ready`` reports the database actually
    connected. Why it is safe for this to be unauthenticated:
    docs/DEPLOYMENT.md § Health checks.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HealthResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
