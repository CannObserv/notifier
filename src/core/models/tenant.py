"""Tenant model — top-level isolation boundary for the notifications service."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, TimestampMixin, ULIDType, generate_ulid


class Tenant(Base, TimestampMixin):
    """A tenant owns its own templates, channels, and dispatch logs."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
