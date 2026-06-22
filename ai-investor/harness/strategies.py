"""
harness/strategies.py

Swappable strategies for the harness. Each only ever sees point-in-time
history and the as-of universe — none can cheat by construction.

Add your own by subclassing Strategy and implementing target_weights.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .core import Strategy


class EqualWeightBuyHold(Strategy):
    """Benchmark. Own the whole as-of universe in equal weight. Every active
    strategy must beat this after costs. Most never do."""

    name = "equal_weight_buy_hold"

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        uni = [t for t in universe if t in history.columns]
        if not uni:
            return {}
        w = 1.0 / len(uni)
        return {t: w for t in uni}


class TimeSeriesTrend(Strategy):
    """
    Absolute momentum. Go long only if a name's own trailing return over
    `lookback` days is positive, else hold cash in that slot. Equal weight
    across passing names. Manufactures positive skew: cut losers, ride winners.
    """

    name = "time_series_trend"

    def __init__(self, lookback: int = 200, top_n: int | None = None):
        self.lookback = lookback
        self.top_n = top_n

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        uni = [t for t in universe if t in history.columns]
        if len(history) < self.lookback + 1 or not uni:
            return {}
        window = history[uni].iloc[-(self.lookback + 1):]
        trailing = window.iloc[-1] / window.iloc[0] - 1.0
        winners = trailing[trailing > 0.0]
        if winners.empty:
            return {}
        if self.top_n:
            winners = winners.sort_values(ascending=False).head(self.top_n)
        w = 1.0 / len(winners)
        return {t: w for t in winners.index}


class CrossSectionalMomentum(Strategy):
    """
    Relative momentum. Rank the as-of universe by trailing return and hold
    the top fraction in equal weight. Skips the most recent `skip` days to
    dodge the short-term reversal effect. Long only.
    """

    name = "cross_sectional_momentum"

    def __init__(self, lookback: int = 252, skip: int = 21, top_frac: float = 0.2):
        self.lookback = lookback
        self.skip = skip
        self.top_frac = top_frac

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        uni = [t for t in universe if t in history.columns]
        need = self.lookback + self.skip + 1
        if len(history) < need or not uni:
            return {}
        window = history[uni]
        end = window.iloc[-(self.skip + 1)]
        start = window.iloc[-(self.lookback + self.skip + 1)]
        mom = (end / start - 1.0).dropna()
        if mom.empty:
            return {}
        k = max(1, int(round(len(mom) * self.top_frac)))
        picks = mom.sort_values(ascending=False).head(k)
        w = 1.0 / len(picks)
        return {t: w for t in picks.index}


class RSIMomentum(Strategy):
    """
    RSI filter + moving average trend confirmation. Buys names where:
      - RSI(rsi_period) < oversold threshold (mean-reversion entry)
      - Price is above its long MA (only buy in uptrends)

    Equal-weights the qualifying names. Purely deterministic — no LLM.
    This is the kind of signal layer that feeds into the allocation agent.
    """

    name = "rsi_momentum"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 40.0,
        ma_period: int = 200,
        top_n: int | None = None,
    ):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.ma_period = ma_period
        self.top_n = top_n

    @staticmethod
    def _rsi(prices: pd.Series, period: int) -> float:
        delta = prices.diff().dropna()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        if loss.iloc[-1] == 0:
            return 100.0
        rs = gain.iloc[-1] / loss.iloc[-1]
        return float(100.0 - 100.0 / (1.0 + rs))

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        uni = [t for t in universe if t in history.columns]
        need = max(self.rsi_period + 1, self.ma_period)
        if len(history) < need or not uni:
            return {}

        picks: list[tuple[str, float]] = []
        for ticker in uni:
            col = history[ticker].dropna()
            if len(col) < need:
                continue
            rsi_val = self._rsi(col.iloc[-self.rsi_period * 3:], self.rsi_period)
            ma_val = float(col.iloc[-self.ma_period:].mean())
            price = float(col.iloc[-1])
            if rsi_val < self.oversold and price > ma_val:
                picks.append((ticker, rsi_val))

        if not picks:
            return {}

        # sort by most oversold first (lowest RSI = strongest mean-reversion signal)
        picks.sort(key=lambda x: x[1])
        if self.top_n:
            picks = picks[: self.top_n]

        w = 1.0 / len(picks)
        return {t: w for t, _ in picks}


class DualMomentum(Strategy):
    """
    Gary Antonacci's Dual Momentum: combines absolute momentum (is return
    above T-bills proxy?) with relative momentum (rank vs peers). Only holds
    the top relative performer if it also clears the absolute threshold.
    Falls to cash otherwise — this is the crash-protection property.
    """

    name = "dual_momentum"

    def __init__(self, lookback: int = 252, abs_threshold: float = 0.0):
        self.lookback = lookback
        self.abs_threshold = abs_threshold  # annualized proxy for risk-free rate

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        uni = [t for t in universe if t in history.columns]
        if len(history) < self.lookback + 1 or not uni:
            return {}
        window = history[uni].iloc[-(self.lookback + 1):]
        trailing = (window.iloc[-1] / window.iloc[0] - 1.0).dropna()
        # absolute filter: must beat threshold
        passing = trailing[trailing > self.abs_threshold]
        if passing.empty:
            return {}
        # relative: best of the passing set
        best = passing.idxmax()
        return {best: 1.0}


class VolatilityTargeting(Strategy):
    """
    Wraps any weight set with a volatility overlay. Scales the portfolio up or
    down so realized volatility targets `target_vol`. Caps at `max_leverage`
    (default 1.0 = no leverage, long only constraint preserved).

    Use as a wrapper: pass a base strategy and this adjusts position sizes.
    """

    name = "volatility_targeting"

    def __init__(
        self,
        base: Strategy,
        target_vol: float = 0.15,
        lookback: int = 60,
        max_leverage: float = 1.0,
    ):
        self.base = base
        self.target_vol = target_vol / np.sqrt(TRADING_DAYS := 252)
        self.lookback = lookback
        self.max_leverage = max_leverage

    def fit(self, train_prices: pd.DataFrame) -> None:
        self.base.fit(train_prices)

    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        base_w = self.base.target_weights(history, universe)
        if not base_w:
            return {}

        tickers = [t for t in base_w if t in history.columns]
        if not tickers or len(history) < self.lookback + 1:
            return base_w

        w = pd.Series(base_w).reindex(tickers).fillna(0.0)
        rets = history[tickers].pct_change().dropna().iloc[-self.lookback:]
        port_vol = float(np.sqrt((w.values @ rets.cov().values @ w.values) * 252))
        if port_vol <= 0:
            return base_w

        scale = min(self.target_vol * np.sqrt(252) / port_vol, self.max_leverage)
        scaled = {t: float(base_w[t] * scale) for t in base_w}
        return scaled
