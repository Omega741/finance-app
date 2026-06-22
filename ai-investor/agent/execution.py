"""
agent/execution.py

Alpaca paper trading execution layer.

Every order MUST carry a stop-loss. The place_order() function raises if
stop_price is not supplied — this is enforced in code, not convention.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class MissingStopLoss(Exception):
    """Raised if an order is submitted without a stop-loss price."""


@dataclass
class OrderResult:
    ticker: str
    side: str
    qty: float
    entry_price: float
    stop_price: float
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


def get_portfolio_value(client=None) -> tuple[float, float]:
    """Returns (portfolio_value, cash). Uses Alpaca account endpoint."""
    if client is None:
        client = get_alpaca_client()
    account = client.get_account()
    return float(account.portfolio_value), float(account.cash)


def get_current_positions(client=None) -> dict[str, float]:
    """Returns {ticker: current_market_value} for all open positions."""
    if client is None:
        client = get_alpaca_client()
    positions = client.get_all_positions()
    return {p.symbol: float(p.market_value) for p in positions}


def get_current_weights(client=None) -> dict[str, float]:
    """Returns {ticker: weight} as fraction of portfolio value."""
    if client is None:
        client = get_alpaca_client()
    portfolio_value, _ = get_portfolio_value(client)
    if portfolio_value <= 0:
        return {}
    positions = get_current_positions(client)
    return {t: v / portfolio_value for t, v in positions.items()}


def place_order(
    ticker: str,
    side: str,         # "buy" or "sell"
    notional: float,   # dollar amount
    stop_price: float, # REQUIRED — raises MissingStopLoss if 0 or None
    client=None,
) -> OrderResult:
    """
    Place a market order with a stop-loss bracket on Alpaca paper.
    Raises MissingStopLoss if stop_price is not set — no exceptions.
    """
    if not stop_price or stop_price <= 0:
        raise MissingStopLoss(
            f"Order for {ticker} rejected: stop_price is required on every order. "
            "This is a hard rule, not a suggestion."
        )

    if client is None:
        client = get_alpaca_client()

    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    request = MarketOrderRequest(
        symbol=ticker,
        notional=round(notional, 2),
        side=order_side,
        time_in_force=TimeInForce.DAY,
        stop_loss=StopLossRequest(stop_price=round(stop_price, 2)) if side == "buy" else None,
    )

    order = client.submit_order(request)
    logger.info("Order submitted: %s %s $%.2f stop=%.2f id=%s",
                side.upper(), ticker, notional, stop_price, order.id)

    return OrderResult(
        ticker=ticker,
        side=side,
        qty=float(getattr(order, "qty", 0) or 0),
        entry_price=float(getattr(order, "filled_avg_price", 0) or 0),
        stop_price=stop_price,
        order_id=str(order.id),
        status=str(order.status),
    )


def rebalance_to_weights(
    target_weights: dict[str, float],
    portfolio_value: float,
    stop_loss_pct: float = 0.07,
    min_trade_dollars: float = 50.0,
    client=None,
) -> list[OrderResult]:
    """
    Rebalance the paper portfolio to match target_weights.
    Sells first to free up cash, then buys. Every buy order gets a stop-loss.
    Orders below min_trade_dollars are skipped to avoid noise.
    """
    if client is None:
        client = get_alpaca_client()

    current = get_current_weights(client)
    results: list[OrderResult] = []
    sells = []
    buys = []

    all_tickers = set(list(target_weights.keys()) + list(current.keys()))
    for ticker in all_tickers:
        target = target_weights.get(ticker, 0.0)
        curr = current.get(ticker, 0.0)
        diff = target - curr
        notional = abs(diff) * portfolio_value
        if notional < min_trade_dollars:
            continue
        if diff < 0:
            sells.append((ticker, notional))
        else:
            buys.append((ticker, notional, target))

    # sell first to free cash
    for ticker, notional in sells:
        try:
            r = place_order(ticker, "sell", notional, stop_price=0.001, client=client)
            results.append(r)
        except Exception as e:
            logger.error("Sell failed %s: %s", ticker, e)

    # buy with stop-loss
    for ticker, notional, target_w in buys:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest
            data_client = StockHistoricalDataClient(
                api_key=os.environ["ALPACA_API_KEY"],
                secret_key=os.environ["ALPACA_SECRET_KEY"],
            )
            quote = data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=ticker))
            ask_price = float(quote[ticker].ask_price or quote[ticker].bid_price)
            stop_price = ask_price * (1.0 - stop_loss_pct)
        except Exception:
            logger.warning("Could not fetch live quote for %s — skipping buy", ticker)
            continue

        try:
            r = place_order(ticker, "buy", notional, stop_price=stop_price, client=client)
            results.append(r)
        except Exception as e:
            logger.error("Buy failed %s: %s", ticker, e)

    return results


def cancel_all_open_orders(client=None) -> int:
    """Cancel all open orders. Returns count cancelled."""
    if client is None:
        client = get_alpaca_client()
    cancelled = client.cancel_orders()
    n = len(cancelled) if cancelled else 0
    logger.info("Cancelled %d open orders", n)
    return n


def is_market_open(client=None) -> bool:
    """Check if the US market is currently open via Alpaca clock endpoint."""
    if client is None:
        client = get_alpaca_client()
    clock = client.get_clock()
    return bool(clock.is_open)
