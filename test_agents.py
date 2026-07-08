"""End-to-end test for the multi-agent pipeline (Step 3).

Downloads a sample clothing image and runs it through all three agents:
  VisionAgent → StylingAgent → RecommendationAgent
"""

from __future__ import annotations

import asyncio
import urllib.request
from uuid import uuid4

from backend.agents import AgentContext, RecommendationAgent, StylingAgent, VisionAgent
from backend.services.vision import VisionService


async def main() -> None:
    # 1. Download a sample image
    url = "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400"
    print("Downloading sample image …")
    req = urllib.request.Request(url, headers={"User-Agent": "SynclookAI/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        image_bytes = resp.read()
    print(f"  → {len(image_bytes):,} bytes\n")

    # 2. Build context
    ctx = AgentContext(request_id=uuid4(), image_bytes=image_bytes)

    # 3. Vision Agent
    vision_agent = VisionAgent(VisionService())
    ctx = await vision_agent.run(ctx)
    attrs = ctx.clothing_attributes
    assert attrs is not None
    print("=== Vision Agent ===")
    print(f"  Type    : {attrs.clothing_type.value}")
    print(f"  Color   : {attrs.primary_color.value}")
    print(f"  Pattern : {attrs.pattern.value}")
    print(f"  Style   : {attrs.style.value}")
    print(f"  Conf    : {attrs.confidence}")
    print(f"  Caption : {attrs.description}")
    print(f"  Time    : {ctx.agent_timings.get('vision', '?')}s\n")

    # 4. Styling Agent
    styling_agent = StylingAgent()
    ctx = await styling_agent.run(ctx)
    print("=== Styling Agent ===")
    for i, m in enumerate(ctx.style_matches, 1):
        print(f"  [{i}] {m.item_type:12s}  colors={m.recommended_colors[:3]}  "
              f"styles={m.recommended_styles[:2]}  score={m.match_score}")
    print(f"  Time    : {ctx.agent_timings.get('styling', '?')}s\n")

    # 5. Recommendation Agent
    rec_agent = RecommendationAgent()
    ctx = await rec_agent.run(ctx)
    print("=== Recommendation Agent ===")
    for j, rec in enumerate(ctx.recommendations, 1):
        print(f"  Outfit #{j}  (confidence={rec.confidence})")
        for item in rec.items:
            print(f"    • {item.color} {item.item_type} — {item.reason[:80]}")
        print(f"    Explanation: {rec.overall_explanation[:120]}…")
        print(f"    Tags: {rec.style_tags}")
    print(f"  Time    : {ctx.agent_timings.get('recommendation', '?')}s\n")

    # 6. Summary
    print("=== Pipeline Timings ===")
    for agent_name, elapsed in ctx.agent_timings.items():
        print(f"  {agent_name:20s} → {elapsed}s")
    print(f"\nErrors: {ctx.errors or 'none'}")
    print("✓ All agents ran successfully.")


if __name__ == "__main__":
    asyncio.run(main())
