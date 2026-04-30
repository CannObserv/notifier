from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.channel_test_response import ChannelTestResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    channel_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/channels/{channel_id}/test".format(
            channel_id=quote(str(channel_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ChannelTestResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChannelTestResponse.from_dict(response.json())

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
) -> Response[ChannelTestResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    channel_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[ChannelTestResponse | HTTPValidationError]:
    """Test Channel

     Fire a test notification to a channel. Useful for connection diagnosis.

    Args:
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelTestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        channel_id=channel_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    channel_id: str,
    *,
    client: AuthenticatedClient,
) -> ChannelTestResponse | HTTPValidationError | None:
    """Test Channel

     Fire a test notification to a channel. Useful for connection diagnosis.

    Args:
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelTestResponse | HTTPValidationError
    """

    return sync_detailed(
        channel_id=channel_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    channel_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[ChannelTestResponse | HTTPValidationError]:
    """Test Channel

     Fire a test notification to a channel. Useful for connection diagnosis.

    Args:
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChannelTestResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        channel_id=channel_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    channel_id: str,
    *,
    client: AuthenticatedClient,
) -> ChannelTestResponse | HTTPValidationError | None:
    """Test Channel

     Fire a test notification to a channel. Useful for connection diagnosis.

    Args:
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChannelTestResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            channel_id=channel_id,
            client=client,
        )
    ).parsed
