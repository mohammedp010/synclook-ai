"""Tests for catalog retrieval logic (pure functions — no DB, no models)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.core.config import get_settings
from backend.jobs.catalog_ingest import (
    GRID_COLORS,
    GRID_TYPES,
    _veto_group,
    build_grid,
    deduplicate,
    parse_price_inr,
    search_with_retry,
    slots_from_catalog,
)
from backend.models.records import ProductCatalogItem
from backend.schemas.clothing import ClothingType
from backend.services.product_catalog import (
    CatalogDocument,
    CatalogQuery,
    ProductCatalogService,
    arm_ranks,
    catalog_text,
    freshness_fact,
    fuse_by_rank,
    retrieval_evidence,
    to_websearch_query,
    unseen_rows_stmt,
)


def _document(external_id: str, title: str = "product") -> CatalogDocument:
    return CatalogDocument(
        source="fixture",
        external_id=external_id,
        title=title,
        product_url=f"https://example.test/{external_id}",
        clothing_type="shirt",
        color="white",
    )


class TestWebsearchQuery:
    def test_terms_are_or_joined_so_partial_matches_survive(self) -> None:
        # AND semantics would drop a product titled just "Navy Blazer".
        assert to_websearch_query("navy formal blazer") == "navy OR formal OR blazer"

    def test_operator_characters_are_stripped(self) -> None:
        assert to_websearch_query('"slim-fit" shirt -women') == "slimfit OR shirt OR women"

    def test_empty_text_yields_no_query(self) -> None:
        assert to_websearch_query("   ") == ""


class TestReciprocalRankFusion:
    def test_agreement_between_arms_outranks_one_arms_top_hit(self) -> None:
        agreed, lexical_favourite, semantic_favourite = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        fused = fuse_by_rank(
            [
                [lexical_favourite, agreed],
                [semantic_favourite, agreed],
            ],
            k=60,
        )
        assert fused[0] == agreed

    def test_single_arm_ranking_is_preserved(self) -> None:
        ids = [uuid.uuid4() for _ in range(3)]
        assert fuse_by_rank([ids], k=60) == ids

    def test_ties_break_on_first_appearance(self) -> None:
        first, second = uuid.uuid4(), uuid.uuid4()
        assert fuse_by_rank([[first], [second]], k=60) == [first, second]

    def test_no_rankings_yields_nothing(self) -> None:
        assert fuse_by_rank([[], []], k=60) == []


class TestRetrievalEvidence:
    """Fusion collapses provenance; the UI needs it back."""

    def test_arm_ranks_records_each_arms_position(self) -> None:
        only_lexical, agreed, only_semantic = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ranks = arm_ranks([only_lexical, agreed], [agreed, only_semantic])
        assert ranks[only_lexical] == (1, None)
        assert ranks[agreed] == (2, 1)
        assert ranks[only_semantic] == (None, 2)

    def test_both_arms_are_named_and_their_agreement_stated(self) -> None:
        facts = retrieval_evidence(lexical_rank=2, semantic_rank=1, rerank_score=0.87, fusion_rank=1)
        assert facts == (
            "Keyword search ranked it #2",
            "Vector search ranked it #1",
            "Both retrieval arms agreed on it",
            "Cross-encoder relevance 0.87",
        )

    def test_single_arm_claims_no_agreement(self) -> None:
        facts = retrieval_evidence(lexical_rank=None, semantic_rank=3, rerank_score=0.4, fusion_rank=2)
        assert "Vector search ranked it #3" in facts
        assert not any("Keyword" in fact or "agreed" in fact for fact in facts)

    def test_without_a_reranker_the_fusion_rank_is_shown_instead(self) -> None:
        # The reranker is optional; evidence must still say how the order was decided.
        facts = retrieval_evidence(lexical_rank=1, semantic_rank=None, rerank_score=None, fusion_rank=4)
        assert facts[-1] == "Ranked #4 by rank fusion (reranker unavailable)"
        assert not any("Cross-encoder" in fact for fact in facts)


class TestCatalogText:
    def test_taxonomy_is_appended_to_the_copy(self) -> None:
        text = catalog_text(
            title="Slim Fit Formal Wear",
            brand="Louis Philippe",
            clothing_type="trousers",
            color="navy",
            style="smart_casual",
        )
        # The category the title never states must still be searchable.
        assert "trousers" in text
        assert "smart casual" in text
        assert text.startswith("Louis Philippe")

    def test_missing_fields_leave_no_stray_whitespace(self) -> None:
        assert catalog_text(title="White Shirt") == "White Shirt"


class TestPriceParsing:
    @pytest.mark.parametrize(
        ("display", "expected"),
        [
            ("₹1,299", 1299),
            ("₹8,999.00", 8999),
            ("Rs. 450", 450),
            ("N/A", None),
            ("", None),
        ],
    )
    def test_rupee_strings(self, display: str, expected: int | None) -> None:
        assert parse_price_inr(display) == expected


class TestGrid:
    def test_truncated_grid_stays_broad(self) -> None:
        slots = build_grid(max_queries=len(GRID_TYPES))
        # Spending the whole budget on one garment would leave slots unserved.
        assert len({slot.clothing_type for slot in slots}) == len(GRID_TYPES)

    def test_full_grid_covers_every_combination(self) -> None:
        slots = build_grid(max_queries=10_000)
        assert len(slots) == len(GRID_TYPES) * len(GRID_COLORS) * 2

    def test_query_reads_like_a_shopper_search(self) -> None:
        assert build_grid(max_queries=1)[0].query == "black shirt for men"


class TestDeduplicate:
    def test_repeated_identity_is_collapsed(self) -> None:
        # Grid slots overlap: one navy blazer answers both "navy" and "blue".
        documents = [_document("a", "first"), _document("a", "second"), _document("b")]
        collapsed = deduplicate(documents)
        assert [d.external_id for d in collapsed] == ["a", "b"]
        assert collapsed[0].title == "first"


class TestThumbnailVetoGrouping:
    """The veto compares body regions, not the style engine's categories."""

    def test_topwear_and_outerwear_share_a_group(self) -> None:
        # CLIP reads a real blazer photo as `blouse`; treating outerwear and
        # topwear as different would veto correct products on that confusion.
        assert _veto_group("blazer") == _veto_group("blouse")

    def test_bottomwear_is_a_different_group_from_topwear(self) -> None:
        assert _veto_group("jeans") != _veto_group("shirt")

    def test_shoes_and_accessories_are_distinct(self) -> None:
        assert _veto_group("shoes") != _veto_group("accessory")

    def test_every_garment_type_has_a_group(self) -> None:
        assert all(_veto_group(clothing_type.value) is not None for clothing_type in ClothingType)


