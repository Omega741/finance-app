# AI Investor — CLAUDE.md

Project memory for Claude Code. Read before modifying any code here.

## What this is

A bias-guarded backtesting harness + paper trading agent for methodologically
honest systematic investing. Goal: learn what works before risking real money.

## Architecture

```
harness/          # Bias-guarded backtesting (four structural guards)
  core.py         # Walk-forward engine, metrics, lookahead guard
  strategies.py   # Swappable strategy slot (EqualWeight, TST, CSM, RSI, DualMom)

agent/            # Paper trading loop (Alpaca paper account)
  signals.py      # DETERMINISTIC: RSI, MA, MACD, ATR, momentum scores
  risk_gate.py    # DETERMINISTIC: position caps, daily loss halt, PDT, stop-loss
  research.py     # LLM: news synthesis, sentiment, red flag extraction
  allocation.py   # LLM: target weights from signals + research + challenger veto
  execution.py    # Alpaca paper orders — every buy requires a stop-loss price
  journal.py      # DuckDB journal + LLM narrative entry

paper_trader.py   # Main daily orchestration loop
run_example.py    # Backtesting demo (no broker required)
```

## Non-negotiable methodology rules (harness)

Never weaken these. They are why the harness exists.

1. **Point-in-time**: Strategy only sees data up to the decision bar.
   `_assert_point_in_time` raises `LookaheadError` if anything leaks.
2. **Signal lag**: Decisions on bar T execute at bar T+lag. Never set lag=0.
3. **As-of universe**: Always use `Universe.as_of(date)`. Static current
   tickers trigger a survivorship-bias warning — that warning is correct.
4. **Walk-forward only**: Report OOS numbers, never in-sample.
5. **Costs always on**: commission_bps + slippage_bps. Never set to zero.
6. **Beat the benchmark**: Must beat equal-weight buy-and-hold after costs.
   If it does not, it has not earned real capital.

## Hard trading rules (agent)

- **Long only**. No shorts, no options until long-only is proven on paper.
- **Every order carries a stop-loss**. `place_order()` raises `MissingStopLoss`
  if stop_price is absent. This is enforced in code.
- **Risk gate has veto power** over all LLM decisions. Never route orders
  around `apply_risk_gate()`.
- **LLM does synthesis only**: research.py and allocation.py. Signals and risk
  are deterministic code. The LLM never predicts prices directly.
- **Paper trade 90+ days** and 100+ trades before any real money.
- **Keep a kill switch**: fastest is ALPACA_API_KEY revocation.
- **No trades under 1-hour timeframe**. That is noise vs HFT firms.

## What the challenger does

`allocation.py` calls Claude twice: once to propose weights, once to argue
against them. The objections are logged in the journal. If the challenger
raises a flag, it does not block the trade — but it must be visible in the
journal so you can audit decisions over time.

## Code conventions

- Python, pandas, numpy. Type hints on public functions.
- `harness/core.py` stays broker-agnostic (no Alpaca imports there).
- New strategies: subclass `Strategy` in `harness/strategies.py`.
- Signal additions: go in `agent/signals.py`, deterministic only.
- Keep `apply_risk_gate()` pure (no side effects, no I/O).
- DuckDB for all persistence. No in-memory-only state for trade records.

## Running locally

```bash
# Backtesting only (no API keys needed)
cd ai-investor
pip install -r requirements.txt
python run_example.py

# Paper trading (requires .env with API keys)
cp .env.example .env
# fill in ANTHROPIC_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY
python paper_trader.py
```

## What's next (do not implement until backtest validates)

- FRED macro regime filter (bull/bear overlay based on yield curve + unemployment)
- Congressional disclosure mirror (Quiver Quantitative API)
- Point-in-time universe loader (removes survivorship bias from backtests)
- Scheduler for daily auto-run (Windows Task Scheduler or cron)
- Performance dashboard pulling from DuckDB journal
