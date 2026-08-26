"""
agent/earnings.py

Earnings-avoidance guard for the growth sleeve.

The one overnight-gap risk a resting trailing stop CANNOT protect against is an
earnings report after the close: the stock can gap straight through the stop
before it ever trades. Research on the "overnight drift" says being invested
overnight is normally a feature (that's where index returns accrue), so we do
NOT reduce overnight exposure in general — we surgically flatten a growth name
only around ITS OWN earnings date, then let it back in once the event passes.

Deterministic and best-effort: any data failure returns "no earnings known"
so it can never block trading.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)


def _to_date(d) -> date | None:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    try:                                   # pandas Timestamp
        return d.to_pydatetime().date()
    except Exception:
        try:
            return datetime.fromisoformat(str(d)[:10]).date()
        except Exception:
            return None


def next_earnings_date(ticker: str) -> date | None:
    """Next upcoming (today-or-later) earnings date for a ticker, or None."""
    try:
        import yfinance as yf
        cal = getattr(yf.Ticker(ticker), "calendar", None)
        raw = []
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                raw = ed if isinstance(ed, (list, tuple)) else [ed]
        today = date.today()
        future = sorted(d for d in (_to_date(x) for x in raw) if d and d >= today)
        return future[0] if future else None
    except Exception as e:
        logger.debug("Earnings lookup failed for %s: %s", ticker, e)
        return None


def days_until_earnings(ticker: str, today: date | None = None) -> int | None:
    ed = next_earnings_date(ticker)
    if ed is None:
        return None
    return (ed - (today or date.today())).days


def apply_earnings_guard(
    growth_weights: dict[str, float],
    avoid_days: int,
    today: date | None = None,
) -> tuple[dict[str, float], list[str]]:
    """
    Flatten (weight -> 0) any growth name whose earnings land within the window
    [today .. today+avoid_days]. Removing it from the target makes the rebalance
    sell it, and the freed budget falls through to cash (SGOV) downstream.

    Returns (adjusted_weights, flagged) where flagged is a human-readable list.
    """
    today = today or date.today()
    adjusted = dict(growth_weights)
    flagged: list[str] = []
    for t in list(adjusted.keys()):
        d = days_until_earnings(t, today)
        if d is not None and 0 <= d <= avoid_days:
            adjusted[t] = 0.0
            flagged.append(f"{t} (earnings in {d}d)")
    if flagged:
        logger.info("Earnings guard: flattening %s — avoiding overnight gap risk", flagged)
    return {k: v for k, v in adjusted.items() if v > 1e-9}, flagged
