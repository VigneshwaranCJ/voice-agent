"""drop voice profiles (voice now runs on hosted Sarvam Voice Agents)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-20 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Dropping the column also drops its foreign key to voice_profiles (PostgreSQL; SQLite rebuilds the table).
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.drop_column('voice_profile_id')
    with op.batch_alter_table('voice_profiles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_voice_profiles_tenant_id'))
    op.drop_table('voice_profiles')


def downgrade() -> None:
    op.create_table('voice_profiles',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('tts_model', sa.String(length=40), nullable=False),
    sa.Column('speakers', sa.JSON(), nullable=False),
    sa.Column('pace', sa.Float(), nullable=False),
    sa.Column('temperature', sa.Float(), nullable=False),
    sa.Column('sample_rate', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('voice_profiles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_voice_profiles_tenant_id'), ['tenant_id'], unique=False)
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('voice_profile_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_agents_voice_profile_id', 'voice_profiles', ['voice_profile_id'], ['id'],
                                    ondelete='SET NULL')
