"""
paper_trader.py

Main orchestration loop for the paper trading agent.

Run once per day after market open:
    python paper_trader.py

Flow:
  1. Market status check (exit if closed)
  2. Research agent: news + price context via Claude
  3. Signal engine: deterministic RSI, MA, MACD, momentum
  4. Allocation agent: Claude proposes target weights
  5. Challenger: second Claude call argues against the allocation
  6. Risk gate: deterministic veto and position caps
  7. Execution: Alpaca paper orders, each with a stop-loss
  8. Journal: Claude writes narrative entry to DuckDB

The LLM drives synthesis. Code drives safety.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# Make the script runnable from ANY working directory (e.g. an Odysseus
# scheduled task or Windows Task Scheduler). Anchor cwd, import path, and
# config to this file's own folder before importing anything local.
_HERE = Path(__file__).resolve().parent
os.chdir(_HERE)
sys.path.insert(0, str(_HERE))

# Load .env BEFORE importing agent modules (they read config at import time).
from dotenv import load_dotenv
load_dotenv(_HERE / ".env")

import yfinance as yf

from agent.signals import compute_signals, signals_to_dict
from agent.research import run_research_agent, fetch_news_headlines
from agent.allocation import run_allocation_agent
from agent.risk_gate import apply_risk_gate, RiskConfig, RiskState, RiskVeto
from agent.execution import (
    get_alpaca_client, get_portfolio_value, get_current_weights,
    rebalance_to_weights, cancel_all_open_orders, is_market_open,
)
from agent.journal import log_decision, log_order, generate_journal_entry
from agent.llm import backend_info
from agent import odysseus_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("paper_trader")

# ---------------------------------------------------------------------------
# Configuration — edit this section
# ---------------------------------------------------------------------------
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "JPM", "BRK-B", "UNH", "XOM", "JNJ",
]

RISK_CONFIG = RiskConfig(
    max_position_pct=0.20,
    cash_floor_pct=0.10,
    max_daily_loss_pct=0.02,
    stop_loss_pct=0.07,
)

MIN_TRADE_DOLLARS = 50.0
# ---------------------------------------------------------------------------


def _check_env() -> None:
    # Alpaca is always required. The LLM backend is pluggable: Ollama (local,
    # free) needs no key; Anthropic needs ANTHROPIC_API_KEY.
    required = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]
    if os.environ.get("LLM_BACKEND", "ollama").lower() == "anthropic":
        required.append("ANTHROPIC_API_KEY")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.error("Missing env vars: %s. Check your .env file.", missing)
        sys.exit(1)
    logger.info("LLM backend: %s", backend_info())


def _load_prices(tickers: list[str], period: str = "2y") -> object:
    """Pull 2 years of daily closes via yfinance for signal computation."""
    df = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    return df["Close"].dropna(how="all").ffill()


def run_daily_cycle(state: RiskState, dry_run: bool = False) -> None:
    today = date.today()
    mode = "DRY RUN (no orders)" if dry_run else "LIVE PAPER"
    logger.info("=== Paper trader daily cycle %s [%s] ===", today, mode)

    client = get_alpaca_client()

    if not dry_run and not is_market_open(client):
        logger.info("Market is closed. Nothing to do. (Use --dry-run to preview any day.)")
        return

    portfolio_value, cash = get_portfolio_value(client)
    cash_pct = cash / portfolio_value if portfolio_value > 0 else 1.0
    current_weights = get_current_weights(client)
    logger.info("Portfolio $%.2f | Cash %.1f%%", portfolio_value, cash_pct * 100)

    # 1. Load price data for signals
    logger.info("Fetching price data for %d tickers...", len(WATCHLIST))
    prices = _load_prices(WATCHLIST)

    # 2. Compute deterministic signals
    signal_bundles = compute_signals(prices, WATCHLIST)
    signals_dict = signals_to_dict(signal_bundles)
    logger.info("Signals computed for %d tickers", len(signal_bundles))

    # 3. Research agent
    logger.info("Running research agent...")
    headlines = fetch_news_headlines(WATCHLIST)
    research = run_research_agent(WATCHLIST, signals_dict, headlines)

    # 4. Allocation agent + challenger
    logger.info("Running allocation agent...")
    proposed_weights, objections = run_allocation_agent(
        tickers=WATCHLIST,
        signal_bundles=signal_bundles,
        research=research,
        current_weights=current_weights,
        cash_pct=cash_pct,
    )
    logger.info("Proposed: %s", {t: f"{w:.1%}" for t, w in proposed_weights.items()})
    if objections:
        logger.info("Challenger objections: %s", objections)

    # 5. Risk gate — deterministic, has veto power
    try:
        final_weights = apply_risk_gate(
            proposed_weights=proposed_weights,
            portfolio_value=portfolio_value,
            portfolio_value_open=state.portfolio_value_open or portfolio_value,
            equity=portfolio_value,
            today=today,
            state=state,
            config=RISK_CONFIG,
        )
    except RiskVeto as e:
        logger.warning("RISK VETO: %s", e)
        final_weights = {}

    # 6. Execute rebalance
    orders_placed = []
    if dry_run:
        logger.info("DRY RUN — skipping order execution. Would target: %s",
                    {t: f"{w:.1%}" for t, w in final_weights.items()})
    elif final_weights:
        cancel_all_open_orders(client)
        order_results = rebalance_to_weights(
            target_weights=final_weights,
            portfolio_value=portfolio_value,
            stop_loss_pct=RISK_CONFIG.stop_loss_pct,
            min_trade_dollars=MIN_TRADE_DOLLARS,
            client=client,
        )
        for r in order_results:
            orders_placed.append({
                "ticker": r.ticker, "side": r.side,
                "stop_price": r.stop_price, "order_id": r.order_id,
            })
            log_order(today, r.ticker, r.side, 0, r.stop_price, r.order_id, r.status)
    else:
        logger.info("No trades — holding current positions.")

    # 7. Journal entry
    research_dict = {
        t: {"sentiment": r.sentiment, "summary": r.summary, "flags": r.flags}
        for t, r in research.items()
    }
    notes = generate_journal_entry(
        today, final_weights, objections, orders_placed, portfolio_value, research_dict
    )
    log_decision(
        run_date=today,
        watchlist=WATCHLIST,
        signals=signals_dict,
        research=research_dict,
        proposed_weights=proposed_weights,
        objections=objections,
        final_weights=final_weights,
        orders=orders_placed,
        portfolio_value=portfolio_value,
        notes=notes,
    )
    logger.info("Journal entry saved.")
    logger.info("Notes: %s", notes)

    # 8. Pair to Odysseus — push the decision report to the web UI (best-effort)
    if odysseus_sync.is_paired():
        odysseus_sync.push_decision(
            run_date=today,
            final_weights=final_weights,
            objections=objections,
            orders=orders_placed,
            portfolio_value=portfolio_value,
            research=research_dict,
            notes=notes,
        )

    logger.info("=== Cycle complete ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trading agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full analysis and push report, but place no orders. "
                             "Works any day, market open or closed.")
    args = parser.parse_args()

    _check_env()
    state = RiskState()
    run_daily_cycle(state, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
