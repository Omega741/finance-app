"""
agent/portfolio_model.py

Core-satellite target model. The portfolio is split into three structural
tiers whose top-level weights are FIXED (not LLM-decided):

    Cash floor  20%  -> SGOV (T-bills, ~4-5% yield, parked)
    Core        60%  -> VOO  (broad S&P 500 index, buy-and-hold, no stop)
    Growth      20%  -> a few volatile names, actively managed WITH stops

Only the growth sleeve is allocated by the LLM, and only within its 20%
budget. The core and cash tiers are deterministic. This is what keeps the
taxable turnover confined to a small slice of the book: the core just
compounds and is essentially never sold; the growth sleeve is where the
active buy/sell (and the trailing stops) live.

Research backing (see conversation): core-satellite 80/20 is the standard
conservative split; DCA/averaging belongs on the broad core, not single
names; the profit lever is the allocation + staying invested, not the
averaging technique.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# --- Tier definitions (the 20/60/20 the user chose) -------------------------
CASH_TICKER = "SGOV"
CASH_WEIGHT = 0.20

CORE_ETF = "VOO"          # S&P 500. VTI (total market) is an equivalent swap.
CORE_WEIGHT = 0.60

GROWTH_BUDGET = 0.20      # total sleeve size the LLM allocates within
GROWTH_MAX_PER_NAME = 0.10  # no single growth name > half the sleeve

# Higher-beta names the growth sleeve picks among. Deliberately excludes the
# defensive/value names (JPM, JNJ, XOM, UNH, BRK-B) — those are already held
# inside VOO, so putting them here too would just dilute back toward the index.
GROWTH_WATCHLIST = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN"]


def compose_target_weights(growth_weights_raw: dict[str, float]) -> dict[str, float]:
    """
    Turn the LLM's raw growth-sleeve weights into a full portfolio target:
    {VOO: 0.60, <growth names>: up to 0.20 total, SGOV: remainder}.

    The LLM is allowed to run the growth sleeve UNDER budget when it is
    cautious (bearish) — the unspent portion falls through to SGOV rather
    than being forced into stocks. It can never run OVER 20%, and no single
    growth name exceeds GROWTH_MAX_PER_NAME.
    """
    growth: dict[str, float] = {}
    for t, w in growth_weights_raw.items():
        if t in GROWTH_WATCHLIST and isinstance(w, (int, float)) and w > 0:
            growth[t] = min(float(w), GROWTH_MAX_PER_NAME)

    gsum = sum(growth.values())
    if gsum > GROWTH_BUDGET and gsum > 0:          # scale down to fit budget
        scale = GROWTH_BUDGET / gsum
        growth = {t: w * scale for t, w in growth.items()}
        gsum = GROWTH_BUDGET

    target: dict[str, float] = {CORE_ETF: CORE_WEIGHT}
    for t, w in growth.items():
        if w > 1e-4:
            target[t] = w

    # SGOV absorbs whatever isn't in core + growth (>= 20% by construction).
    target[CASH_TICKER] = max(0.0, 1.0 - CORE_WEIGHT - gsum)

    logger.info("Target: core %s %.0f%% | growth %s | cash %s %.0f%%",
                CORE_ETF, CORE_WEIGHT * 100,
                {t: f"{w:.1%}" for t, w in growth.items()},
                CASH_TICKER, target[CASH_TICKER] * 100)
    return target
