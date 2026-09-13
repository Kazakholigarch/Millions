# Millions Agent

An AI/analysis agent for investing and crypto research — v1 is an
**analyze-and-alert** tool: it pulls live market data, computes technical
signals, and prints a report. It does **not** place trades and needs no API
keys to run.

> ⚠️ **Not financial advice.** The signals here are simple, transparent
> technical-analysis rules (moving averages, RSI, momentum). They describe
> past price behavior, not future performance. Treat this as one research
> input, never as a command to buy or sell.

## What it does

- Fetches crypto prices from [CoinGecko](https://www.coingecko.com/en/api) (free, no key).
- Fetches stock prices from Yahoo Finance via `yfinance` (free, no key).
- Computes SMA20, SMA50, RSI14, and 10-period momentum.
- Combines them into a BULLISH / BEARISH / NEUTRAL verdict with the reasons behind it.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Crypto only (CoinGecko coin ids, not tickers — e.g. "bitcoin" not "BTC")
python3 main.py --crypto bitcoin,ethereum,solana

# Stocks only
python3 main.py --stocks AAPL,MSFT,TSLA

# Both, with custom lookback windows
python3 main.py --crypto bitcoin --stocks NVDA --crypto-days 180 --stock-period 1y
```

Example output:

```
============================================================
  MILLIONS AGENT — market analysis report
  (educational signals, not financial advice)
============================================================

[+] BITCOIN (crypto)  →  BULLISH
    price: $63,210.44
    - price ($63,210.44) is above SMA20 ($61,004.10)
    - SMA20 is above SMA50 (short-term uptrend)
    - RSI14 is 58.3 (neutral zone)
    - up 4.2% over the last 10 periods
============================================================
```

## Project layout

```
main.py               CLI entrypoint
agent/data_sources.py fetching crypto (CoinGecko) and stock (yfinance) price history
agent/indicators.py   SMA, RSI, momentum calculations
agent/signals.py      rule-based BULLISH/BEARISH/NEUTRAL verdict logic
agent/report.py       terminal report formatting
```

## Roadmap / where this can go next

This is intentionally a v1 foundation. Natural next steps, roughly in order
of risk:

1. **Scheduler + alerts** — run on a timer, push alerts to Slack/email/Discord
   instead of just printing.
2. **Backtesting** — replay a strategy against historical data to see how it
   would have performed before trusting it with anything.
3. **Paper trading** — connect to a broker/exchange's *sandbox* API
   (simulated money, real live prices) to measure real strategy performance
   risk-free.
4. **LLM-assisted research** — have an LLM read news/filings/on-chain data
   and summarize context alongside the technical signals.
5. **Live automated trading** — only after (2) and (3) show a strategy is
   actually sound. This is real-money risk; build and validate carefully.

## Disclaimer

This project is for educational and research purposes. It is not
investment advice, and past performance (real or backtested) does not
guarantee future results. Any trading, automated or manual, carries risk
of loss.
