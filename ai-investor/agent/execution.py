"""
agent/execution.py

Alpaca paper trading execution layer.

IMPORTANT — fractional shares cannot carry stop orders at Alpaca. So buys use
WHOLE-SHARE quantities, which lets every position carry a real, broker-side
TRAILING STOP that:
  - actually exists and triggers automatically (a notional/bracket stop on a
    fractional position is silently dropped by Alpaca)
  - trails upward as the price rises, locking in gains while letting winners run

Enforcement model: after every rebalance, ensure_trailing_stops() guarantees
each position has a correctly-sized trailing-stop sell resting at the broker.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cash-equivalent tickers used only to park idle cash (see portfolio_model.py).
# They are NOT equity positions: skip trailing-stop enforcement for them —
# a 7% stop on a T-bill ETF is meaningless and would churn.
CASH_EQUIVALENTS = {"SGOV"}

# Core buy-and-hold tier (broad index). Deliberately carries NO trailing stop:
# the core is meant to ride through drawdowns and compound long-term, and a
# stop would both defeat that and realize taxable gains. Only the growth sleeve
# is stop-protected.
CORE_HOLDINGS = {"VOO"}

# Union of everything execution must NOT place a protective stop on.
NO_STOP = CASH_EQUIVALENTS | CORE_HOLDINGS


class MissingStopLoss(Exception):
    """Raised if a position is left without a protective stop."""


@dataclass
class OrderResult:
    ticker: str
    side: str
    qty: float
    entry_price: float
    stop_price: float   # initial trail trigger (price * (1 - trail)) for logging
    order_id: str
    status: str


def get_alpaca_client():
    """Returns an Alpaca TradingClient configured for paper trading."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        raise ImportError("alpaca-py not installed. Run: pip install alpaca-py")
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=True,  # PAPER TRADING ONLY — never change this without explicit review
    )


def _data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
    )


def latest_price(ticker: str) -> float | None:
    """Latest ask (fallback bid) price for a ticker, or None on failure."""
    from alpaca.data.requests import StockLatestQuoteRequest
    try:
        q = _data_client().get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=ticker)
        )
        return float(q[ticker].ask_price or q[ticker].bid_price)
    except Exception as e:
        logger.warning("Quote fetch failed for %s: %s", ticker, e)
        return None


def get_portfolio_value(client=None) -> tuple[float, float]:
    """Returns (portfolio_value, cash)."""
    if client is None:
        client = get_alpaca_client()
    account = client.get_account()
    return float(account.portfolio_value), float(account.cash)


def get_current_positions(client=None) -> dict[str, float]:
    """Returns {ticker: current_market_value} for all open positions."""
    if client is None:
        client = get_alpaca_client()
    return {p.symbol: float(p.market_value) for p in client.get_all_positions()}


def get_position_qtys(client=None) -> dict[str, float]:
    """Returns {ticker: share_qty} for all open positions."""
    if client is None:
        client = get_alpaca_client()
    return {p.symbol: float(p.qty) for p in client.get_all_positions()}


def get_current_weights(client=None) -> dict[str, float]:
    """Returns {ticker: weight} as fraction of portfolio value."""
    if client is None:
        client = get_alpaca_client()
    portfolio_value, _ = get_portfolio_value(client)
    if portfolio_value <= 0:
        return {}
    positions = get_current_positions(client)
    return {t: v / portfolio_value for t, v in positions.items()}


# ---------------------------------------------------------------------------
# Order primitives
# ---------------------------------------------------------------------------
def _market_order(ticker: str, side: str, qty: float, client) -> OrderResult:
    """Place a plain market order by share quantity. No stop attached here."""
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    req = MarketOrderRequest(
        symbol=ticker,
        qty=round(qty, 4),
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(req)
    logger.info("Market %s %s qty=%s id=%s", side.upper(), ticker, qty, order.id)
    return OrderResult(
        ticker=ticker, side=side, qty=float(qty),
        entry_price=float(getattr(order, "filled_avg_price", 0) or 0),
        stop_price=0.0, order_id=str(order.id), status=str(order.status),
    )


def place_trailing_stop(ticker: str, qty: int, trail_percent: float, client) -> str | None:
    """
    Place a broker-side trailing-stop SELL for `qty` whole shares.
    trail_percent is a percent (e.g. 7.0 for 7%). GTC so it persists.
    Returns the order id, or None on failure.
    """
    from alpaca.trading.requests import TrailingStopOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    qty = int(qty)
    if qty < 1:
        return None
    try:
        req = TrailingStopOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.GTC,
            trail_percent=round(trail_percent, 2),
        )
        order = client.submit_order(req)
        logger.info("Trailing stop %s qty=%d trail=%.1f%% id=%s",
                    ticker, qty, trail_percent, order.id)
        return str(order.id)
    except Exception as e:
        logger.error("Trailing stop failed for %s: %s", ticker, e)
        return None


