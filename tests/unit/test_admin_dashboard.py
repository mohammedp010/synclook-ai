"""Tests for the admin dashboard page.

The page's data comes from `/admin/metrics` at runtime, so what is worth
testing here is that it is served, that it points at that endpoint, and that
the substitution left nothing behind — the failure mode is a dashboard that
loads and then quietly shows nothing.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.routes.admin import _dashboard_html
from backend.app import create_app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestDashboardTemplate:
    def test_metrics_url_is_substituted(self) -> None:
        html = _dashboard_html()
        assert "METRICS_URL" not in html
        assert "/api/v1/admin/metrics" in html

    def test_page_has_no_external_dependencies(self) -> None:
        # The dashboard must render on a laptop with no network — a CDN script
        # tag would turn a demo into an outage.
        html = _dashboard_html()
        assert "https://" not in html
        assert "<script src" not in html
        assert "<link " not in html


class TestDashboardRoute:
    async def test_dashboard_is_served_as_html(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/admin/dashboard")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Synclook AI" in response.text

    async def test_dashboard_is_not_in_the_openapi_schema(self, client: AsyncClient) -> None:
        # It is a page, not an API: listing it in /docs invites clients to
        # treat the markup as a contract.
        schema = (await client.get("/openapi.json")).json()
        assert "/api/v1/admin/dashboard" not in schema["paths"]
        assert "/api/v1/admin/metrics" in schema["paths"]
