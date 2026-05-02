"""Unit tests for FastAPI dependencies."""

from unittest.mock import AsyncMock, MagicMock

from ulid import ULID

from src.api.deps import require_api_key


async def test_require_api_key_returns_str_tenant_id():
    """require_api_key returns str, not ULID — guards against the str() cast being removed."""
    ulid_obj = ULID.from_str("01H5K3G8V4HCQ2DXFE5FJNWQER")
    mock_api_key = MagicMock()
    mock_api_key.tenant_id = ulid_obj

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_api_key

    session = AsyncMock()
    session.execute.return_value = mock_result

    tenant_id = await require_api_key(raw_key="any-key", session=session)

    assert isinstance(tenant_id, str)
    assert tenant_id == "01H5K3G8V4HCQ2DXFE5FJNWQER"
