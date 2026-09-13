# The $100K Month: what I'd actually do

> Written as the answer to: *"You're a human. You have Claude Code and 30 days.
> Sole goal: $100,000. Go."*

This document is the reasoning. The code in [`engine/`](engine/) is the execution.

---

## 0. The uncomfortable part, first

**$100K in 30 days is a sales problem wearing a build problem's clothes.**

Claude Code collapses *build* time. A thing that took a 3-person shop six weeks
now takes an afternoon. That is a genuine, enormous edge — and it is an edge on
the wrong axis. Nothing about it collapses the time it takes a stranger to trust
you with $20,000. That trust is bought in conversations, and conversations are
the binding constraint.

So the correct use of a month of Claude Code is **not** "build the app that makes
$100K." It is: **build the machine that manufactures qualified conversations,
then spend 27 days running it.**

Honest probabilities, executing well:

| Outcome in 30 days | Probability |
| --- | --- |
| $0 | ~15% |
| $10K+ | ~65% |
| $25K+ | ~45% |
| $50K+ | ~30% |
| **$100K+** | **~15–25%** |

The modal good outcome is **$25–40K**, with $100K as the tail you're playing for.
Anyone quoting you higher odds is selling something. I'd take that bet — a 20%
shot at $100K plus a 45% shot at $25K+ is an excellent month — but I'd take it
knowing what it is.

---

## 1. Ranked paths (and why four of them lose)

### ❌ Path: Memecoin / sniper bots — *you asked, so here's the straight answer*

This is the one people most want to hear yes on. The math says no.

- **You lose the latency race before you start.** Competitive snipers run
  co-located nodes with private orderflow (Jito bundles on Solana, private
  mempools on EVM) and sub-50ms reaction times. From a laptop over a consumer
  connection you're at 200–800ms. On a launch, that gap *is* the entire edge.
- **Exit liquidity is the real killer.** People model entry and ignore exit. You
  can put $2,000 *in* to a thin pool. Getting $2,000 *out* moves the price
  against you by more than your gain. Backtests that ignore exit slippage are
  fiction.
- **Contract risk eats the rest.** Un-revoked mint authority, un-burned LP,
  transfer-tax traps, blacklist functions, honeypots. A bot that doesn't check
  every one of these loses to contract risk alone, independent of price action.
- **The base rate is brutal.** The overwhelming majority of new launchpad tokens
  go to approximately zero. You are not picking from a neutral distribution;
  you're picking from one that is adversarially constructed against you.

**Where the actual money is: selling shovels.** Rug scanners, risk dashboards,
alert feeds, wallet-tracking tools — subscription revenue from people who want to
trade, which is stable, legal, and doesn't require you to win a latency war. That
is a real business, and it is a special case of Path A below.

If you want crypto exposure anyway: this repo's existing
[market-analysis agent](README.md) is the honest starting point, and its roadmap
has the order right — **backtest, then paper trade, then risk real money.** Skip
either step and you're donating.

### ❌ Path: Launch a SaaS, reach $100K MRR

0 → $100K MRR in 30 days has essentially no precedent. Median month-one revenue
for a new indie SaaS is **$0**. This is the right *month 2–6* play, funded by
Path A. It is not the 30-day play.

### ❌ Path: $99 info product / template pack

Needs ~1,000 sales in 30 days, which needs an audience you don't have. Audience
is a 6-month asset. Not available inside the window.

### ⚠️ Path: Freelance marketplaces (Upwork, Contra)

Real money, but new profiles rank badly, rates are compressed by global
competition, and escrow release lags. Worth **$5–15K** as a *fill* channel while
the main engine warms up. Not the main bet.

### ✅ **Path A: Evidence-led technical services for SMBs**

This is the bet. Here's why it's structurally different: **the revenue is
contracted, not speculative.** You are not hoping a market rewards you. Someone
signs a document agreeing to pay you a specific number.

And the bottleneck — "how do I get enough qualified conversations?" — is an
*arithmetic* problem, which means it's a *code* problem, which means it's the one
thing Claude Code actually solves.

---

## 2. The arithmetic that decides everything

