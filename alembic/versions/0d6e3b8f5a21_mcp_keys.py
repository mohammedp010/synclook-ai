"""mcp_keys: the hashed secret in each closet's MCP URL

Revision ID: 0d6e3b8f5a21
Revises: f4a9c2d81e37
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0d6e3b8f5a21"
down_revision: str | Sequence[str] | None = "f4a9c2d81e37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "mcp_keys",
        sa.Column("user_id", sa.String(128), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Drop the MCP keys (every MCP URL stops working)."""
    op.drop_table("mcp_keys")
