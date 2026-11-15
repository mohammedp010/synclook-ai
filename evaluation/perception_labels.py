"""Ground-truth label schema and storage for the perception eval set.

Labels live in a JSONL file (``data/perception/labels.jsonl``) rather than one
JSON array so the labeling tool can append after every image. Hand-labeling
~120 photos is the one task in Phase 0 that cannot be automated, and losing an
hour of it to a crashed process would be the difference between the eval set
existing and not.

Labels are written against ``backend.schemas.taxonomy`` — the *target*
vocabulary — not against the live enums. Scoring the current pipeline then maps
down through ``COARSE_TYPE`` / ``COARSE_COLOR``, so the baseline is judged only
on distinctions it was actually offered.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.taxonomy import (  # noqa: E402
    AccessoryType,
    Aesthetic,
    ColorName,
    Formality,
    GarmentType,
    Occasion,
    PatternName,
)

DATA_DIR = PROJECT_ROOT / "data" / "perception"
IMAGES_DIR = DATA_DIR / "images"
LABELS_PATH = DATA_DIR / "labels.jsonl"

Split = Literal["holdout", "adversarial", "weak", "public"]

SPLITS: tuple[Split, ...] = ("holdout", "adversarial", "weak", "public")
"""``holdout`` — real-world photos, hand-labeled; the set that counts.
``adversarial`` — non-garment and hostile inputs for the Phase 3 guardrail.
``weak`` — auto-labeled from catalog product titles; cheap, clean, optimistic.
``public`` — freely-licensed photos from Wikimedia Commons. Redistributable, so
these images are committed and the numbers on them *are* reproducible by an
outsider. A different distribution from ``holdout`` (amateur snapshots and
museum pieces rather than a user's phone), so the two are never pooled. It also
carries its own non-garment images, flagged by ``is_garment_photo``, which is
how the guardrail is scored without needing private photos."""

PhotoKind = Literal["on_body", "flat_lay", "hanger", "product_shot", "mirror_selfie", "not_garment"]

PHOTO_KINDS: tuple[PhotoKind, ...] = (
    "on_body",
    "flat_lay",
    "hanger",
    "product_shot",
    "mirror_selfie",
    "not_garment",
)


class GarmentLabel(BaseModel):
    """Ground truth for one garment within a photo."""

    type: GarmentType
    accessory: AccessoryType | None = None
    """Set when ``type`` is ``OTHER`` and the item is an accessory.

    ``GarmentType`` and ``AccessoryType`` are deliberately separate vocabularies
    — a belt is not a kind of garment — but a photo of a belt still needs a
    label. Without this field every accessory would collapse to ``other`` and
    the Phase 4 accessory work would have no ground truth to be scored against.
    """

    primary_color: ColorName
    secondary_color: ColorName | None = None
    pattern: PatternName = PatternName.SOLID
    aesthetic: Aesthetic = Aesthetic.CLASSIC


class Provenance(BaseModel):
    """Where an image came from. Required for redistributable splits.

    CC BY and CC BY-SA oblige us to name the author and the licence; recording
    the description page as well means any claim about an image can be checked
    at the source rather than taken on trust.
    """

    page: str = ""
    license: str = ""
    author: str = ""


class PerceptionLabel(BaseModel):
    """Ground truth for one image in the eval set."""

    image: str = Field(description="Path relative to data/perception/images/, e.g. 'holdout/img_0042.jpg'")
    split: Split = "holdout"
    provenance: Provenance | None = None

    is_garment_photo: bool = True
    photo_kind: PhotoKind = "on_body"

    garment_count: int = Field(default=1, ge=0, le=8)
    primary: GarmentLabel | None = Field(
        default=None,
        description="The garment being styled. None only for non-garment images.",
    )
    others: list[GarmentLabel] = Field(
        default_factory=list,
        description="Additional garments visible, for the multi-garment eval.",
    )

    occasions: list[Occasion] = Field(
        default_factory=list,
        description="Every occasion the primary garment could honestly be worn to. Multi-label by design.",
    )
    formality: Formality = Formality.CASUAL

    notes: str = ""
    labeler: str = ""
    labeled_at: str = ""

    def stamp(self, labeler: str = "") -> PerceptionLabel:
        """Return a copy carrying the labeler and an ISO timestamp."""
        return self.model_copy(
            update={
                "labeler": labeler or self.labeler,
                "labeled_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        )


# ──────────────────────────────────────────────────────────────────────
#  Storage — append-only JSONL, last write per image wins
# ──────────────────────────────────────────────────────────────────────


def load_labels(path: Path = LABELS_PATH) -> dict[str, PerceptionLabel]:
    """Read the label file, keyed by image path.

    Later entries override earlier ones, so relabeling an image is a matter of
    appending a corrected line — no rewrite, no lost work if the tool dies
    mid-session. Malformed lines are skipped loudly rather than aborting the
    load: one bad row should not cost the other 119.
    """
    if not path.exists():
        return {}

    labels: dict[str, PerceptionLabel] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            label = PerceptionLabel.model_validate_json(line)
            labels[label.image] = label
        except Exception as exc:
            print(f"warning: {path.name}:{lineno} skipped — {exc}", file=sys.stderr)
    return labels


def append_label(label: PerceptionLabel, path: Path = LABELS_PATH) -> None:
    """Append one label. Creates the file and parent directory if absent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(label.model_dump_json() + "\n")


def compact(path: Path = LABELS_PATH) -> int:
    """Rewrite the file with one line per image, dropping superseded entries.

    Optional housekeeping — ``load_labels`` already resolves duplicates.
    Returns the number of labels kept.
    """
    labels = load_labels(path)
    path.write_text(
        "".join(label.model_dump_json() + "\n" for label in labels.values()),
        encoding="utf-8",
    )
    return len(labels)


def list_images(split: Split | None = None, images_dir: Path = IMAGES_DIR) -> list[str]:
    """Every image file under ``images_dir``, as split-relative paths."""
    if not images_dir.exists():
        return []
    suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    roots = [images_dir / split] if split else [images_dir / s for s in SPLITS]
    found: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for item in sorted(root.rglob("*")):
            if item.suffix.lower() in suffixes and not item.name.startswith("."):
                found.append(item.relative_to(images_dir).as_posix())
    return found


def coverage(path: Path = LABELS_PATH, images_dir: Path = IMAGES_DIR) -> dict[str, Any]:
    """How much of the image set has been labeled, per split."""
    labels = load_labels(path)
    report: dict[str, Any] = {}
    for split in SPLITS:
        images = list_images(split, images_dir)
        done = [img for img in images if img in labels]
        report[split] = {
            "images": len(images),
            "labeled": len(done),
            "remaining": len(images) - len(done),
        }
    report["total_labeled"] = len(labels)
    return report


# ──────────────────────────────────────────────────────────────────────
#  Vocabulary served to the labeling UI
# ──────────────────────────────────────────────────────────────────────


def vocabulary() -> dict[str, Any]:
    """Every option the labeling tool offers, derived from the taxonomy.

    Generated rather than hardcoded in the HTML so the tool can never drift
    from ``backend.schemas.taxonomy``.
    """
    from backend.schemas.taxonomy import FORMALITY_CRITERIA, TYPE_CATEGORY

    return {
        "types": [
            {"value": t.value, "category": TYPE_CATEGORY[t].value if t in TYPE_CATEGORY else "other"}
            for t in GarmentType
        ],
        "accessories": [a.value for a in AccessoryType],
        "colors": [c.value for c in ColorName],
        "patterns": [p.value for p in PatternName],
        "aesthetics": [a.value for a in Aesthetic],
        "occasions": [o.value for o in Occasion],
        "formality": [
            {"level": int(f), "label": f.name.lower(), "criteria": FORMALITY_CRITERIA[int(f)]} for f in Formality
        ],
        "photo_kinds": list(PHOTO_KINDS),
        "splits": list(SPLITS),
    }
