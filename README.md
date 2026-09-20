# Millions Agent

An AI/analysis agent for investing and crypto research — it pulls live
market data, runs a technical + fundamentals checklist, and prints a
report with a plain-English writeup. It tracks its own past calls and
adjusts how much it trusts each indicator based on whether they turned
out to be right. It does **not** place trades and needs no API keys to
run (an optional key upgrades the writeup style only — see below).

> ⚠️ **Not financial advice.** Every verdict here comes from a fixed,
> transparent checklist — technical indicators (moving averages, RSI,
> momentum) plus, for stocks, a value-investing checklist (valuation,
> debt, margins, growth, cash flow). None of it predicts the future. A
> good historical track record is not a guarantee of future accuracy —
> markets change. Treat this as one research input, never as a command
> to buy or sell.

## What it does

- **Live prices**: crypto from [CoinGecko](https://www.coingecko.com/en/api) (free, no key), stocks from Yahoo Finance via `yfinance` (free, no key).
- **Technicals**: SMA20, SMA50, RSI14, and 10-period momentum.
- **Fundamentals** (stocks only): P/E ratio, debt/equity, profit margin, revenue growth, free cash flow, return on equity — the numbers a value investor actually checks, turned into a plain checklist.
- **News** (stocks only): recent headlines via Yahoo Finance, shown as context — not scored, just something to read yourself.
- **A track record that adapts**: every signal is logged. Once it's old enough (7 days by default) to check against what the price actually did, the agent scores it and adjusts how much weight each indicator gets going forward — indicators with a real history of being right count for more. See "How the learning actually works" below for the honest version of what this is and isn't.
- **A plain-English writeup**: a templated summary by default; optionally upgraded to an AI-generated narrative if you set `ANTHROPIC_API_KEY` (see below) — the verdict itself never depends on this, only the prose explaining it does.

## Setup

```bash
pip install -r requirements.txt
```

Optional, to upgrade the writeup style to an AI-generated narrative:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Everything works without this — it only changes how the explanation is worded, never the underlying BULLISH/BEARISH/NEUTRAL call or the weights behind it.

## Usage — web app (easiest, point-and-click)

```bash
python3 app.py
```

Then open the app in your browser:
- **GitHub Codespaces**: a popup will offer "Open in Browser" for port 5000, or check the **Ports** tab at the bottom panel and tap the globe/open icon next to port 5000.
- **Local machine**: open `http://localhost:5000`.

Tick the checkboxes for the coins/stocks you want, tap **Analyze**, done — no typed commands, no commas to get right.

## Usage — command line

```bash
# Crypto only (CoinGecko coin ids, not tickers — e.g. "bitcoin" not "BTC")
python3 main.py --crypto bitcoin,ethereum,solana

# Stocks only
python3 main.py --stocks AAPL,MSFT,TSLA

# Both, with custom lookback windows
python3 main.py --crypto bitcoin --stocks NVDA --crypto-days 180 --stock-period 1y
```

## How the learning actually works

This is the part worth being precise about, because "learns from its
mistakes" can mean a lot of things and most of them are hype.

What this agent does **not** do: it is not a neural network, it does not
retrain a model, and it does not get smarter through some mysterious
process. What it **does** do is simple and fully inspectable:

1. Every time it makes a call on a symbol, it logs the verdict, the price,
   and which individual indicators voted bullish/bearish (in `agent_history.db`,
   a local SQLite file — never committed to git).
2. A signal isn't checked immediately — it needs `AGENT_SCORE_HORIZON_DAYS`
   (7 by default) to pass first, so there's an actual outcome to compare
   against.
3. The next time you analyze that same symbol after that window has
   passed, the agent looks up what the price actually did and marks each
   indicator that contributed to the old call as having been right or
   wrong about the direction.
4. Each indicator's **weight** is just its running win rate (correct calls
   ÷ total calls), bounded between 15% and 95% so no indicator is ever
   fully trusted or fully ignored on the strength of a short streak.
5. Future verdicts use these weights instead of counting every indicator
   equally — an indicator with a stronger track record influences the
   verdict more.

That's the whole mechanism: a per-indicator win-rate estimate that updates
as outcomes come in. It's honest, explainable, and genuinely adapts — but
it needs real elapsed time and a real number of scored signals before the
weights mean much. On a fresh install, everything starts at a neutral 50%
(a coin flip) until enough history accumulates. Don't expect it to be
"smart" after five minutes of use — expect it to slowly separate what's
actually been predictive for the assets you check from what hasn't.

The web app and CLI report both show the current track record (total
scored, % correct) whenever there's history to show.

## Project layout

```
app.py                    Flask web UI (checkboxes, no typing needed)
templates/index.html      web UI page
main.py                   CLI entrypoint
agent/data_sources.py     fetching crypto (CoinGecko) and stock (yfinance) price history
agent/indicators.py       SMA, RSI, momentum calculations
agent/fundamentals.py     fetching + scoring stock fundamentals (P/E, debt, margins, growth, FCF, ROE)
agent/news.py             fetching recent headlines for a stock
agent/signals.py          combines technicals + fundamentals into a weighted BULLISH/BEARISH/NEUTRAL verdict
agent/tracker.py          logs signals, scores past ones, adapts indicator weights (the "learning" system)
agent/narrative.py        turns a signal into a plain-English writeup (rule-based, or AI-enhanced with an API key)
agent/analysis.py         orchestrates all of the above; what main.py and app.py both call
agent/report.py           terminal report formatting
```

## Roadmap / where this can go next

Natural next steps, roughly in order of risk:

1. **Scheduler + alerts** — run on a timer, push alerts to Slack/email/Discord
   instead of just printing.
2. **Backtesting** — replay a strategy against historical data to see how it
   would have performed before trusting it with anything.
3. **Paper trading** — connect to a broker/exchange's *sandbox* API
   (simulated money, real live prices) to measure real strategy performance
   risk-free.
4. **Live automated trading** — only after (2) and (3) show a strategy is
   actually sound. This is real-money risk; build and validate carefully.

## Disclaimer

This project is for educational and research purposes. It is not
investment advice, and past performance (real, backtested, or reflected
in the agent's own track record) does not guarantee future results. Any
trading, automated or manual, carries risk of loss.
