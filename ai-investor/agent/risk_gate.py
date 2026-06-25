"""
agent/risk_gate.py

Deterministic veto layer. Has final say over every allocation before
any order touches Alpaca. The LLM never bypasses this.

Rules enforced here:
  - Max position size per name
  - Portfolio cash floor
  - Max daily loss halt
  - PDT guard (pattern day trader: <3 round trips per 5 days if equity < $25k)
  - Every order must carry a stop-loss price

If any rule triggers, the gate either trims the weights or raises RiskVeto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class RiskVeto(Exception):
    """Raised when a hard rule is violated and trading must halt."""


@dataclass
class RiskConfig:
    max_position_pct: float = 0.20    # no single name > 20% of portfolio
    cash_floor_pct: float = 0.10      # always keep >= 10% in cash
    max_daily_loss_pct: float = 0.02  # halt if portfolio down > 2% today
    stop_loss_pct: float = 0.07       # default stop-loss: 7% below entry
    pdt_equity_threshold: float = 25_000.0  # PDT rule kicks in below this
    pdt_max_day_trades: int = 3       # max round trips in a rolling 5-day window
    no_trade_band: float = 0.04       # hold a position unless it drifts > 4pp from target


@dataclass
class RiskState:
    """Mutable state the gate tracks across calls in a session."""
    portfolio_value_open: float = 0.0   # portfolio value at market open today
    day_trades_last_5: list[date] = field(default_factory=list)

    def record_day_trade(self, today: date) -> None:
        self.day_trades_last_5 = [
            d for d in self.day_trades_last_5
            if d >= today - timedelta(days=4)
        ]
        self.day_trades_last_5.append(today)

    def day_trade_count(self, today: date) -> int:
        cutoff = today - timedelta(days=4)
        return sum(1 for d in self.day_trades_last_5 if d >= cutoff)


def apply_risk_gate(
    proposed_weights: dict[str, float],
    portfolio_value: float,
    portfolio_value_open: float,
    equity: float,
    today: date,
    state: RiskState,
    config: RiskConfig | None = None,
) -> dict[str, float]:
    """
    Takes proposed target weights (from allocation agent), returns
    risk-adjusted weights. Raises RiskVeto if a hard halt is needed.

    proposed_weights: {ticker: weight} from allocation agent, summing <= 1.0
    portfolio_value: current mark-to-market value
    portfolio_value_open: value at today's open (for daily loss check)
    equity: account equity (for PDT threshold)
    today: current date
    state: mutable session state (day trades, etc.)
    config: rule parameters (uses defaults if None)
    """
    cfg = config or RiskConfig()

    # Daily loss halt
    if portfolio_value_open > 0:
        daily_loss = (portfolio_value - portfolio_value_open) / portfolio_value_open
        if daily_loss < -cfg.max_daily_loss_pct:
            raise RiskVeto(
                f"Daily loss {daily_loss:.2%} exceeds halt threshold "
                f"{cfg.max_daily_loss_pct:.2%}. No new orders today."
            )

    # PDT guard
    if equity < cfg.pdt_equity_threshold:
        day_trades_today = state.day_trade_count(today)
        if day_trades_today >= cfg.pdt_max_day_trades:
            logger.warning(
                "PDT guard: %d day trades in rolling 5 days, equity $%.0f < $25k. "
                "Blocking new round trips.", day_trades_today, equity
            )
            # Don't raise — just log and let existing positions stand
            return {}

    # Cap each position at max_position_pct
    capped: dict[str, float] = {}
    for ticker, w in proposed_weights.items():
        if w > cfg.max_position_pct:
            logger.info("Capping %s from %.1f%% to %.1f%%", ticker, w * 100, cfg.max_position_pct * 100)
            capped[ticker] = cfg.max_position_pct
        else:
            capped[ticker] = w

    # Enforce cash floor
    invested = sum(capped.values())
    max_invested = 1.0 - cfg.cash_floor_pct
    if invested > max_invested:
        scale = max_invested / invested
        capped = {t: w * scale for t, w in capped.items()}
        logger.info("Scaled weights by %.3f to enforce %.0f%% cash floor", scale, cfg.cash_floor_pct * 100)

    logger.info("Risk gate passed. Weights: %s", {t: f"{w:.1%}" for t, w in capped.items()})
    return capped


def compute_stop_price(entry_price: float, stop_loss_pct: float | None = None,
                        config: RiskConfig | None = None) -> float:
    """Return the stop-loss price for a given entry. Always required on every order."""
    cfg = config or RiskConfig()
    pct = stop_loss_pct if stop_loss_pct is not None else cfg.stop_loss_pct
    return round(entry_price * (1.0 - pct), 4)


def apply_turnover_control(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    config: RiskConfig | None = None,
) -> dict[str, float]:
    """
    Deterministic turnover discipline. A position whose target is within
    `no_trade_band` of its current weight is held at its current weight
    instead of traded — this kills pointless micro-rebalancing (the 1-share
    trims) and dampens day-to-day churn.

    Large moves still pass through: building from cash (0 -> 0.18) or fully
    exiting a name (0.18 -> 0) is a big drift and trades normally. This trims
    noise, it does not freeze the strategy.

    Returns the execution weights (drops ~zero entries).
    """
    cfg = config or RiskConfig()
    adjusted: dict[str, float] = dict(target_weights)
    held = []
    for t in set(current_weights) | set(target_weights):
        cur = current_weights.get(t, 0.0)
        tgt = target_weights.get(t, 0.0)
        if abs(tgt - cur) < cfg.no_trade_band:
            adjusted[t] = cur            # hold; don't trade a small drift
            if abs(tgt - cur) > 1e-9:
                held.append(t)
    if held:
        logger.info("Turnover control: holding %d position(s) within %.0f%% band: %s",
                    len(held), cfg.no_trade_band * 100, held)
    return {t: w for t, w in adjusted.items() if w > 1e-9}
