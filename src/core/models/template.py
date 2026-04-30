"""Template model — Jinja2 title/body pair with a JSON-Schema variable contract."""

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models.base import Base, TimestampMixin, ULIDType, generate_ulid


class Template(Base, TimestampMixin):
    """A reusable notification template owned by a Tenant.

    ``variables_schema`` is a JSON Schema (Draft 2020-12) describing the
    expected ``variables`` bag at dispatch time. ``sample_variables`` seeds
    the preview UI and is also used by ``POST /templates/{id}/preview`` when
    no explicit variables are supplied.
    """

    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_templates_tenant_name"),
    )

    id: Mapped[str] = mapped_column(ULIDType, primary_key=True, default=generate_ulid)
    tenant_id: Mapped[str] = mapped_column(
        ULIDType, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    title_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sample_variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
