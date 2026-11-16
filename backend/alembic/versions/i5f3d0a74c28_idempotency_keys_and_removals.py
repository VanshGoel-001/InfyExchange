"""idempotency keys and the record of removed listings and needs

Backward compatible with the previous revision's code: it only adds two tables the old code never
touches. Nothing existing is altered, so the previous Cloud Run revision keeps working while this one
rolls out, and removals made before this release have no record.

Revision ID: i5f3d0a74c28
Revises: h4e2c9f63b17
Create Date: 2026-11-16 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'i5f3d0a74c28'
down_revision: Union[str, Sequence[str], None] = 'h4e2c9f63b17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('scope', sa.String(length=40), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_idempotency_user_key'),
    )
    op.create_index(op.f('ix_idempotency_keys_user_id'), 'idempotency_keys', ['user_id'], unique=False)
    op.create_index(op.f('ix_idempotency_keys_created_at'), 'idempotency_keys', ['created_at'], unique=False)

    op.create_table(
        'removals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=150), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=True),
        sa.Column('item_type', sa.String(length=20), nullable=True),
        sa.Column('amount', sa.Integer(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.Column('removed_by_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['removed_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_removals_kind'), 'removals', ['kind'], unique=False)
    op.create_index(op.f('ix_removals_owner_id'), 'removals', ['owner_id'], unique=False)
    op.create_index(op.f('ix_removals_reason'), 'removals', ['reason'], unique=False)
    op.create_index(op.f('ix_removals_created_at'), 'removals', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('removals')
    op.drop_table('idempotency_keys')
