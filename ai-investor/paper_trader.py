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

# Make the script runnable from ANY working directory (e.g. a Windows Task
# Scheduler job). Anchor cwd, import path, and config to this file's own
# folder before importing anything local.
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
from agent.risk_gate import (
    apply_risk_gate, apply_turnover_control, atr_trail_percent,
    RiskConfig, RiskState, RiskVeto,
)
from agent.execution import (
    get_alpaca_client, get_portfolio_value, get_current_weights,
    rebalance_to_weights, ensure_trailing_stops, is_market_open,
    flatten_fractional_dust,
)
from agent.journal import log_decision, log_order, log_equity, generate_journal_entry
from agent.portfolio_model import (
    GROWTH_WATCHLIST, GROWTH_BUDGET, GROWTH_MAX_PER_NAME, EARNINGS_AVOID_DAYS,
    compose_target_weights,
)
from agent.earnings import apply_earnings_guard
from agent.llm import backend_info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("paper_trader")

# ---------------------------------------------------------------------------
# Configuration — edit this section
# ---------------------------------------------------------------------------
# The portfolio is a 20/60/20 core-satellite model defined in
# agent/portfolio_model.py:  20% SGOV cash  |  60% VOO core  |  20% growth.
# Only the growth sleeve is actively allocated; its universe is GROWTH_WATCHLIST.

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


