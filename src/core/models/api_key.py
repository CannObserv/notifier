"""ApiKey model — hashed API credentials owned by a Tenant."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, ULIDType, generate_ulid


class ApiKey(Base):
    """Stores a SHA-256 hash of each API key; raw key is never persisted."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    tenant_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
