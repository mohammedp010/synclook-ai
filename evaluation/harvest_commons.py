"""Harvest freely-licensed garment photos from Wikimedia Commons.

This is how ``data/perception/images/public/`` was built. Commons was chosen
over Unsplash, Pexels or retailer catalogs for one reason: it permits
*redistribution*, not just download. That turns the scraped set into a
committed asset, which is what makes the ``public`` split's numbers
reproducible by someone who clones the repo — see ``data/perception/README.md``
§5 for the tradeoff that buys and the one it does not.

The script stages images and a manifest; it does not label. Labeling is a
separate judgment call and lives in ``label_tool.py``.

Usage::

    poetry run python evaluation/harvest_commons.py --out /tmp/stage
    poetry run python evaluation/harvest_commons.py --out /tmp/stage --bucket topwear
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

API = "https://commons.wikimedia.org/w/api.php"

USER_AGENT = "synclook-perception-eval/0.1 (https://github.com/mohammedp010; portfolio eval set; contact via GitHub)"
"""Commons blocks anonymous bulk clients. A contactable UA is their stated
condition for automated access, not a nicety."""

MIN_INTERVAL = 0.35
MAX_WORKERS = 3
"""Six workers with no delay earns an immediate 429. Three workers behind a
0.35s gate finished 455 of 466 candidates without one."""

ALLOWED_LICENSES = (
    "cc0",
    "cc by",
    "cc by-sa",
    "public domain",
    "no restrictions",
)
"""Prefix match, lowercased. Deliberately excludes GFDL/GPL/MIT, which Commons
also carries: they are free, but their attribution and copyleft terms are a
poor fit for a folder of JPEGs in someone else's repo."""

THUMB_PX = 800
"""Large enough for a VLM to read fabric and print detail in Phase 2, small
enough that ~200 images stay under 25MB. Resizing happens locally: rewriting
the API's thumbnail width to an arbitrary value returns HTTP 400, because only
pre-generated sizes are served."""

QUERIES: dict[str, tuple[str, ...]] = {
    "topwear": ("t-shirt", "white t-shirt", "shirt", "black shirt", "polo shirt", "blouse", "hoodie", "sweater"),
    "bottomwear": ("jeans", "black jeans", "chinos", "trousers", "shorts", "skirt"),
    "outerwear": ("blazer", "navy blazer", "denim jacket", "bomber jacket", "overcoat", "beige trench coat"),
    "fullbody": ("dress", "jumpsuit", "navy suit", "charcoal suit"),
    "footwear": ("sneakers", "leather boots", "loafers", "high heels", "sandals"),
    "ethnic": ("kurta", "sari", "lehenga", "salwar kameez", "sherwani", "dupatta"),
    "accessory": ("wristwatch", "leather belt", "sunglasses", "handbag", "scarf", "necklace"),
    "adversarial": (
        "domestic cat",
        "dog puppy",
        "plate of food",
        "mountain landscape",
        "brick wall",
        "houseplant",
        "paper receipt",
        "software screenshot",
    ),
}
"""``adversarial`` is not a mistake. The guardrail in Phase 3 has to reject
non-garment uploads, and it can only be scored against examples of them.

Worth knowing before you extend this list: keyword search on Commons fails in
useful ways. "bomber jacket" returns aircraft, "Blazer" returns a Chevrolet,
"chinos" returns a moon crater. Those misses were kept — they are precisely the
confusions a garment guardrail exists to catch."""


class _Throttle:
    """One shared gate, so worker count and request rate stay independent."""

    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            gap = self._interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()


_throttle = _Throttle(MIN_INTERVAL)


def _get(url: str, retries: int = 3) -> bytes:
    """Fetch with backoff. 429 is expected under load and is worth waiting out."""
    last: Exception | None = None
    for attempt in range(retries):
        _throttle.wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                data: bytes = resp.read()
                return data
        except Exception as exc:  # noqa: BLE001 - urllib raises several unrelated types
            last = exc
            if "429" in str(exc):
                time.sleep(2.0 + attempt * 3.0)
                continue
            break
    raise RuntimeError(f"GET failed: {url[:90]} — {last}")


