"""closet items carry the Phase 2 tags and a photo; drop the CLIP embedding

Revision ID: b7e2d4c19a60
Revises: a1c0f1e5d2b3
Create Date: 2026-11-15

Old rows are deleted: they hold CLIP-era tags and no photo, so they can be
neither shown nor used by the outfit engine (which needs formality and warmth).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b7e2d4c19a60"
down_revision: str | Sequence[str] | None = "a1c0f1e5d2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = ("label", "clothing_type", "style", "embedding")


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DELETE FROM wardrobe_items")
    for column in _OLD:
        op.drop_column("wardrobe_items", column)
    for column in (
        sa.Column("garment_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("color_family", sa.String(16), nullable=False),
        sa.Column("color_hex", sa.String(7), nullable=False),
        sa.Column("secondary_color", sa.String(16), nullable=True),
        sa.Column("formality", sa.SmallInteger(), nullable=False),
        sa.Column("warmth", sa.String(8), nullable=False),
        sa.Column("occasions", postgresql.JSONB(), nullable=False),
        sa.Column("short_label", sa.String(64), nullable=False),
        sa.Column("item_count", sa.SmallInteger(), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("image_hash", sa.String(64), nullable=False),
    ):
        op.add_column("wardrobe_items", column)
    op.create_unique_constraint("uq_wardrobe_items_user_image", "wardrobe_items", ["user_id", "image_hash"])


def downgrade() -> None:
    """Back to the CLIP-era columns (rows are deleted both ways)."""
    op.execute("DELETE FROM wardrobe_items")
    op.drop_constraint("uq_wardrobe_items_user_image", "wardrobe_items")
    for column in (
        "garment_type",
        "category",
        "color_family",
        "color_hex",
        "secondary_color",
        "formality",
        "warmth",
        "occasions",
        "short_label",
        "item_count",
        "image",
        "image_hash",
    ):
        op.drop_column("wardrobe_items", column)
    op.add_column("wardrobe_items", sa.Column("label", sa.String(256), nullable=False, server_default=""))
    op.add_column("wardrobe_items", sa.Column("clothing_type", sa.String(32), nullable=False))
    op.add_column("wardrobe_items", sa.Column("style", sa.String(32), nullable=False))
    op.add_column("wardrobe_items", sa.Column("embedding", postgresql.JSONB(), nullable=False))
