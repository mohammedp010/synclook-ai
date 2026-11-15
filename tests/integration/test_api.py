"""API endpoint tests using httpx AsyncClient — no real server needed."""

from httpx import ASGITransport, AsyncClient

from backend.app import create_app


async def test_health_returns_200() -> None:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data
