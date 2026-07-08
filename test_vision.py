"""Smoke-test the vision pipeline with a real image download."""

import asyncio
from io import BytesIO

import httpx
from PIL import Image


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
    result = await service.analyze_image(image_bytes)
    attrs = result.attributes

    print("\n=== RESULTS ===")
    print(f"  Clothing Type : {attrs.clothing_type.value} (conf={attrs.confidence})")
    print(f"  Primary Color : {attrs.primary_color.value} (conf={attrs.color_confidence})")
    print(f"  Pattern       : {attrs.pattern.value} (conf={attrs.pattern_confidence})")
    print(f"  Style         : {attrs.style.value} (conf={attrs.style_confidence})")
    print(f"  Caption       : {attrs.description or '(captioning disabled)'}")
    print(f"  Embedding dim : {len(result.image_embedding)}")


if __name__ == "__main__":
    asyncio.run(main())
