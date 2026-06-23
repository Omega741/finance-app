"""
agent/finbert_sentiment.py

Finance-domain sentiment scoring with FinBERT (ProsusAI/finbert by default).

FinBERT is a BERT model fine-tuned on financial text. For the narrow task of
"is this headline bullish/bearish?" it is more reliable than a general LLM and
runs in milliseconds. It outputs three classes (positive/negative/neutral),
which we collapse into a single signed score in [-1, 1] per ticker.

This is deterministic feature extraction, not price prediction. It feeds the
research layer; the general LLM still writes summaries and extracts red flags.

The model loads lazily and is cached. If transformers/torch or the model are
unavailable, score_ticker() returns None so the caller can fall back to the LLM.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

FINBERT_MODEL = os.environ.get("FINBERT_MODEL", "ProsusAI/finbert")

_pipeline = None
_load_failed = False


def _get_pipeline():
    """Lazily build and cache the FinBERT text-classification pipeline."""
    global _pipeline, _load_failed
    if _pipeline is not None:
        return _pipeline
    if _load_failed:
        return None
    try:
        from transformers import pipeline
        _pipeline = pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            top_k=None,          # return scores for all classes
            truncation=True,
            max_length=512,
        )
        logger.info("FinBERT loaded: %s", FINBERT_MODEL)
        return _pipeline
    except Exception as e:
        logger.warning("FinBERT unavailable (%s) — falling back to LLM sentiment.", e)
        _load_failed = True
        return None


def is_available() -> bool:
    return _get_pipeline() is not None


def _signed_score(class_scores: dict[str, float]) -> float:
    """positive - negative, in [-1, 1]. neutral mass is ignored."""
    pos = class_scores.get("positive", 0.0)
    neg = class_scores.get("negative", 0.0)
    return float(pos - neg)


def score_texts(texts: list[str]) -> list[float]:
    """Per-text signed sentiment in [-1, 1]. Empty list if FinBERT unavailable."""
    pipe = _get_pipeline()
    if pipe is None or not texts:
        return []
    out = pipe(texts)
    scores: list[float] = []
    for row in out:
        # row is a list of {label, score} dicts (top_k=None)
        cs = {d["label"].lower(): float(d["score"]) for d in row}
        scores.append(_signed_score(cs))
    return scores


def score_ticker(headlines: list[str]) -> dict | None:
    """
    Aggregate FinBERT sentiment across a ticker's headlines.

    Returns {"sentiment": "bullish|bearish|neutral", "confidence": 0..1,
             "net_score": -1..1, "n": count} or None if FinBERT is unavailable
    or there are no headlines to score.
    """
    headlines = [h for h in (headlines or []) if h and h.strip()]
    if not headlines:
        return None
    scores = score_texts(headlines)
    if not scores:
        return None
    net = sum(scores) / len(scores)
    if net > 0.15:
        sentiment = "bullish"
    elif net < -0.15:
        sentiment = "bearish"
    else:
        sentiment = "neutral"
    return {
        "sentiment": sentiment,
        "confidence": round(min(abs(net), 1.0), 3),
        "net_score": round(net, 3),
        "n": len(scores),
    }
