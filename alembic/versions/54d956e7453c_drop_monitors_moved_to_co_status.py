"""drop monitors: the dead-man's timers moved to co-status

Notifier publishes; it does not originate alerts. Monitors were the one
exception, and CannObserv/status took all three over on 2026-09-28 (#83).
Notifier's copies were disabled at the handover and soaked until 2026-10-02.
The rows were archived first to /var/backups/notifier/ on the production VM.

The downgrade recreates the table exactly as 69c6ef344536 made it, empty.

Revision ID: 54d956e7453c
Revises: 69c6ef344536
Create Date: 2026-10-02 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '54d956e7453c'
down_revision: Union[str, Sequence[str], None] = '69c6ef344536'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_monitors_enabled', table_name='monitors')
    op.drop_table('monitors')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('monitors',
    sa.Column('id', sa.String(length=26), nullable=False),
    sa.Column('tenant_id', sa.String(length=26), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('interval_seconds', sa.Integer(), nullable=False),
    sa.Column('grace_seconds', sa.Integer(), server_default='0', nullable=False),
    sa.Column('renotify_seconds', sa.Integer(), nullable=True),
    sa.Column('channel_ids', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
    sa.Column('template_id', sa.String(length=26), nullable=True),
    sa.Column('title_template', sa.Text(), nullable=True),
    sa.Column('body_template', sa.Text(), nullable=True),
    sa.Column('state', sa.String(), server_default='pending', nullable=False),
    sa.Column('last_checkin_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_status', sa.String(), nullable=True),
    sa.Column('last_variables', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('last_alert_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("state IN ('pending', 'ok', 'missing')", name='ck_monitors_state'),
    sa.CheckConstraint('grace_seconds >= 0', name='ck_monitors_grace_non_negative'),
    sa.CheckConstraint('interval_seconds > 0', name='ck_monitors_interval_positive'),
    sa.CheckConstraint('renotify_seconds IS NULL OR renotify_seconds > 0', name='ck_monitors_renotify_positive'),
    sa.ForeignKeyConstraint(['template_id'], ['templates.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'name', name='uq_monitors_tenant_name')
    )
    op.create_index('ix_monitors_enabled', 'monitors', ['enabled'], unique=False)
