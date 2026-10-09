"""
health_check.py

Deterministic portfolio watchdog — NO LLM, NO paid API, $0 to run.

Reads the live Alpaca paper account and checks it against the 20/60/20
core-satellite targets. Flags drift beyond set thresholds, margin, unprotected
positions, and dust — exactly the kinds of silent problems (e.g. the Aug/Sep
margin creep) that a once-a-week glance would otherwise miss.

Run anytime (read-only, no orders):
    python health_check.py

Exit code: 0 = all healthy, 1 = at least one WARN/FAIL (handy for schedulers).
Appends a one-line status to data/health_log.txt each run.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
os.chdir(_HERE)
sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv
load_dotenv(_HERE / ".env")

from agent.execution import (
    get_alpaca_client, get_portfolio_value, get_current_weights,
    get_position_qtys, _open_orders, NO_STOP,
)
from agent.portfolio_model import (
    CORE_ETF, CORE_WEIGHT, CASH_TICKER, CASH_WEIGHT,
    GROWTH_WATCHLIST, GROWTH_BUDGET,
)

# ---------------------------------------------------------------------------
# Thresholds — edit to taste
# ---------------------------------------------------------------------------
CORE_DRIFT = 0.05        # warn if VOO is >5pp off its 60% target
CASH_DRIFT = 0.07        # warn if SGOV is >7pp off its 20% target
GROWTH_OVER = 0.02       # warn if growth sleeve exceeds its 20% budget by >2pp
GROWTH_UNDER = 0.08      # warn if growth sleeve is >8pp UNDER budget (very idle)
DUST_DOLLARS = 50.0      # sub-1-share positions worth less than this = "dust"
LOG_PATH = _HERE / "data" / "health_log.txt"
# ---------------------------------------------------------------------------

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_ICON = {PASS: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]"}


def main() -> None:
    client = get_alpaca_client()
    pv, cash = get_portfolio_value(client)
    weights = get_current_weights(client)
    qtys = get_position_qtys(client)

    core = weights.get(CORE_ETF, 0.0)
    cashw = weights.get(CASH_TICKER, 0.0)
    growth = sum(w for t, w in weights.items() if t in GROWTH_WATCHLIST)
    invested = sum(weights.values())

    results: list[tuple[str, str]] = []

    # 1. Margin / negative cash — the big one.
    if cash < 0:
        results.append((FAIL, f"On MARGIN: cash ${cash:,.0f}, {invested*100:.0f}% invested. "
                              f"Should be <=100%."))
    else:
        results.append((PASS, f"Cash positive (${cash:,.0f}, {invested*100:.0f}% invested)."))

    # 2. Core (VOO) drift.
    d = core - CORE_WEIGHT
    results.append(((WARN if abs(d) > CORE_DRIFT else PASS),
                    f"Core {CORE_ETF} {core*100:.1f}% (target {CORE_WEIGHT*100:.0f}%, "
                    f"drift {d*100:+.1f}pp)."))

    # 3. Cash tier (SGOV) drift.
    d = cashw - CASH_WEIGHT
    results.append(((WARN if abs(d) > CASH_DRIFT else PASS),
                    f"Cash tier {CASH_TICKER} {cashw*100:.1f}% (target {CASH_WEIGHT*100:.0f}%, "
                    f"drift {d*100:+.1f}pp)."))

    # 4. Growth sleeve vs budget (over = risk creep; very under = idle).
    if growth > GROWTH_BUDGET + GROWTH_OVER:
        results.append((WARN, f"Growth sleeve {growth*100:.1f}% OVER {GROWTH_BUDGET*100:.0f}% budget."))
    elif growth < GROWTH_BUDGET - GROWTH_UNDER:
        results.append((WARN, f"Growth sleeve {growth*100:.1f}% far UNDER {GROWTH_BUDGET*100:.0f}% "
                              f"budget (idle risk capacity)."))
    else:
        results.append((PASS, f"Growth sleeve {growth*100:.1f}% within budget."))

    # 5. Every real equity position (>=1 share, not core/cash) must carry a stop.
    stopped = set()
    for o in _open_orders(client):
        otype = str(getattr(o, "order_type", "")).split(".")[-1].lower()
        if "trailing" in otype or "stop" in otype:
            stopped.add(o.symbol)
    unprotected = [s for s, q in qtys.items()
                   if s not in NO_STOP and q >= 1 and s not in stopped]
    if unprotected:
        results.append((FAIL, f"Unprotected position(s) with no stop: {', '.join(unprotected)}."))
    else:
        results.append((PASS, "Every equity position has a protective stop."))

    # 6. Fractional dust (informational — can't carry a stop, just clutter).
    dust = [s for s, q in qtys.items()
            if s not in NO_STOP and 0 < q < 1 and weights.get(s, 0) * pv < DUST_DOLLARS]
    if dust:
        results.append((WARN, f"Fractional dust (sub-1-share leftovers): {', '.join(dust)}."))

    # --- Report ---
    worst = FAIL if any(s == FAIL for s, _ in results) else (
        WARN if any(s == WARN for s, _ in results) else PASS)
    print(f"\n=== Portfolio Health — {date.today()} ===")
    print(f"Value ${pv:,.2f}  |  overall: {worst}\n")
    for status, msg in results:
        print(f"  {_ICON[status]} {msg}")
    print()

    # Append a one-line history entry.
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            issues = [m for s, m in results if s != PASS]
            f.write(f"{date.today()}\t{worst}\t${pv:,.2f}\t"
                    f"core={core*100:.0f}% cash={cashw*100:.0f}% growth={growth*100:.0f}%\t"
                    f"{' | '.join(issues) if issues else 'all clear'}\n")
    except Exception as e:
        print(f"(log write failed: {e})")

    sys.exit(0 if worst == PASS else 1)


if __name__ == "__main__":
    main()