def _open_orders(client):
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    return client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100))


def cancel_orders_for_symbol(symbol: str, client) -> int:
    """Cancel all open orders for a single symbol. Returns count cancelled."""
    n = 0
    for o in _open_orders(client):
        if o.symbol == symbol:
            try:
                client.cancel_order_by_id(o.id)
                n += 1
            except Exception as e:
                logger.warning("Cancel failed %s %s: %s", symbol, o.id, e)
    return n


def cancel_all_open_orders(client=None) -> int:
    """Cancel all open orders. Returns count cancelled."""
    if client is None:
        client = get_alpaca_client()
    cancelled = client.cancel_orders()
    n = len(cancelled) if cancelled else 0
    logger.info("Cancelled %d open orders", n)
    return n


def _wait_for_fills(order_ids: list[str], client, timeout: float = 15.0) -> None:
    """Poll until the given orders are filled/closed, or timeout."""
    deadline = time.time() + timeout
    pending = set(order_ids)
    while pending and time.time() < deadline:
        for oid in list(pending):
            try:
                o = client.get_order_by_id(oid)
                if str(o.status).split(".")[-1].lower() in ("filled", "canceled", "rejected", "expired"):
                    pending.discard(oid)
            except Exception:
                pending.discard(oid)
        if pending:
            time.sleep(1.0)


# ---------------------------------------------------------------------------
# Trailing-stop enforcement
# ---------------------------------------------------------------------------
def ensure_trailing_stops(trail_percent: float, client=None,
                          trail_overrides: dict[str, float] | None = None) -> list[dict]:
    """
    Guarantee every position has a correctly-sized trailing-stop sell.

    - Preserves an existing trailing stop whose qty already matches the
      whole-share position size (so its trail keeps ratcheting up — resetting
      it would drop the high-water mark and could loosen protection).
    - For positions with no stop, or a stop whose size is stale, cancels any
      existing and places a fresh trailing stop for floor(position qty).

    `trail_overrides` gives a per-ticker trail percent (e.g. ATR-based); any
    ticker not present uses the `trail_percent` default. Note: because existing
    stops are preserved, an updated override only applies when a stop is newly
    placed (new or resized position), by design.

    Returns a list of {ticker, qty, order_id} for stops placed this call.
    """
    if client is None:
        client = get_alpaca_client()
    trail_overrides = trail_overrides or {}

    # map existing OPEN trailing-stop sells by symbol
    existing: dict[str, object] = {}
    for o in _open_orders(client):
        otype = str(getattr(o, "order_type", "")).split(".")[-1].lower()
        oside = str(o.side).split(".")[-1].lower()
        if "trailing" in otype and oside == "sell":
            existing[o.symbol] = o

    placed: list[dict] = []
    for sym, qty in get_position_qtys(client).items():
        if sym in NO_STOP:
            continue  # cash-parking layer or buy-and-hold core — no stop
        whole = int(qty)  # floor for long positions
        if whole < 1:
            logger.warning("%s position is fractional-only (%.4f) — cannot place a "
                           "broker stop; will be covered once it reaches >=1 share", sym, qty)
            continue
        ex = existing.get(sym)
        if ex is not None and int(float(ex.qty)) == whole:
            continue  # already protected at the right size; leave trail intact
        if ex is not None:
            cancel_orders_for_symbol(sym, client)
        sym_trail = trail_overrides.get(sym, trail_percent)
        oid = place_trailing_stop(sym, whole, sym_trail, client)
        if oid:
            placed.append({"ticker": sym, "qty": whole, "order_id": oid})
        else:
            raise MissingStopLoss(f"Could not place protective trailing stop for {sym}")
    return placed


