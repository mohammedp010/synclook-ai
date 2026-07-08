"""Tests for evaluation harness metrics."""

from pathlib import Path

import pytest

from evaluation.harness import THRESHOLDS, check_thresholds, evaluate_cases

CASES_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "test_cases.json"


@pytest.mark.asyncio
async def test_evaluation_harness_returns_metrics() -> None:
    report = await evaluate_cases(CASES_PATH)

    assert "summary" in report
    summary = report["summary"]

    assert summary["num_cases"] >= 100  # broad fixture grid, not a handful of examples
    assert summary["num_golden_cases"] >= 3
    for metric in (
        "invalid_item_rate",
        "intent_mismatch_rate",
        "recommendation_consistency_error_rate",
        "empty_recommendation_rate",
        "complete_outfit_rate",
        "duplicate_item_rate",
    ):
        assert 0.0 <= summary[metric] <= 1.0
    assert "latency_s" in summary


@pytest.mark.asyncio
async def test_evaluation_gates_pass_on_current_rules() -> None:
    """Regression guard: the calibrated rule engine must satisfy every gate."""
    report = await evaluate_cases(CASES_PATH)
    violations = check_thresholds(report["summary"])
    assert violations == [], f"eval gates failed: {violations}"


def test_thresholds_are_strict() -> None:
    """Policy metrics have zero tolerance; structural gates stay tight."""
    assert THRESHOLDS["invalid_item_rate"] == 0.0
    assert THRESHOLDS["intent_mismatch_rate"] == 0.0
    assert THRESHOLDS["duplicate_item_rate"] == 0.0
    assert THRESHOLDS["empty_recommendation_rate"] <= 0.05
    assert THRESHOLDS["complete_outfit_rate_min"] >= 0.9
