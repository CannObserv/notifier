from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_error_detail import AuthErrorDetail
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    monitor_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/monitors/{monitor_id}".format(
            monitor_id=quote(str(monitor_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | AuthErrorDetail | HTTPValidationError | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

    if response.status_code == 401:
        response_401 = AuthErrorDetail.from_dict(response.json())

        return response_401

    if response.status_code == 403:
        response_403 = AuthErrorDetail.from_dict(response.json())

        return response_403

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | AuthErrorDetail | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[Any | AuthErrorDetail | HTTPValidationError]:
    """Delete Monitor

     Delete a monitor. Its past dispatches are kept.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | AuthErrorDetail | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        monitor_id=monitor_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
) -> Any | AuthErrorDetail | HTTPValidationError | None:
    """Delete Monitor

     Delete a monitor. Its past dispatches are kept.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | AuthErrorDetail | HTTPValidationError
    """

    return sync_detailed(
        monitor_id=monitor_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[Any | AuthErrorDetail | HTTPValidationError]:
    """Delete Monitor

     Delete a monitor. Its past dispatches are kept.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | AuthErrorDetail | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        monitor_id=monitor_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
) -> Any | AuthErrorDetail | HTTPValidationError | None:
    """Delete Monitor

     Delete a monitor. Its past dispatches are kept.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | AuthErrorDetail | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            monitor_id=monitor_id,
            client=client,
        )
    ).parsed
