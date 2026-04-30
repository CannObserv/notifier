from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.assemble_request import AssembleRequest
from ...models.assemble_response import AssembleResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    schema: str,
    *,
    body: AssembleRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/apprise/plugins/{schema}/assemble".format(
            schema=quote(str(schema), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AssembleResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AssembleResponse.from_dict(response.json())

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
) -> Response[AssembleResponse | HTTPValidationError]:
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
    body: AssembleRequest,
) -> Response[AssembleResponse | HTTPValidationError]:
    """Assemble Apprise Url

     Assemble a candidate Apprise URL from a token bag without persisting it.

    Args:
        schema (str):
        body (AssembleRequest): POST /apprise/plugins/{schema}/assemble — token bag + variant
            index.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AssembleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        schema=schema,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    schema: str,
    *,
    client: AuthenticatedClient,
    body: AssembleRequest,
) -> AssembleResponse | HTTPValidationError | None:
    """Assemble Apprise Url

     Assemble a candidate Apprise URL from a token bag without persisting it.

    Args:
        schema (str):
        body (AssembleRequest): POST /apprise/plugins/{schema}/assemble — token bag + variant
            index.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AssembleResponse | HTTPValidationError
    """

    return sync_detailed(
        schema=schema,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    schema: str,
    *,
    client: AuthenticatedClient,
    body: AssembleRequest,
) -> Response[AssembleResponse | HTTPValidationError]:
    """Assemble Apprise Url

     Assemble a candidate Apprise URL from a token bag without persisting it.

    Args:
        schema (str):
        body (AssembleRequest): POST /apprise/plugins/{schema}/assemble — token bag + variant
            index.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AssembleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        schema=schema,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    schema: str,
    *,
    client: AuthenticatedClient,
    body: AssembleRequest,
) -> AssembleResponse | HTTPValidationError | None:
    """Assemble Apprise Url

     Assemble a candidate Apprise URL from a token bag without persisting it.

    Args:
        schema (str):
        body (AssembleRequest): POST /apprise/plugins/{schema}/assemble — token bag + variant
            index.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AssembleResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            schema=schema,
            client=client,
            body=body,
        )
    ).parsed
