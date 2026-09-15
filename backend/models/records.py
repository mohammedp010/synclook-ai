"""ORM models for persistent storage."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Computed, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base

# Dimensions are model-determined: BGE-small emits 384, CLIP ViT-B/32 emits 512.
# They are constants rather than settings because changing either requires a
# migration and a full re-embed, not a config flip.
TEXT_EMBEDDING_DIM = 384
IMAGE_EMBEDDING_DIM = 512

# Full-text vector for the lexical arm of catalog search. Title and brand are
# weighted above description so a term in the name outranks the same term
# buried in marketing copy. Kept in sync with migration c3f81a2b7d64 -- the
# expression is duplicated there because migrations must not import app code.
_SEARCH_DOCUMENT_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(brand, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


class AnalysisRecord(Base):
    """Stores each clothing analysis request and its results."""

    __tablename__ = "analysis_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    detected_attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    recommendations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedbackRecord(Base):
    """Stores user feedback on recommendations."""

    __tablename__ = "feedback_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    feedback: Mapped[str] = mapped_column(String(16), nullable=False)  # "like" / "dislike"
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WardrobeItem(Base):
    """A garment the user owns, auto-tagged by the vision pipeline.

    ``embedding`` stores the normalized CLIP image embedding as JSON. At
    personal-wardrobe scale (hundreds of items) brute-force cosine in Python
    is faster than a network round-trip; if wardrobes ever grow to catalog
    scale, the migration path is a pgvector column + HNSW index.
    """

    __tablename__ = "wardrobe_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    clothing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False)
    pattern: Mapped[str] = mapped_column(String(32), nullable=False, default="solid")
    style: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(Base):
    """One execution of the evaluation harness, for tracking metrics over time."""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    num_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductCatalogItem(Base):
    """A product in the local retrieval corpus.

    Unlike the live-search path — which queries a provider per request and
    filters whatever comes back — catalog items are ingested ahead of time,
    normalized onto the project's own taxonomy, and embedded once. That makes
    retrieval reproducible (the same query returns the same corpus) and moves
    embedding cost out of the request path.

    Two vector columns, deliberately different sizes: ``text_embedding`` is a
    384-dim BGE sentence embedding used for semantic search over product copy,
    ``image_embedding`` is the 512-dim CLIP embedding already used everywhere
    else, kept so a garment photo can be matched against product imagery
    without a second model. ``search_document`` backs the lexical arm of the
    hybrid query; it is maintained by a trigger-free generated column so it can
    never drift from the text it indexes.
    """

    __tablename__ = "product_catalog_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Provenance. (source, external_id) is the idempotency key for re-ingestion.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    brand: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    store: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    product_url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Whole rupees, matching `StyleIntent.budget_total_inr` so budget checks
    # need no conversion; the provider's display string is kept verbatim for
    # the UI. Nullable because listings without a parseable price still belong
    # in the corpus -- they are simply exempt from price filtering.
    price_inr: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    price_display: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # Normalized onto the project taxonomy at ingest so retrieval filters and
    # the rule engine speak the same language.
    clothing_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    style: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    gender_lean: Mapped[str] = mapped_column(String(16), nullable=False, default="unisex", index=True)

    text_embedding: Mapped[list[float]] = mapped_column(Vector(TEXT_EMBEDDING_DIM), nullable=False)
    image_embedding: Mapped[list[float] | None] = mapped_column(Vector(IMAGE_EMBEDDING_DIM), nullable=True)

    # Availability freshness — stale rows can be demoted or filtered rather
    # than silently served as if they were still buyable.
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Maintained by PostgreSQL, never written from Python: `Computed` marks it
    # read-only for INSERT/UPDATE, and it is deferred because nothing in the
    # application reads the vector itself -- only the index does.
    search_document: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(_SEARCH_DOCUMENT_SQL, persisted=True),
        nullable=False,
        deferred=True,
    )

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_product_catalog_source_external_id"),)
