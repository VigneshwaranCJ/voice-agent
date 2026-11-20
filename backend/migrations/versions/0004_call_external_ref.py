"""call_sessions.external_ref (Sarvam Voice Agents interaction id)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20 13:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('call_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('external_ref', sa.String(length=200), nullable=True))
        batch_op.create_index(batch_op.f('ix_call_sessions_external_ref'), ['external_ref'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('call_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_call_sessions_external_ref'))
        batch_op.drop_column('external_ref')
