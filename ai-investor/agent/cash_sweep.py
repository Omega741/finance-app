"""
agent/cash_sweep.py

Idle-cash sweep into a short T-bill ETF (SGOV) so uninvested cash earns
~4-5% instead of 0. SGOV is treated as a CASH-EQUIVALENT parking layer,
never as an agent position:

  - At the START of each cycle, liquidate_cash_sweep() sells all SGOV back
    to cash BEFORE the allocation agent runs, so the agent always reasons
    over full cash exactly as it does today. SGOV never appears as an
    equity weight and never competes with the watchlist.
  - At the END of each cycle, after equity trades + trailing stops are set,
    sweep_excess_cash() parks whatever cash the agent chose not to deploy
    (above a small liquid buffer) into SGOV.

SGOV is deliberately excluded from trailing-stop enforcement in
execution.py — a 7% stop on a T-bill fund is meaningless and would churn.

This layer is fully deterministic. The LLM never decides anything here.
"""

from __future__ import annotations

import logging

from .execution import (
    get_alpaca_client, get_position_qtys, latest_price,
    _market_order, _wait_for_fills,
)

logger = logging.getLogger(__name__)

# Ticker used to park idle cash. Kept in one place; execution.CASH_EQUIVALENTS
# must stay in sync so it is skipped by trailing-stop enforcement.
SWEEP_TICKER = "SGOV"

# Keep this fraction of portfolio value as liquid cash (fees, slippage,
# stop execution headroom). Everything above it gets swept into SGOV.
DEFAULT_BUFFER_PCT = 0.02

# Don't bother sweeping trivial amounts.
MIN_SWEEP_DOLLARS = 200.0


def liquidate_cash_sweep(client=None) -> float:
    """
    Sell the entire SGOV position back to cash and wait for the fill.
    Call at the START of a cycle so all cash is available to the agent.
    Returns the share qty liquidated (0.0 if none / on failure).
    """
    if client is None:
        client = get_alpaca_client()
    qty = get_position_qtys(client).get(SWEEP_TICKER, 0.0)
    if qty <= 0:
        return 0.0
    try:
        r = _market_order(SWEEP_TICKER, "sell", qty, client)
        _wait_for_fills([r.order_id], client)
        logger.info("Cash sweep liquidated: sold %.4f %s back to cash", qty, SWEEP_TICKER)
        return qty
    except Exception as e:
        logger.error("Cash sweep liquidation failed for %s: %s", SWEEP_TICKER, e)
        return 0.0


def sweep_excess_cash(
    portfolio_value: float,
    cash: float,
    buffer_pct: float = DEFAULT_BUFFER_PCT,
    client=None,
) -> dict | None:
    """
    Park excess cash (above buffer_pct of portfolio value) into SGOV using
    whole shares. Call at the END of a cycle, after equity trades and stops.
    Returns {ticker, qty, order_id} on a placed buy, else None.
    """
    if client is None:
        client = get_alpaca_client()
    if portfolio_value <= 0:
        return None

    buffer_dollars = buffer_pct * portfolio_value
    excess = cash - buffer_dollars
    if excess < MIN_SWEEP_DOLLARS:
        logger.info("Cash sweep: excess $%.2f below $%.2f floor — leaving in cash",
                    max(excess, 0.0), MIN_SWEEP_DOLLARS)
        return None

    price = latest_price(SWEEP_TICKER)
    if not price:
        logger.warning("Cash sweep: no quote for %s — skipping", SWEEP_TICKER)
        return None

    qty = int(excess // price)  # whole shares; tiny remainder stays as cash
    if qty < 1:
        return None
    try:
        r = _market_order(SWEEP_TICKER, "buy", qty, client)
        logger.info("Cash sweep: parked ~$%.2f into %d sh %s", qty * price, qty, SWEEP_TICKER)
        return {"ticker": SWEEP_TICKER, "qty": qty, "order_id": r.order_id}
    except Exception as e:
        logger.error("Cash sweep buy failed for %s: %s", SWEEP_TICKER, e)
        return None
