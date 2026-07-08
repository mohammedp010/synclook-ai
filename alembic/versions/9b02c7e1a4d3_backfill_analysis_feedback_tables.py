"""backfill analysis_records and feedback_records tables

Revision ID: 9b02c7e1a4d3
Revises: 7c41a90de512
Create Date: 2026-07-09

The original initial migration was generated empty because the tables
already existed (created by SQLAlchemy create_all during early development).
That left fresh databases without them — this migration creates the tables
when missing so `alembic upgrade head` yields a complete schema on a clean
database while remaining a no-op on legacy ones.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9b02c7e1a4d3"
down_revision: str | Sequence[str] | None = "7c41a90de512"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("analysis_records"):
        op.create_table(
            "analysis_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.String(128), nullable=True, index=True),
            sa.Column("image_path", sa.String(512), nullable=False),
            sa.Column("detected_attributes", postgresql.JSONB(), nullable=False),
            sa.Column("recommendations", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not inspector.has_table("feedback_records"):
        op.create_table(
            "feedback_records",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
            sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.String(128), nullable=True, index=True),
            sa.Column("feedback", sa.String(16), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("feedback_records")
    op.drop_table("analysis_records")
