"""conversation_analyses (post-call analyst agent: sentiment, outcome, follow-ups)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversation_analyses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('conversation_id', sa.String(length=36), nullable=False),
        sa.Column('agent_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('sentiment', sa.String(length=20), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('sentiment_trend', sa.String(length=20), nullable=True),
        sa.Column('emotions', sa.JSON(), nullable=False),
        sa.Column('outcome', sa.String(length=30), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('topics', sa.JSON(), nullable=False),
        sa.Column('key_quotes', sa.JSON(), nullable=False),
        sa.Column('follow_ups', sa.JSON(), nullable=False),
        sa.Column('needs_human', sa.Boolean(), nullable=False),
        sa.Column('agent_issues', sa.JSON(), nullable=False),
        sa.Column('checks', sa.JSON(), nullable=False),
        sa.Column('escalation_id', sa.String(length=36), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=80), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('conversation_analyses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversation_analyses_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversation_analyses_conversation_id'), ['conversation_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_conversation_analyses_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversation_analyses_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversation_analyses_sentiment'), ['sentiment'], unique=False)


def downgrade() -> None:
    op.drop_table('conversation_analyses')
