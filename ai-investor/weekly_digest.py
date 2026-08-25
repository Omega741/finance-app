"""
weekly_digest.py

Weekly performance digest for the paper trading agent. Answers the only
question that matters: is it actually beating just buying the index?

  - Builds the portfolio equity curve from the journal (equity table,
    backfilled from decisions.portfolio_value so it works before the equity
    table has filled in).
  - Benchmarks total and trailing-week return against SPY over the SAME dates.
  - Reports current and max drawdown.
  - Prints the report to the console.

Run standalone any day (no market or broker needed — reads the journal):
    python weekly_digest.py

Intended to run weekly (e.g. Friday after close) via Task Scheduler.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
os.chdir(_HERE)
sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv
load_dotenv(_HERE / ".env")

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger("weekly_digest")

START_EQUITY = 100_000.0  # paper account starting value


def _equity_series() -> list[tuple[date, float]]:
    """
    Merged {date: portfolio_value} series, newest last. Prefers the equity
    table; backfills any missing dates from decisions.portfolio_value so the
    digest is useful before the equity table has accumulated history.
    """
    import duckdb
    con = duckdb.connect("data/journal.duckdb", read_only=True)
    merged: dict[date, float] = {}
    # decisions first (older source), then equity overwrites (authoritative)
    for tbl, dcol, vcol in [("decisions", "run_date", "portfolio_value"),
                            ("equity", "snapshot_date", "portfolio_value")]:
        try:
            rows = con.execute(
                f"SELECT {dcol}, {vcol} FROM {tbl} WHERE {vcol} IS NOT NULL"
            ).fetchall()
        except Exception:
            rows = []
        for d, v in rows:
            merged[d] = float(v)  # one row per day; last table wins
    con.close()
    return sorted(merged.items())


def _spy_return(start: date, end: date) -> float | None:
    """SPY total return between two dates, using nearest available closes."""
    try:
        df = yf.download("SPY", start=start - timedelta(days=5),
                         end=end + timedelta(days=3), auto_adjust=True, progress=False)
        s = df["Close"]
        if hasattr(s, "columns"):      # 1-col DataFrame in newer yfinance
            s = s.iloc[:, 0]
        s = s.dropna()
        if len(s) < 2:
            return None
        first = s[s.index.date <= start]
        last = s[s.index.date <= end]
        p0 = float(first.iloc[-1]) if len(first) else float(s.iloc[0])
        p1 = float(last.iloc[-1]) if len(last) else float(s.iloc[-1])
        return (p1 / p0 - 1.0) if p0 else None
    except Exception as e:
        logger.warning("SPY fetch failed: %s", e)
        return None


def _drawdowns(series: list[tuple[date, float]]) -> tuple[float, float]:
    """Return (current_drawdown, max_drawdown) as fractions (<=0)."""
    peak = series[0][1]
    max_dd = 0.0
    for _, v in series:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1.0)
    cur_dd = series[-1][1] / peak - 1.0
    return cur_dd, max_dd


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x*100:+.2f}%"


def build_digest() -> str:
    series = _equity_series()
    if len(series) < 2:
        return "# Weekly Digest\n\nNot enough journal history yet to report."

    start_date, _ = series[0]
    end_date, end_val = series[-1]

    # trailing-week anchor: last point on or before 7 days ago
    week_ago = end_date - timedelta(days=7)
    prior = [(d, v) for d, v in series if d <= week_ago]
    week_start_date, week_start_val = prior[-1] if prior else series[0]

    total_ret = end_val / START_EQUITY - 1.0
    week_ret = end_val / week_start_val - 1.0 if week_start_val else None

    spy_total = _spy_return(start_date, end_date)
    spy_week = _spy_return(week_start_date, end_date)
    cur_dd, max_dd = _drawdowns(series)

    def edge(p, b):
        return None if (p is None or b is None) else p - b

    lines = [
        f"# Weekly Digest — {end_date}",
        "",
        f"**Portfolio:** ${end_val:,.2f}  |  **Days tracked:** {len(series)}",
        "",
        "## Performance vs SPY (the honest test)",
        "",
        "| Window | Portfolio | SPY | Edge |",
        "|---|---|---|---|",
        f"| This week | {_fmt(week_ret)} | {_fmt(spy_week)} | {_fmt(edge(week_ret, spy_week))} |",
        f"| Since {start_date} | {_fmt(total_ret)} | {_fmt(spy_total)} | {_fmt(edge(total_ret, spy_total))} |",
        "",
        "## Risk",
        "",
        f"- Current drawdown: {_fmt(cur_dd)}",
        f"- Max drawdown: {_fmt(max_dd)}",
        "",
        "## Read",
        "",
        _verdict(total_ret, spy_total, week_ret, spy_week, max_dd),
    ]
    return "\n".join(lines)


def _verdict(total, spy_total, week, spy_week, max_dd) -> str:
    bits = []
    if spy_total is not None:
        if total > spy_total:
            bits.append(f"Beating buy-and-hold SPY by {(total-spy_total)*100:+.1f} pts since inception — the strategy is adding value, not just riding the market.")
        else:
            bits.append(f"Trailing SPY by {(total-spy_total)*100:.1f} pts since inception — buy-and-hold would have done better so far. Watch whether the edge returns.")
    if week is not None and spy_week is not None and week < spy_week:
        bits.append("Lagged the index this week specifically.")
    if max_dd <= -0.03:
        bits.append(f"Worst drawdown seen is {max_dd*100:.1f}% — keep this in mind for real-money position sizing.")
    return " ".join(bits) if bits else "Not enough data for a verdict."


def main() -> None:
    report = build_digest()
    print("\n" + report + "\n")


if __name__ == "__main__":
    main()
