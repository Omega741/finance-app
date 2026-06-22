"""
run_example.py

Runnable demo. Tries to pull real prices with yfinance. Falls back to
synthetic data if unavailable so the harness still runs end-to-end.

    python run_example.py

Honest expectation: on real broad data, after costs, active strategies will
usually land near or below the buy-and-hold benchmark. That is the point.
A clean harness that tells you the truth is worth more than a dirty one
that flatters you.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from harness.core import (
    Universe, CostModel, walk_forward, summarize, warn_if_overfit,
    sharpe, run_backtest,
)
from harness import strategies as S


def load_prices() -> tuple[pd.DataFrame, list[str], bool]:
    tickers = ["AAPL", "MSFT", "JNJ", "PG", "XOM", "JPM", "KO", "WMT", "NVDA", "CVX"]
    try:
        import yfinance as yf
        df = yf.download(tickers, start="2010-01-01", auto_adjust=True, progress=False)
        prices = df["Close"].dropna(how="all").ffill().dropna()
        if len(prices) > 500:
            return prices, list(prices.columns), True
    except Exception as e:
        warnings.warn(f"yfinance unavailable ({e!r}); using synthetic data.")

    rng = np.random.default_rng(7)
    n = 252 * 14
    dates = pd.bdate_range("2011-01-01", periods=n)
    drifts = np.array([0.16, 0.14, 0.05, 0.06, 0.02, 0.08, 0.04, 0.07, 0.20, 0.03]) / 252
    vols = np.array([0.26, 0.22, 0.16, 0.15, 0.27, 0.24, 0.17, 0.16, 0.34, 0.25]) / np.sqrt(252)
    rets = rng.normal(drifts, vols, size=(n, len(drifts)))
    cols = [f"SYN{i}" for i in range(len(drifts))]
    prices = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=cols)
    return prices, cols, False


def run_strategy(label: str, factory, prices, universe, cost) -> None:
    print(f"\n=== {label} (out-of-sample, walk-forward) ===")
    res = walk_forward(prices, factory, universe, cost,
                       train_years=4, test_years=1, rebalance="ME", signal_lag=1)
    table = summarize(res)
    print(table.round(3).to_string())

    strat = factory()
    strat.fit(prices)
    in_sample = run_backtest(prices, strat, universe, cost).returns
    warn_if_overfit(sharpe(in_sample), sharpe(res.oos_returns),
                    n_params=2, n_oos_obs=len(res.oos_returns))

    oos_s = sharpe(res.oos_returns)
    bm_s = sharpe(res.benchmark_returns)
    verdict = "BEATS" if oos_s > bm_s else "LOSES TO"
    print(f"-> OOS Sharpe {oos_s:.2f} {verdict} benchmark {bm_s:.2f}")

    for fold in res.fold_metrics:
        beat = "+" if fold["strategy_sharpe"] > fold["benchmark_sharpe"] else "-"
        print(f"   {fold['test_start']} to {fold['test_end']}: "
              f"strat={fold['strategy_sharpe']:.2f} bm={fold['benchmark_sharpe']:.2f} {beat}")


def main() -> None:
    prices, tickers, real = load_prices()
    print(f"Data: {'REAL (yfinance)' if real else 'SYNTHETIC fallback'} | "
          f"{prices.index.min().date()} to {prices.index.max().date()} | {len(tickers)} names")

    universe = Universe.static(tickers)
    cost = CostModel(commission_bps=1.0, slippage_bps=5.0)

    configs = {
        "time_series_trend": lambda: S.TimeSeriesTrend(lookback=200),
        "cross_sectional_momentum": lambda: S.CrossSectionalMomentum(lookback=252, skip=21, top_frac=0.3),
        "rsi_momentum": lambda: S.RSIMomentum(rsi_period=14, oversold=45, ma_period=200),
        "dual_momentum": lambda: S.DualMomentum(lookback=252),
        "vol_targeting_trend": lambda: S.VolatilityTargeting(
            S.TimeSeriesTrend(lookback=200), target_vol=0.12
        ),
    }

    for label, factory in configs.items():
        run_strategy(label, factory, prices, universe, cost)

    print("\n\nNote: static universe on current tickers = survivorship bias warning is expected.")
    print("For a clean study, supply a point-in-time constituents file via Universe(members=...).")


if __name__ == "__main__":
    main()
