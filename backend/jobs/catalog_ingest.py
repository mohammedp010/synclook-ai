"""Catalog ingestion — populate the retrieval corpus.

Products enter the corpus from one of two sources:

- **A provider grid** (``--grid``): a cross product of the garment slots the
  recommendation engine can actually ask for, one provider search each. Every
  slot costs one SerpAPI credit, so the grid is capped and must be widened
  deliberately.
- **A JSON seed file** (``--from-file``): the same records, checked in. This is
  what makes retrieval evaluation reproducible and what lets the demo run
  without an API key or a network.

Whatever the source, every product is normalized the same way before it is
stored: the title is classified against the *same* CLIP zero-shot heads the
vision pipeline uses, so a catalog row's ``clothing_type`` means exactly what
it means everywhere else in the system. Products whose title classifies to a
different garment than the query asked for are dropped — mislabelled rows
would poison the retrieval filter, and a filter that cannot be trusted is
worse than no filter.

The thumbnail is fetched and embedded too — ingestion is offline, so unlike
the live path it can afford every image — and that embedding is what fills
``image_embedding``.

It also acts as a check on the title, but only a coarse one. Measured on real
garment photos, CLIP ViT-B/32 confuses neighbouring garments badly: a
photograph of a blazer classifies as *blouse*, and a picture of buttons
classifies as *other* with low confidence. Vetoing on exact type would
therefore throw away correct products. Vetoing on **category** — topwear vs
bottomwear vs shoes vs accessory — is a distinction the same model makes
reliably, so that is the granularity of the gate: a "blazer" whose photo is
plainly a pair of shoes is dropped, a blazer that photographs like a blouse is
not.

A third mode, ``--refresh``, re-asks the questions the corpus was built from.
Ingested rows would otherwise assert availability forever: nothing expires a
product that sold out the day after it was indexed. Refreshing upserts whatever
still comes back (which rolls ``last_seen_at`` forward) and demotes what does
not — conservatively, since one search missing a product is not proof it is
gone. See ``ProductCatalogService.deactivate_unseen``.

Usage::

    poetry run python -m backend.jobs.catalog_ingest --from-file data/catalog_seed.json
    poetry run python -m backend.jobs.catalog_ingest --grid --max-queries 20
    poetry run python -m backend.jobs.catalog_ingest --grid --dry-run --export data/catalog_seed.json
    poetry run python -m backend.jobs.catalog_ingest --refresh --max-queries 10
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

from backend.core.config import get_settings
from backend.core.logging import get_logger, setup_logging
from backend.db.session import async_session_factory
from backend.schemas.api import ProductLink
from backend.schemas.clothing import ClothingType, Color
from backend.services.embeddings import EmbeddingService, classify_embedding
from backend.services.product_catalog import CatalogDocument, ProductCatalogService
from backend.services.product_search import ProductSearchService
from backend.tools.style_rules import CLOTHING_TYPE_CATEGORIES

logger = get_logger(__name__)

# The garment slots the rule engine can put in an outfit. Accessories are
# excluded: the taxonomy lumps belts, bags and watches together, so a
# "accessory" filter would retrieve an unusable mix.
GRID_TYPES: tuple[ClothingType, ...] = (
    ClothingType.SHIRT,
    ClothingType.TSHIRT,
    ClothingType.TROUSERS,
    ClothingType.JEANS,
    ClothingType.CHINOS,
    ClothingType.SHORTS,
    ClothingType.BLAZER,
    ClothingType.JACKET,
    ClothingType.SWEATER,
    ClothingType.HOODIE,
    ClothingType.DRESS,
    ClothingType.SKIRT,
    ClothingType.SHOES,
)

# Neutrals first: the colour rules pair almost everything with them, so a
# truncated grid should still cover the combinations most outfits need.
GRID_COLORS: tuple[Color, ...] = (
    Color.BLACK,
    Color.WHITE,
    Color.NAVY,
    Color.GREY,
    Color.BEIGE,
    Color.BLUE,
    Color.BROWN,
    Color.GREEN,
    Color.RED,
)

GRID_GENDERS: tuple[str, ...] = ("men", "women")

# Digits and separators of an Indian price string: "₹1,299.00" -> 1299.
_PRICE_PATTERN = re.compile(r"(\d[\d,]*)(?:\.\d+)?")

# Below this the zero-shot head is guessing, and a guessed category is worse
# than dropping the row. Matches the gate the shopping agent applies live.
MIN_CLASSIFICATION_CONFIDENCE = 0.35

# Confidence a thumbnail needs before it may overrule the title. Lower than
# the live path's 0.5 because this gate is category-level, not type-level:
# measured on real photos, CLIP's top-1 confidence over the 18-way garment head
# sits around 0.35-0.45 even when correct (a shoe photo scores `shoes` at
# 0.44), so 0.5 effectively disables the gate. The same-category confusions
# that dominate CLIP's errors — blazer read as blouse at 0.39 — cannot trigger
# a category veto at any threshold, which is what makes the lower bar safe.
IMAGE_VETO_MIN_CONFIDENCE = 0.35

# Shopping-intent labels from the gender head, mapped onto the catalog column.
_GENDER_LEAN = {"menswear": "men", "womenswear": "women"}

# What the thumbnail veto compares. Coarser than `CLOTHING_TYPE_CATEGORIES`,
# which keeps topwear and outerwear apart because outfit composition needs
# them apart — but that is exactly the distinction CLIP cannot make from a
# photo (a real blazer reads as `blouse` at 0.39, and vetoing on it would
# discard correct products). Grouping by where a garment is worn restricts the
# gate to differences a photograph actually shows.
_VETO_GROUPS = {
    "topwear": "upper body",
    "outerwear": "upper body",
    "bottomwear": "lower body",
    "footwear": "feet",
    "accessory": "accessory",
}


@dataclass(frozen=True)
class GridSlot:
    """One provider query: a garment, a colour and an audience."""

    clothing_type: ClothingType
    color: Color
    gender: str

    @property
    def query(self) -> str:
        # "for unisex" is not a phrase shoppers or providers use; an audience is
        # only stated when it narrows the search.
        audience = f" for {self.gender}" if self.gender in {"men", "women"} else ""
        return f"{self.color.value} {self.clothing_type.value}{audience}"


def build_grid(*, max_queries: int) -> list[GridSlot]:
    """Enumerate slots, colour-major so a truncated grid stays broad.

    Iterating colours innermost would spend the whole budget on shirts. Types
    outermost with colours cycling means a 20-query run covers 20 different
    garment/colour pairs rather than one garment in 20 colours.
    """
    slots = [
        GridSlot(clothing_type=clothing_type, color=color, gender=gender)
        for color, gender, clothing_type in product(GRID_COLORS, GRID_GENDERS, GRID_TYPES)
    ]
    return slots[:max_queries]


def parse_price_inr(display: str) -> int | None:
    """Extract whole rupees from a provider price string, or None."""
    match = _PRICE_PATTERN.search(display or "")
    if match is None:
        return None
    return int(match.group(1).replace(",", ""))


def external_id_for(link: str) -> str:
    """Stable identity for a listing.

    The provider's own product id is not exposed by ``ProductSearchService``,
    so the canonical URL stands in. Hashing keeps it inside the column width
    and out of the logs regardless of how long the tracking-laden URL is.
    """
    return hashlib.sha256(link.encode()).hexdigest()


async def normalize(
    products: list[ProductLink],
    *,
    slot: GridSlot,
    embeddings: EmbeddingService,
) -> list[CatalogDocument]:
    """Classify provider results onto the project taxonomy, dropping mismatches."""
    if not products:
        return []

    title_embeddings = await embeddings.embed_texts([p.title for p in products])
    # Unfetchable thumbnails come back as None; the product is then judged on
    # its title alone rather than being penalized for a broken image host.
    thumbnail_embeddings = await asyncio.gather(*(embeddings.embed_image_url(p.thumbnail) for p in products))

    documents: list[CatalogDocument] = []
    for link, embedding, thumbnail in zip(products, title_embeddings, thumbnail_embeddings, strict=True):
        clothing_type, type_confidence = classify_embedding(embedding, "clothing_type")
        if clothing_type != slot.clothing_type.value or type_confidence < MIN_CLASSIFICATION_CONFIDENCE:
            _log_rejection(link.title, expected=slot.clothing_type.value, got=clothing_type, by="title")
            continue

        if thumbnail is not None and _image_contradicts(thumbnail, clothing_type):
            _log_rejection(link.title, expected=clothing_type, got="image category", by="thumbnail")
            continue

        color, _ = classify_embedding(embedding, "color")
        style, _ = classify_embedding(embedding, "style")
        gender, _ = classify_embedding(embedding, "gender")

        documents.append(
            CatalogDocument(
                source="serpapi",
                external_id=external_id_for(link.link),
                title=link.title,
                product_url=link.link,
                clothing_type=clothing_type,
                color=color,
                style=style,
                store=link.source,
                thumbnail_url=link.thumbnail,
                price_inr=parse_price_inr(link.price),
                price_display=link.price,
                # The product's own lean, not the slot's: a women's blazer
                # surfaced by a menswear query is still a women's blazer, and
                # filing it under "men" would sell it to the wrong shopper.
                gender_lean=_GENDER_LEAN.get(gender, "unisex"),
                image_embedding=thumbnail,
            )
        )
    return documents


def _veto_group(clothing_type: str) -> str | None:
    category = CLOTHING_TYPE_CATEGORIES.get(ClothingType(clothing_type))
    return _VETO_GROUPS.get(category or "")


def _image_contradicts(thumbnail: list[float], clothing_type: str) -> bool:
    """True when the photo confidently shows a garment worn somewhere else."""
    image_type, confidence = classify_embedding(thumbnail, "clothing_type")
    if confidence < IMAGE_VETO_MIN_CONFIDENCE:
        return False
    expected, seen = _veto_group(clothing_type), _veto_group(image_type)
    return expected is not None and seen is not None and expected != seen


def _log_rejection(title: str, *, expected: str, got: str, by: str) -> None:
    logger.debug("catalog_ingest_rejected", title=title[:60], expected=expected, classified=got, source=by)


async def search_with_retry(
    search: ProductSearchService,
    query: str,
    *,
    attempts: int = 2,
    backoff_s: float = 1.0,
) -> list[ProductLink]:
    """Run one provider query, retrying transport failures.

    Measured on the first real ingest: 8 of 12 queries failed with an empty
    transport error while the same query answered in 0.7s when issued on its
    own, so the failures are local and transient — most likely sockets still
    winding down from the thumbnail fetches between queries.

    A retry is not free: the failed attempt already spent its credit and the
    retry spends another. It is still the cheaper option, because the
    alternative is a credit spent for no row at all.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await search.search(query)
        except Exception as exc:
            if attempt == attempts:
                logger.warning("catalog_query_failed", query=query, error=str(exc), attempts=attempts)
                return []
            logger.info("catalog_query_retry", query=query, error=str(exc), attempt=attempt)
            await asyncio.sleep(backoff_s)
    return []