def run_daily_cycle(state: RiskState, dry_run: bool = False,
                    rebalance_now: bool = False) -> None:
    today = date.today()
    mode = "DRY RUN (no orders)" if dry_run else "LIVE PAPER"
    if rebalance_now:
        mode += " + REBALANCE-NOW (skip turnover cap, move straight to target)"
    logger.info("=== Paper trader daily cycle %s [%s] ===", today, mode)

    client = get_alpaca_client()

    # Equity snapshot on EVERY run — including market-closed and no-trade days —
    # so the journal keeps an unbroken daily curve for drawdown/Sharpe.
    pv_now, cash_now = get_portfolio_value(client)
    log_equity(today, pv_now, cash_now)

    if not dry_run and not is_market_open(client):
        logger.info("Market is closed. Nothing to do. (Use --dry-run to preview any day.)")
        return

    # Hygiene: clear tiny sub-1-share "dust" left by past sells before we
    # rebalance, so the book is clean and every real position can carry a stop.
    if not dry_run:
        flatten_fractional_dust(client)

    portfolio_value, cash = get_portfolio_value(client)
    cash_pct = cash / portfolio_value if portfolio_value > 0 else 1.0
    current_weights = get_current_weights(client)
    logger.info("Portfolio $%.2f | Cash %.1f%%", portfolio_value, cash_pct * 100)

    # --- GROWTH SLEEVE — the only tier the LLM sizes ------------------------
    # Core (VOO 60%) and cash (SGOV 20%) are structural constants set in
    # portfolio_model. The LLM only sizes these higher-beta names, within a
    # 20% budget; unused budget falls through to cash.
    logger.info("Fetching price data for %d growth names...", len(GROWTH_WATCHLIST))
    prices = _load_prices(GROWTH_WATCHLIST)

    signal_bundles = compute_signals(prices, GROWTH_WATCHLIST)
    signals_dict = signals_to_dict(signal_bundles)
    logger.info("Signals computed for %d growth names", len(signal_bundles))

    # Volatility-scaled (ATR-based) trailing-stop width per growth name — tighter
    # when a name is calm, wider when it's volatile, so we're neither giving back
    # profit nor getting whipsawed out on noise. Core/cash carry no stop at all.
    trail_overrides: dict[str, float] = {}
    for t, sb in signal_bundles.items():
        try:
            trail_overrides[t] = atr_trail_percent(sb.atr_14, float(prices[t].iloc[-1]), RISK_CONFIG)
        except Exception:
            pass
    if trail_overrides:
        logger.info("ATR trailing stops: %s", {t: f"{p:.1f}%" for t, p in trail_overrides.items()})

    logger.info("Running research agent...")
    headlines = fetch_news_headlines(GROWTH_WATCHLIST)
    research = run_research_agent(GROWTH_WATCHLIST, signals_dict, headlines)

    logger.info("Running growth allocation agent...")
    growth_current = {t: w for t, w in current_weights.items() if t in GROWTH_WATCHLIST}
    proposed_growth, objections = run_allocation_agent(
        tickers=GROWTH_WATCHLIST,
        signal_bundles=signal_bundles,
        research=research,
        current_weights=growth_current,
        cash_pct=cash_pct,
        budget=GROWTH_BUDGET,
        max_per_name=GROWTH_MAX_PER_NAME,
    )
    logger.info("Proposed growth: %s", {t: f"{w:.1%}" for t, w in proposed_growth.items()})
    if objections:
        logger.info("Challenger objections: %s", objections)

    # Risk gate on the growth sleeve (per-name cap, daily-loss halt, PDT guard).
    try:
        growth_final = apply_risk_gate(
            proposed_weights=proposed_growth,
            portfolio_value=portfolio_value,
            portfolio_value_open=state.portfolio_value_open or portfolio_value,
            equity=portfolio_value,
            today=today,
            state=state,
            config=RISK_CONFIG,
        )
    except RiskVeto as e:
        logger.warning("RISK VETO: %s", e)
        growth_final = {}

    # Earnings guard: flatten any growth name reporting within the window — the
    # one overnight-gap a resting stop can't cover. Freed budget falls to cash.
    growth_final, earnings_flags = apply_earnings_guard(growth_final, EARNINGS_AVOID_DAYS, today)
    if earnings_flags:
        objections = list(objections) + [f"Earnings guard flattened: {'; '.join(earnings_flags)}"]

    # Compose the full portfolio target: 60% VOO core + growth sleeve + SGOV.
    final_weights = compose_target_weights(growth_final)

    # Turnover control spreads the move toward target over several cycles — a
    # gradual, DCA-like build into the core rather than one jarring rotation.
    # --rebalance-now bypasses it for a single deliberate reset straight to
    # target (the cap exists to bound growth-sleeve whipsaw, not to slow-walk a
    # one-time structural repositioning — and on paper there's no tax/spread
    # cost to moving promptly, which research favors anyway).
    if rebalance_now:
        logger.info("REBALANCE-NOW: skipping turnover cap — moving straight to target.")
    else:
        final_weights = apply_turnover_control(current_weights, final_weights, RISK_CONFIG)

    # 6. Execute rebalance
    orders_placed = []
    if dry_run:
        logger.info("DRY RUN — skipping order execution. Would target: %s",
                    {t: f"{w:.1%}" for t, w in final_weights.items()})
    elif final_weights:
        order_results = rebalance_to_weights(
            target_weights=final_weights,
            portfolio_value=portfolio_value,
            stop_loss_pct=RISK_CONFIG.stop_loss_pct,
            min_trade_dollars=MIN_TRADE_DOLLARS,
            client=client,
            trail_overrides=trail_overrides,
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
        watchlist=GROWTH_WATCHLIST,
        signals=signals_dict,
        research=research_dict,
        proposed_weights=proposed_growth,
        objections=objections,
        final_weights=final_weights,
        orders=orders_placed,
        portfolio_value=portfolio_value,
        notes=notes,
    )
    logger.info("Journal entry saved.")
    logger.info("Notes: %s", notes)

    logger.info("=== Cycle complete ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper trading agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full analysis and push report, but place no orders. "
                             "Works any day, market open or closed.")
    parser.add_argument("--protect-only", action="store_true",
                        help="Skip analysis/trading; just place trailing stops on "
                             "existing positions. Use to secure current holdings now.")
    parser.add_argument("--rebalance-now", action="store_true",
                        help="One-time clean reset: bypass the turnover cap and move "
                             "straight to the target allocation in a single run "
                             "(instead of drifting there over several cycles).")
    args = parser.parse_args()

    _check_env()

    if args.protect_only:
        client = get_alpaca_client()
        # ATR-size stops for held growth names; fall back to fixed on any hiccup.
        from agent.execution import get_position_qtys
        overrides: dict[str, float] = {}
        held_growth = [t for t in get_position_qtys(client) if t in GROWTH_WATCHLIST]
        if held_growth:
            try:
                prices = _load_prices(held_growth)
                for t, sb in compute_signals(prices, held_growth).items():
                    overrides[t] = atr_trail_percent(sb.atr_14, float(prices[t].iloc[-1]), RISK_CONFIG)
            except Exception as e:
                logger.warning("ATR sizing failed (%s); using fixed stop.", e)
        placed = ensure_trailing_stops(RISK_CONFIG.stop_loss_pct * 100.0, client,
                                       trail_overrides=overrides)
        if placed:
            for p in placed:
                logger.info("Protected %s with trailing stop (%d sh)", p["ticker"], p["qty"])
        else:
            logger.info("All positions already protected (or none to protect).")
        return

    state = RiskState()
    run_daily_cycle(state, dry_run=args.dry_run, rebalance_now=args.rebalance_now)


if __name__ == "__main__":
    main()
