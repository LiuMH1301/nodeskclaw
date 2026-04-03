"""Unit tests for cost tracker."""

import time
from unittest.mock import patch

import pytest

from lib.cost_tracker import create_cost_tracker


MOCK_PROVIDERS = [
    {
        "cost_limits": {
            "generate_image": {"cost_per_call": 0.04, "max_per_hour": 3},
            "generate_video": {"cost_per_call": 0.50, "max_per_hour": 2},
        },
    },
]


@pytest.mark.asyncio
async def test_allows_within_budget():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    result = await tracker.check_budget("generate_image")
    assert result["allowed"] is True
    assert result["calls_this_hour"] == 1


@pytest.mark.asyncio
async def test_blocks_over_budget():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    await tracker.check_budget("generate_image")
    await tracker.check_budget("generate_image")
    await tracker.check_budget("generate_image")
    result = await tracker.check_budget("generate_image")
    assert result["allowed"] is False
    assert result["error"] == "budget_exceeded"
    assert result["calls_this_hour"] == 3


@pytest.mark.asyncio
async def test_allows_unknown_tool():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    result = await tracker.check_budget("unknown_tool")
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_budget_resets_after_hour():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    # Fill budget
    for _ in range(3):
        await tracker.check_budget("generate_image")

    # Simulate 1 hour passing
    future = time.time() + 3601
    with patch("lib.cost_tracker.time") as mock_time:
        mock_time.time.return_value = future
        result = await tracker.check_budget("generate_image")
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_budget_multiplier():
    tracker = create_cost_tracker(MOCK_PROVIDERS, budget_multiplier=2.0)
    # Should allow 6 calls (3 * 2.0)
    for _ in range(6):
        result = await tracker.check_budget("generate_image")
        assert result["allowed"] is True
    result = await tracker.check_budget("generate_image")
    assert result["allowed"] is False


@pytest.mark.asyncio
async def test_reports_estimated_spend():
    tracker = create_cost_tracker(MOCK_PROVIDERS)
    for _ in range(2):
        await tracker.check_budget("generate_video")
    result = await tracker.check_budget("generate_video")
    assert result["allowed"] is False
    assert result["estimated_spend_usd"] > 0


@pytest.mark.asyncio
async def test_concurrent_budget_checks_respect_limit():
    """Concurrent asyncio.gather calls must not exceed max_per_hour."""
    import asyncio

    providers = [
        {"cost_limits": {"concurrent_tool": {"cost_per_call": 0.01, "max_per_hour": 5}}},
    ]
    tracker = create_cost_tracker(providers)

    results = await asyncio.gather(*[tracker.check_budget("concurrent_tool") for _ in range(10)])

    allowed_count = sum(1 for r in results if r["allowed"])
    denied_count = sum(1 for r in results if not r["allowed"])

    assert allowed_count == 5
    assert denied_count == 5