async def collect_from_provider(slots: list[GridSlot]) -> list[CatalogDocument]:
    """Run the grid against the provider and normalize everything it returns.

    Queries run sequentially on purpose: this is an offline job with no latency
    budget, and providers rate-limit bursts far more readily than steady load.
    """
    search = ProductSearchService()
    if not search.enabled:
        raise SystemExit("SERPAPI_API_KEY is required for --grid; use --from-file for an offline ingest")

    embeddings = EmbeddingService()
    documents: list[CatalogDocument] = []
    for index, slot in enumerate(slots, start=1):
        products = await search_with_retry(search, slot.query)
        if not products:
            continue
        normalized = await normalize(products, slot=slot, embeddings=embeddings)
        documents.extend(normalized)
        logger.info(
            "catalog_ingest_query",
            progress=f"{index}/{len(slots)}",
            query=slot.query,
            returned=len(products),
            kept=len(normalized),
        )
    return documents


def load_from_file(path: Path) -> list[CatalogDocument]:
    """Read documents previously written by ``--export``."""
    records = json.loads(path.read_text())
    return [CatalogDocument(**record) for record in records]


def deduplicate(documents: list[CatalogDocument]) -> list[CatalogDocument]:
    """Keep one document per identity — a batched upsert cannot self-conflict.

    PostgreSQL rejects ``ON CONFLICT`` when a single statement presents the
    same key twice, and grid slots overlap constantly (the same navy blazer
    answers both "navy blazer" and "blue blazer").
    """
    unique: dict[tuple[str, str], CatalogDocument] = {}
    for document in documents:
        unique.setdefault((document.source, document.external_id), document)
    return list(unique.values())


