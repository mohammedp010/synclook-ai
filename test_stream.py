"""Smoke test for SSE streaming endpoint (Step 9).

Starts the app, uploads a test image to /api/v1/analyze/stream,
and prints each SSE event as it arrives.
"""

import asyncio
import sys
from pathlib import Path

import httpx


async def main() -> None:
    # Find a test image
    uploads = Path("uploads")
    images = list(uploads.glob("*"))
    if not images:
        # Create a minimal JPEG for testing
        from PIL import Image
        import io

        img = Image.new("RGB", (100, 100), color=(0, 0, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        test_bytes = buf.getvalue()
        filename = "test_blue.jpg"
        content_type = "image/jpeg"
    else:
        test_bytes = images[0].read_bytes()
        filename = images[0].name
        content_type = "image/jpeg"

    print(f"Using image: {filename} ({len(test_bytes)} bytes)")

    base = "http://127.0.0.1:8000/api/v1"

    async with httpx.AsyncClient(timeout=120.0) as client:
        # POST to streaming endpoint
        resp = await client.post(
            f"{base}/analyze/stream",
            files={"image": (filename, test_bytes, content_type)},
            params={"user_id": "test-stream-user"},
        )

        if resp.status_code != 200:
            print(f"ERROR: status {resp.status_code}")
            print(resp.text[:500])
            sys.exit(1)

        print(f"\nStatus: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        print("\n--- SSE Events ---")
        for line in resp.text.split("\n"):
            if line.strip():
                print(line)


if __name__ == "__main__":
    asyncio.run(main())
