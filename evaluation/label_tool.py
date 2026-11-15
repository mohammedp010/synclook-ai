"""Local labeling tool for the perception eval set.

Hand-labeling ~120 photos is the one Phase 0 task that cannot be automated, so
the tool it is done with decides whether it takes an afternoon or a weekend.
This is a keyboard-driven single-page app served by the standard library —
no FastAPI, no build step, no CDN, matching the admin dashboard's stance that
a tool you run twice should not carry a dependency.

Every field is rendered from ``perception_labels.vocabulary()``, which is
derived from ``backend.schemas.taxonomy``, so the options offered can never
drift from the options the eval scores.

Usage::

    poetry run python evaluation/label_tool.py                  # all splits
    poetry run python evaluation/label_tool.py --split holdout  # one split
    poetry run python evaluation/label_tool.py --port 8901
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.color_palette import PALETTE_HEX  # noqa: E402
from evaluation.perception_labels import (  # noqa: E402
    IMAGES_DIR,
    LABELS_PATH,
    SPLITS,
    PerceptionLabel,
    append_label,
    coverage,
    list_images,
    load_labels,
    vocabulary,
)

INDEX_PATH = Path(__file__).with_name("label_tool.html")
"""The whole UI: one file, no build step, no CDN, no framework.

It sits next to this module rather than inside it so the CSS and JS stay
readable at their natural line lengths — an embedded string would either be
linted as Python or hand-minified into something nobody wants to edit.
"""


class _Handler(BaseHTTPRequestHandler):
    split: str | None = None

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        return  # the tool is interactive; request logs are noise

    # ── helpers ──────────────────────────────────────────────────────

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    # ── routes ───────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        path = unquote(urlparse(self.path).path)

        if path in ("/", "/index.html"):
            # Read per request rather than at import: editing the UI then hitting
            # reload is the whole development loop for this tool.
            self._send(200, INDEX_PATH.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/api/state":
            vocab = vocabulary()
            vocab["hex"] = {name.value: value for name, value in PALETTE_HEX.items()}
            labels = {key: value.model_dump(mode="json") for key, value in load_labels().items()}
            images = list_images(self.split)  # type: ignore[arg-type]
            shown = set(images)
            self._json(
                {
                    "images": images,
                    "labels": {k: v for k, v in labels.items() if k in shown},
                    "vocab": vocab,
                }
            )
            return

        if path.startswith("/img/"):
            self._serve_image(path[len("/img/") :])
            return

        self._send(404, b"not found", "text/plain")

    def _serve_image(self, rel: str) -> None:
        """Serve one image, refusing anything that escapes the images root.

        The tool binds to localhost, but a path-traversal hole in a local
        server is still a path-traversal hole — ``resolve()`` then
        ``is_relative_to`` is the check that actually holds, because it
        collapses ``..`` and symlinks before comparing.
        """
        try:
            target = (IMAGES_DIR / rel).resolve()
        except OSError:
            self._send(400, b"bad path", "text/plain")
            return

        if not target.is_relative_to(IMAGES_DIR.resolve()) or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return

        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/label":
            self._send(404, b"not found", "text/plain")
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            label = PerceptionLabel.model_validate_json(raw).stamp(labeler=_LABELER)
        except Exception as exc:
            self._send(422, str(exc).encode("utf-8"), "text/plain")
            return

        append_label(label)
        self._json({"ok": True, "image": label.image})


_LABELER = ""


def main() -> None:
    global _LABELER

    parser = argparse.ArgumentParser(description="Label the perception eval set")
    parser.add_argument("--split", choices=list(SPLITS), default=None)
    parser.add_argument("--port", type=int, default=8900)
    parser.add_argument("--labeler", default="", help="recorded on every label")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _LABELER = args.labeler
    _Handler.split = args.split

    images = list_images(args.split)
    if not images:
        print(f"No images under {IMAGES_DIR}. See data/perception/README.md for what to collect.", file=sys.stderr)

    report = coverage()
    for split in SPLITS:
        row = report[split]
        if row["images"]:
            print(f"  {split:12} {row['labeled']:3}/{row['images']:3} labeled")

    url = f"http://127.0.0.1:{args.port}/"
    print(f"\nLabeling {len(images)} image(s) → {LABELS_PATH}")
    print(f"Open {url}   (Ctrl-C to stop; progress is saved after every image)\n")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), _Handler)
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped — labels are saved")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
