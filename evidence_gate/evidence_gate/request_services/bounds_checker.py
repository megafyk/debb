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
    """Check and optionally narrow Quickwit query plan bounds.

    `from`/`to` may be ISO 8601, epoch ms, or a Grafana relative string
    (e.g. `now-1h`). Only ISO values get the 24h narrowing; the other forms
    pass through (the connector translates them at the wire boundary).
    """
    narrowing: list[str] = []
    adjusted = dict(plan)

    start = _parse_iso(adjusted.get("from"))
    end = _parse_iso(adjusted.get("to"))

    # Reject mixed forms: an ISO `from` paired with a relative `to` (or vice
    # versa) skips the order check and 24h narrowing entirely, letting an
    # agent submit unbounded windows like `from=2020-01-01T00:00:00, to=now`.
    if (start is None) != (end is None):
        return BoundsResult(
            ok=False,
            rejection_reason="from and to must use the same format (both ISO 8601 or both relative)",
        )

    if start is not None and end is not None:
        if end <= start:
            return BoundsResult(ok=False, rejection_reason="to must be after from")

        hours = (end - start).total_seconds() / 3600
        if hours > MAX_TIME_WINDOW_HOURS:
            new_start = end - timedelta(hours=MAX_TIME_WINDOW_HOURS)
            adjusted["from"] = new_start.isoformat()
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


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def check_metabase_bounds(plan: dict) -> BoundsResult:
    """Check Metabase query plan bounds."""
    sql = plan.get("sql_candidate", "")

    # `params is None` (missing key) is the reject signal — an explicit
    # empty list means "this SQL is fully literal (e.g. an introspection
    # query against information_schema)" and is a valid plan shape.
    if sql and plan.get("params") is None:
        return BoundsResult(ok=False, rejection_reason="sql_candidate requires params list")

    facts = plan.get("facts_requested", [])
    if len(facts) > 20:
        adjusted = dict(plan)
        adjusted["facts_requested"] = facts[:20]
        return BoundsResult(
            ok=True,
            narrowed=True,
            narrowing_applied=[f"facts_requested truncated from {len(facts)} to 20"],
            adjusted_plan=adjusted,
        )

    return BoundsResult(ok=True)
