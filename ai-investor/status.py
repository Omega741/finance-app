"""
status.py

Quick read-only snapshot of the Alpaca paper account: portfolio value,
day P/L, open positions with unrealized P/L, and recent orders.

    python status.py
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus


def main() -> None:
    c = TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=True,
    )
    acct = c.get_account()
    pv = float(acct.portfolio_value)
    eq = float(acct.equity)
    last_eq = float(acct.last_equity)
    day_pl = eq - last_eq
    day_pct = (day_pl / last_eq * 100) if last_eq else 0.0

    print("=== ACCOUNT ===")
    print(f"Portfolio value: ${pv:,.2f}")
    print(f"Cash:            ${float(acct.cash):,.2f}")
    print(f"Today P/L:       ${day_pl:,.2f} ({day_pct:+.2f}%)")

    print("\n=== POSITIONS ===")
    pos = c.get_all_positions()
    if not pos:
        print("No open positions (orders may be pending/unfilled, or market closed).")
    total_upl = 0.0
    for p in pos:
        upl = float(p.unrealized_pl)
        total_upl += upl
        uplpc = float(p.unrealized_plpc) * 100
        print(f"{p.symbol:<6} qty={p.qty:<4} mkt=${float(p.market_value):>10,.2f}  "
              f"avg=${float(p.avg_entry_price):>8.2f}  last=${float(p.current_price):>8.2f}  "
              f"uPL=${upl:>9,.2f} ({uplpc:+.2f}%)")
    if pos:
        print(f"{'TOTAL':<6} unrealized P/L: ${total_upl:,.2f}")

    print("\n=== RECENT ORDERS ===")
    orders = c.get_orders(GetOrdersRequest(status=QueryOrderStatus.ALL, limit=20))
    for o in orders:
        side = str(o.side).split(".")[-1]
        status = str(o.status).split(".")[-1]
        filled = o.filled_avg_price or "-"
        print(f"{o.symbol:<6} {side:<4} qty={str(o.qty):<5} status={status:<10} filled_avg={filled}")


if __name__ == "__main__":
    main()
