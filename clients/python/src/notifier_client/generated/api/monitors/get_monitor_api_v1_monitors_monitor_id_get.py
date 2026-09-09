from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_error_detail import AuthErrorDetail
from ...models.http_validation_error import HTTPValidationError
from ...models.monitor_out import MonitorOut
from ...types import Response


def _get_kwargs(
    monitor_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/monitors/{monitor_id}".format(
            monitor_id=quote(str(monitor_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    if response.status_code == 200:
        response_200 = MonitorOut.from_dict(response.json())

        return response_200

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
) -> Response[AuthErrorDetail | HTTPValidationError | MonitorOut]:
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
) -> Response[AuthErrorDetail | HTTPValidationError | MonitorOut]:
    """Get Monitor

     Fetch a single monitor, including its last report and next deadline.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | HTTPValidationError | MonitorOut]
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
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    """Get Monitor

     Fetch a single monitor, including its last report and next deadline.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | HTTPValidationError | MonitorOut
    """

    return sync_detailed(
        monitor_id=monitor_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[AuthErrorDetail | HTTPValidationError | MonitorOut]:
    """Get Monitor

     Fetch a single monitor, including its last report and next deadline.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | HTTPValidationError | MonitorOut]
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
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    """Get Monitor

     Fetch a single monitor, including its last report and next deadline.

    Args:
        monitor_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | HTTPValidationError | MonitorOut
    """

    return (
        await asyncio_detailed(
            monitor_id=monitor_id,
            client=client,
        )
    ).parsed
