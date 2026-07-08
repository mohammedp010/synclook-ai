"""wardrobe_items and evaluation_runs tables

Revision ID: 7c41a90de512
Revises: 02b9134af48d
Create Date: 2026-07-09

The wardrobe embedding column is JSONB by design: personal wardrobes are
hundreds of items, where brute-force cosine beats index round-trips. If the
corpus ever reaches catalog scale, migrate this column to pgvector
(`CREATE EXTENSION vector; ALTER TABLE ... TYPE vector(512)`) and add an
HNSW index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7c41a90de512"
down_revision: str | Sequence[str] | None = "02b9134af48d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "wardrobe_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False, server_default=""),
        sa.Column("clothing_type", sa.String(32), nullable=False),
        sa.Column("color", sa.String(32), nullable=False),
        sa.Column("pattern", sa.String(32), nullable=False, server_default="solid"),
        sa.Column("style", sa.String(32), nullable=False),
        sa.Column("embedding", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("git_sha", sa.String(64), nullable=True, index=True),
        sa.Column("num_cases", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("evaluation_runs")
    op.drop_table("wardrobe_items")