class TestHardFilters:
    """`_filtered` is shared by both retrieval arms, so its clauses are checked
    by compiling the statement rather than by round-tripping a database."""

    @staticmethod
    def _sql(query: CatalogQuery) -> str:
        stmt = ProductCatalogService()._filtered(select(ProductCatalogItem.id), query)
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))

    def test_out_of_stock_is_always_excluded(self) -> None:
        assert "in_stock IS true" in self._sql(CatalogQuery(text="navy blazer"))

    def test_unfiltered_query_constrains_nothing_else(self) -> None:
        sql = self._sql(CatalogQuery(text="navy blazer"))
        assert "clothing_type" not in sql
        assert "source IN" not in sql

    def test_gender_filter_always_admits_unisex(self) -> None:
        sql = self._sql(CatalogQuery(text="navy blazer", gender="men"))
        assert "'men'" in sql and "'unisex'" in sql

    def test_price_filter_keeps_unpriced_rows(self) -> None:
        # A missing price is unknown, not expensive — dropping those rows would
        # silently shrink the corpus for every budget-bearing request.
        sql = self._sql(CatalogQuery(text="navy blazer", max_price_inr=5000))
        assert "price_inr IS NULL" in sql
        assert "price_inr <= 5000" in sql

    def test_source_scoping_restricts_the_corpus(self) -> None:
        # What makes the retrieval benchmark independent of whatever else is
        # ingested on the machine running it.
        assert "source IN ('eval')" in self._sql(CatalogQuery(text="navy blazer", sources=("eval",)))

    def test_stale_rows_are_excluded_by_default(self) -> None:
        assert "last_seen_at >=" in self._sql(CatalogQuery(text="navy blazer"))

    def test_freshness_window_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A corpus that is refreshed by other means should not age out; 0 has to
        # remove the clause entirely rather than compare against the epoch.
        monkeypatch.setattr(get_settings(), "catalog_stale_after_days", 0)
        sql = self._sql(CatalogQuery(text="navy blazer"))
        assert "last_seen_at" not in sql
        assert "in_stock IS true" in sql


