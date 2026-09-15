"""Catalog retrieval evaluation — does hybrid RAG beat each arm alone?

The existing product-relevance eval measures *filtering*: given a fixed list of
candidates, does the matcher keep the right ones? Retrieval is a different
problem — the system must find the right products in a corpus it was not handed
— so it needs ranking metrics rather than a keep/drop confusion matrix.

Method: every product across the labelled fixtures becomes one corpus row (53
rows, 10 desired-item queries), normalized by the *production* ingest path so
the clothing-type filter sees exactly what it would in production. Each query
then runs through four configurations:

- ``lexical``   — PostgreSQL full text alone
- ``semantic``  — BGE embeddings + pgvector alone
- ``hybrid``    — the two fused by Reciprocal Rank Fusion
- ``reranked``  — hybrid, then reordered by the cross-encoder

Each configuration runs twice:

- **taxonomy_filter** — production settings, where clothing type and gender
  are hard filters before retrieval ranks anything.
- **retrieval_only** — the same queries with those filters removed, so the
  retriever must separate a blouse from a shirt on text alone.

The first answers "how does the shipped system behave"; the second is what
actually separates the arms, because after the taxonomy filter only a handful
of rows remain and every retriever finds them.

Metrics are ``recall@k``, ``precision@k`` and MRR against the fixtures' own
labels. One caveat is worth stating plainly: relevance is labelled *per case*,
so a product that would genuinely suit another case's query counts as a miss
there. Every number below is therefore a lower bound, and only comparable
between arms — which is what the comparison is for.

Rows are written under ``source='eval'`` and removed afterwards, so running
this never disturbs the real catalog.

Usage::

    poetry run python evaluation/catalog_retrieval.py
    poetry run python evaluation/catalog_retrieval.py --k 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete  # noqa: E402

from backend.agents.shopping_agent import build_item_spec  # noqa: E402
from backend.core.config import get_settings  # noqa: E402
from backend.db.session import async_session_factory  # noqa: E402
from backend.models.records import ProductCatalogItem  # noqa: E402
from backend.services.embeddings import EmbeddingService, classify_embedding  # noqa: E402
from backend.services.product_catalog import (  # noqa: E402
    CatalogDocument,
    CatalogQuery,
    ProductCatalogService,
    fuse_by_rank,
)
from evaluation.recording import record_if_asked  # noqa: E402

CASES_PATH = Path(__file__).resolve().parent / "product_cases.json"
EVAL_SOURCE = "eval"

ARMS = ("lexical", "semantic", "hybrid", "reranked")

# Shopping intent -> the catalog's `gender_lean` vocabulary.
GENDER_LEAN = {"menswear": "men", "womenswear": "women", "unisex": ""}


async def build_corpus(cases: list[dict[str, Any]]) -> list[CatalogDocument]:
    """Turn every fixture product into a catalog row.

    Distractors are kept, not dropped: a corpus containing only each query's
    own answers would make retrieval trivial. Their taxonomy comes from the
    same zero-shot heads the ingest job uses, so a women's blouse filed under a
    menswear-shirt case is classified as a blouse — exactly as in production.
    """
    embeddings = EmbeddingService()
    titles = [product["title"] for case in cases for product in case["products"]]
    title_embeddings = await embeddings.embed_texts(titles)

    documents: list[CatalogDocument] = []
    index = 0
    for case in cases:
        for product in case["products"]:
            embedding = title_embeddings[index]
            index += 1
            clothing_type, _ = classify_embedding(embedding, "clothing_type")
            color, _ = classify_embedding(embedding, "color")
            style, _ = classify_embedding(embedding, "style")
            gender, _ = classify_embedding(embedding, "gender")
            documents.append(
                CatalogDocument(
                    source=EVAL_SOURCE,
                    # Fixture links are all placeholders, so identity comes from
                    # the case the product belongs to plus its title.
                    external_id=f"{case['name']}::{product['title']}",
                    title=product["title"],
                    product_url="https://example.test/eval",
                    clothing_type=clothing_type,
                    color=color,
                    style=style,
                    store=product.get("source", ""),
                    price_display=product.get("price", ""),
                    gender_lean=GENDER_LEAN.get(gender, "") or "unisex",
                )
            )
    return documents


async def retrieve(
    catalog: ProductCatalogService,
    db: Any,
    query: CatalogQuery,
    *,
    arm: str,
    k: int,
) -> list[uuid.UUID]:
    """Run one retrieval configuration and return ranked catalog ids."""
    settings = get_settings()
    depth = settings.catalog_retrieval_limit

    if arm == "lexical":
        return (await catalog._lexical_ids(db, query, limit=depth))[:k]
    if arm == "semantic":
        return (await catalog._semantic_ids(db, query, limit=depth))[:k]

    lexical = await catalog._lexical_ids(db, query, limit=depth)
    semantic = await catalog._semantic_ids(db, query, limit=depth)
    fused = fuse_by_rank([lexical, semantic], k=settings.catalog_rrf_k)
    if arm == "hybrid":
        return fused[:k]

    items = await catalog._load_items(db, fused[: settings.catalog_rerank_limit])
    hits = await catalog._rerank(query, items)
    return [hit.item.id for hit in hits[:k]]


def score_arm(retrieved: list[uuid.UUID], relevant: set[uuid.UUID]) -> tuple[int, float]:
    """Hits in the returned list, and the reciprocal rank of the first one."""
    hits = sum(1 for item_id in retrieved if item_id in relevant)
    for rank, item_id in enumerate(retrieved, start=1):
        if item_id in relevant:
            return hits, 1.0 / rank
    return hits, 0.0


async def score_configuration(
    catalog: ProductCatalogService,
    db: Any,
    cases: list[dict[str, Any]],
    ids_by_external: dict[str, uuid.UUID],
    *,
    arm: str,
    k: int,
    taxonomy_filter: bool,
) -> dict[str, Any]:
    """Aggregate ranking metrics for one arm under one filter setting."""
    hits_total = relevant_total = returned_total = 0
    reciprocal_rank_total = 0.0
    per_case: list[dict[str, Any]] = []

    for case in cases:
        desired = case["desired"]
        relevant = {
            ids_by_external[f"{case['name']}::{product['title']}"]
            for product in case["products"]
            if product["relevant"]
        }
        query = CatalogQuery(
            text=build_item_spec(
                item_type=desired["item_type"],
                color=desired["color"],
                style=desired["style"],
                shopping_intent=desired["shopping_intent"],
            ),
            clothing_type=desired["item_type"] if taxonomy_filter else "",
            gender=GENDER_LEAN[desired["shopping_intent"]] if taxonomy_filter else "",
            # Score only the fixture corpus. Without this the numbers would move
            # with whatever else happens to be ingested on the machine, which is
            # the opposite of what a benchmark is for.
            sources=(EVAL_SOURCE,),
        )
        retrieved = await retrieve(catalog, db, query, arm=arm, k=k)
        hits, reciprocal_rank = score_arm(retrieved, relevant)

        hits_total += hits
        relevant_total += len(relevant)
        returned_total += len(retrieved)
        reciprocal_rank_total += reciprocal_rank
        per_case.append({"name": case["name"], "retrieved": len(retrieved), "relevant": len(relevant), "hits": hits})

    return {
        f"recall@{k}": round(hits_total / max(relevant_total, 1), 4),
        f"precision@{k}": round(hits_total / max(returned_total, 1), 4),
        "mrr": round(reciprocal_rank_total / max(len(cases), 1), 4),
        "cases": per_case,
    }


async def evaluate_catalog_retrieval(*, k: int = 5, cases_path: Path = CASES_PATH) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    documents = await build_corpus(cases)

    catalog = ProductCatalogService()
    reports: dict[str, Any] = {}

    async with async_session_factory() as db:
        await db.execute(delete(ProductCatalogItem).where(ProductCatalogItem.source == EVAL_SOURCE))
        await catalog.upsert(db, documents)
        await db.commit()

        # Map fixture identity back to the ids the retriever returns.
        ids_by_external = {
            item.external_id: item.id
            for item in (
                await db.execute(ProductCatalogItem.__table__.select().where(ProductCatalogItem.source == EVAL_SOURCE))
            )
        }

        try:
            for configuration, taxonomy_filter in (("taxonomy_filter", True), ("retrieval_only", False)):
                reports[configuration] = {
                    arm: await score_configuration(
                        catalog,
                        db,
                        cases,
                        ids_by_external,
                        arm=arm,
                        k=k,
                        taxonomy_filter=taxonomy_filter,
                    )
                    for arm in ARMS
                }
        finally:
            await db.execute(delete(ProductCatalogItem).where(ProductCatalogItem.source == EVAL_SOURCE))
            await db.commit()

    return {
        "corpus_size": len(documents),
        "num_queries": len(cases),
        "k": k,
        "configurations": reports,
    }


async def main() -> None:
    from backend.core.logging import setup_logging

    setup_logging("ERROR")
    parser = argparse.ArgumentParser(description="Evaluate catalog retrieval arms")
    parser.add_argument("--k", type=int, default=5, help="cut-off for recall/precision (default: 5)")
    parser.add_argument("--record", action="store_true", help="persist the run to PostgreSQL")
    args = parser.parse_args()

    report = await evaluate_catalog_retrieval(k=args.k)
    print(json.dumps(report, indent=2))

    # Flatten `configuration.arm.metric` into one level: the history table is
    # read by charts, and a nested blob would push that reshaping into every
    # consumer instead of doing it once here.
    metrics = {
        f"{configuration}.{arm}.{metric}": value
        for configuration, arms in report["configurations"].items()
        for arm, results in arms.items()
        for metric, value in results.items()
        if not isinstance(value, list)
    }
    await record_if_asked(args.record, "catalog_retrieval", num_cases=report["num_queries"], metrics=metrics)


if __name__ == "__main__":
    asyncio.run(main())
