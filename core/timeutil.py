"""Human-friendly timestamp formatting.

Anything stored as ISO-8601 (which is what core.db writes) gets turned
into a short relative or compact-absolute string for display.

Used by the Streamlit UI so users never see '2026-06-17T13:03:07Z'.
"""
from __future__ import annotations

from datetime import datetime, timezone


def humanize(iso_string: str, *, now: datetime | None = None) -> str:
    """Turn an ISO-8601 timestamp into something like '3m ago', '2h ago',
    'yesterday 13:03', '3 days ago', 'Jun 14', or 'Jun 14, 2024'.

    Returns an em-dash if the input is empty/None. Returns the input
    unchanged if it can't be parsed (so users still see *something*).
    """
    if not iso_string:
        return "—"
    try:
        # tolerate 'Z' suffix
        clean = iso_string.rstrip()
        if clean.endswith("Z"):
            clean = clean[:-1] + "+00:00"
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError, TypeError):
        return iso_string

    now = now or datetime.now(timezone.utc)
    delta = now - dt
    seconds = delta.total_seconds()

    if seconds < 0:
        return "just now"   # clock skew shouldn't show "in the future"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    if delta.days == 1:
        return f"yesterday {dt.strftime('%H:%M')}"
    if delta.days < 7:
        return f"{delta.days}d ago"
    if dt.year == now.year:
        return dt.strftime("%b %d")
    return dt.strftime("%b %d, %Y")
