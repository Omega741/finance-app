# AI Investor

A bias-guarded backtesting harness and a long-only paper trading agent.

**Goal: methodological honesty, not maximum reported returns.** The valuable
artifact is a clean evaluation system that tells you the truth. Most strategies
honestly lose to buy-and-hold after costs — and this harness will show you that
instead of hiding it.

> Paper trading only. Not financial advice.

## Why this exists

Two problems with opposite difficulty:

- **The plumbing** (data in, reasoning, orders out, journaling): easy.
- **Consistent alpha** (beating buy-and-hold after costs): one of the hardest
  problems in finance. The evidence says an LLM will not reliably deliver it.

So the design splits responsibilities: the **LLM does synthesis, screening, and
explanation**; the **signals and risk rules stay deterministic**. The profit
expectation is "match a benchmark while learning," not "beat the market."

News sentiment uses **FinBERT** (a finance-tuned classifier) rather than a
general LLM guess — it is more reliable at the narrow bullish/bearish call and
runs in milliseconds. The general LLM still writes summaries and extracts red
flags. This is feature extraction, not price prediction.

## Free by default

The LLM backend is pluggable. It defaults to **local Ollama** (runs on your own
GPU, $0, fully private) and can flip to the Anthropic API for sharper synthesis.
Because the risk gate is deterministic, a weaker local model still cannot bypass
position caps or skip stop-losses — it only affects the quality of synthesis.

Set the backend in `.env`:

```
LLM_BACKEND=ollama          # local + free (default)
LLM_MODEL=qwen3.5:9b
# or:
LLM_BACKEND=anthropic       # paid API
```

## Optional: Odysseus pairing

If you run [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus), set
`ODYSSEUS_URL` and `ODYSSEUS_API_TOKEN` in `.env` and each day's decision report
is pushed to the Odysseus web UI (viewable on your phone too). Pairing is
best-effort: if Odysseus is down, trading and the local journal are unaffected.

## Architecture

```
harness/          Bias-guarded backtesting
  core.py         Walk-forward engine, metrics, four structural guards
  strategies.py   Swappable strategies (buy-hold, trend, momentum, RSI, dual-mom)

agent/            Paper trading loop (Alpaca paper account)
  llm.py          Pluggable LLM backend: local Ollama (default, free) or Anthropic
  finbert_sentiment.py  FinBERT: finance-tuned per-headline sentiment classifier
  signals.py      DETERMINISTIC: RSI, MA, MACD, ATR, momentum -> numeric scores
  risk_gate.py    DETERMINISTIC: position caps, daily-loss halt, PDT, stop-loss
  research.py     LLM: news synthesis, sentiment, red-flag extraction
  allocation.py   LLM: target weights + a challenger that argues against them
  execution.py    Alpaca paper orders — every buy requires a stop-loss
  journal.py      DuckDB journal + LLM narrative entry
  odysseus_sync.py Best-effort push of the daily report to Odysseus (optional)

paper_trader.py   Main daily orchestration loop (supports --dry-run)
status.py         Read-only snapshot of the paper account (value, P/L, positions)
run_example.py    Backtest demo (no broker or API keys needed)
```

## The four bias guards (the whole point)

1. **Point-in-time** — a strategy only ever sees prices up to the decision bar.
   Future rows are sliced off; `_assert_point_in_time` raises if any leak.
2. **Signal lag** — weights decided on bar T execute at bar T+1. You cannot
   trade on the bar you used to decide.
3. **As-of universe** — strategies pick only from names investable on that date.
   Feeding a current ticker list trips the survivorship warning.
4. **Walk-forward** — fit on train, score only on the following out-of-sample
   window. Reported numbers are OOS, compared to buy-and-hold after costs.

## Quick start

### Backtesting (no keys needed)

```bash
cd ai-investor
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
python run_example.py
```

### Paper trading

Only an Alpaca paper account is required — the LLM runs locally on Ollama by
default, so no paid API key is needed.

```bash
cp .env.example .env
# fill in ALPACA_API_KEY and ALPACA_SECRET_KEY (free paper account)
# LLM_BACKEND defaults to ollama; install Ollama and pull the model:
#   ollama pull qwen3.5:9b
# (only set ANTHROPIC_API_KEY if you switch LLM_BACKEND=anthropic)

python paper_trader.py             # live: trades when the market is open
python paper_trader.py --dry-run   # preview any day: full analysis, no orders
python status.py                   # snapshot: portfolio value, P/L, positions
```

Get a free Alpaca paper account at [alpaca.markets](https://alpaca.markets).
The execution layer is hardcoded to `paper=True`.

### Automating the daily run

`paper_trader.py` is self-locating (runs from any working directory), so it can
be driven by a scheduler. On Windows, register a Task Scheduler job to run it
each weekday shortly after the market opens:

```powershell
$action  = New-ScheduledTaskAction -Execute "<path>\venv\Scripts\python.exe" `
           -Argument '"<path>\paper_trader.py"' -WorkingDirectory "<path>"
$trigger = New-ScheduledTaskTrigger -Weekly `
           -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 9:35AM
Register-ScheduledTask -TaskName "AI Paper Trader" -Action $action -Trigger $trigger
```

The schedule fires in your local timezone; pick a time after the 9:30am ET open.

## Hard rules

- Long only. No shorts or options until long-only is proven on paper.
- Buys use whole-share quantities so every position can carry a real,
  broker-side **trailing stop** (7% trail) — fractional shares cannot hold
  stop orders at Alpaca. Stops are enforced after every cycle, in code.
- The risk gate is deterministic code with veto power over the LLM.
- Paper trade 90+ days and 100+ trades before any real money.
- Kill switch: revoke the Alpaca API key.

## Validation bar before real money

Paper-trade 90+ days / 100+ trades, beat buy-and-hold on the same universe after
costs, and confirm every order had a stop and a position cap. If a backtest fails
any of the four guards, treat it as fiction.

## License

MIT. See [LICENSE](LICENSE).
