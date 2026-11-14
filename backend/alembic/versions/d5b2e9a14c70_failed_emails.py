"""failed emails: keep an undeliverable email until an admin retries or discards it

Backward compatible with the previous revision's code: it only adds a table
that the old code never touches.

Revision ID: d5b2e9a14c70
Revises: c3a8f1d27b64
Create Date: 2026-11-14 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5b2e9a14c70'
down_revision: Union[str, Sequence[str], None] = 'c3a8f1d27b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'failed_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('to_email', sa.String(length=255), nullable=False),
        sa.Column('to_name', sa.String(length=100), nullable=True),
        sa.Column('subject', sa.String(length=200), nullable=False),
        sa.Column('html', sa.Text(), nullable=False),
        sa.Column('reply_to_email', sa.String(length=255), nullable=True),
        sa.Column('reply_to_name', sa.String(length=100), nullable=True),
        sa.Column('error', sa.String(length=300), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_failed_emails_created_at'), 'failed_emails', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_failed_emails_created_at'), table_name='failed_emails')
    op.drop_table('failed_emails')
