"""sarvam agent links

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20 11:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('sarvam_agent_links',
    sa.Column('agent_id', sa.String(length=36), nullable=False),
    sa.Column('org_id', sa.String(length=100), nullable=False),
    sa.Column('workspace_id', sa.String(length=100), nullable=False),
    sa.Column('app_id', sa.String(length=100), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('tool_token_hash', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('agent_id'),
    )
    with op.batch_alter_table('sarvam_agent_links', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sarvam_agent_links_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sarvam_agent_links_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_sarvam_agent_links_tool_token_hash'), ['tool_token_hash'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('sarvam_agent_links', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sarvam_agent_links_tool_token_hash'))
        batch_op.drop_index(batch_op.f('ix_sarvam_agent_links_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_sarvam_agent_links_agent_id'))
    op.drop_table('sarvam_agent_links')
