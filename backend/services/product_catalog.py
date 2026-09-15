"""Product catalog retrieval — hybrid lexical + vector search over pgvector.

This is the RAG layer for shopping. Live provider search answers "what does
the store have for this phrase right now"; the catalog answers "what in our
own indexed corpus best serves this outfit slot", reproducibly and without a
network hop per query.

Retrieval runs two arms over the same filtered candidate set:

- **Lexical** — PostgreSQL full-text over a generated ``tsvector``. Exact on
  brand names, model numbers and rare words, where embeddings blur ("Levi's
  511" and "Levi's 501" are near-identical vectors).
- **Semantic** — cosine over BGE embeddings via an HNSW index. Catches phrasing
  the corpus does not literally contain ("office wear" -> "formal trousers").

Their scores are not comparable (``ts_rank_cd`` is unbounded and corpus
dependent, cosine is [-1, 1]), so they are combined by **Reciprocal Rank
Fusion**, which reads only the ranks. RRF needs no per-corpus tuning and no
score normalization, which is exactly why it is the default fusion for hybrid
search.

A cross-encoder then reranks the fused shortlist (see
:mod:`backend.services.reranker`). Every stage degrades to the previous one:
no reranker means fusion order, no matches in one arm means the other arm
alone, an empty catalog means the caller falls back to live search.

Superseding note: [ADR 002](../../docs/adr/002-no-vector-database-yet.md) argued
against a vector database while the only corpus was a user's few-hundred-item
wardrobe. That reasoning still holds for the wardrobe, which continues to scan
in Python; it does not hold for a catalog of thousands of products.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import ColumnElement, Select, desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.models.records import ProductCatalogItem
from backend.schemas.api import ProductLink
from backend.services.reranker import RerankerService
from backend.services.text_embeddings import TextEmbeddingService

logger = get_logger(__name__)

# Fields refreshed when re-ingesting a product we have already seen. Provenance
# (id, source, external_id, created_at) is immutable by definition.
_REFRESHABLE_COLUMNS = (
    "title",
    "description",
    "brand",
    "store",
    "product_url",
    "thumbnail_url",
    "price_inr",
    "price_display",
    "clothing_type",
    "color",
    "style",
    "gender_lean",
    "text_embedding",
    "image_embedding",
    "in_stock",
)


@dataclass(frozen=True)
class CatalogDocument:
    """An ingest-ready product, already normalized onto the project taxonomy."""

    source: str
    external_id: str
    title: str
    product_url: str
    clothing_type: str
    color: str
    description: str = ""
    brand: str = ""
    store: str = ""
    thumbnail_url: str = ""
    price_inr: int | None = None
    price_display: str = ""
    style: str = ""
    gender_lean: str = "unisex"
    image_embedding: list[float] | None = None

    @property
    def searchable_text(self) -> str:
        """The text that gets embedded and shown to the cross-encoder.

        Taxonomy terms are appended to the human-readable copy: a title like
        "Louis Philippe Slim Fit Formal Wear" never says "trousers", and both
        the bi-encoder and the cross-encoder score better when the category is
        stated rather than implied.
        """
        return catalog_text(
            title=self.title,
            brand=self.brand,
            description=self.description,
            clothing_type=self.clothing_type,
            color=self.color,
            style=self.style,
        )


@dataclass(frozen=True)
class CatalogQuery:
    """A retrieval request for one outfit slot."""

    text: str
    clothing_type: str = ""
    gender: str = ""
    max_price_inr: int | None = None

    # Restrict retrieval to specific ingestion sources. Unset in the request
    # path — production searches the whole catalog — but it is what lets the
    # retrieval benchmark score a fixed corpus on a database that may hold
    # unrelated rows, and what would scope a search to a trusted feed.
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogHit:
    """A retrieved product with the score that ordered it."""

    item: ProductCatalogItem
    score: float
    reason: str
    # Per-arm provenance: which retriever found this product, at what rank, and
    # what the cross-encoder made of it. `reason` is the one-line summary of the
    # same story, kept for logs and for callers that want a single string.
    evidence: tuple[str, ...] = ()

    def to_product_link(self) -> ProductLink:
        return ProductLink(
            title=self.item.title,
            price=self.item.price_display,
            link=self.item.product_url,
            thumbnail=self.item.thumbnail_url,
            source=self.item.store or self.item.source,
            match_score=round(min(max(self.score, 0.0), 1.0), 2),
            match_reason=self.reason,
            match_evidence=list(self.evidence),
        )


def catalog_text(
    *,
    title: str,
    brand: str = "",
    description: str = "",
    clothing_type: str = "",
    color: str = "",
    style: str = "",
) -> str:
    """Assemble the canonical searchable representation of a product."""
    taxonomy = " ".join(part.replace("_", " ") for part in (color, clothing_type, style) if part)
    parts = (brand, title, description, taxonomy)
    return " ".join(part.strip() for part in parts if part.strip())


def to_websearch_query(text: str) -> str:
    """Rewrite free text as an OR-joined ``websearch_to_tsquery`` expression.

    PostgreSQL's ``websearch_to_tsquery`` ANDs bare terms, so "navy formal
    blazer" would miss a product titled "Navy Blazer" — unacceptable recall for
    one arm of a fused retriever, where precision comes from ranking and from
    the other arm. Joining with OR keeps every partial match and lets
    ``ts_rank_cd`` sort by how much of the query a document covers.

    Operator characters are stripped rather than escaped: ``websearch_to_tsquery``
    tolerates malformed input, but quotes and dashes would silently change the
    query's meaning.
    """
    tokens = ["".join(ch for ch in term if ch.isalnum()) for term in text.lower().split()]
    return " OR ".join(token for token in tokens if token)


def fuse_by_rank(
    rankings: Sequence[Sequence[uuid.UUID]],
    *,
    k: int,
) -> list[uuid.UUID]:
    """Reciprocal Rank Fusion over several ranked id lists.

    Each list contributes ``1 / (k + rank)`` to every id it contains; ``k``
    damps the head of the list so a single arm's top hit cannot outvote broad
    agreement between arms. Ids are returned best-fused-score first, with ties
    broken deterministically by the order in which they were first seen.
    """
    scores: dict[uuid.UUID, float] = {}
    first_seen: dict[uuid.UUID, int] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(item_id, len(first_seen))
    return sorted(scores, key=lambda item_id: (-scores[item_id], first_seen[item_id]))


def arm_ranks(
    lexical: Sequence[uuid.UUID],
    semantic: Sequence[uuid.UUID],
) -> dict[uuid.UUID, tuple[int | None, int | None]]:
    """Which arm found each id, and at what rank. ``None`` means "not by this arm".

    ``fuse_by_rank`` deliberately collapses this — it reads ranks and returns a
    single order — so provenance has to be recovered from the input lists before
    it is lost.
    """
    lexical_rank = {item_id: rank for rank, item_id in enumerate(lexical, start=1)}
    semantic_rank = {item_id: rank for rank, item_id in enumerate(semantic, start=1)}
    return {
        item_id: (lexical_rank.get(item_id), semantic_rank.get(item_id)) for item_id in {*lexical_rank, *semantic_rank}
    }


def freshness_fact(last_seen_at: datetime | None) -> str:
    """How long ago this row's availability was actually confirmed.

    Retrieval already refuses rows outside the freshness window; this states
    the age of the ones it kept, so "in stock" reads as a dated observation
    rather than a standing promise.
    """
    if last_seen_at is None:
        return ""
    seen = last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=UTC)
    days = (datetime.now(UTC) - seen).days
    if days <= 0:
        return "Stock confirmed today"
    if days == 1:
        return "Stock confirmed yesterday"
    return f"Stock confirmed {days} days ago"


def unseen_rows_stmt(
    *,
    source: str,
    clothing_type: str,
    gender_lean: str,
    seen_external_ids: Sequence[str],
    confirmed_within_days: int,
) -> Any:
    """The UPDATE behind :meth:`ProductCatalogService.deactivate_unseen`.

    Built as a free function so its guards can be asserted by compiling the
    statement, the way the retrieval filters are — the dangerous failure here is
    a missing WHERE clause, which is exactly what a compiled statement shows.
    """
    cutoff = datetime.now(UTC) - timedelta(days=confirmed_within_days)
    return (
        update(ProductCatalogItem)
        .where(
            ProductCatalogItem.source == source,
            ProductCatalogItem.clothing_type == clothing_type,
            ProductCatalogItem.gender_lean == gender_lean,
            ProductCatalogItem.in_stock.is_(True),
            ProductCatalogItem.last_seen_at < cutoff,
            # An empty "seen" list must still scope to the slot, never match
            # everything: NOT IN ('') excludes nothing but stays well-formed.
            ProductCatalogItem.external_id.notin_(list(seen_external_ids) or [""]),
        )
        .values(in_stock=False)
    )


def retrieval_evidence(
    *,
    lexical_rank: int | None,
    semantic_rank: int | None,
    rerank_score: float | None,
    fusion_rank: int,
    last_seen_at: datetime | None = None,
) -> tuple[str, ...]:
    """Readable retrieval provenance for one hit.

    Written for a user, not a log line: "keyword search ranked it #2" says what
    happened without assuming the reader knows what a tsvector or a bi-encoder
    is. Agreement between the arms is stated explicitly because it is the single
    strongest signal RRF acts on.
    """
    facts: list[str] = []
    if lexical_rank is not None:
        facts.append(f"Keyword search ranked it #{lexical_rank}")
    if semantic_rank is not None:
        facts.append(f"Vector search ranked it #{semantic_rank}")
    if lexical_rank is not None and semantic_rank is not None:
        facts.append("Both retrieval arms agreed on it")
    if rerank_score is not None:
        facts.append(f"Cross-encoder relevance {rerank_score:.2f}")
    else:
        facts.append(f"Ranked #{fusion_rank} by rank fusion (reranker unavailable)")
    freshness = freshness_fact(last_seen_at)
    if freshness:
        facts.append(freshness)
    return tuple(facts)


@dataclass
class ProductCatalogService:
    """Hybrid retrieval and ingestion for the local product corpus."""

    text_embeddings: TextEmbeddingService = field(default_factory=TextEmbeddingService)
    reranker: RerankerService = field(default_factory=RerankerService)

    # ── Retrieval ─────────────────────────────────────────────────────

    async def search(self, db: AsyncSession, query: CatalogQuery, *, limit: int = 5) -> list[CatalogHit]:
        """Retrieve, fuse and rerank catalog products for one outfit slot."""
        settings = get_settings()
        candidates = settings.catalog_retrieval_limit

        lexical = await self._lexical_ids(db, query, limit=candidates)
        semantic = await self._semantic_ids(db, query, limit=candidates)
        fused = fuse_by_rank([lexical, semantic], k=settings.catalog_rrf_k)
        if not fused:
            return []

        shortlist = await self._load_items(db, fused[: settings.catalog_rerank_limit])
        hits = await self._rerank(query, shortlist, arm_ranks(lexical, semantic))

        logger.info(
            "catalog_search",
            query=query.text,
            clothing_type=query.clothing_type,
            lexical=len(lexical),
            semantic=len(semantic),
            fused=len(fused),
            returned=min(len(hits), limit),
        )
        return hits[:limit]

    async def _lexical_ids(self, db: AsyncSession, query: CatalogQuery, *, limit: int) -> list[uuid.UUID]:
        expression = to_websearch_query(query.text)
        if not expression:
            return []
        tsquery = func.websearch_to_tsquery("english", expression)
        rank = func.ts_rank_cd(ProductCatalogItem.search_document, tsquery).label("rank")
        stmt = (
            self._filtered(select(ProductCatalogItem.id, rank), query)
            .where(ProductCatalogItem.search_document.bool_op("@@")(tsquery))
            .order_by(desc(rank))
            .limit(limit)
        )
        rows = await db.execute(stmt)
        return [row.id for row in rows]

    async def _semantic_ids(self, db: AsyncSession, query: CatalogQuery, *, limit: int) -> list[uuid.UUID]:
        embedding = await self.text_embeddings.embed_query(query.text)
        # Ordering by cosine distance is what lets PostgreSQL use the HNSW
        # index; the WHERE clauses are applied after the index scan, so we
        # over-fetch (`catalog_retrieval_limit` is deliberately well above the
        # handful of products a slot needs) rather than tune `hnsw.ef_search`.
        distance = ProductCatalogItem.text_embedding.cosine_distance(embedding)
        stmt = self._filtered(select(ProductCatalogItem.id), query).order_by(distance).limit(limit)
        rows = await db.execute(stmt)
        return [row.id for row in rows]

    def _filtered(self, stmt: Select[Any], query: CatalogQuery) -> Select[Any]:
        """Apply the hard constraints both arms share.

        Clothing type is a filter, not a ranking signal: the pipeline asks for a
        specific slot, and a shirt returned for a trousers slot is never a
        useful result however similar it scores. Colour deliberately is *not*
        filtered — it rides in the query text, where a near-miss shade can still
        rank if nothing exact exists.

        Availability is two clauses, not one. ``in_stock`` is what a refresh
        actually observed; the ``last_seen_at`` window covers the case nothing
        observed anything — an un-refreshed corpus ages out instead of serving
        stock claims it can no longer support. A slot that empties this way
        falls through to live search, which is the honest answer when the local
        corpus has gone stale.
        """
        settings = get_settings()
        clauses: list[ColumnElement[bool]] = [ProductCatalogItem.in_stock.is_(True)]
        if settings.catalog_stale_after_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=settings.catalog_stale_after_days)
            clauses.append(ProductCatalogItem.last_seen_at >= cutoff)
        if query.sources:
            clauses.append(ProductCatalogItem.source.in_(query.sources))
        if query.clothing_type:
            clauses.append(ProductCatalogItem.clothing_type == query.clothing_type)
        if query.gender:
            clauses.append(ProductCatalogItem.gender_lean.in_([query.gender, "unisex"]))
        if query.max_price_inr is not None:
            clauses.append(
                or_(ProductCatalogItem.price_inr.is_(None), ProductCatalogItem.price_inr <= query.max_price_inr)
            )
        return stmt.where(*clauses)

    async def _load_items(self, db: AsyncSession, ids: Sequence[uuid.UUID]) -> list[ProductCatalogItem]:
        """Fetch the shortlist in one round-trip, preserving the fused order."""
        rows = await db.execute(select(ProductCatalogItem).where(ProductCatalogItem.id.in_(ids)))
        by_id = {item.id: item for item in rows.scalars()}
        return [by_id[item_id] for item_id in ids if item_id in by_id]

    async def _rerank(
        self,
        query: CatalogQuery,
        items: list[ProductCatalogItem],
        ranks: dict[uuid.UUID, tuple[int | None, int | None]] | None = None,
    ) -> list[CatalogHit]:
        if not items:
            return []
        arms = ranks or {}
        fusion_positions = {item.id: position for position, item in enumerate(items, start=1)}

        def evidence_for(item: ProductCatalogItem, rerank_score: float | None) -> tuple[str, ...]:
            lexical_rank, semantic_rank = arms.get(item.id, (None, None))
            return retrieval_evidence(
                lexical_rank=lexical_rank,
                semantic_rank=semantic_rank,
                rerank_score=rerank_score,
                fusion_rank=fusion_positions.get(item.id, 0),
                last_seen_at=getattr(item, "last_seen_at", None),
            )

        documents = [
            catalog_text(
                title=item.title,
                brand=item.brand,
                description=item.description,
                clothing_type=item.clothing_type,
                color=item.color,
                style=item.style,
            )
            for item in items
        ]
        ranked = await self.reranker.rerank(query.text, documents)
        if not self.reranker.enabled:
            # Fusion order already ranks these; expose a descending score so
            # callers can threshold consistently either way.
            return [
                CatalogHit(
                    item=item,
                    score=_fusion_score(position, len(items)),
                    reason="hybrid retrieval (fused)",
                    evidence=evidence_for(item, None),
                )
                for position, item in enumerate(items)
            ]
        return [
            CatalogHit(
                item=items[candidate.index],
                score=candidate.score,
                reason=f"hybrid retrieval; cross-encoder relevance {candidate.score:.2f}",
                evidence=evidence_for(items[candidate.index], candidate.score),
            )
            for candidate in ranked
        ]

    # ── Ingestion ─────────────────────────────────────────────────────

    async def upsert(self, db: AsyncSession, documents: Sequence[CatalogDocument]) -> int:
        """Embed and insert products, refreshing any already ingested.

        Embedding happens in one batched forward pass per call, and only here —
        never on the request path. Re-ingesting the same ``(source,
        external_id)`` updates price, availability and copy in place, so the
        job is safe to re-run on a schedule.
        """
        if not documents:
            return 0

        embeddings = await self.text_embeddings.embed_documents([doc.searchable_text for doc in documents])
        rows = [
            {
                "id": uuid.uuid4(),
                "source": doc.source,
                "external_id": doc.external_id,
                "title": doc.title,
                "description": doc.description,
                "brand": doc.brand,
                "store": doc.store,
                "product_url": doc.product_url,
                "thumbnail_url": doc.thumbnail_url,
                "price_inr": doc.price_inr,
                "price_display": doc.price_display,
                "clothing_type": doc.clothing_type,
                "color": doc.color,
                "style": doc.style,
                "gender_lean": doc.gender_lean,
                "text_embedding": embedding,
                "image_embedding": doc.image_embedding,
                "in_stock": True,
            }
            for doc, embedding in zip(documents, embeddings, strict=True)
        ]

        stmt = pg_insert(ProductCatalogItem).values(rows)
        refreshed = {column: getattr(stmt.excluded, column) for column in _REFRESHABLE_COLUMNS}
        refreshed["last_seen_at"] = func.now()
        await db.execute(
            stmt.on_conflict_do_update(
                constraint="uq_product_catalog_source_external_id",
                set_=refreshed,
            )
        )
        logger.info("catalog_upsert", documents=len(rows), source=rows[0]["source"])
        return len(rows)

    async def distinct_slots(self, db: AsyncSession, *, source: str = "") -> list[tuple[str, str, str]]:
        """The (type, colour, audience) combinations the corpus actually holds.

        A refresh re-asks the questions that produced the corpus, rather than
        walking the full ingest grid: slots nothing was ever ingested for would
        spend credits to confirm the absence of rows that do not exist.
        """
        stmt = select(
            ProductCatalogItem.clothing_type,
            ProductCatalogItem.color,
            ProductCatalogItem.gender_lean,
        ).distinct()
        if source:
            stmt = stmt.where(ProductCatalogItem.source == source)
        stmt = stmt.order_by(
            ProductCatalogItem.clothing_type,
            ProductCatalogItem.color,
            ProductCatalogItem.gender_lean,
        )
        rows = await db.execute(stmt)
        return [(row.clothing_type, row.color, row.gender_lean) for row in rows]

    async def deactivate_unseen(
        self,
        db: AsyncSession,
        *,
        source: str,
        clothing_type: str,
        gender_lean: str,
        seen_external_ids: Sequence[str],
        confirmed_within_days: int,
    ) -> int:
        """Mark rows the provider no longer returns for this slot as out of stock.

        Absence from one search is weak evidence: providers paginate, reorder
        and personalize, so a product that is genuinely buyable can simply miss
        the top-N of a single query. Demoting on that alone would empty the
        corpus a little more with every refresh.

        So absence only counts against a row that has *also* gone unconfirmed
        for ``confirmed_within_days`` — the row must both fail to appear now and
        have failed to appear for a while. Anything confirmed recently is left
        alone, which makes a refresh safe to run as often as the budget allows.
        """
        stmt = unseen_rows_stmt(
            source=source,
            clothing_type=clothing_type,
            gender_lean=gender_lean,
            seen_external_ids=seen_external_ids,
            confirmed_within_days=confirmed_within_days,
        )
        result = await db.execute(stmt)
        # UPDATE always yields a CursorResult; the base Result protocol that
        # `execute` is typed as does not carry `rowcount`.
        demoted = int(cast("CursorResult[Any]", result).rowcount or 0)
        if demoted:
            logger.info(
                "catalog_deactivated_unseen",
                source=source,
                clothing_type=clothing_type,
                gender_lean=gender_lean,
                demoted=demoted,
            )
        return demoted

    async def count(self, db: AsyncSession, *, clothing_type: str = "") -> int:
        stmt = select(func.count()).select_from(ProductCatalogItem)
        if clothing_type:
            stmt = stmt.where(ProductCatalogItem.clothing_type == clothing_type)
        return int((await db.execute(stmt)).scalar_one())


def _fusion_score(position: int, total: int) -> float:
    """Map a fusion position onto a descending [0.5, 1.0] score.

    Fused RRF scores are tiny (~0.03) and corpus dependent, so they are
    unusable as the ``match_score`` the API exposes. This keeps the ordering
    and the "retrieved, but unverified by a reranker" semantics.
    """
    if total <= 1:
        return 1.0
    return round(1.0 - 0.5 * position / (total - 1), 4)
