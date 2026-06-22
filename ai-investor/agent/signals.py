"""
agent/signals.py

Deterministic signal engine. No LLM here — pure math.
Outputs a numeric score per ticker that feeds into the allocation agent.

The risk gate and execution layer trust these numbers. Keep them honest.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SignalBundle:
    ticker: str
    rsi_14: float
    ma_50: float
    ma_200: float
    macd_signal: float   # MACD line minus signal line (positive = bullish)
    atr_14: float        # Average True Range — used for stop-loss sizing
    momentum_12_1: float # 12-month minus 1-month return (Fama-French style)
    score: float         # composite score in [-1, 1]; higher = more bullish


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / last_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _macd_signal_diff(series: pd.Series) -> float:
    """MACD(12,26) minus signal(9). Positive means bullish crossover territory."""
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return float((macd - signal).iloc[-1])


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])


def compute_signals(prices: pd.DataFrame, tickers: list[str]) -> dict[str, SignalBundle]:
    """
    Compute deterministic signals for each ticker. Requires at minimum 252
    rows of close-price data. Returns empty dict for any ticker below that.

    prices: DataFrame indexed by date, columns = tickers (close prices).
    For ATR, pass a prices frame with MultiIndex columns or call with OHLC
    data — if only close is available, ATR falls back to close-based proxy.
    """
    results: dict[str, SignalBundle] = {}
    min_rows = 260

    for ticker in tickers:
        if ticker not in prices.columns:
            continue
        col = prices[ticker].dropna()
        if len(col) < min_rows:
            continue

        close = col.iloc[-min_rows:]
        rsi = _rsi(close)
        ma50 = float(close.iloc[-50:].mean())
        ma200 = float(close.iloc[-200:].mean())
        macd_diff = _macd_signal_diff(close)

        # ATR proxy using close only (high-low not always available)
        atr = float(close.diff().abs().ewm(span=14, adjust=False).mean().iloc[-1])

        # 12-month minus 1-month momentum (skip most recent month to avoid reversal)
        if len(close) >= 253:
            mom_12_1 = float(close.iloc[-252] / close.iloc[-253] - 1.0)
            mom_1 = float(close.iloc[-1] / close.iloc[-22] - 1.0)
            momentum = mom_12_1 - mom_1
        else:
            momentum = 0.0

        # composite score in [-1, 1]
        rsi_score = (50.0 - rsi) / 50.0          # oversold = positive
        ma_score = 1.0 if close.iloc[-1] > ma200 else -1.0
        macd_score = np.tanh(macd_diff / (close.iloc[-1] * 0.01 + 1e-9))
        mom_score = np.tanh(momentum * 5)
        score = float(0.25 * rsi_score + 0.35 * ma_score + 0.20 * macd_score + 0.20 * mom_score)

        results[ticker] = SignalBundle(
            ticker=ticker,
            rsi_14=rsi,
            ma_50=ma50,
            ma_200=ma200,
            macd_signal=macd_diff,
            atr_14=atr,
            momentum_12_1=momentum,
            score=score,
        )

    return results


def signals_to_dict(bundles: dict[str, SignalBundle]) -> dict[str, dict]:
    """Serialize for Claude API context or journaling."""
    return {
        t: {
            "rsi_14": round(b.rsi_14, 2),
            "price_above_ma200": b.ma_50 > b.ma_200,
            "macd_signal": round(b.macd_signal, 4),
            "momentum_12_1": round(b.momentum_12_1, 4),
            "atr_14": round(b.atr_14, 4),
            "score": round(b.score, 4),
        }
        for t, b in bundles.items()
    }
