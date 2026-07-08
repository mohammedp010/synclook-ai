"""Test for Step 8 — Feedback loop with DB persistence and memory updates.

Tests:
1. FeedbackService.save_analysis() persists to PostgreSQL
2. FeedbackService.record_feedback() persists + updates Redis preferences
3. Round-trip: analysis → feedback → verify DB rows + memory state
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import get_settings
from backend.models.records import AnalysisRecord, FeedbackRecord
from backend.schemas.api import Recommendation, RecommendationItem
from backend.services.feedback import FeedbackService
from backend.services.memory import MemoryService


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    mem = MemoryService()
    svc = FeedbackService(mem)
    user_id = "test-user-step8"
    request_id = uuid4()

    # --- Build a fake analysis result ---
    rec_id = uuid4()
    rec = Recommendation(
        id=rec_id,
        items=[
            RecommendationItem(item_type="trousers", color="white", style="minimalist", reason="test"),
            RecommendationItem(item_type="blazer", color="navy", style="smart_casual", reason="test"),
        ],
        overall_explanation="Test outfit explanation",
        style_tags=["minimalist", "smart_casual"],
        confidence=0.85,
    )
    detected = {
        "clothing_type": "shirt",
        "primary_color": "navy",
        "pattern": "solid",
        "style": "minimalist",
        "confidence": 0.9,
        "description": "a navy shirt",
    }

    # --- 1. Save analysis ---
    print("=== Save Analysis ===")
    async with session_factory() as db:
        record = await svc.save_analysis(
            db,
            request_id=request_id,
            user_id=user_id,
            image_path="test_image.jpg",
            detected_attributes=detected,
            recommendations=[rec],
        )
        await db.commit()
        print(f"  AnalysisRecord saved: id={record.id}")

    # --- 2. Verify analysis in DB ---
    async with session_factory() as db:
        result = await db.execute(select(AnalysisRecord).where(AnalysisRecord.id == request_id))
        row = result.scalar_one_or_none()
        assert row is not None, "AnalysisRecord not found in DB"
        print(f"  DB verify: user_id={row.user_id}, image_path={row.image_path}")
        print(f"  Stored {len(row.recommendations)} recommendation(s)")

    # --- 3. Submit feedback (like) ---
    print("\n=== Submit Feedback (like) ===")
    async with session_factory() as db:
        fb = await svc.record_feedback(
            db,
            request_id=request_id,
            recommendation_id=rec_id,
            feedback="like",
            user_id=user_id,
            comment="Love this outfit!",
        )
        await db.commit()
        print(f"  FeedbackRecord saved: id={fb.id}")

    # --- 4. Verify feedback in DB ---
    async with session_factory() as db:
        result = await db.execute(
            select(FeedbackRecord).where(FeedbackRecord.request_id == request_id)
        )
        fb_row = result.scalar_one_or_none()
        assert fb_row is not None, "FeedbackRecord not found in DB"
        print(f"  DB verify: feedback={fb_row.feedback}, comment={fb_row.comment}")

    # --- 5. Verify memory was updated ---
    print("\n=== Memory State ===")
    prefs = await mem.get_preferences(user_id)
    print(f"  Preferences: {prefs.to_dict()}")
    assert "white" in prefs.liked_colors or "navy" in prefs.liked_colors, \
        "Expected feedback colors in liked_colors"

    # --- 6. Submit dislike feedback ---
    print("\n=== Submit Feedback (dislike) ===")
    rec_id_2 = uuid4()
    async with session_factory() as db:
        await svc.record_feedback(
            db,
            request_id=request_id,
            recommendation_id=rec_id_2,
            feedback="dislike",
            user_id=user_id,
        )
        await db.commit()
        print("  Dislike recorded (no matching rec in DB — memory skipped gracefully)")

    # --- 7. Count records ---
    async with session_factory() as db:
        analysis_count = (await db.execute(text("SELECT count(*) FROM analysis_records"))).scalar()
        feedback_count = (await db.execute(text("SELECT count(*) FROM feedback_records"))).scalar()
    print(f"\n=== DB Totals ===")
    print(f"  analysis_records: {analysis_count}")
    print(f"  feedback_records: {feedback_count}")

    # --- Cleanup ---
    await mem.close()
    await engine.dispose()
    print("\n✓ Feedback loop test passed.")


if __name__ == "__main__":
    asyncio.run(main())
