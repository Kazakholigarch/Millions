# CiteLocal — AI visibility audits for local businesses

Find out whether AI assistants can see, understand and recommend a local
business — then hand over the exact fixes, ready to paste.

```bash
pip install -r requirements.txt
python3 -m citelocal.web          # then open http://localhost:5000
```

No API key is needed. Every site check runs without one; only the optional live
probe calls an LLM.

---

## Why this exists

Local search moved into AI assistants faster than local businesses noticed:

- AI use for local search went from **6% to 45% in a single year**.
- Google AI Overviews appear on up to **68% of local queries**, and referral
  traffic to sites is down **33–38% year over year** (smaller sites, ~60%).
- An assistant names **3–5 businesses**, not ten blue links. It is
  winner-take-most.
- Only **1.2%** of local business locations are ever recommended by AI search.

The businesses that lose here mostly do not know it is happening, because their
Google rankings did not move — only the clicks did.

Agencies already sell this as a service at **$500–$1,500 per client per month**.
CiteLocal is the tool that makes the work repeatable and the report sellable.

## What makes it different

Existing AI-visibility tools are monitoring dashboards: they tell a brand it is
invisible and charge $95–$595/month to keep saying so. CiteLocal answers the
next question — *why*, and *what do I paste where* — for the segment those
tools ignore.

The check most audits skip is the one that matters most: **whether the site's
robots.txt is silently blocking the crawlers that build AI retrieval indexes.**
A business can do everything else right and still be uncitable because someone
pasted a "block AI bots" snippet from a blog post two years ago.

CiteLocal draws the distinction those snippets miss:

| Crawler kind | Example | Blocking it costs you |
|---|---|---|
| Retrieval / citation | `OAI-SearchBot`, `PerplexityBot`, `Claude-SearchBot`, `Googlebot` | Your ability to be cited at all |
| Training only | `ClaudeBot`, `CCBot`, `Applebot-Extended` | Nothing in today's answers |

So a business can stay out of model training and still be recommended. Generic
advice conflates the two and quietly makes businesses invisible.

## What it checks

**Foundations**
- **AI crawler access** — parses robots.txt properly (user-agent groups,
  longest-prefix matching, wildcards) and reports the exact rule and line number
  blocking each crawler. Flags CDN/WAF bot-blocking that overrides robots.txt.
- **Structured data** — LocalBusiness (and the right schema.org subtype for the
  trade), completeness of NAP fields, graded address quality, FAQPage markup,
  and invalid JSON-LD that parsers silently discard.

**Content**
- **Answer readiness** — whether the page states its service and city in text,
  uses question-shaped headings, exposes the phone number as text rather than
  inside an image, and has per-service and per-town pages.

**Authority**
- **Off-site citation sources** — whether Google Business Profile, Yelp, BBB and
  Nextdoor are linked and declared in `sameAs`; internal NAP conflicts; plus
  ready-made verification URLs for each directory and for Reddit, which is one
  of the most-cited sources in AI business recommendations.

**Visibility (optional, needs an API key)**
- **Live probe** — asks assistants the questions real customers ask
  ("I need a plumber in Austin. Who are the best options?"), records whether the
  business is named, at what rank, and **which competitors are named instead**.

Every failure produces a ranked fix, and where possible the generated artifact:
a complete robots.txt block, a filled-in LocalBusiness JSON-LD node typed to the
trade, and FAQ schema seeded with the questions local buyers actually ask.

## Usage

### Web

```bash
python3 -m citelocal.web
```

The results page *is* the client-ready report — same renderer as the file
output, so there is no drift between what you see and what you send. Set the
branding field to white-label it. "Print / save as PDF" produces the deliverable.

### CLI

```bash
python3 -m citelocal.cli \
  --name "Precision Plumbing" \
  --site precisionplumbingatx.com \
  --city Austin --region TX \
  --category "emergency plumber" \
  --html report.html
```

Useful flags:

| Flag | Effect |
|---|---|
| `--no-probe` | Site checks only; no API key, no inference cost |
| `--mode memory` | Probe without web search — tests the model's built-in knowledge |
| `--providers anthropic,openai` | Choose which assistants to test |
| `--snippets` | Print paste-ready code in the terminal |
| `--json out.json` | Machine-readable results |

### API

```bash
curl -X POST http://localhost:5000/api/audit \
  -H 'Content-Type: application/json' \
  -d '{"name":"Precision Plumbing","website":"precisionplumbingatx.com",
       "city":"Austin","region":"TX","category":"plumber","probe":true}'
```

### Live probe keys

Set any of these to enable the probe. Without them everything else still runs.

```bash
export ANTHROPIC_API_KEY=...     # Claude
export OPENAI_API_KEY=...        # ChatGPT
export PERPLEXITY_API_KEY=...    # Perplexity
```

A six-question probe against one provider costs a few cents.

## The business model

The economics are why this product and not a consumer app. $50K MRR is 10,000
consumers at $5/month, or **170 agencies at $299/month**. The second is a
reachable sales target; the first is a marketing budget.

Sell to the agency, not the plumber:

| Tier | Price | For |
|---|---|---|
| Solo | $99/mo | Freelancer, up to 10 audits |
| Agency | $299/mo | White-label reports, up to 50 clients |
| Agency Pro | $699/mo | Unlimited, API access, scheduled re-audits |

The pitch writes itself: an agency reselling this at $500–$1,500 per client
covers a $299 tool with its first client and keeps the rest.

The free audit is the funnel. A report that opens with "4 AI crawlers are
blocked, here is the exact line in your robots.txt" is a better cold outreach
asset than any pitch deck, and it costs nothing to generate because the site
checks need no API key.

**Where the real work is:** the product is the easy half. Distribution is the
bottleneck — agency Facebook groups and Slacks, local-SEO communities, cold
outreach with a free audit attached, and being present wherever agencies discuss
AI search. No amount of code substitutes for that.

## Running the tests

```bash
python3 tests/test_audit.py
```

84 assertions covering robots.txt parsing (group resolution, longest-prefix
matching, wildcards), category→schema mapping, and full end-to-end audits
against three locally-served fixture sites — an invisible one (scores 17), a
partially-optimized one (44) and a well-optimized one (96) — plus an
unreachable-site case that must score 0 rather than falling through to a
misleading 100.

## Limitations, stated plainly

- Assistant answers vary run to run. The probe samples; it does not measure a
  fixed ranking, and a small sample is a weak signal. More questions is a better
  read than more providers.
- Directory presence is verified by link, not by scraping each directory. The
  report emits verification URLs rather than pretending to have checked.
- These checks improve the *conditions* for citation. Nothing here guarantees
  placement in an AI answer, and any tool claiming otherwise is selling
  something.
