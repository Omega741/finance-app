"""
agent/research.py

Research agent: pulls recent news + price context for the watchlist,
then calls Claude to synthesize sentiment and flag risks.

Output feeds into the allocation agent as context — NOT as a direct
price prediction. The LLM says "here is what the news suggests";
the deterministic signal engine says "here is what the math says."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .llm import chat_json
from . import finbert_sentiment

logger = logging.getLogger(__name__)

MAX_TOKENS = 2048


@dataclass
class ResearchResult:
    ticker: str
    sentiment: str        # "bullish" | "bearish" | "neutral"
    confidence: float     # 0.0 to 1.0
    summary: str          # 2-3 sentence synthesis
    flags: list[str]      # red flags to surface to risk gate / journal


def _normalize_items(parsed) -> list:
    """
    Coerce whatever JSON shape a local model returned into a list of
    per-ticker dicts. Handles:
      - list of dicts (intended)            -> as-is
      - dict wrapping a list under any key  -> the inner list
      - dict keyed by ticker {AAPL: {...}}  -> [{ticker: AAPL, ...}, ...]
      - anything else                       -> [] (caller falls back)
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        inner = next((v for v in parsed.values() if isinstance(v, list)), None)
        if inner is not None:
            return inner
        if parsed and all(isinstance(v, dict) for v in parsed.values()):
            return [{**v, "ticker": k} for k, v in parsed.items()]
        return [parsed]
    return []


def fetch_news_headlines(tickers: list[str]) -> dict[str, list[str]]:
    """Pull recent news headlines via yfinance. Returns {ticker: [headline, ...]}."""
    headlines: dict[str, list[str]] = {}
    try:
        import yfinance as yf
        for ticker in tickers:
            try:
                info = yf.Ticker(ticker).news
                headlines[ticker] = [
                    item.get("content", {}).get("title", "")
                    for item in (info or [])[:5]
                    if item.get("content", {}).get("title")
                ]
            except Exception:
                headlines[ticker] = []
    except ImportError:
        logger.warning("yfinance not available — skipping news fetch")
    return headlines


def run_research_agent(
    tickers: list[str],
    signals_summary: dict[str, dict],
    headlines: dict[str, list[str]] | None = None,
) -> dict[str, ResearchResult]:
    """
    Call Claude to synthesize news + signal context into a structured
    research view per ticker.

    Returns a dict of ResearchResult per ticker. Falls back to neutral
    if the call fails — never blocks execution.
    """
    if headlines is None:
        headlines = fetch_news_headlines(tickers)

    context_lines = []
    for t in tickers:
        sig = signals_summary.get(t, {})
        news = headlines.get(t, [])
        context_lines.append(
            f"{t}: RSI={sig.get('rsi_14','?')}, "
            f"above_MA200={'yes' if sig.get('price_above_ma200') else 'no'}, "
            f"momentum={sig.get('momentum_12_1','?')}, "
            f"score={sig.get('score','?')}. "
            f"News: {'; '.join(news[:3]) if news else 'none available'}"
        )

    prompt = (
        "You are a research analyst. Below is signal data and recent news headlines "
        "for a set of stocks. For EACH ticker, output a JSON object with keys: "
        "ticker, sentiment (bullish/bearish/neutral), confidence (0.0-1.0), "
        "summary (2-3 sentences), flags (list of red flags, empty list if none).\n\n"
        "Return a JSON array of these objects. No other text.\n\n"
        "Data:\n" + "\n".join(context_lines)
    )

    results: dict[str, ResearchResult] = {}
    try:
        parsed = chat_json(prompt, max_tokens=MAX_TOKENS)
        for item in _normalize_items(parsed):
            if not isinstance(item, dict):
                continue  # local models sometimes emit bare strings — skip them
            t = item.get("ticker", "")
            if t in tickers:
                flags = item.get("flags", [])
                if not isinstance(flags, list):
                    flags = [str(flags)] if flags else []
                results[t] = ResearchResult(
                    ticker=t,
                    sentiment=str(item.get("sentiment", "neutral")),
                    confidence=float(item.get("confidence", 0.5) or 0.5),
                    summary=str(item.get("summary", "")),
                    flags=flags,
                )
    except Exception as e:
        logger.error("Research agent failed: %s. Falling back to neutral.", e)

    # fill missing tickers with neutral
    for t in tickers:
        if t not in results:
            results[t] = ResearchResult(
                ticker=t, sentiment="neutral", confidence=0.0,
                summary="Research unavailable.", flags=[]
            )

    # FinBERT override: a finance-tuned classifier is more reliable than a
    # general LLM at the sentiment label. Where it has headlines to score, its
    # sentiment + confidence replace the LLM's. The LLM keeps summary + flags.
    if finbert_sentiment.is_available():
        for t in tickers:
            fb = finbert_sentiment.score_ticker(headlines.get(t, []))
            if fb:
                results[t].sentiment = fb["sentiment"]
                results[t].confidence = fb["confidence"]
                if fb["sentiment"] != "neutral":
                    results[t].summary = (
                        f"[FinBERT {fb['sentiment']} {fb['net_score']:+.2f} "
                        f"from {fb['n']} headlines] " + results[t].summary
                    )

    return results
