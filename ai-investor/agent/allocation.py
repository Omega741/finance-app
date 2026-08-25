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

from .llm import chat_json
from .research import ResearchResult
from .signals import SignalBundle, signals_to_dict

logger = logging.getLogger(__name__)

MAX_TOKENS = 2048


def _call_allocation(
    tickers: list[str],
    signals: dict[str, dict],
    research: dict[str, ResearchResult],
    current_weights: dict[str, float],
    cash_pct: float,
    budget: float = 0.90,
    max_per_name: float = 0.20,
) -> dict[str, float]:
    """
    Primary allocation call. Returns raw target weights.

    `budget` is the total fraction of the WHOLE portfolio these tickers may
    occupy (e.g. 0.20 when allocating only the growth sleeve); `max_per_name`
    caps any single name. Unspent budget falls through to cash downstream.
    """
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
        "You are the allocation agent for the GROWTH SLEEVE of a core-satellite "
        "portfolio. The core (a broad index) and a cash reserve are handled "
        "separately — you ONLY size these higher-volatility growth names. Rules:\n"
        "- Long only. No shorts.\n"
        f"- Weights are fractions of the WHOLE portfolio and must sum to <= {budget:.2f} "
        "(this is the growth sleeve's total budget; anything you don't use becomes cash).\n"
        f"- No single weight > {max_per_name:.2f}.\n"
        "- Prefer names with bullish sentiment AND positive signal score.\n"
        "- This sleeve is for MAX upside with contained downside: when a name's "
        "outlook is weak, size it small or drop it — leave that budget in cash "
        "rather than forcing a bad bet. Under-using the budget is fine.\n"
        "- STICKINESS: prefer keeping current positions. Only change a holding "
        "when the signal/sentiment clearly justifies it. Do NOT flip-flop into "
        "names you were bearish on yesterday — whipsaws lose money.\n\n"
        f"Current growth weights: {current_weights}\n"
        f"Current cash: {cash_pct:.1%}\n\n"
        "Signal + research data:\n" + "\n".join(research_lines) + "\n\n"
        "Output ONLY a JSON object like {\"NVDA\": 0.08, \"AMZN\": 0.06}."
    )

    result = chat_json(prompt, max_tokens=MAX_TOKENS)
    return result if isinstance(result, dict) else {}


def _call_challenger(
    proposed: dict[str, float],
    signals: dict[str, dict],
    research: dict[str, ResearchResult],
) -> list[str]:
    """
    A second LLM call that argues AGAINST the proposed allocation.
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
        'Output a JSON array of short objection strings like ["too concentrated in tech"]. '
        "Empty array [] if no serious concerns."
    )
    result = chat_json(prompt, max_tokens=1024)
    return result if isinstance(result, list) else []


def run_allocation_agent(
    tickers: list[str],
    signal_bundles: dict[str, SignalBundle],
    research: dict[str, ResearchResult],
    current_weights: dict[str, float],
    cash_pct: float,
    budget: float = 0.90,
    max_per_name: float = 0.20,
) -> tuple[dict[str, float], list[str]]:
    """
    Returns (proposed_weights, challenger_objections).
    Caller should log objections and pass weights through risk gate.

    `budget`/`max_per_name` constrain the sleeve (see _call_allocation).
    """
    signals_dict = signals_to_dict(signal_bundles)

    try:
        proposed = _call_allocation(tickers, signals_dict, research,
                                    current_weights, cash_pct,
                                    budget=budget, max_per_name=max_per_name)
    except Exception as e:
        logger.error("Allocation agent failed: %s. Holding current weights.", e)
        return current_weights, [f"Allocation agent error: {e}"]

    # validate types
    proposed = {k: float(v) for k, v in proposed.items()
                if k in tickers and isinstance(v, (int, float))}

    try:
        objections = _call_challenger(proposed, signals_dict, research)
    except Exception as e:
        logger.warning("Challenger failed: %s", e)
        objections = []

    if objections:
        logger.info("Challenger raised %d objection(s): %s", len(objections), objections)

    return proposed, objections
