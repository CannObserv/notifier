from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.auth_error_detail import AuthErrorDetail
from ...models.checkin_request import CheckinRequest
from ...models.checkin_response import CheckinResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    monitor_id: str,
    *,
    body: CheckinRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/monitors/{monitor_id}/checkin".format(
            monitor_id=quote(str(monitor_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AuthErrorDetail | CheckinResponse | HTTPValidationError | None:
    if response.status_code == 202:
        response_202 = CheckinResponse.from_dict(response.json())

        return response_202

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
) -> Response[AuthErrorDetail | CheckinResponse | HTTPValidationError]:
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
    body: CheckinRequest,
) -> Response[AuthErrorDetail | CheckinResponse | HTTPValidationError]:
    """Checkin

     Record a check-in, and dispatch anything it warrants.

    Send one every tick whether or not there is anything to report. Zero
    findings and zero traffic is what a dead probe looks like too, so the
    report's *arrival* is the part notifier cannot infer.

    Args:
        monitor_id (str):
        body (CheckinRequest): Request body for POST /monitors/{id}/checkin.

            Send one **every tick, regardless of findings** — the arrival is the
            signal. ``status`` is the consumer's own judgement about the contents:
            ``alert`` renders and dispatches the monitor's template, ``ok`` records
            the check-in and sends nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | CheckinResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        monitor_id=monitor_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
    body: CheckinRequest,
) -> AuthErrorDetail | CheckinResponse | HTTPValidationError | None:
    """Checkin

     Record a check-in, and dispatch anything it warrants.

    Send one every tick whether or not there is anything to report. Zero
    findings and zero traffic is what a dead probe looks like too, so the
    report's *arrival* is the part notifier cannot infer.

    Args:
        monitor_id (str):
        body (CheckinRequest): Request body for POST /monitors/{id}/checkin.

            Send one **every tick, regardless of findings** — the arrival is the
            signal. ``status`` is the consumer's own judgement about the contents:
            ``alert`` renders and dispatches the monitor's template, ``ok`` records
            the check-in and sends nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | CheckinResponse | HTTPValidationError
    """

    return sync_detailed(
        monitor_id=monitor_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
    body: CheckinRequest,
) -> Response[AuthErrorDetail | CheckinResponse | HTTPValidationError]:
    """Checkin

     Record a check-in, and dispatch anything it warrants.

    Send one every tick whether or not there is anything to report. Zero
    findings and zero traffic is what a dead probe looks like too, so the
    report's *arrival* is the part notifier cannot infer.

    Args:
        monitor_id (str):
        body (CheckinRequest): Request body for POST /monitors/{id}/checkin.

            Send one **every tick, regardless of findings** — the arrival is the
            signal. ``status`` is the consumer's own judgement about the contents:
            ``alert`` renders and dispatches the monitor's template, ``ok`` records
            the check-in and sends nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AuthErrorDetail | CheckinResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        monitor_id=monitor_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    monitor_id: str,
    *,
    client: AuthenticatedClient,
    body: CheckinRequest,
) -> AuthErrorDetail | CheckinResponse | HTTPValidationError | None:
    """Checkin

     Record a check-in, and dispatch anything it warrants.

    Send one every tick whether or not there is anything to report. Zero
    findings and zero traffic is what a dead probe looks like too, so the
    report's *arrival* is the part notifier cannot infer.

    Args:
        monitor_id (str):
        body (CheckinRequest): Request body for POST /monitors/{id}/checkin.

            Send one **every tick, regardless of findings** — the arrival is the
            signal. ``status`` is the consumer's own judgement about the contents:
            ``alert`` renders and dispatches the monitor's template, ``ok`` records
            the check-in and sends nothing.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AuthErrorDetail | CheckinResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            monitor_id=monitor_id,
            client=client,
            body=body,
        )
    ).parsed
