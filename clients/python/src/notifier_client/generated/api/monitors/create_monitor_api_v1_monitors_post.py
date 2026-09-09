from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_error_detail import AuthErrorDetail
from ...models.http_validation_error import HTTPValidationError
from ...models.monitor_create import MonitorCreate
from ...models.monitor_out import MonitorOut
from ...types import Response


def _get_kwargs(
    *,
    body: MonitorCreate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/monitors",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    if response.status_code == 201:
        response_201 = MonitorOut.from_dict(response.json())

        return response_201

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
    *,
    client: AuthenticatedClient,
    body: MonitorCreate,
) -> Response[AuthErrorDetail | HTTPValidationError | MonitorOut]:
    """Create Monitor

     Create a monitor. It starts ``pending`` and its clock starts now.

    The deadline is anchored on creation until the first check-in arrives, so
    a probe that is configured here but never wired up on the consumer's side
    alerts rather than sitting silent.

    Args:
        body (MonitorCreate): Request body for POST /monitors.

            ``interval_seconds`` is the cadence the consumer promises; a check-in is
            only late once ``grace_seconds`` on top of it has also passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | HTTPValidationError | MonitorOut]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: MonitorCreate,
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    """Create Monitor

     Create a monitor. It starts ``pending`` and its clock starts now.

    The deadline is anchored on creation until the first check-in arrives, so
    a probe that is configured here but never wired up on the consumer's side
    alerts rather than sitting silent.

    Args:
        body (MonitorCreate): Request body for POST /monitors.

            ``interval_seconds`` is the cadence the consumer promises; a check-in is
            only late once ``grace_seconds`` on top of it has also passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | HTTPValidationError | MonitorOut
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: MonitorCreate,
) -> Response[AuthErrorDetail | HTTPValidationError | MonitorOut]:
    """Create Monitor

     Create a monitor. It starts ``pending`` and its clock starts now.

    The deadline is anchored on creation until the first check-in arrives, so
    a probe that is configured here but never wired up on the consumer's side
    alerts rather than sitting silent.

    Args:
        body (MonitorCreate): Request body for POST /monitors.

            ``interval_seconds`` is the cadence the consumer promises; a check-in is
            only late once ``grace_seconds`` on top of it has also passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | HTTPValidationError | MonitorOut]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: MonitorCreate,
) -> AuthErrorDetail | HTTPValidationError | MonitorOut | None:
    """Create Monitor

     Create a monitor. It starts ``pending`` and its clock starts now.

    The deadline is anchored on creation until the first check-in arrives, so
    a probe that is configured here but never wired up on the consumer's side
    alerts rather than sitting silent.

    Args:
        body (MonitorCreate): Request body for POST /monitors.

            ``interval_seconds`` is the cadence the consumer promises; a check-in is
            only late once ``grace_seconds`` on top of it has also passed.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | HTTPValidationError | MonitorOut
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
