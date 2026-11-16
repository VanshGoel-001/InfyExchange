"""notifications: store who did it, the listing title and one short detail instead of relying on a sentence

Backward compatible with the previous revision's code: it only adds three nullable columns, and the
old `message` column stays and is still written, so the old code keeps reading and writing it during a
rollout. Notifications created before this revision keep a null actor; the API works the actor out
from the enquiry they belong to.

Revision ID: f2c9a6b17d34
Revises: e7a3c1d94b52
Create Date: 2026-11-16 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2c9a6b17d34'
down_revision: Union[str, Sequence[str], None] = 'e7a3c1d94b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode: plain ALTER on PostgreSQL, table rebuild on SQLite.
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.add_column(sa.Column('actor_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('listing_title', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('detail', sa.String(length=120), nullable=True))
        batch_op.create_foreign_key(
            'fk_notifications_actor_id', 'users', ['actor_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('fk_notifications_actor_id', type_='foreignkey')
        batch_op.drop_column('detail')
        batch_op.drop_column('listing_title')
        batch_op.drop_column('actor_id')
