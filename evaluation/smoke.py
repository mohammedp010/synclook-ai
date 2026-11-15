"""Smoke test of a running Synclook (not an eval): the three jobs, the chat agent and the MCP tool list.

    poetry run python -m evaluation.smoke http://localhost:8000
    poetry run python -m evaluation.smoke https://<service>.onrender.com

Each run uses a new closet id. Paid calls per run: add item 1 vision + 1 Jev call (0 when the photo's
perception is already cached on that database), outfits 1 text-model call, shop search 1 SerpAPI search
(0 when cached, 7 days) + 1 Jev call, chat about 2 gpt-4o-mini calls: about $0.002 and at most 1 search.
``--free`` skips the paid steps (upload, search, chat). A free host may take a minute to wake: the first
request waits up to 120 s. Exit code 1 if any step fails.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

IMAGES = Path(__file__).parent.parent / "data/perception/images/public"
PHOTO = IMAGES / "back_side_chino_trousers_with_welt_pocket_jpg_64256c.jpg"
API = "/api/v1"


class Smoke:
    def __init__(self, base: str) -> None:
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=60, follow_redirects=True)
        self.headers = {"X-User-Id": f"smoke-{uuid.uuid4().hex[:8]}"}
        self.failed = 0

    def step(self, name: str, run: Callable[[], str]) -> None:
        start = time.perf_counter()
        try:
            summary, ok = run(), True
        except Exception as exc:  # noqa: BLE001  (report every step, then exit non-zero)
            summary, ok = f"{type(exc).__name__}: {exc}", False
            self.failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name:<12} {time.perf_counter() - start:6.2f} s  {summary}")

    def post(self, path: str, want: int = 200, **kwargs: Any) -> Any:
        resp = self.http.post(f"{API}{path}", headers={**self.headers, **kwargs.pop("headers", {})}, **kwargs)
        assert resp.status_code == want, f"{path} → {resp.status_code}: {resp.text[:300]}"
        return resp.json() if "json" in resp.headers.get("content-type", "") else resp.text

    # ── the steps ────────────────────────────────────────────────────

    def health(self) -> str:
        resp = self.http.get(f"{API}/health", timeout=120)  # a sleeping free instance wakes on this
        assert resp.status_code == 200, resp.text
        return f"version {resp.json()['version']}"

    def add_item(self) -> str:
        files = {"file": (PHOTO.name, PHOTO.read_bytes(), "image/jpeg")}
        item = self.post("/closet/items", 201, files=files)
        assert item["garment_type"] and item["category"], item
        return f"{item['short_label']} ({item['garment_type']}, {item['category']})"

    def demo(self) -> str:
        out = self.post("/closet/demo")
        assert out["added"] >= 20, out
        return f"{out['added']} demo items copied, {out['total']} in the closet"

    def outfits(self) -> str:
        out = self.post("/outfits", json={"occasion": "interview"})
        assert out["outfits"], out
        first = out["outfits"][0]
        assert first["explanation"], first
        labels = ", ".join(i["short_label"] for i in first["items"])
        return f"{len(out['outfits'])} outfits; #1 {labels} [{first['explanation_source']}]"

    def gaps(self) -> str:
        self.gap = self.post("/shop/gaps", json={"buyer": "menswear"})["gaps"]
        assert self.gap, "no gap items"
        return "; ".join(f"{g['label']} +{g['new_outfits']}" for g in self.gap)

    def search(self) -> str:
        top = self.gap[0]
        body = {"garment_type": top["garment_type"], "color": top["color"], "buyer": "menswear", "max_price": 3000}
        out = self.post("/shop/search", json=body)
        assert all(p["link"].startswith("http") for p in out["products"]), out
        return f"'{out['query']}': {out['checked']} checked → {len(out['products'])} shown {out['note'] or ''}"

    def chat(self) -> str:
        text = self.post("/chat", json={"message": "What should I wear to a job interview?", "history": []})
        events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
        reply = next(e["text"] for e in events if e["type"] == "reply")
        done = events[-1]
        assert done["type"] == "done" and not done.get("stopped"), done
        tools = [e["name"] for e in events if e["type"] == "tool_call"]
        return f"tools {tools}, {done['steps']} steps: {reply[:70]!r}…"

    def mcp(self) -> str:
        url = self.post("/closet/mcp-key")["url"]
        headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}

        def rpc(method: str, params: dict[str, Any]) -> Any:
            msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            resp = self.http.post(url, json=msg, headers=headers)
            assert resp.status_code == 200, f"{method} → {resp.status_code}: {resp.text[:200]}"
            return resp.json()["result"]

        client = {"name": "smoke", "version": "1"}
        rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": client})
        names = [t["name"] for t in rpc("tools/list", {})["tools"]]
        assert len(names) == 5, names
        assert url.startswith("https://") or "localhost" in url or "127.0.0.1" in url, f"not https: {url}"
        return ", ".join(names)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_url")
    parser.add_argument("--free", action="store_true", help="skip the paid steps (upload, search, chat)")
    args = parser.parse_args()
    s = Smoke(args.base_url)
    print(f"Smoke test of {args.base_url} as {s.headers['X-User-Id']}")
    steps: list[tuple[str, Callable[[], str], bool]] = [
        ("health", s.health, False),
        ("add item", s.add_item, True),
        ("demo closet", s.demo, False),
        ("what to wear", s.outfits, False),
        ("what to buy", s.gaps, False),
        ("shop search", s.search, True),
        ("chat", s.chat, True),
        ("mcp tools", s.mcp, False),
    ]
    for name, run, paid in steps:
        if not (paid and args.free):
            s.step(name, run)
    print("all passed" if not s.failed else f"{s.failed} failed")
    sys.exit(1 if s.failed else 0)


if __name__ == "__main__":
    main()