# ---------------------------------------------------------------------------
# Rebalance
# ---------------------------------------------------------------------------
def rebalance_to_weights(
    target_weights: dict[str, float],
    portfolio_value: float,
    stop_loss_pct: float = 0.07,
    min_trade_dollars: float = 50.0,
    client=None,
    trail_overrides: dict[str, float] | None = None,
) -> list[OrderResult]:
    """
    Rebalance to target_weights using WHOLE-SHARE buys, then ensure every
    position carries a trailing stop. Sells first to free cash. Trades below
    min_trade_dollars are skipped to avoid churn.
    """
    if client is None:
        client = get_alpaca_client()

    current = get_current_weights(client)
    qtys = get_position_qtys(client)
    results: list[OrderResult] = []
    sells, buys = [], []

    all_tickers = set(list(target_weights.keys()) + list(current.keys()))
    for ticker in all_tickers:
        target = target_weights.get(ticker, 0.0)
        curr = current.get(ticker, 0.0)
        diff = target - curr
        notional = abs(diff) * portfolio_value
        if notional < min_trade_dollars:
            continue
        (sells if diff < 0 else buys).append((ticker, notional, target))

    buy_ids: list[str] = []

    # SELLS first (free cash). Cancel the symbol's resting stop so the shares
    # are not locked by the open stop order.
    for ticker, notional, target in sells:
        cancel_orders_for_symbol(ticker, client)
        held = qtys.get(ticker, 0.0)
        if held <= 0:
            continue
        if target <= 0.0:
            # Full exit — use close_position, which liquidates the EXACT holding
            # (incl. fractional shares). A manual qty would be round()'d and can
            # land ABOVE the true position (e.g. 31.269488 -> 31.2695), which
            # Alpaca rejects as insufficient qty and silently strands the
            # position on margin. close_position also cancels related orders.
            try:
                o = client.close_position(ticker)
                results.append(OrderResult(
                    ticker=ticker, side="sell", qty=held, entry_price=0.0,
                    stop_price=0.0, order_id=str(o.id), status=str(o.status),
                ))
                logger.info("Closed position %s (%.6f sh)", ticker, held)
            except Exception as e:
                logger.error("Close position failed %s: %s", ticker, e)
            continue
        price = latest_price(ticker)
        if not price:
            logger.warning("No quote for %s — skipping partial trim this cycle", ticker)
            continue
        sell_qty = min(held, round(notional / price, 4))
        if sell_qty <= 0:
            continue
        try:
            results.append(_market_order(ticker, "sell", sell_qty, client))
        except Exception as e:
            logger.error("Sell failed %s: %s", ticker, e)

    # BUYS as whole shares.
    for ticker, notional, target in buys:
        price = latest_price(ticker)
        if not price:
            logger.warning("No quote for %s — skipping buy", ticker)
            continue
        qty = int(notional // price)   # whole shares only
        if qty < 1:
            logger.info("%s buy notional $%.2f < 1 share ($%.2f) — skipping",
                        ticker, notional, price)
            continue
        try:
            r = _market_order(ticker, "buy", qty, client)
            trail_frac = (trail_overrides or {}).get(ticker, stop_loss_pct * 100.0) / 100.0
            r.stop_price = round(price * (1.0 - trail_frac), 2)
            results.append(r)
            buy_ids.append(r.order_id)
        except Exception as e:
            logger.error("Buy failed %s: %s", ticker, e)

    # Wait for buys to fill so positions reflect new size, then protect everything.
    if buy_ids:
        _wait_for_fills(buy_ids, client)
    ensure_trailing_stops(stop_loss_pct * 100.0, client, trail_overrides=trail_overrides)

    return results


def flatten_fractional_dust(client=None, min_dollars: float = 50.0) -> list[dict]:
    """
    Sell off tiny sub-1-share leftover positions ("dust") that accumulate as
    residue from earlier sells. These can't carry a broker stop (needs whole
    shares) and just clutter the book. Skips core/cash tickers. Returns a list
    of {ticker, qty} flattened.

    Only touches positions that are BOTH fractional (<1 share) AND worth less
    than min_dollars — i.e. genuine dust, never a real holding.
    """
    if client is None:
        client = get_alpaca_client()
    flattened: list[dict] = []
    for p in client.get_all_positions():
        sym = p.symbol
        if sym in NO_STOP:
            continue
        qty = float(p.qty)
        mv = abs(float(p.market_value))
        if 0 < qty < 1 and mv < min_dollars:
            cancel_orders_for_symbol(sym, client)
            try:
                _market_order(sym, "sell", qty, client)
                flattened.append({"ticker": sym, "qty": qty})
                logger.info("Flattened dust: %s %.6f sh ($%.2f)", sym, qty, mv)
            except Exception as e:
                logger.warning("Dust flatten failed for %s: %s", sym, e)
    return flattened


def is_market_open(client=None) -> bool:
    """Check if the US market is currently open via Alpaca clock endpoint."""
    if client is None:
        client = get_alpaca_client()
    return bool(client.get_clock().is_open)