Target: **$100,000 / 30 days.**

I first worked this out by hand and got it wrong. The engine's funnel model
(`engine/pipeline.py`) caught the error, which is a decent argument for building
the model before committing to the plan. Both versions are below, because the
mistake is the instructive part.

### The naive version

A realistic deal mix, blended average **$8,333**:

| Package | Price | Count | Subtotal |
| --- | --- | --- | --- |
| Overhaul | $20,000 | 2 | $40,000 |
| Fix Sprint | $6,500 | 8 | $52,000 |
| Retainer (first month) | $3,500 | 2 | $7,000 |
| | | **12 closes** | **$99,000** |

Funnel rates for **evidence-backed** outreach — a message citing a specific
measured defect on the prospect's own site. Generic outreach runs ~10× worse and
isn't worth modelling:

```
send → reply         8%     (generic outreach: 1–2%)
reply → call booked  35%
call → closed        25%
────────────────────────────
send → close         0.70%
```

13 closes ÷ 0.007 ≈ **1,863 sends**. Over 30 days that's **62 a day**. Tough but
survivable. That was my answer, and it's wrong.

### The correction: you do not have 30 send-days

A deal takes about 10 days from first touch to signature. A message sent on day
26 **cannot close inside the window** — it's next month's revenue. So the sends
have to fit into the first 20 days, not all 30:

```
1,863 sends ÷ (30 − 10) send-days = 94 per day
```

Not 62. **94.** And 94 personalised sends a day is past what one person sustains
— the engine flags it outright:

```
PER DAY: 94 sends, 233 scans   [not achievable at these rates]
! 94 sends/day exceeds a realistic capacity of 60.
```

Most plans that fail in week four failed on day one, at this exact division.

### What actually closes the gap

Run the levers separately (`money plan --scenarios`) and one dominates:

| Lever | Sends/day | Verdict |
| --- | --- | --- |
| Baseline — $8.3k deals, 10d cycle, 8% reply | 94 | not achievable |
| Compress the sales cycle to 7 days | 81 | not achievable |
| Lift close rate 25% → 35% | 69 | not achievable |
| Lift reply rate 8% → 12% | 63 | not achievable |
| **Raise average deal to $15k** | **50** | **achievable** |
| $15k deals + 7-day cycle | 44 | achievable |
| $15k + 7-day cycle + 12% reply | 29 | comfortable |

**Average deal value beats every other lever, and beats most of them combined.**
Doubling your reply rate — the hardest thing on this list — is worth less than
selling deals twice the size.

This is counterintuitive enough to be worth restating: the instinct when you're
behind is to send more. The arithmetic says send *better-targeted*, to people who
can sign bigger.

### The revised plan

Seven deals at a **$15,000 average**:

| Package | Price | Count | Subtotal |
| --- | --- | --- | --- |
| Overhaul | $20,000 | 3 | $60,000 |
| Mid engagement | $15,000 | 2 | $30,000 |
| Fix Sprint | $6,500 | 2 | $13,000 |
| | | **7 closes** | **$103,000** |

Which demands: **1,000 sends · 80 replies · 28 calls · 7 closes** — **50 sends
and 125 scans a day** across a 20-day send window. Demanding, achievable.

### Three consequences that change what you build

1. **Target businesses that can sign $15–20k.** A broken site belonging to
   someone who has never spent a dollar online is a $2,500 deal at best, and
   forty of those don't fit in the window. The engine scores this explicitly
   (`BudgetSignal`): CDN in front, multiple analytics tools, a large sitemap,
   existing security headers. All observable from one HTTP response.
2. **Rank by expected value, not by damage.** Sorting by how broken a site is
   sends you to the worst prospect on your list first. `rank_prospects()` sorts
   by `package price × deal fit`.
3. **Scope honestly by site scale.** The same fix across 2,400 templated pages
   genuinely is more work than on a 12-page brochure site — more templates, more
   regression surface. That is a legitimate route to a higher average deal.
   *Padding a small client's quote to hit your revenue target is not*, and it
   loses the deal the moment they get a second opinion.

### The caveat worth keeping

