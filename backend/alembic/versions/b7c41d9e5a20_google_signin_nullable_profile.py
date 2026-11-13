"""google sign-in: nullable profile columns and google_sub

Backward compatible with the previous revision's code: only relaxes NOT NULL
and adds a nullable column. Old code never writes NULLs, so a rolling deploy
is safe. (One caveat: an old instance serving a Google-created user that has
not finished the profile step cannot render it. That window lasts only until
the old revision drains.)

Revision ID: b7c41d9e5a20
Revises: ee1edd3df3f3
Create Date: 2026-11-12 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c41d9e5a20'
down_revision: Union[str, Sequence[str], None] = 'ee1edd3df3f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE = sa.Enum('SE', 'DSE', 'SP_L1', 'SP_L2', name='userrole')


def upgrade() -> None:
    # batch mode: plain ALTER on PostgreSQL, table rebuild on SQLite.
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('google_sub', sa.String(length=64), nullable=True))
        batch_op.alter_column('phone', existing_type=sa.String(length=20), nullable=True)
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=True)
        batch_op.alter_column('role', existing_type=ROLE, nullable=True)
        batch_op.alter_column('joining_date', existing_type=sa.Date(), nullable=True)
        batch_op.create_index(batch_op.f('ix_users_google_sub'), ['google_sub'], unique=True)


def downgrade() -> None:
    # Fails if any Google-created user still has NULLs: complete or delete them first.
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_google_sub'))
        batch_op.alter_column('joining_date', existing_type=sa.Date(), nullable=False)
        batch_op.alter_column('role', existing_type=ROLE, nullable=False)
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=False)
        batch_op.alter_column('phone', existing_type=sa.String(length=20), nullable=False)
        batch_op.drop_column('google_sub')
