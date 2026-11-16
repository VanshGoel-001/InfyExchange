"""notification expiry: every notification expires 30 days after it was created

Backward compatible with the previous revision's code: it only adds a column, and the column has a
database default (30 days from now) so rows the previous release inserts without it still get one.
Existing rows are set to created_at + 30 days, so anything older than that is gone from the bell as
soon as this runs, and the daily cleanup then deletes it.

Revision ID: h4e2c9f63b17
Revises: f2c9a6b17d34
Create Date: 2026-11-16 21:00:00

"""
from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'h4e2c9f63b17'
down_revision: Union[str, Sequence[str], None] = 'f2c9a6b17d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXPIRY_DAYS = 30


def upgrade() -> None:
    bind = op.get_bind()
    default = (
        sa.text("((now() at time zone 'utc') + interval '30 days')")
        if bind.dialect.name == 'postgresql'
        else sa.text("(datetime('now', '+30 days'))")
    )

    # batch mode: plain ALTER on PostgreSQL, table rebuild on SQLite.
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.add_column(sa.Column('expires_at', sa.DateTime(), nullable=False, server_default=default))
        batch_op.create_index(batch_op.f('ix_notifications_expires_at'), ['expires_at'], unique=False)

    notifications = sa.table(
        'notifications',
        sa.column('id', sa.Integer),
        sa.column('created_at', sa.DateTime),
        sa.column('expires_at', sa.DateTime),
    )
    for row_id, created_at in bind.execute(sa.select(notifications.c.id, notifications.c.created_at)).all():
        bind.execute(
            sa.update(notifications)
            .where(notifications.c.id == row_id)
            .values(expires_at=created_at + timedelta(days=EXPIRY_DAYS))
        )


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_index(batch_op.f('ix_notifications_expires_at'))
        batch_op.drop_column('expires_at')
