"""wear_events: what each user wore, saved or skipped

Revision ID: f4a9c2d81e37
Revises: b7e2d4c19a60
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4a9c2d81e37"
down_revision: str | Sequence[str] | None = "b7e2d4c19a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "wear_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("item_ids", postgresql.JSONB(), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("occasion", sa.String(32), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('worn', 'saved', 'skipped')", name="ck_wear_events_action"),
    )
    op.create_index("ix_wear_events_user_id", "wear_events", ["user_id"])


def downgrade() -> None:
    """Drop the wear log."""
    op.drop_index("ix_wear_events_user_id", "wear_events")
    op.drop_table("wear_events")
