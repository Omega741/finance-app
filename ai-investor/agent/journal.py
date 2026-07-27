"""
agent/journal.py

DuckDB-backed trade journal. Every decision — including no-ops — gets
a structured entry. The agent's own explanations are the diagnostic for
what to fix.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("JOURNAL_DB_PATH", "data/journal.duckdb"))

SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS decisions_id_seq;
CREATE SEQUENCE IF NOT EXISTS orders_id_seq;

CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY DEFAULT nextval('decisions_id_seq'),
    ts          TIMESTAMP NOT NULL,
    run_date    DATE NOT NULL,
    watchlist   TEXT,
    signals     TEXT,      -- JSON
    research    TEXT,      -- JSON
    proposed_weights TEXT, -- JSON (from allocation agent)
    objections  TEXT,      -- JSON (from challenger)
    final_weights TEXT,    -- JSON (after risk gate)
    orders      TEXT,      -- JSON
    portfolio_value DOUBLE,
    notes       TEXT       -- LLM narrative explanation
);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY DEFAULT nextval('orders_id_seq'),
    ts          TIMESTAMP NOT NULL,
    run_date    DATE NOT NULL,
    ticker      TEXT,
    side        TEXT,
    notional    DOUBLE,
    stop_price  DOUBLE,
    order_id    TEXT,
    status      TEXT
);

-- Continuous daily equity curve. Written on EVERY run, including
-- market-closed and no-trade days, so drawdown/Sharpe can be computed
-- from an unbroken series. One row per calendar day (upsert by date).
CREATE TABLE IF NOT EXISTS equity (
    snapshot_date   DATE PRIMARY KEY,
    ts              TIMESTAMP NOT NULL,
    portfolio_value DOUBLE,
    cash            DOUBLE,
    invested_value  DOUBLE
);
"""


def _get_conn():
    try:
        import duckdb
    except ImportError:
        raise ImportError("duckdb not installed. Run: pip install duckdb")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(SCHEMA)
    return conn


def log_decision(
    run_date: date,
    watchlist: list[str],
    signals: dict,
    research: dict,
    proposed_weights: dict,
    objections: list[str],
    final_weights: dict,
    orders: list[dict],
    portfolio_value: float,
    notes: str = "",
) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO decisions
           (ts, run_date, watchlist, signals, research, proposed_weights,
            objections, final_weights, orders, portfolio_value, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            datetime.utcnow(),
            run_date,
            json.dumps(watchlist),
            json.dumps(signals),
            json.dumps({t: {"sentiment": r.get("sentiment"), "summary": r.get("summary"),
                            "flags": r.get("flags", [])} for t, r in research.items()}),
            json.dumps(proposed_weights),
            json.dumps(objections),
            json.dumps(final_weights),
            json.dumps(orders),
            portfolio_value,
            notes,
        ],
    )
    conn.close()
    logger.info("Journal entry written for %s", run_date)


def log_order(run_date: date, ticker: str, side: str, notional: float,
              stop_price: float, order_id: str, status: str) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO orders (ts, run_date, ticker, side, notional, stop_price, order_id, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [datetime.utcnow(), run_date, ticker, side, notional, stop_price, order_id, status],
    )
    conn.close()


def log_equity(snapshot_date: date, portfolio_value: float, cash: float) -> None:
    """
    Record a daily equity snapshot. Called on every run — even when the
    market is closed or no trades happen — to keep an unbroken equity curve.
    Upserts: one row per calendar day, last write wins.
    """
    conn = _get_conn()
    conn.execute("DELETE FROM equity WHERE snapshot_date = ?", [snapshot_date])
    conn.execute(
        """INSERT INTO equity (snapshot_date, ts, portfolio_value, cash, invested_value)
           VALUES (?, ?, ?, ?, ?)""",
        [snapshot_date, datetime.utcnow(), portfolio_value, cash,
         portfolio_value - cash],
    )
    conn.close()
    logger.info("Equity snapshot: %s $%.2f (cash $%.2f)",
                snapshot_date, portfolio_value, cash)


def get_recent_decisions(n: int = 10) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM decisions ORDER BY ts DESC LIMIT ?", [n]
    ).fetchall()
    cols = [d[0] for d in conn.description]
    conn.close()
    return [dict(zip(cols, row)) for row in rows]


def generate_journal_entry(
    run_date: date,
    final_weights: dict[str, float],
    objections: list[str],
    orders_placed: list[dict],
    portfolio_value: float,
    research: dict,
) -> str:
    """
    Call the LLM to write a narrative journal entry explaining the day's decisions.
    Returned string is stored in decisions.notes.
    """
    from .llm import chat

    order_summary = json.dumps(orders_placed, indent=2) if orders_placed else "No orders placed."
    research_summary = {
        t: {"sentiment": r.get("sentiment"), "flags": r.get("flags", [])}
        for t, r in research.items()
    }

    prompt = (
        f"Date: {run_date}\n"
        f"Final portfolio weights: {json.dumps(final_weights)}\n"
        f"Orders: {order_summary}\n"
        f"Challenger objections: {json.dumps(objections)}\n"
        f"Research sentiment: {json.dumps(research_summary)}\n"
        f"Portfolio value: ${portfolio_value:,.2f}\n\n"
        "Write a concise trade journal entry (3-5 sentences) explaining what happened today, "
        "why these positions were taken or held, what the challenger flagged, and what to watch "
        "for tomorrow. Plain text, no markdown."
    )

    try:
        text = chat(prompt, max_tokens=1024)
        return text.strip() if text else "Journal narrative unavailable."
    except Exception as e:
        logger.warning("Journal narrative failed: %s", e)
        return f"Journal narrative unavailable: {e}"
