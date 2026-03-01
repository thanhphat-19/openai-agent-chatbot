"""add_role_enum_and_fix_timestamps

Revision ID: 5c4524a46621
Revises: ac15e28eac25
Create Date: 2026-03-01 10:59:43.429858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5c4524a46621'
down_revision: Union[str, None] = 'ac15e28eac25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create the chatrole enum type
    chatrole_enum = sa.Enum('USER', 'ASSISTANT', name='chatrole')
    chatrole_enum.create(op.get_bind(), checkfirst=True)

    # 2. Convert role column: VARCHAR -> chatrole enum
    #    First cast existing string values to match enum labels
    op.execute("UPDATE chat_messages SET role = UPPER(role)")
    op.alter_column(
        'chat_messages', 'role',
        type_=sa.Enum('USER', 'ASSISTANT', name='chatrole'),
        existing_type=sqlmodel.sql.sqltypes.AutoString(),
        existing_nullable=False,
        postgresql_using="role::chatrole",
    )

    # 3. Add server_default to created_at on both tables
    op.alter_column(
        'chat_sessions', 'created_at',
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        'chat_messages', 'created_at',
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )

    # 4. Add server_default to updated_at on chat_sessions
    #    (onupdate is handled at ORM level; server_default ensures DB-level default)
    op.alter_column(
        'chat_sessions', 'updated_at',
        server_default=sa.func.now(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Convert role back to VARCHAR
    op.alter_column(
        'chat_messages', 'role',
        type_=sqlmodel.sql.sqltypes.AutoString(),
        existing_type=sa.Enum('USER', 'ASSISTANT', name='chatrole'),
        existing_nullable=False,
        postgresql_using="role::text",
    )
    op.execute("UPDATE chat_messages SET role = LOWER(role)")

    # 2. Drop enum type
    sa.Enum(name='chatrole').drop(op.get_bind(), checkfirst=True)

    # 3. Remove server_defaults
    op.alter_column(
        'chat_sessions', 'created_at',
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        'chat_messages', 'created_at',
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        'chat_sessions', 'updated_at',
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )

