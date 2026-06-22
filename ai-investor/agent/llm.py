"""
agent/llm.py

Pluggable LLM backend. Defaults to local Ollama (free, runs on your GPU).
Optionally switches to the Anthropic API if you want sharper synthesis.

Backend is chosen by the LLM_BACKEND env var:
  - "ollama"    (default) — local, free, private
  - "anthropic"           — paid API, higher quality

The rest of the agent calls chat() / chat_json() and does not care which
backend is active. The deterministic risk gate clamps every decision
regardless, so a weaker local model cannot bypass position caps or stops.
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

BACKEND = os.environ.get("LLM_BACKEND", "ollama").lower()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("LLM_MODEL", "qwen3.5:9b")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Local models need headroom — some emit reasoning before the answer.
DEFAULT_MAX_TOKENS = 2048
OLLAMA_TIMEOUT = 180


def chat(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str | None = None) -> str:
    """Single-turn completion. Returns raw text. Backend-agnostic."""
    if BACKEND == "anthropic":
        return _chat_anthropic(prompt, max_tokens, model)
    return _chat_ollama(prompt, max_tokens, model)


def chat_json(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, model: str | None = None):
    """
    Completion that must return JSON. Appends a strict instruction, then
    robustly extracts the first JSON object/array from the reply (local
    models sometimes wrap it in prose or code fences). Returns the parsed
    object, or None if nothing parseable came back.
    """
    full = prompt.rstrip() + "\n\nRespond with ONLY valid JSON. No prose, no markdown fences."
    raw = chat(full, max_tokens, model)
    return _extract_json(raw)


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------
def _chat_ollama(prompt: str, max_tokens: int, model: str | None) -> str:
    mdl = model or OLLAMA_MODEL
    payload = {
        "model": mdl,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        # think:false disables reasoning. Thinking models (qwen3.5, deepseek-r1)
        # otherwise burn the whole token budget on <think> and return empty
        # content (done_reason=length). Harmless for non-thinking models.
        "think": False,
        # NOTE: do NOT set "format":"json" — it returns empty on some models.
        # Prompt-based JSON is more reliable. See chat_json().
        "options": {"num_predict": max_tokens, "temperature": 0.3},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        if r.status_code == 400:
            # some non-thinking models reject the "think" field — retry without it
            payload.pop("think", None)
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception as e:
        logger.error("Ollama call failed (%s): %s", mdl, e)
        return ""


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------
def _chat_anthropic(prompt: str, max_tokens: int, model: str | None) -> str:
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic not installed but LLM_BACKEND=anthropic")
        return ""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    try:
        resp = client.messages.create(
            model=model or ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        logger.error("Anthropic call failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------
def _extract_json(raw: str):
    if not raw:
        return None
    text = raw.strip()

    # strip markdown code fences
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()

    # try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass

    # fall back: grab the first balanced {...} or [...] block
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    try:
                        return json.loads(chunk)
                    except Exception:
                        break
    logger.warning("Could not extract JSON from LLM reply: %s", raw[:200])
    return None


def backend_info() -> str:
    if BACKEND == "anthropic":
        return f"anthropic:{ANTHROPIC_MODEL}"
    return f"ollama:{OLLAMA_MODEL} @ {OLLAMA_URL}"
