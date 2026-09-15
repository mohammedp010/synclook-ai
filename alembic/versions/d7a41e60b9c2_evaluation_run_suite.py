"""evaluation_runs.suite — one history table for every evaluation suite

Revision ID: d7a41e60b9c2
Revises: c3f81a2b7d64
Create Date: 2026-09-10

Existing rows all came from the structural harness, which is the only suite
that could record until now, so the backfill is a constant rather than a guess.
The server default is kept afterwards: it makes the column safe for any writer
that predates this migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a41e60b9c2"
down_revision: str | Sequence[str] | None = "c3f81a2b7d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "evaluation_runs",
        sa.Column("suite", sa.String(32), nullable=False, server_default="harness"),
    )
    op.create_index("ix_evaluation_runs_suite", "evaluation_runs", ["suite"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_evaluation_runs_suite", table_name="evaluation_runs")
    op.drop_column("evaluation_runs", "suite")
