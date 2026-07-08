"""Tests for evaluation harness metrics."""

from pathlib import Path

import pytest

from evaluation.harness import evaluate_cases


@pytest.mark.asyncio
async def test_evaluation_harness_returns_metrics() -> None:
    path = Path(__file__).resolve().parents[2] / "evaluation" / "test_cases.json"
    report = await evaluate_cases(path)

    assert "summary" in report
    summary = report["summary"]

    assert summary["num_cases"] >= 1
    assert 0.0 <= summary["invalid_item_rate"] <= 1.0
    assert 0.0 <= summary["gender_mismatch_rate"] <= 1.0
    assert 0.0 <= summary["recommendation_consistency_error_rate"] <= 1.0
    assert summary["recommendation_consistency_error_rate"] < 0.1