At **pessimistic** rates (4% reply, 25% call, 15% close), $100k needs 205
sends/day even at $15k deals. It does not happen. If week one comes back at
pessimistic rates, the honest move is to reset the target to $40k and take the
good month — not to send four times as much worse mail.

## 3. The 30-day plan

**Days 1–3 — build the machine.** (This repo. It's built; see §4.)

**Days 4–6 — calibrate on 50 prospects.** Scan, rank, send. You're not selling
yet, you're measuring: does the audit find real problems? Do replies come? Fix
the message before scaling it.

**Days 7–24 — run it.** 50 sends/day, front-loaded — remember the send window
closes on day 20. Every reply gets a call. Every call gets a same-day scoped
proposal generated from the audit you already ran. This is the grind; there is
no trick that replaces it.

**Days 25–30 — close and deliver.** Deliver fast with Claude Code (this is where
your build edge finally pays), collect testimonials, convert one-off clients to
retainers so month two doesn't start at zero.

### Pricing: anchor to their revenue, never to your hours

Hourly billing caps you at your clock and punishes you for being fast — which,
with Claude Code, is exactly backwards. Price the outcome. A checkout page that
takes 8 seconds to load is losing them money continuously; your fee is a fraction
of the recovered amount, not a function of how long it took you.

**Never invent their numbers.** Say "page-load improvements of this size are
associated with meaningful conversion lift in published industry studies" — cite
the benchmark, flag it as a benchmark. Do not say "this will make you $40,000."
You don't know that, and a prospect who catches you inventing a number is gone,
correctly. The engine enforces this in code (§4, *grounding*).

### Guardrails that are also self-interest

- **robots.txt, rate limits, honest User-Agent.** Non-negotiable, and also: the
  fastest way to get your IP nullrouted is to behave like a scraper.
- **CAN-SPAM / GDPR.** Accurate headers, real physical address, working
  one-click opt-out, legitimate-interest basis in the EU.
- **Never fabricate a measurement.** The single thing that makes this work is
  that the evidence is real. Break that and you have spam with extra steps.

Domain reputation is the asset that's hardest to rebuild. Protect it.

---

## 4. What I built

[`engine/`](engine/) — a zero-heavy-dependency revenue engine (stdlib + `requests`).

| Module | What it does |
| --- | --- |
| `fetch.py` | Polite HTTP: robots.txt, per-host rate limiting, honest UA, redirect chains, byte caps |
| `htmlparse.py` | Stdlib HTML extraction — no BeautifulSoup, no lxml |
| `checks.py` | ~35 checks that each produce a **measured number**, not an opinion |
| `scan.py` | Orchestrates a full audit into an `AuditResult` |
| `score.py` | Health score, **deal-fit** score, and the recommended package + price |
| `audit_report.py` | The client-facing deliverable (Markdown + standalone HTML) |
| `outreach.py` | Drafts grounded in findings — with a verifier that **fails** on any unsourced number |
| `pipeline.py` | The §2 arithmetic, live: required daily volume, pace, weighted pipeline |
| `storage.py` | Plain JSON under `.engine/` |
| `cli.py` | `scan` · `report` · `outreach` · `pipeline` · `plan` · `today` · `run` |

The load-bearing piece is **grounding**. `outreach.verify_grounded()` extracts
every numeric claim from a draft and asserts it traces back to a recorded
measurement. A draft that invents a number raises. That isn't decoration — it's
the property the entire strategy rests on.

Start here: **`python3 money.py plan --scenarios`** shows the lever table above
against your own numbers. **`python3 money.py today`** tells you whether you're
behind and by how much.

---

## 5. The one-paragraph version

Don't build an app and hope. Build the thing that finds a thousand businesses
with a provable, measurable, expensive defect; prove it to them with a number you
actually measured; and convert 0.7% of them into contracted work you can deliver
absurdly fast because you have Claude Code. Sell to the ones who can sign
five figures, because deal size beats every other lever. The build is three days.
The other twenty-seven are conversations. **The engine is the edge; the grind is
still the grind** — and anyone who tells you the grind is optional is selling you
something.
