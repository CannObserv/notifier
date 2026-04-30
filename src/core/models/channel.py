"""Channel model — an Apprise destination owned by a Tenant."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, TimestampMixin, ULIDType, generate_ulid


class Channel(Base, TimestampMixin):
    """A configured Apprise destination. The URL is encrypted at rest with Fernet."""

    __tablename__ = "channels"

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    tenant_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    apprise_url_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    channel_hint: Mapped[str | None] = mapped_column(String, nullable=True)
