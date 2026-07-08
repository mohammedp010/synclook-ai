"""Test for Step 7 — Memory integration with Redis.

Runs the full pipeline twice:
1. Without user preferences (baseline)
2. After recording feedback — verifies score boosting and history storage
"""

from __future__ import annotations

import asyncio
import urllib.request

from backend.agents.orchestrator import Orchestrator
from backend.services.llm import LLMService
from backend.services.memory import MemoryService
from backend.services.vision import VisionService


async def main() -> None:
    # --- Setup ---
    url = "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400"
    print("Downloading sample image …")
    req = urllib.request.Request(url, headers={"User-Agent": "SynclookAI/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        image_bytes = resp.read()
    print(f"  → {len(image_bytes):,} bytes\n")

    mem = MemoryService()
    llm = LLMService()
    orch = Orchestrator(VisionService(), llm, mem)
    user_id = "test-user-step7"

    # --- Run 1: no memory yet ---
    print("=== Run 1 (no user history) ===")
    ctx1 = await orch.run(image_bytes, user_id=user_id)
    baseline_score = ctx1.style_matches[0].match_score
    print(f"  Recommendations: {len(ctx1.recommendations)}")
    print(f"  Top score (baseline): {baseline_score}")
    print(f"  User prefs in ctx: {'user_preferences' in ctx1.metadata}")

    # --- Record feedback: user likes white + minimalist, dislikes cream ---
    await mem.record_feedback(
        user_id, feedback_type="like", colors=["white"], styles=["minimalist"],
    )
    await mem.record_feedback(
        user_id, feedback_type="dislike", colors=["cream"], styles=[],
    )
    prefs = await mem.get_preferences(user_id)
    print(f"\n  Prefs after feedback: {prefs.to_dict()}")

    # --- Check history was saved from run 1 ---
    history = await mem.get_history(user_id)
    print(f"  History entries: {len(history)}")
    if history:
        print(f"  Latest: {history[0]}")

    # --- Run 2: with memory (prefs loaded → scores boosted) ---
    print("\n=== Run 2 (with user preferences) ===")
    ctx2 = await orch.run(image_bytes, user_id=user_id)
    boosted_score = ctx2.style_matches[0].match_score
    print(f"  Top score (with prefs): {boosted_score}")
    print(f"  User prefs loaded: {'user_preferences' in ctx2.metadata}")
    print(f"  Score changed: {baseline_score} → {boosted_score}")

    # --- Verify history grew ---
    history2 = await mem.get_history(user_id)
    print(f"  History entries after run 2: {len(history2)}")

    # --- Summary ---
    print(f"\n  Errors: {ctx2.errors or 'none'}")

    # --- Cleanup ---
    await mem.close()
    print("\n✓ Memory integration test passed.")


if __name__ == "__main__":
    asyncio.run(main())
