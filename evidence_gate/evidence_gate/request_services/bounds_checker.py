from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


MAX_TIME_WINDOW_HOURS = 24
MAX_HITS_LIMIT = 500


@dataclass
class BoundsResult:
    ok: bool
    narrowed: bool = False
    narrowing_applied: list[str] = field(default_factory=list)
    rejection_reason: str = ""
    adjusted_plan: dict | None = None


def check_quickwit_bounds(plan: dict) -> BoundsResult:
    """Check and optionally narrow Quickwit query plan bounds."""
    narrowing: list[str] = []
    adjusted = dict(plan)

    tw = adjusted.get("time_window", {})
    try:
        start = datetime.fromisoformat(tw.get("start", ""))
        end = datetime.fromisoformat(tw.get("end", ""))
    except (ValueError, TypeError):
        return BoundsResult(ok=False, rejection_reason="invalid time_window format")

    if end <= start:
        return BoundsResult(ok=False, rejection_reason="time_window end must be after start")

    hours = (end - start).total_seconds() / 3600
    if hours > MAX_TIME_WINDOW_HOURS:
        new_start = end - timedelta(hours=MAX_TIME_WINDOW_HOURS)
        adjusted["time_window"] = {
            "start": new_start.isoformat(),
            "end": tw["end"],
        }
        narrowing.append(f"time_window narrowed from {hours:.0f}h to {MAX_TIME_WINDOW_HOURS}h")

    max_hits = adjusted.get("max_hits", 100)
    if max_hits > MAX_HITS_LIMIT:
        adjusted["max_hits"] = MAX_HITS_LIMIT
        narrowing.append(f"max_hits narrowed from {max_hits} to {MAX_HITS_LIMIT}")

    # Reject if no filters
    filters = adjusted.get("filters", [])
    if not filters:
        return BoundsResult(ok=False, rejection_reason="at least one filter required")

    return BoundsResult(
        ok=True,
        narrowed=len(narrowing) > 0,
        narrowing_applied=narrowing,
        adjusted_plan=adjusted if narrowing else None,
    )


def check_metabase_bounds(plan: dict) -> BoundsResult:
    """Check Metabase query plan bounds."""
    sql = plan.get("sql_candidate", "")

    if sql and not plan.get("params"):
        return BoundsResult(ok=False, rejection_reason="sql_candidate requires params list")

    facts = plan.get("facts_requested", [])
    if len(facts) > 20:
        return BoundsResult(
            ok=True,
            narrowed=True,
            narrowing_applied=[f"facts_requested truncated from {len(facts)} to 20"],
        )

    return BoundsResult(ok=True)