class TestFreshnessEvidence:
    """In-stock is an observation with a date, and says so."""

    def test_unknown_last_seen_produces_no_claim(self) -> None:
        assert freshness_fact(None) == ""

    def test_today_and_yesterday_read_naturally(self) -> None:
        assert freshness_fact(datetime.now(UTC)) == "Stock confirmed today"
        assert freshness_fact(datetime.now(UTC) - timedelta(days=1)) == "Stock confirmed yesterday"

    def test_older_rows_report_their_age(self) -> None:
        assert freshness_fact(datetime.now(UTC) - timedelta(days=9)) == "Stock confirmed 9 days ago"

    def test_naive_timestamps_are_assumed_utc_not_crashed_on(self) -> None:
        # Postgres returns tz-aware values, but a hand-built row or a sqlite
        # fixture will not; subtracting those would raise.
        assert freshness_fact(datetime.now(UTC).replace(tzinfo=None)) == "Stock confirmed today"

    def test_freshness_joins_the_retrieval_facts(self) -> None:
        facts = retrieval_evidence(
            lexical_rank=1,
            semantic_rank=None,
            rerank_score=0.9,
            fusion_rank=1,
            last_seen_at=datetime.now(UTC) - timedelta(days=3),
        )
        assert facts[-1] == "Stock confirmed 3 days ago"


class TestDeactivateUnseen:
    """The dangerous failure is a missing WHERE clause, so compile and look."""

    @staticmethod
    def _sql(seen: list[str]) -> str:
        stmt = unseen_rows_stmt(
            source="serpapi",
            clothing_type="blazer",
            gender_lean="men",
            seen_external_ids=seen,
            confirmed_within_days=30,
        )
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))

    def test_demotion_is_scoped_to_the_slot_that_was_queried(self) -> None:
        sql = self._sql(["abc"])
        assert "SET in_stock=false" in sql.replace("in_stock = false", "in_stock=false")
        assert "source = 'serpapi'" in sql
        assert "clothing_type = 'blazer'" in sql
        assert "gender_lean = 'men'" in sql

    def test_recently_confirmed_rows_are_never_demoted(self) -> None:
        # One search missing a product is not proof it is gone; the row must
        # also have been unconfirmed for a while.
        assert "last_seen_at <" in self._sql(["abc"])

    def test_products_that_came_back_are_excluded(self) -> None:
        assert "'abc'" in self._sql(["abc"])

    def test_an_empty_result_set_still_scopes_to_the_slot(self) -> None:
        # A provider outage returning nothing must not demote the whole corpus.
        sql = self._sql([])
        assert "clothing_type = 'blazer'" in sql
        assert "NOT IN ('')" in sql.replace("(NULL)", "('')")


class TestSearchRetry:
    """A credit spent on a transient transport error should not be wasted."""

    class _FlakyProvider:
        def __init__(self, failures: int, products: list[str]) -> None:
            self.failures = failures
            self.products = products
            self.calls = 0

        async def search(self, query: str) -> list[str]:
            self.calls += 1
            if self.calls <= self.failures:
                raise RuntimeError("")  # empty message, as the real failure had
            return self.products

    @pytest.mark.asyncio
    async def test_a_transient_failure_is_retried(self) -> None:
        provider = self._FlakyProvider(failures=1, products=["shirt"])
        got = await search_with_retry(provider, "black shirt", backoff_s=0)  # type: ignore[arg-type]
        assert got == ["shirt"]
        assert provider.calls == 2

    @pytest.mark.asyncio
    async def test_a_persistent_failure_gives_up_rather_than_burning_credits(self) -> None:
        provider = self._FlakyProvider(failures=99, products=["shirt"])
        got = await search_with_retry(provider, "black shirt", attempts=2, backoff_s=0)  # type: ignore[arg-type]
        assert got == []
        assert provider.calls == 2

    @pytest.mark.asyncio
    async def test_a_working_provider_is_called_once(self) -> None:
        provider = self._FlakyProvider(failures=0, products=["shirt"])
        await search_with_retry(provider, "black shirt", backoff_s=0)  # type: ignore[arg-type]
        assert provider.calls == 1


class TestRefreshSlots:
    """A refresh re-asks only the questions the corpus already answered."""

    def test_stored_taxonomy_becomes_a_provider_query(self) -> None:
        slots = slots_from_catalog([("blazer", "navy", "men")], max_queries=10)
        assert [slot.query for slot, _ in slots] == ["navy blazer for men"]

    def test_unisex_rows_do_not_invent_an_audience(self) -> None:
        slots = slots_from_catalog([("shirt", "white", "unisex")], max_queries=10)
        assert [slot.query for slot, _ in slots] == ["white shirt"]

    def test_unknown_taxonomy_is_skipped_rather_than_guessed(self) -> None:
        assert slots_from_catalog([("spacesuit", "navy", "men")], max_queries=10) == []

    def test_the_credit_budget_is_respected(self) -> None:
        rows = [("blazer", "navy", "men"), ("shirt", "white", "men"), ("jeans", "blue", "men")]
        assert len(slots_from_catalog(rows, max_queries=2)) == 2
