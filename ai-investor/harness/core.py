"""
harness/core.py

Bias-guarded backtesting harness with a swappable strategy slot.

Four structural guards against the things that make backtests lie:
  1. Point-in-time data: strategy only ever sees prices up to the decision bar.
     _assert_point_in_time raises LookaheadError if anything leaks through.
  2. Signal lag: weights decided on bar T execute at bar T+lag. Cannot trade
     on the bar used to decide.
  3. As-of universe: Universe.as_of(date) is the only entry point for ticker
     lists. A current-constituent list triggers the survivorship warning.
  4. Walk-forward: parameters fit on train window, scored on following OOS
     window only. Reported numbers are always out-of-sample.

This module has no opinion on strategy. Drop any Strategy subclass into it.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------
class Strategy(ABC):
    """
    Subclass this and implement target_weights.

    fit() is optional — runs once per walk-forward fold on the train window.
    Must never see test data.

    target_weights() runs on each rebalance date. Receives only point-in-time
    history and the as-of universe. Returns {ticker: weight}, long-only,
    weights summing to <= 1.0. Remainder is cash.
    """

    name: str = "unnamed"

    def fit(self, train_prices: pd.DataFrame) -> None:
        return None

    @abstractmethod
    def target_weights(self, history: pd.DataFrame, universe: list[str]) -> dict[str, float]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------
@dataclass
class CostModel:
    """Per-trade costs charged on turnover at each rebalance."""
    commission_bps: float = 1.0
    slippage_bps: float = 5.0

    def cost_on_turnover(self, turnover: float) -> float:
        per_unit = (self.commission_bps + self.slippage_bps) / 1e4
        return turnover * per_unit


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
@dataclass
class Universe:
    """
    Point-in-time investable set.

    For a survivorship-free study, back members with a file of historical
    index constituents (date, ticker) so the set changes over time and
    includes names that were later delisted.
    """
    members: Callable[[pd.Timestamp], list[str]]
    _static_warned: bool = field(default=False, repr=False)

    @classmethod
    def static(cls, tickers: list[str]) -> "Universe":
        """Fixed universe. WILL warn: static current-ticker lists are the
        classic survivorship-bias source."""
        tickers = list(tickers)
        return cls(members=lambda _d: tickers)

    def as_of(self, date: pd.Timestamp) -> list[str]:
        return list(self.members(date))


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
class LookaheadError(RuntimeError):
    pass


def _assert_point_in_time(history: pd.DataFrame, decision_date: pd.Timestamp) -> None:
    if len(history.index) and history.index.max() > decision_date:
        raise LookaheadError(
            f"Strategy received data dated {history.index.max()} while deciding "
            f"on {decision_date}. That is lookahead. Aborting."
        )


def warn_if_static_universe(universe: Universe, dates: list[pd.Timestamp]) -> None:
    if len(dates) < 2 or universe._static_warned:
        return
    first = set(universe.as_of(dates[0]))
    last = set(universe.as_of(dates[-1]))
    if first == last:
        universe._static_warned = True
        warnings.warn(
            "Universe is identical at the start and end of the test period. "
            "If this is a current ticker list, results are almost certainly "
            "inflated by survivorship bias (delisted names are missing). "
            "Use a point-in-time constituents file instead.",
            stacklevel=2,
        )


def warn_if_overfit(in_sample_sharpe: float, oos_sharpe: float,
                    n_params: int, n_oos_obs: int) -> None:
    if n_oos_obs > 0 and n_params > 0 and n_params > n_oos_obs / 30:
        warnings.warn(
            f"{n_params} tuned params against {n_oos_obs} OOS observations is a high "
            "ratio. High risk of data snooping. Reduce params or extend the window.",
            stacklevel=2,
        )
    if in_sample_sharpe > 0 and oos_sharpe < 0.5 * in_sample_sharpe:
        warnings.warn(
            f"OOS Sharpe ({oos_sharpe:.2f}) is far below in-sample ({in_sample_sharpe:.2f}). "
            "Classic overfitting signature. Treat the backtest as fiction until this closes.",
            stacklevel=2,
        )


# ---------------------------------------------------------------------------
# Single-window backtest
# ---------------------------------------------------------------------------
@dataclass
class BacktestResult:
    returns: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series

    @property
    def equity(self) -> pd.Series:
        return (1.0 + self.returns).cumprod()


def run_backtest(
    prices: pd.DataFrame,
    strategy: Strategy,
    universe: Universe,
    cost_model: CostModel,
    rebalance: str = "ME",
    signal_lag: int = 1,
) -> BacktestResult:
    """
    Run one strategy over one price window. Enforces point-in-time data and
    signal lag. Returns net-of-cost daily returns.
    """
    prices = prices.sort_index()
    daily_ret = prices.pct_change().fillna(0.0)

    rebal_dates = prices.resample(rebalance).last().index
    rebal_dates = [d for d in rebal_dates if d in prices.index]

    warn_if_static_universe(universe, list(prices.index[[0, -1]]))

    weight_rows: dict[pd.Timestamp, dict[str, float]] = {}
    turnover_rows: dict[pd.Timestamp, float] = {}
    prev_w = pd.Series(dtype=float)

    held = pd.Series(0.0, index=prices.columns)
    held_by_day: dict[pd.Timestamp, pd.Series] = {}

    all_days = list(prices.index)
    live_day: dict[pd.Timestamp, pd.Timestamp] = {}
    for d in rebal_dates:
        i = all_days.index(d)
        j = min(i + signal_lag, len(all_days) - 1)
        live_day[all_days[j]] = d

    pending_cost: dict[pd.Timestamp, float] = {}

    for day in all_days:
        if day in live_day:
            decision_date = live_day[day]
            history = prices.loc[:decision_date]
            _assert_point_in_time(history, decision_date)
            uni = universe.as_of(decision_date)
            raw = strategy.target_weights(history, uni) or {}
            w = pd.Series(raw, dtype=float).reindex(prices.columns).fillna(0.0)
            w = w.clip(lower=0.0)
            total = w.sum()
            if total > 1.0:
                w = w / total
            prev = (prev_w.reindex(prices.columns).fillna(0.0)
                    if len(prev_w) else pd.Series(0.0, index=prices.columns))
            turn = float((w - prev).abs().sum())
            turnover_rows[decision_date] = turn
            weight_rows[decision_date] = {k: float(v) for k, v in w[w != 0].items()}
            pending_cost[day] = cost_model.cost_on_turnover(turn)
            held = w
            prev_w = w
        held_by_day[day] = held.copy()

    held_df = pd.DataFrame(held_by_day).T.reindex(prices.index).fillna(0.0)
    gross = (held_df.shift(1).fillna(0.0) * daily_ret).sum(axis=1)
    cost_series = pd.Series(pending_cost).reindex(prices.index).fillna(0.0)
    net = gross - cost_series

    return BacktestResult(
        returns=net,
        weights=pd.DataFrame(weight_rows).T.fillna(0.0),
        turnover=pd.Series(turnover_rows),
    )


# ---------------------------------------------------------------------------
# Walk-forward driver
# ---------------------------------------------------------------------------
@dataclass
class Fold:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def make_folds(index: pd.DatetimeIndex, train_years: float, test_years: float) -> list[Fold]:
    folds: list[Fold] = []
    start = index.min()
    end = index.max()
    train_delta = pd.DateOffset(months=int(round(train_years * 12)))
    test_delta = pd.DateOffset(months=int(round(test_years * 12)))
    cur_train_start = start
    while True:
        train_end = cur_train_start + train_delta
        test_end = train_end + test_delta
        if test_end > end:
            if train_end < end:
                folds.append(Fold(cur_train_start, train_end, train_end, end))
            break
        folds.append(Fold(cur_train_start, train_end, train_end, test_end))
        cur_train_start = train_end
    return folds


@dataclass
class WalkForwardResult:
    oos_returns: pd.Series
    benchmark_returns: pd.Series
    folds: list[Fold]
    fold_metrics: list[dict]

    @property
    def equity(self) -> pd.Series:
        return (1.0 + self.oos_returns).cumprod()

    @property
    def benchmark_equity(self) -> pd.Series:
        return (1.0 + self.benchmark_returns).cumprod()


def walk_forward(
    prices: pd.DataFrame,
    strategy_factory: Callable[[], Strategy],
    universe: Universe,
    cost_model: CostModel,
    train_years: float = 3.0,
    test_years: float = 1.0,
    rebalance: str = "ME",
    signal_lag: int = 1,
    benchmark_factory: Callable[[], Strategy] | None = None,
) -> WalkForwardResult:
    """
    Fit on each train window, score only on the following test window. Stitches
    OOS segments into one equity curve. Benchmark is run over identical OOS
    windows for a fair comparison.
    """
    from .strategies import EqualWeightBuyHold

    folds = make_folds(prices.index, train_years, test_years)
    if not folds:
        raise ValueError("Not enough data for even one train/test fold.")

    bench_factory = benchmark_factory or EqualWeightBuyHold

    oos_chunks: list[pd.Series] = []
    bench_chunks: list[pd.Series] = []
    fold_metrics: list[dict] = []

    for f in folds:
        train = prices.loc[f.train_start:f.train_end]
        test = prices.loc[:f.test_end]

        strat = strategy_factory()
        strat.fit(train)
        res = run_backtest(test, strat, universe, cost_model, rebalance, signal_lag)
        oos = res.returns.loc[f.test_start:f.test_end]
        oos_chunks.append(oos)

        bench = bench_factory()
        bench.fit(train)
        bres = run_backtest(test, bench, universe, cost_model, rebalance, signal_lag)
        boos = bres.returns.loc[f.test_start:f.test_end]
        bench_chunks.append(boos)

        fold_metrics.append({
            "test_start": f.test_start.date(),
            "test_end": f.test_end.date(),
            "strategy_sharpe": sharpe(oos),
            "benchmark_sharpe": sharpe(boos),
        })

    oos_returns = pd.concat(oos_chunks).sort_index()
    oos_returns = oos_returns[~oos_returns.index.duplicated(keep="first")]
    bench_returns = pd.concat(bench_chunks).sort_index()
    bench_returns = bench_returns[~bench_returns.index.duplicated(keep="first")]

    return WalkForwardResult(oos_returns, bench_returns, folds, fold_metrics)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def sharpe(returns: pd.Series, rf_daily: float = 0.0) -> float:
    r = returns.dropna()
    if r.std() == 0 or len(r) < 2:
        return 0.0
    return float((r.mean() - rf_daily) / r.std() * np.sqrt(TRADING_DAYS))


def sortino(returns: pd.Series, rf_daily: float = 0.0) -> float:
    r = returns.dropna()
    downside = r[r < rf_daily]
    dd = downside.std()
    if dd == 0 or len(r) < 2:
        return 0.0
    return float((r.mean() - rf_daily) / dd * np.sqrt(TRADING_DAYS))


def cagr(returns: pd.Series) -> float:
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    total = (1.0 + r).prod()
    years = len(r) / TRADING_DAYS
    if years <= 0 or total <= 0:
        return 0.0
    return float(total ** (1.0 / years) - 1.0)


def max_drawdown(returns: pd.Series) -> float:
    eq = (1.0 + returns.fillna(0.0)).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return float(dd.min())


def calmar(returns: pd.Series) -> float:
    """CAGR divided by absolute max drawdown. Higher = better risk-adjusted return."""
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return 0.0
    return float(cagr(returns) / mdd)


def longest_drawdown_days(returns: pd.Series) -> int:
    eq = (1.0 + returns.fillna(0.0)).cumprod()
    peak = eq.cummax()
    underwater = eq < peak
    longest = cur = 0
    for u in underwater:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return int(longest)


def summarize(result: WalkForwardResult) -> pd.DataFrame:
    """Side-by-side OOS strategy vs benchmark. The only table that matters."""
    s, b = result.oos_returns, result.benchmark_returns
    rows = {
        "CAGR": [cagr(s), cagr(b)],
        "Sharpe": [sharpe(s), sharpe(b)],
        "Sortino": [sortino(s), sortino(b)],
        "Calmar": [calmar(s), calmar(b)],
        "MaxDrawdown": [max_drawdown(s), max_drawdown(b)],
        "LongestDD_days": [longest_drawdown_days(s), longest_drawdown_days(b)],
        "Vol_ann": [float(s.std() * np.sqrt(TRADING_DAYS)), float(b.std() * np.sqrt(TRADING_DAYS))],
    }
    df = pd.DataFrame(rows, index=["strategy", "benchmark"]).T
    return df
