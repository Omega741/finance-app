"""
agent/allocation.py

Allocation agent: Claude synthesizes signals + research into target weights.
A challenger Claude then argues against the allocation before it proceeds.

Output is strict JSON {ticker: weight}. The risk gate caps everything
deterministically after this — the LLM never has final authority.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic

from .research import ResearchResult
from .signals import SignalBundle, signals_to_dict

logger = logging.getLogger(__name__)

ALLOCATION_MODEL = "claude-sonnet-4-6"
CHALLENGER_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 512


def _call_allocation(
    client: anthropic.Anthropic,
    tickers: list[str],
    signals: dict[str, dict],
    research: dict[str, ResearchResult],
    current_weights: dict[str, float],
    cash_pct: float,
) -> dict[str, float]:
    """Primary allocation call. Returns raw target weights."""
    research_lines = []
    for t in tickers:
        r = research.get(t)
        s = signals.get(t, {})
        if r:
            research_lines.append(
                f"{t}: sentiment={r.sentiment} (conf={r.confidence:.1f}), "
                f"score={s.get('score','?')}, flags={r.flags or 'none'}. {r.summary}"
            )

    prompt = (
        "You are a portfolio allocation agent. Your job is to set target weights "
        "for a long-only paper trading portfolio. Rules:\n"
        "- Long only. No shorts.\n"
        "- Weights must sum to <= 0.90 (10% cash floor enforced externally).\n"
        "- No single weight > 0.20.\n"
        "- Prefer names with bullish sentiment AND positive signal score.\n"
        "- If net outlook is poor, reduce all weights and hold more cash.\n\n"
        f"Current weights: {current_weights}\n"
        f"Current cash: {cash_pct:.1%}\n\n"
        "Signal + research data:\n" + "\n".join(research_lines) + "\n\n"
        "Output ONLY a JSON object like {\"AAPL\": 0.15, \"MSFT\": 0.20}. "
        "No explanation, no markdown."
    )

    response = client.messages.create(
        model=ALLOCATION_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _call_challenger(
    client: anthropic.Anthropic,
    proposed: dict[str, float],
    signals: dict[str, dict],
    research: dict[str, ResearchResult],
) -> list[str]:
    """
    A second Claude call that argues AGAINST the proposed allocation.
    Returns a list of objections. Measurably reduces dumb trades.
    """
    research_flags = {t: r.flags for t, r in research.items() if r.flags}
    prompt = (
        "You are a risk-skeptic reviewer. Another agent proposed these portfolio weights:\n"
        f"{json.dumps(proposed, indent=2)}\n\n"
        f"Flags from research: {json.dumps(research_flags)}\n"
        f"Signal scores: { {t: s.get('score') for t, s in signals.items()} }\n\n"
        "List specific objections to this allocation. Focus on: concentration risk, "
        "contradictions between signals and sentiment, overlooked red flags, "
        "or names where conviction is too high given uncertainty.\n"
        "Output a JSON array of short objection strings. Empty array if no serious concerns."
    )
    response = client.messages.create(
        model=CHALLENGER_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except Exception:
        return []


def run_allocation_agent(
    tickers: list[str],
    signal_bundles: dict[str, SignalBundle],
    research: dict[str, ResearchResult],
    current_weights: dict[str, float],
    cash_pct: float,
) -> tuple[dict[str, float], list[str]]:
    """
    Returns (proposed_weights, challenger_objections).
    Caller should log objections and pass weights through risk gate.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    signals_dict = signals_to_dict(signal_bundles)

    try:
        proposed = _call_allocation(client, tickers, signals_dict, research,
                                    current_weights, cash_pct)
    except Exception as e:
        logger.error("Allocation agent failed: %s. Holding current weights.", e)
        return current_weights, [f"Allocation agent error: {e}"]

    # validate types
    proposed = {k: float(v) for k, v in proposed.items() if k in tickers}

    try:
        objections = _call_challenger(client, proposed, signals_dict, research)
    except Exception as e:
        logger.warning("Challenger failed: %s", e)
        objections = []

    if objections:
        logger.info("Challenger raised %d objection(s): %s", len(objections), objections)

    return proposed, objections
