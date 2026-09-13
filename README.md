# Millions

Two tools live here. They are independent — you can use either without the other.

| | |
| --- | --- |
| **[Revenue engine](#revenue-engine)** (`money.py`) | Find businesses with provable, expensive defects — and prove it. Built to answer "how would you make $100k in a month with Claude Code?"; the reasoning is in **[STRATEGY.md](STRATEGY.md)**. |
| **[Market analysis agent](#market-analysis-agent)** (`main.py`) | Pulls live crypto/stock prices, computes technical signals, prints a report. Analyse-and-alert only — it places no trades. |

---

# Revenue engine

$100,000 in 30 days is a **sales** problem wearing a build problem's clothes.
Claude Code collapses build time; it does nothing to the time it takes a stranger
to trust you with $20,000. That trust is bought in conversations, and
conversations are the constraint.

So this is not an app that makes money. It is the machine that manufactures
qualified conversations at volume: it scans a prospect's site, measures a real
defect, and drafts an opener that cites the measurement — **and refuses to send
a number it cannot trace back to something it observed.**

**[STRATEGY.md](STRATEGY.md)** has the full argument, including the honest
probabilities and why memecoin bots are not the answer.

## Quickstart

```bash
pip install requests          # that's the whole dependency list
python3 money.py plan --scenarios
```

`plan` tells you what your target actually demands. Then:

```bash
python3 money.py init                        # your details, for the CAN-SPAM footer
echo "example.com" > urls.txt
python3 money.py run -f urls.txt             # scan, rank, queue, draft
python3 money.py report example.com          # the client-facing audit
python3 money.py today                       # what to do now
```

There is also a dashboard at `/engine`:

```bash
pip install -r requirements.txt && python3 app.py   # then open :5000/engine
```

## Commands

| Command | What it does |
| --- | --- |
| `plan [--target --days --deal] [--scenarios]` | What the target demands. `--scenarios` shows which levers actually move it |
| `scan <url…>` / `-f urls.txt` | Audit sites and save the results |
| `run -f urls.txt` | Scan → rank → queue → draft, in one pass |
| `report <domain> [--format html\|md\|both]` | The deliverable a prospect asked for |
| `outreach <domain> [--all] [--name Sam]` | Grounded drafts; `--all` for the full sequence |
| `add` / `stage <domain> <stage>` | Move the pipeline |
| `pipeline [-v]` | The board: booked, weighted, gap to target |
| `today` | Today's number, and whether you're behind |

## What it measures

41 checks, all from one HTTP response and a few probes — no headless browser, no
API keys. Speed (TTFB, payload, compression, render-blocking scripts, layout
shift), security (HTTPS, HSTS, CSP, frame and MIME protection, mixed content),
search visibility (title, description, headings, canonical, sitemap, Open Graph,
structured data, alt text), mobile, conversion (analytics, contact routes, lead
capture) and credibility (broken links, soft 404s).

Each finding carries the measurement that proves it, why it costs money, how to
fix it, and an effort estimate.

## The part that matters: grounding

The failure mode this is built against: once you're producing 50 personalised
messages a day, it is very tempting to let a template invent a plausible number
— *"this is costing you about $40,000 a year."* You don't know that. You've never
seen their revenue. A prospect who catches it is gone, correctly, and they tell
people.

So the composer never writes a number of its own. It interpolates only from
recorded measurements, and `outreach.verify_grounded()` re-reads the finished
draft and traces every numeric claim back to one. A draft that can't be traced is
flagged; in `strict=True` it raises.

```python
>>> verify_grounded(draft_saying("costing you about $40,000 a year"), result)
(False, ['$40,000'])

>>> verify_grounded(draft_saying("takes 1,840 ms and ships 182 KB"), result)
(True, [])
```

The trust boundary is explicit: per-prospect generated text is untrusted, while
benchmark figures quoted from the reviewed check copy in `checks.py` are allowed,
because those live in version control and show up in a diff.

## Etiquette, which is also self-interest

Obeys `robots.txt`, rate-limits per host, identifies itself honestly, caps bytes
and time, and reads only public pages. Drafts carry a real postal address and a
working opt-out because CAN-SPAM requires it. None of this is decoration —
domain reputation is the asset that is hardest to rebuild, and behaving like a
scraper is the fastest way to end a campaign early.

The tool never sends anything. It writes drafts to `.engine/drafts/` for you to
read and send yourself.

## Layout

```
money.py                  entrypoint
engine/fetch.py           polite HTTP: robots, rate limits, real TTFB
engine/htmlparse.py       stdlib HTML extraction (no BeautifulSoup, no lxml)
engine/checks.py          the 41 checks — each produces a measured number
engine/scan.py            orchestrates one audit
engine/score.py           health score, deal fit, budget signal, pricing
engine/audit_report.py    the client deliverable (Markdown + standalone HTML)
engine/outreach.py        grounded drafting + the verifier
engine/pipeline.py        the funnel arithmetic, live
engine/storage.py         plain JSON under .engine/
engine/cli.py             the commands
```

## Tests

```bash
pip install pytest && python3 -m pytest tests/ -q     # 139 tests
```

The integration tests run real HTTP servers on localhost serving a deliberately
broken site and a deliberately healthy one, then assert the findings against what
those fixtures actually do. Mocked responses would only prove the mocks match the
assertions.

---

# Market analysis agent

> ⚠️ **Not financial advice.** These are simple, transparent technical-analysis
> rules (moving averages, RSI, momentum). They describe past price behaviour, not
> future performance. One research input, never a command to buy or sell.

Fetches crypto prices from [CoinGecko](https://www.coingecko.com/en/api) and
stocks from Yahoo Finance (both free, no key), computes SMA20, SMA50, RSI14 and
10-period momentum, and combines them into a BULLISH / BEARISH / NEUTRAL verdict
with the reasoning shown.

```bash
pip install -r requirements.txt

python3 app.py                                   # web UI at :5000
python3 main.py --crypto bitcoin,ethereum        # or the CLI
python3 main.py --stocks AAPL,MSFT --stock-period 1y
```

```
[+] BITCOIN (crypto)  →  BULLISH
    price: $63,210.44
    - price ($63,210.44) is above SMA20 ($61,004.10)
    - SMA20 is above SMA50 (short-term uptrend)
    - RSI14 is 58.3 (neutral zone)
```

```
main.py                CLI entrypoint
agent/data_sources.py  CoinGecko + yfinance fetching
agent/indicators.py    SMA, RSI, momentum
agent/signals.py       the BULLISH/BEARISH/NEUTRAL rules
agent/report.py        terminal formatting
```

**Where this goes next**, in order of risk: scheduled alerts → backtesting →
paper trading against a sandbox API → and only then, if the first three showed a
strategy is genuinely sound, live trading. Skipping straight to the end is how
people donate money to better-capitalised counterparties. STRATEGY.md §1 has the
longer version of that argument.

## Disclaimer

Educational and research purposes. Not investment advice. Past performance, real
or backtested, does not guarantee future results. All trading carries risk of
loss.
