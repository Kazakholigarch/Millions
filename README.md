# Millions

Two projects live here.

## 1. CiteLocal — AI visibility audits for local businesses

**The main project.** Audits whether AI assistants (ChatGPT, Claude, Perplexity,
Google AI Overviews) can see, understand and recommend a local business, then
generates the exact fixes as paste-ready code.

```bash
pip install -r requirements.txt
python3 -m citelocal.web        # http://localhost:5000
```

Runs with no API keys. Full documentation: **[citelocal/README.md](citelocal/README.md)**

Why it exists: AI use for local search went from 6% to 45% in a year, assistants
name only 3–5 businesses per answer, and just 1.2% of local business locations
ever get recommended. Agencies already sell this service at $500–$1,500 per
client per month — CiteLocal is the tool that makes the work repeatable and the
report sellable.

What most audits miss, and this one leads with: a site's `robots.txt` may be
silently blocking the crawlers that build AI retrieval indexes, which makes the
business uncitable no matter how good its content is.

```bash
# Audit a business, produce a client-ready report
python3 -m citelocal.cli --name "Precision Plumbing" --site example.com \
  --city Austin --region TX --category plumber --html report.html

# Run the test suite (84 assertions, no network required)
python3 tests/test_audit.py
```

## 2. Millions Agent — market analysis

An earlier analyze-and-alert tool for investing and crypto research. Pulls live
market data, computes technical signals, prints a report. Places no trades and
needs no API keys.

> ⚠️ **Not financial advice.** Simple, transparent technical-analysis rules
> (moving averages, RSI, momentum) describing past price behaviour, not future
> performance.

```bash
python3 app.py                                      # web UI on port 5000
python3 main.py --crypto bitcoin --stocks AAPL      # CLI
```

```
agent/data_sources.py   crypto (CoinGecko) and stock (yfinance) price history
agent/indicators.py     SMA, RSI, momentum
agent/signals.py        BULLISH / BEARISH / NEUTRAL verdict rules
agent/report.py         terminal report formatting
app.py                  Flask web UI (templates/index.html)
main.py                 CLI entrypoint
```

Both apps default to port 5000 — run one at a time, or set `PORT` for CiteLocal.

## Layout

```
citelocal/          AI visibility audit engine, CLI, and web app
tests/              end-to-end tests with local fixture sites
agent/              market analysis engine
main.py app.py      market analysis CLI and web UI
```
