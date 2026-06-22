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

## Architecture

```
harness/          Bias-guarded backtesting
  core.py         Walk-forward engine, metrics, four structural guards
  strategies.py   Swappable strategies (buy-hold, trend, momentum, RSI, dual-mom)

agent/            Paper trading loop (Alpaca paper account)
  signals.py      DETERMINISTIC: RSI, MA, MACD, ATR, momentum -> numeric scores
  risk_gate.py    DETERMINISTIC: position caps, daily-loss halt, PDT, stop-loss
  research.py     LLM: news synthesis, sentiment, red-flag extraction
  allocation.py   LLM: target weights + a challenger that argues against them
  execution.py    Alpaca paper orders — every buy requires a stop-loss
  journal.py      DuckDB journal + LLM narrative entry

paper_trader.py   Main daily orchestration loop
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

### Paper trading (requires API keys)

```bash
cp .env.example .env
# fill in ANTHROPIC_API_KEY, ALPACA_API_KEY, ALPACA_SECRET_KEY (paper account)
python paper_trader.py
```

Get a free Alpaca paper account at [alpaca.markets](https://alpaca.markets).
The execution layer is hardcoded to `paper=True`.

## Hard rules

- Long only. No shorts or options until long-only is proven on paper.
- Every order carries a stop-loss — enforced in code, not convention.
- The risk gate is deterministic code with veto power over the LLM.
- Paper trade 90+ days and 100+ trades before any real money.
- Kill switch: revoke the Alpaca API key.

## Validation bar before real money

Paper-trade 90+ days / 100+ trades, beat buy-and-hold on the same universe after
costs, and confirm every order had a stop and a position cap. If a backtest fails
any of the four guards, treat it as fiction.

## License

MIT. See [LICENSE](LICENSE).
