"""
agent/odysseus_sync.py

Pairs the paper trading agent to Odysseus. After each daily cycle, the
decision report is pushed to Odysseus via the scoped Codex API so you can
review it in the Odysseus web UI — and on your phone via Tailscale.

Uses ODYSSEUS_URL + ODYSSEUS_API_TOKEN (same scoped token the Claude Agent
integration uses). All calls are best-effort: a failure here NEVER blocks
trading or the local DuckDB journal.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 20


def _config() -> tuple[str, str] | None:
    url = os.environ.get("ODYSSEUS_URL", "").strip().rstrip("/")
    token = os.environ.get("ODYSSEUS_API_TOKEN", "").strip()
    if not url or not token:
        return None
    return url, token


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def is_paired() -> bool:
    return _config() is not None


def _build_report(
    run_date: date,
    final_weights: dict[str, float],
    objections: list[str],
    orders: list[dict],
    portfolio_value: float,
    research: dict,
    notes: str,
) -> str:
    """Render the day's decision as a markdown report for Odysseus documents."""
    lines = [
        f"# Paper Trade {run_date}",
        "",
        f"**Portfolio value:** ${portfolio_value:,.2f}",
        "",
        "## Final weights",
    ]
    if final_weights:
        for t, w in sorted(final_weights.items(), key=lambda kv: -kv[1]):
            lines.append(f"- {t}: {w:.1%}")
    else:
        lines.append("- No positions (held cash / no trades)")

    lines += ["", "## Orders placed"]
    if orders:
        for o in orders:
            lines.append(f"- {o.get('side','?').upper()} {o.get('ticker','?')} "
                         f"(stop {o.get('stop_price','?')})")
    else:
        lines.append("- None")

    lines += ["", "## Challenger objections"]
    lines += [f"- {o}" for o in objections] if objections else ["- None"]

    lines += ["", "## Research sentiment"]
    for t, r in research.items():
        sentiment = r.get("sentiment", "?")
        flags = r.get("flags", [])
        flag_str = f" (flags: {', '.join(flags)})" if flags else ""
        lines.append(f"- {t}: {sentiment}{flag_str}")

    lines += ["", "## Journal", notes]
    return "\n".join(lines)


def push_decision(
    run_date: date,
    final_weights: dict[str, float],
    objections: list[str],
    orders: list[dict],
    portfolio_value: float,
    research: dict,
    notes: str,
) -> bool:
    """
    Push the daily decision report to Odysseus as a document. Returns True
    on success. Best-effort — logs and returns False on any failure.
    """
    cfg = _config()
    if cfg is None:
        logger.info("Odysseus not configured (no ODYSSEUS_URL/TOKEN) — skipping sync.")
        return False
    url, token = cfg

    report = _build_report(run_date, final_weights, objections, orders,
                           portfolio_value, research, notes)
    body = {
        "session_id": None,  # standalone document, not tied to a chat session
        "title": f"Paper Trade {run_date}",
        "content": report,
        "language": "markdown",
    }
    try:
        r = requests.post(f"{url}/api/codex/documents", headers=_headers(token),
                          data=json.dumps(body), timeout=TIMEOUT)
        if r.status_code in (200, 201):
            logger.info("Pushed decision report to Odysseus (%s)", run_date)
            return True
        logger.warning("Odysseus document push returned %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Odysseus sync failed: %s", e)
    return False


def push_memory(text: str, category: str = "fact") -> bool:
    """
    Optionally store a short fact in Odysseus memory so other models on the
    instance can use it (e.g. 'paper portfolio is up 2% this week').
    """
    cfg = _config()
    if cfg is None:
        return False
    url, token = cfg
    body = {"text": text, "category": category, "source": "paper-trader", "session_id": None}
    try:
        r = requests.post(f"{url}/api/codex/memory", headers=_headers(token),
                          data=json.dumps(body), timeout=TIMEOUT)
        return r.status_code in (200, 201)
    except Exception as e:
        logger.warning("Odysseus memory push failed: %s", e)
        return False
