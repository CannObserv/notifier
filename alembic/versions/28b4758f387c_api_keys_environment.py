"""api_keys.environment — mark which deployment a key is meant for.

Production refuses keys marked 'development'; see src/api/deps.py and
issue #22. Existing keys default to 'production', which is what they are.

Revision ID: 28b4758f387c
Revises: 24cb1d802502
Create Date: 2026-08-25 00:05:44.947080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28b4758f387c'
down_revision: Union[str, Sequence[str], None] = '24cb1d802502'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "api_keys",
        sa.Column(
            "environment",
            sa.String(),
            server_default="production",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_api_keys_environment",
        "api_keys",
        "environment IN ('production', 'development')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_api_keys_environment", "api_keys", type_="check")
    op.drop_column("api_keys", "environment")