def slots_from_catalog(rows: list[tuple[str, str, str]], *, max_queries: int) -> list[tuple[GridSlot, str]]:
    """Turn stored (type, colour, audience) triples back into provider queries.

    Rows whose taxonomy is not in the enums are skipped rather than guessed at:
    they cannot have come from this job's normalizer, so re-querying them would
    be asking the provider a question the corpus never asked.
    """
    slots: list[tuple[GridSlot, str]] = []
    for clothing_type, color, gender_lean in rows:
        try:
            slot = GridSlot(
                clothing_type=ClothingType(clothing_type),
                color=Color(color),
                gender=gender_lean,
            )
        except ValueError:
            logger.debug("catalog_refresh_skipped_slot", clothing_type=clothing_type, color=color)
            continue
        slots.append((slot, gender_lean))
    return slots[:max_queries]


async def refresh(*, max_queries: int, source: str, confirmed_within_days: int) -> tuple[int, int]:
    """Re-confirm availability for the slots the corpus already holds.

    Each slot costs one credit, same as ingestion — this *is* an ingest, just
    of products we have seen before. Products that come back are upserted,
    which refreshes price, copy and ``last_seen_at``; products that do not come
    back are handed to ``deactivate_unseen``, which demotes only those that
    have also been missing for a while.
    """
    search = ProductSearchService()
    if not search.enabled:
        raise SystemExit("SERPAPI_API_KEY is required for --refresh")

    catalog = ProductCatalogService()
    embeddings = EmbeddingService()

    async with async_session_factory() as session:
        stored = await catalog.distinct_slots(session, source=source)
    slots = slots_from_catalog(stored, max_queries=max_queries)
    if not slots:
        logger.info("catalog_refresh_empty", source=source)
        return 0, 0

    confirmed = 0
    demoted = 0
    for index, (slot, gender_lean) in enumerate(slots, start=1):
        products = await search_with_retry(search, slot.query)
        if not products:
            # A failed query proves nothing about availability, so this slot is
            # left entirely untouched rather than demoted on a network error.
            logger.warning("catalog_refresh_query_empty", query=slot.query)
            continue

        documents = deduplicate(await normalize(products, slot=slot, embeddings=embeddings))
        async with async_session_factory() as session:
            if documents:
                confirmed += await catalog.upsert(session, documents)
            demoted += await catalog.deactivate_unseen(
                session,
                source=source,
                clothing_type=slot.clothing_type.value,
                gender_lean=gender_lean,
                seen_external_ids=[doc.external_id for doc in documents],
                confirmed_within_days=confirmed_within_days,
            )
            await session.commit()
        logger.info(
            "catalog_refresh_query",
            progress=f"{index}/{len(slots)}",
            query=slot.query,
            returned=len(products),
            confirmed=len(documents),
        )
    return confirmed, demoted


