"""Smoke-test the vision pipeline with a real image download."""

import asyncio
import sys
from pathlib import Path

import httpx
from PIL import Image
from io import BytesIO


async def main() -> None:
    # Download a sample clothing image (a blue shirt from Unsplash — small thumbnail)
    sample_url = "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=320&q=80"
    print(f"Downloading sample image from {sample_url} ...")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(sample_url)
        if resp.status_code != 200:
            print(f"Failed to download image: HTTP {resp.status_code}")
            # Fall back to a locally generated test image
            img = Image.new("RGB", (224, 224), color=(30, 60, 180))  # blue-ish
            buf = BytesIO()
            img.save(buf, format="JPEG")
            image_bytes = buf.getvalue()
            print("Using generated blue test image instead.")
        else:
            image_bytes = resp.content
            print(f"Downloaded {len(image_bytes)} bytes")

    # Run the vision service
    from backend.services.vision import VisionService

    service = VisionService()
    print("\nRunning vision pipeline (first call downloads models — may take a minute) ...")
    attrs = await service.analyze_image(image_bytes)

    print("\n=== RESULTS ===")
    print(f"  Clothing Type : {attrs.clothing_type.value}")
    print(f"  Primary Color : {attrs.primary_color.value}")
    print(f"  Pattern       : {attrs.pattern.value}")
    print(f"  Style         : {attrs.style.value}")
    print(f"  Confidence    : {attrs.confidence}")
    print(f"  Caption       : {attrs.description}")


if __name__ == "__main__":
    asyncio.run(main())
