"""Quick smoke test for the API skeleton."""

import asyncio
import struct
import zlib

from httpx import ASGITransport, AsyncClient

from backend.app import create_app


def make_tiny_png() -> bytes:
    """Generate a minimal valid 1x1 PNG."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    raw = zlib.compress(b"\x00\xff\x00\x00")
    idat_crc = zlib.crc32(b"IDAT" + raw) & 0xFFFFFFFF
    idat = struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc)
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


async def main() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        r = await client.get("/api/v1/health")
        print(f"[health]   Status={r.status_code}  Body={r.json()}")

        # Analysis endpoint
        png = make_tiny_png()
        r = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.png", png, "image/png")},
        )
        data = r.json()
        print(f"[analyze]  Status={r.status_code}  Type={data['detected_attributes']['clothing_type']}")

        # Feedback endpoint
        r = await client.post(
            "/api/v1/feedback",
            json={
                "request_id": data["request_id"],
                "recommendation_id": "00000000-0000-0000-0000-000000000000",
                "feedback": "like",
            },
        )
        print(f"[feedback] Status={r.status_code}  Body={r.json()}")

        # Invalid image type
        r = await client.post(
            "/api/v1/analyze",
            files={"image": ("test.txt", b"hello", "text/plain")},
        )
        print(f"[invalid]  Status={r.status_code}  (expected 400)")


if __name__ == "__main__":
    asyncio.run(main())
