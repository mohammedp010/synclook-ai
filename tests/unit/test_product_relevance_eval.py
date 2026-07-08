"""Tests for the offline product-relevance evaluation."""

from __future__ import annotations

from evaluation.product_relevance import evaluate_product_relevance


async def test_product_relevance_reports_metrics() -> None:
    report = await evaluate_product_relevance(matcher="keyword")
    summary = report["summary"]

    assert summary["num_cases"] >= 10
    assert summary["num_products"] >= 50
    for metric in ("precision", "recall", "f1"):
        assert 0.0 <= summary[metric] <= 1.0
    assert summary["matcher"] == "keyword"


async def test_keyword_baseline_meets_floor() -> None:
    """Regression guard on the legacy matcher (the embedding reranker's baseline)."""
    report = await evaluate_product_relevance(matcher="keyword")
    summary = report["summary"]
    assert summary["f1"] >= 0.8
    assert summary["recall"] >= 0.9