def _extract(meta: dict[str, Any], key: str) -> str:
    """Pull one ``extmetadata`` field, stripped of the HTML Commons embeds in it."""
    raw = str(meta.get(key, {}).get("value", ""))
    return re.sub(r"<[^>]+>", "", raw).strip()


def search(query: str, limit: int) -> list[dict[str, Any]]:
    """Search Commons' file namespace, returning candidates with licence metadata."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": str(THUMB_PX),
    }
    payload = json.loads(_get(f"{API}?{urllib.parse.urlencode(params)}"))
    pages: dict[str, Any] = payload.get("query", {}).get("pages", {})

    out: list[dict[str, Any]] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _extract(meta, "LicenseShortName")
        if not license_name.lower().startswith(ALLOWED_LICENSES):
            continue
        thumb = info.get("thumburl")
        if not thumb:
            continue
        out.append(
            {
                "title": page.get("title", ""),
                # The API's own thumburl, used verbatim. See THUMB_PX.
                "thumb": thumb,
                "page": info.get("descriptionurl", ""),
                "license": license_name,
                "author": _extract(meta, "Artist"),
                "query": query,
            }
        )
    return out


def _slug(title: str) -> str:
    stem = re.sub(r"^File:", "", title)
    return re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower()[:60]


def download(item: dict[str, Any], out_dir: Path) -> str | None:
    """Fetch one image, downscale, write as JPEG. Returns the relative path or None."""
    bucket_dir = out_dir / str(item["bucket"])
    bucket_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.md5(str(item["title"]).encode()).hexdigest()[:6]  # noqa: S324 - a filename, not a signature
    name = f"{_slug(str(item['title']))}_{digest}.jpg"
    target = bucket_dir / name

    if target.exists() and target.stat().st_size > 3000:
        return f"{item['bucket']}/{name}"
    try:
        data = _get(str(item["thumb"]))
        if len(data) < 3000:
            return None
        image = Image.open(BytesIO(data)).convert("RGB")
        image.thumbnail((THUMB_PX, THUMB_PX), Image.Resampling.LANCZOS)
        image.save(target, "JPEG", quality=88)
    except Exception as exc:  # noqa: BLE001 - one bad file should not end the run
        print(f"  skip {str(item['title'])[:50]} — {str(exc)[:60]}", file=sys.stderr)
        return None
    return f"{item['bucket']}/{name}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest CC/PD garment photos from Wikimedia Commons")
    parser.add_argument("--out", required=True, type=Path, help="staging directory")
    parser.add_argument("--bucket", choices=list(QUERIES), default=None, help="one bucket instead of all")
    parser.add_argument("--per-query", type=int, default=12)
    args = parser.parse_args()

    buckets = {args.bucket: QUERIES[args.bucket]} if args.bucket else QUERIES

    candidates: list[dict[str, Any]] = []
    for bucket, queries in buckets.items():
        for query in queries:
            try:
                found = search(query, args.per_query)
            except RuntimeError as exc:
                print(f"  search failed: {query} — {exc}", file=sys.stderr)
                continue
            for item in found:
                item["bucket"] = bucket
            candidates.extend(found)
            print(f"  {bucket:12} {query:24} {len(found):3} candidates")

    # Buckets overlap — "blazer" and "navy blazer" return the same files — so
    # dedupe on title, keeping the first bucket that claimed each image.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        title = str(candidate["title"])
        if title not in seen:
            seen.add(title)
            unique.append(candidate)
    print(f"\n{len(unique)} unique candidates after licence filter; downloading…")

    args.out.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        paths = list(pool.map(lambda c: download(c, args.out), unique))

    manifest = {
        path: {k: item[k] for k in ("page", "license", "author", "query", "title")}
        for path, item in zip(paths, unique, strict=True)
        if path
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    print(f"\ndownloaded {len(manifest)}/{len(unique)} → {args.out}")
    print(f"manifest: {args.out / 'manifest.json'}")
    print("\nNext: review by eye, copy the keepers into data/perception/images/public/,")
    print("and label them with `poetry run python evaluation/label_tool.py --split public`.")
    print("Provenance from the manifest must be carried onto every label — CC BY obliges it.")


if __name__ == "__main__":
    main()
