"""ORM models for persistent storage."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


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
