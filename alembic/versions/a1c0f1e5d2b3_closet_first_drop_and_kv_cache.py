"""closet-first: drop the old pipeline's tables, add kv_cache

Revision ID: a1c0f1e5d2b3
Revises: e5b2c9d41f07
Create Date: 2026-11-15

Drops what the redesign removed: the catalogue (``product_catalog_items`` and
the ``vector`` extension), credits (``credit_ledger``), DB eval recording
(``evaluation_runs``) and the old /analyze flow's ``analysis_records`` and
``feedback_records``. ``IF EXISTS`` because a fresh database never created the
catalogue (``c3f81a2b7d64`` is now a no-op). ``kv_cache`` replaces Redis.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1c0f1e5d2b3"
down_revision: str | Sequence[str] | None = "e5b2c9d41f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DROPPED = ("product_catalog_items", "credit_ledger", "evaluation_runs", "feedback_records", "analysis_records")


def upgrade() -> None:
    """Upgrade schema."""
    for table in _DROPPED:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.create_table(
        "kv_cache",
        sa.Column("key", sa.String(256), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kv_cache_expires_at", "kv_cache", ["expires_at"])


def downgrade() -> None:
    """Not supported: the dropped tables' code is gone; restore from git history if needed."""
    raise NotImplementedError("a1c0f1e5d2b3 drops the old pipeline's tables and cannot be undone")
