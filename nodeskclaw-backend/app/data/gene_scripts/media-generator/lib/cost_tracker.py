"""
Server-side cost budget enforcer.

Prevents runaway API spend by tracking estimated cost per tool per hour.
Cost limits are declared by each provider module -- no hardcoded values here.

Usage:
    tracker = create_cost_tracker(providers)
    tracker.check_budget("generate_image")  # -> {"allowed": True} or {"allowed": False, ...}

Adding a provider: No changes here. The new provider module declares its
cost_limits, and server.py passes all providers to this factory.
"""

from __future__ import annotations

import asyncio
import time


def create_cost_tracker(providers: list[dict], budget_multiplier: float = 1.0) -> "CostTracker":
    """Build tracker from aggregated provider cost_limits."""
    limits: dict[str, dict] = {}
    for p in providers:
        for tool_name, config in p.get("cost_limits", {}).items():
            if tool_name in limits:
                raise ValueError(f"Duplicate cost_limits for tool '{tool_name}' across providers")
            limits[tool_name] = {
                "cost_per_call": config["cost_per_call"],
                "max_per_hour": int(config["max_per_hour"] * budget_multiplier),
            }
    return CostTracker(limits)


class CostTracker:
    """Tracks API call counts per hour. Mutable state (intentional exception)."""

    def __init__(self, limits: dict[str, dict]) -> None:
        self._limits = limits
        self._lock = asyncio.Lock()
        # Mutable: call counts per tool, reset hourly
        self._counts: dict[str, list] = {}  # tool -> [timestamp, ...]

    async def check_budget(self, tool_name: str) -> dict:
        """Check if a tool call is within budget. Returns {"allowed": True/False, ...}."""
        limit = self._limits.get(tool_name)
        if not limit:
            return {"allowed": True}

        async with self._lock:
            now = time.time()
            one_hour_ago = now - 3600

            # Get recent calls (immutable filter)
            recent = [t for t in self._counts.get(tool_name, []) if t > one_hour_ago]
            self._counts[tool_name] = recent

            if len(recent) >= limit["max_per_hour"]:
                estimated_spend = len(recent) * limit["cost_per_call"]
                return {
                    "allowed": False,
                    "error": "budget_exceeded",
                    "tool": tool_name,
                    "calls_this_hour": len(recent),
                    "max_per_hour": limit["max_per_hour"],
                    "estimated_spend_usd": round(estimated_spend, 2),
                    "message": (
                        f"Budget limit reached for {tool_name}: "
                        f"{len(recent)}/{limit['max_per_hour']} calls this hour "
                        f"(~${estimated_spend:.2f}). Wait for the budget window to reset."
                    ),
                }

            # Record this call
            self._counts[tool_name] = [*recent, now]
            return {
                "allowed": True,
                "calls_this_hour": len(recent) + 1,
                "max_per_hour": limit["max_per_hour"],
                "estimated_cost_usd": round(limit["cost_per_call"], 4),
            }