async def ingest(documents: list[CatalogDocument]) -> int:
    catalog = ProductCatalogService()
    async with async_session_factory() as session:
        written = await catalog.upsert(session, documents)
        await session.commit()
        total = await catalog.count(session)
    logger.info("catalog_ingest_complete", written=written, catalog_size=total)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Populate the product retrieval catalog")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--grid", action="store_true", help="query the provider over the taxonomy grid")
    source.add_argument("--from-file", type=Path, help="ingest a previously exported JSON seed file")
    source.add_argument(
        "--refresh",
        action="store_true",
        help="re-confirm availability for slots already in the catalog (costs one credit per slot)",
    )
    parser.add_argument(
        "--source",
        default="serpapi",
        help="provenance to refresh (default: serpapi)",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=20,
        help="cap on provider searches; each one costs an API credit (default: 20)",
    )
    parser.add_argument("--export", type=Path, help="write the normalized documents to JSON as well")
    parser.add_argument("--dry-run", action="store_true", help="collect and report, but do not write to the database")
    return parser.parse_args()


async def main() -> None:
    setup_logging("INFO")
    args = parse_args()

    if args.refresh:
        confirmed, demoted = await refresh(
            max_queries=args.max_queries,
            source=args.source,
            confirmed_within_days=get_settings().catalog_stale_after_days,
        )
        print(f"re-confirmed {confirmed} products; marked {demoted} out of stock")
        return

    if args.grid:
        documents = await collect_from_provider(build_grid(max_queries=args.max_queries))
    else:
        documents = load_from_file(args.from_file)

    documents = deduplicate(documents)
    print(f"collected {len(documents)} unique products")

    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text(json.dumps([asdict(d) for d in documents], indent=2, ensure_ascii=False))
        print(f"exported to {args.export}")

    if args.dry_run:
        print("dry run — nothing written to the database")
        return

    written = await ingest(documents)
    print(f"upserted {written} products")


if __name__ == "__main__":
    asyncio.run(main())
