"""drop call_events (only the removed in-house voice session wrote them)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20 14:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('call_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_call_events_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_call_events_call_session_id'))
    op.drop_table('call_events')


def downgrade() -> None:
    op.create_table('call_events',
    sa.Column('call_session_id', sa.String(length=36), nullable=False),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['call_session_id'], ['call_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('call_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_call_events_call_session_id'), ['call_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_call_events_tenant_id'), ['tenant_id'], unique=False)
