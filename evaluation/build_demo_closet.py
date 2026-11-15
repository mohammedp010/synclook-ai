"""Build the demo closet once: ~25 labelled public photos → ``data/demo_closet/``.

``POST /closet/demo`` copies this folder into a visitor's closet with no model
call. Tags come from the hand-checked labels (``data/perception/labels.jsonl``),
not from perception, so the demo shows the engine on correct inputs:

- type, colour family, pattern, formality and occasions: from the label;
- shade and hex: measured from the pixels (``color_extraction``, as perception does);
- warmth: the labels have none, so ``_WARMTH`` sets it by garment type.

Run it again only to change the selection::

    poetry run python evaluation/build_demo_closet.py
"""

from __future__ import annotations

import json
import shutil
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.schemas.perception import GarmentTags, Warmth  # noqa: E402
from backend.schemas.taxonomy import COARSE_COLOR, ColorName, Formality, Occasion, PatternName  # noqa: E402
from backend.services.closet import DEMO_DIR, thumbnail_jpeg  # noqa: E402
from backend.services.color_extraction import extract_colors, name_from_description  # noqa: E402
from backend.services.perception import category_of  # noqa: E402

LABELS = PROJECT_ROOT / "data" / "perception" / "labels.jsonl"
IMAGES = PROJECT_ROOT / "data" / "perception" / "images"

# Picked for coverage of every slot and register: single-garment product, flat-lay or
# hanger shots where possible. (filename prefix in images/public, short label)
SELECTION: list[tuple[str, str]] = [
    # tops
    ("okm_shirt_front", "white graphic t-shirt"),
    ("gnaegi_unpacked", "charcoal t-shirt"),
    ("eepisat_black_polo", "charcoal polo"),
    ("sudadera_urban", "navy hoodie"),
    ("blue_business_shirt", "blue business shirt"),
    ("blouse_met_84_173", "cream blouse"),
    ("jersei_coll_alt", "khaki sweater"),
    ("blue_khadi_kurta", "blue khadi kurta"),
    # bottoms
    ("high_waisted_jeans", "blue jeans"),
    ("broek_en_jas_van_uniform", "charcoal jeans"),
    ("back_side_chino", "khaki chinos"),
    ("chino_pants", "beige trousers"),
    ("trousers_jpg", "brown trousers"),
    ("men_s_shorts_old_bull_lee", "orange shorts"),
    ("green_poplin_skirt_by_sybil_connolly_full", "green skirt"),
    # one-pieces
    ("dress_met_dt5703", "olive dress"),
    ("ethnic_jpg", "burgundy lehenga"),
    # outerwear
    ("man_in_black_suit_and_white_shirt", "black blazer"),
    ("coat_of_i_s_konev", "brown coat"),
    ("1980s_blue_denim_jacket_finland_01", "denim jacket"),
    # footwear
    ("converse_jack_purcell", "white sneakers"),
    ("louis_vuitton_mens_loafers", "black loafers"),
    ("a_penny_loafer", "brown penny loafers"),
    ("bootsbr", "black boots"),
    ("man_in_sandals_2", "brown sandals"),
    # accessories
    ("corum_coin_watch", "navy watch"),
    ("belt_buckle_blue_jeans_brown_leather_belt", "brown leather belt"),
]

_WARMTH: dict[str, Warmth] = {
    **dict.fromkeys(("t_shirt", "polo", "shorts", "sandals", "blouse", "skirt"), Warmth.LIGHT),
    **dict.fromkeys(("hoodie", "sweater", "coat", "boots"), Warmth.HEAVY),
}


def build() -> list[dict[str, object]]:
    labels = {Path(r["image"]).name: r for r in map(json.loads, LABELS.read_text().splitlines())}
    if DEMO_DIR.exists():
        shutil.rmtree(DEMO_DIR)
    DEMO_DIR.mkdir(parents=True)
    out: list[dict[str, object]] = []
    for n, (prefix, short_label) in enumerate(SELECTION, start=1):
        (name,) = [k for k in labels if k.startswith(prefix)]
        row = labels[name]
        primary = row["primary"]
        garment_type = primary["accessory"] or primary["type"]
        raw = (IMAGES / row["image"]).read_bytes()
        colour = name_from_description(extract_colors(Image.open(BytesIO(raw))), ColorName(primary["primary_color"]))
        secondary = primary["secondary_color"]
        tags = GarmentTags(
            garment_type=garment_type,
            category=category_of(garment_type),
            color=colour.name,
            color_family=COARSE_COLOR[colour.name],
            color_hex=colour.hex,
            secondary_color=ColorName(secondary) if secondary else None,
            pattern=PatternName(primary["pattern"]),
            formality=Formality(row["formality"]),
            warmth=_WARMTH.get(garment_type, Warmth.MEDIUM),
            occasions=[Occasion(o) for o in row["occasions"]],
            short_label=short_label,
        )
        file = f"{n:02d}_{garment_type}.jpg"
        (DEMO_DIR / file).write_bytes(thumbnail_jpeg(raw))
        out.append({"file": file, "source": row["image"], "tags": tags.model_dump(mode="json")})
    (DEMO_DIR / "items.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


if __name__ == "__main__":
    items = build()
    print(f"{len(items)} items → {DEMO_DIR.relative_to(PROJECT_ROOT)}")
