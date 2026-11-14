"""enquiry deal flow, chat, notifications, blocks and reports

Backward compatible with the previous revision's code: only adds nullable
columns, new tables and one enum value. Old code ignores all of it.
One caveat: an old instance that reads an enquiry the new code has set to
CLOSED cannot parse that status. That window lasts only until the old
revision drains.

PostgreSQL cannot remove an enum value, so downgrade() leaves CLOSED in the
type; the rows that used it must be dealt with by hand before downgrading.

Revision ID: c3a8f1d27b64
Revises: b7c41d9e5a20
Create Date: 2026-11-14 10:00:00

"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3a8f1d27b64'
down_revision: Union[str, Sequence[str], None] = 'b7c41d9e5a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate does not see enum value additions. SQLite stores the enum as
    # plain text, so only PostgreSQL needs the ALTER.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("ALTER TYPE intereststatus ADD VALUE IF NOT EXISTS 'CLOSED'")

    with op.batch_alter_table('interests') as batch_op:
        batch_op.add_column(sa.Column('decline_reply', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('last_activity_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reminder_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('deal_closed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('returned_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('received_confirmed', sa.Boolean(), nullable=True))

    # Chats that were accepted before this release get a fresh 48 hours, so the
    # first inactivity reminder is not a surprise burst the moment this deploys.
    op.execute(
        sa.text("UPDATE interests SET last_activity_at = :now WHERE status = 'ACCEPTED'")
        .bindparams(now=datetime.utcnow())
    )

    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interest_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['interest_id'], ['interests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_messages_interest_id_id', 'messages', ['interest_id', 'id'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('message', sa.String(length=300), nullable=False),
        sa.Column('interest_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['interest_id'], ['interests.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_user_id_read_at', 'notifications', ['user_id', 'read_at'], unique=False)

    op.create_table(
        'user_blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('blocker_id', sa.Integer(), nullable=False),
        sa.Column('blocked_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['blocker_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blocked_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('blocker_id', 'blocked_id', name='unique_user_block'),
    )
    op.create_index(op.f('ix_user_blocks_blocker_id'), 'user_blocks', ['blocker_id'], unique=False)
    op.create_index(op.f('ix_user_blocks_blocked_id'), 'user_blocks', ['blocked_id'], unique=False)

    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reporter_id', sa.Integer(), nullable=False),
        sa.Column('reported_user_id', sa.Integer(), nullable=False),
        sa.Column('interest_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reported_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['interest_id'], ['interests.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reports_reported_user_id'), 'reports', ['reported_user_id'], unique=False)
    op.create_index(op.f('ix_reports_created_at'), 'reports', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reports_created_at'), table_name='reports')
    op.drop_index(op.f('ix_reports_reported_user_id'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_user_blocks_blocked_id'), table_name='user_blocks')
    op.drop_index(op.f('ix_user_blocks_blocker_id'), table_name='user_blocks')
    op.drop_table('user_blocks')
    op.drop_index('ix_notifications_user_id_read_at', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_messages_interest_id_id', table_name='messages')
    op.drop_table('messages')

    with op.batch_alter_table('interests') as batch_op:
        batch_op.drop_column('received_confirmed')
        batch_op.drop_column('returned_at')
        batch_op.drop_column('deal_closed_at')
        batch_op.drop_column('reminder_sent_at')
        batch_op.drop_column('last_activity_at')
        batch_op.drop_column('decline_reply')
