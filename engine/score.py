"""Turning an audit into a decision: is this a prospect, and what do you sell them?

Two different scores live here and they are not the same thing:

* **health_score** — how broken the site is. This is what the *client* cares
  about and what goes on the report.
* **deal_fit** — how likely this prospect is to pay you. A perfectly healthy
  site scores 100 on health and near zero on fit: nothing to sell. A completely
  dead site also scores badly on fit — nobody is home to buy.

The sweet spot is a site with real, expensive, *cheaply fixable* problems that
belongs to a business visibly trying to collect leads. Ranking your list by fit
rather than by pain is most of the difference between 57 productive sends a day
and 57 wasted ones.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .checks import Finding
from .scan import AuditResult

SEVERITY_WEIGHT = {"critical": 18.0, "high": 10.0, "medium": 4.0, "low": 1.5}
# No single category may sink the score on its own — twelve low-severity SEO
# nits should not outrank "the site has no HTTPS".
MAX_DEDUCTION_PER_CATEGORY = 30.0

# Categories weighted by how legible the problem is to a non-technical owner.
# "Your site doesn't work on phones" sells. "No Referrer-Policy header" does not.
HEADLINE_CATEGORY_WEIGHT = {
    "performance": 1.30,
    "mobile": 1.30,
    "conversion": 1.20,
    "security": 1.10,
    "trust": 1.00,
    "seo": 0.95,
}


@dataclass
class Package:
    """A priced, scoped offer derived from the findings."""

    key: str
    name: str
    price: int
    scope_hours: float
    summary: str
    includes: list[str] = field(default_factory=list)
    followon: str | None = None


PACKAGES = {
    "quick_win": Package(
        key="quick_win",
        name="Quick Win Sprint",
        price=2500,
        scope_hours=8,
        summary="The three highest-impact fixes, shipped inside a week.",
        includes=[
            "Fix the top 3 findings from the audit",
            "Before/after measurements on each",
            "A written handover of what changed and why",
        ],
        followon="Often becomes a Fix Sprint once the first numbers land.",
    ),
    "fix_sprint": Package(
        key="fix_sprint",
        name="Performance & Conversion Sprint",
        price=6500,
        scope_hours=24,
        summary="Every critical and high finding cleared, with measurement in place.",
        includes=[
            "All critical and high-severity findings resolved",
            "Analytics and conversion tracking installed and verified",
            "Core Web Vitals brought into the green where the stack allows",
            "Two weeks of post-launch monitoring",
        ],
        followon="Natural lead-in to a monthly retainer.",
    ),
    "overhaul": Package(
        key="overhaul",
        name="Site Overhaul",
        price=20000,
        scope_hours=70,
        summary="Structural rebuild — for sites where fixes alone won't get there.",
        includes=[
            "Mobile-first responsive rebuild of the main templates",
            "Full performance re-architecture (CDN, caching, asset pipeline)",
            "Security headers, HTTPS and TLS configuration",
            "SEO foundations: structured data, sitemap, metadata",
            "Analytics, conversion tracking and a reporting dashboard",
        ],
        followon="Ships with the first retainer month included.",
    ),
    "retainer": Package(
        key="retainer",
        name="Monthly Care & Growth",
        price=3500,
        scope_hours=10,
        summary="Ongoing monitoring, fixes and incremental improvement.",
        includes=[
            "Continuous uptime and performance monitoring",
            "Monthly audit re-run with a tracked scorecard",
            "A fixed block of improvement hours each month",
        ],
    ),
}


@dataclass
class BudgetSignal:
    """Observable evidence that a prospect already spends money on their site.

    This exists because of what the funnel model in `pipeline.py` says once you
    run it honestly: at a $8.3k average deal you need ~94 sends a day to reach
    $100k in 30 days, which is past what one person can sustain. At $15k you
    need ~50. **Average deal value is the dominant lever** — it beats reply
    rate, close rate and cycle length combined.

    So ranking prospects purely by how broken they are optimises the wrong
    thing. A badly broken site belonging to someone who has never spent a dollar
    online is a $2,500 deal at best, and twelve of those do not add up to the
    target inside the window. What you want is a prospect with real problems
    *and* a demonstrated willingness to pay to solve them.

    Every signal here is observable from one HTTP response, which is the
    constraint that keeps a scan cheap enough to run hundreds of times a day.
    """

    score: int  # 0-100
    signals: list[str] = field(default_factory=list)

    @property
    def tier(self) -> str:
        if self.score >= 65:
            return "enterprise"
        if self.score >= 35:
            return "established"
        return "small"


def budget_signal(result: AuditResult) -> BudgetSignal:
    """How likely this prospect can sign a five-figure engagement."""
    if not result.ok:
        return BudgetSignal(score=0, signals=[])

    score = 0
    signals: list[str] = []

    # A CDN is a paid product somebody chose and configured.
    if result.cdn:
        score += 22
        signals.append(f"Runs behind {result.cdn} — already paying for infrastructure")

    # Martech stack. Multiple tools, or a paid one, means a real budget line.
    paid_tools = {"Segment", "Hotjar", "Mixpanel", "PostHog"}
    if result.analytics:
        score += 12
        if len(result.analytics) >= 2:
            score += 8
            signals.append(f"Runs {len(result.analytics)} analytics tools — active marketing spend")
        elif any(t in paid_tools for t in result.analytics):
            score += 8
            signals.append(f"Runs {result.analytics[0]} — paid analytics tooling")
        else:
            signals.append(f"Runs {result.analytics[0]}")

    # Site scale. A large sitemap means content investment over time.
    if result.sitemap_urls >= 500:
        score += 25
        signals.append(f"{result.sitemap_urls:,} URLs in the sitemap — substantial site")
    elif result.sitemap_urls >= 100:
        score += 16
        signals.append(f"{result.sitemap_urls:,} URLs in the sitemap — established site")
    elif result.sitemap_urls >= 20:
        score += 8
        signals.append(f"{result.sitemap_urls} URLs in the sitemap")

    if result.internal_link_count >= 60:
        score += 10
        signals.append(f"{result.internal_link_count} internal links — a deep site, not a brochure")
    elif result.internal_link_count >= 25:
        score += 5

    # Someone has done deliberate technical work here before.
    codes = {f.code for f in result.findings}
    if "SEO_NO_STRUCTURED_DATA" not in codes:
        score += 8
        signals.append("Structured data in place — has had technical help before")
    if "SEC_NO_CSP" not in codes:
        score += 8
        signals.append("Content-Security-Policy configured — security work already done")

    return BudgetSignal(score=min(100, score), signals=signals)


# A fix applied across a large site is genuinely more work than the same fix on
# a brochure site — more templates, more regression surface, more to verify.
# Scaling scope this way is honest; it is also, per the funnel model, the only
# legitimate route to a higher average deal value. Padding a small client's
# quote to hit a revenue target is the dishonest version of the same move, and
# it loses the deal the moment they get a second opinion.
SCALE_TIERS = ((2000, 3.2), (500, 2.5), (100, 1.8), (25, 1.3), (0, 1.0))


def scale_multiplier(result: AuditResult) -> float:
    """How much the site's size multiplies the effort behind each finding."""
    size = max(result.sitemap_urls, result.internal_link_count * 2)
    for threshold, multiplier in SCALE_TIERS:
        if size >= threshold:
            return multiplier
    return 1.0


def scaled_effort_hours(result: AuditResult) -> float:
    """Total effort adjusted for how many pages the fixes have to land on."""
    return round(result.total_effort_hours * scale_multiplier(result), 1)


# A package a prospect cannot plausibly afford is a wasted send, however
# accurately it describes what they need. Lead with what they can buy and name
# the full scope as the end state — that is the land-and-expand motion, and it
# is also just more honest than quoting a number to someone you know will balk.
TIER_CEILING = {"small": "fix_sprint", "established": "overhaul", "enterprise": "overhaul"}
PACKAGE_ORDER = ("retainer", "quick_win", "fix_sprint", "overhaul")


def _cap_to_tier(package: Package, tier: str) -> tuple[Package, str | None]:
    ceiling = TIER_CEILING.get(tier, "fix_sprint")
    if PACKAGE_ORDER.index(package.key) <= PACKAGE_ORDER.index(ceiling):
        return package, None
    capped = PACKAGES[ceiling]
    return capped, (
        f"Findings justify the {package.name} (${package.price:,}), but the spend "
        f"signals point to a smaller budget. Lead with the {capped.name} as phase one "
        "and name the full scope as the end state."
    )


@dataclass
class Assessment:
    """The full verdict on one scanned prospect."""

    domain: str
    health_score: int
    deal_fit: int
    grade: str
    package: Package
    headline: Finding | None
    budget: BudgetSignal = field(default_factory=lambda: BudgetSignal(score=0))
    scaled_hours: float = 0.0
    scope_note: str | None = None
    quick_wins: list[Finding] = field(default_factory=list)
    fit_reasons: list[str] = field(default_factory=list)

    @property
    def expected_value(self) -> float:
        """Package price weighted by fit. Sort a list by this to plan a day."""
        return round(self.package.price * (self.deal_fit / 100), 2)

    @property
    def is_prospect(self) -> bool:
        return self.deal_fit >= 45

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "health_score": self.health_score,
            "deal_fit": self.deal_fit,
            "grade": self.grade,
            "package": self.package.key,
            "package_price": self.package.price,
            "budget_score": self.budget.score,
            "budget_tier": self.budget.tier,
            "scaled_hours": self.scaled_hours,
            "scope_note": self.scope_note,
            "expected_value": self.expected_value,
            "headline_code": self.headline.code if self.headline else None,
            "fit_reasons": self.fit_reasons,
        }


def health_score(result: AuditResult) -> int:
    """0–100. How healthy the site is, from the owner's point of view."""
    if not result.ok:
        return 0

    per_category: dict[str, float] = {}
    for finding in result.findings:
        weight = SEVERITY_WEIGHT.get(finding.severity, 1.0)
        # A heuristic finding shouldn't cost as much as a measured one.
        if finding.confidence == "medium":
            weight *= 0.6
        per_category[finding.category] = per_category.get(finding.category, 0.0) + weight

    deduction = sum(min(total, MAX_DEDUCTION_PER_CATEGORY) for total in per_category.values())
    return max(0, min(100, round(100 - deduction)))


def grade_for(score: int) -> str:
    for threshold, letter in ((90, "A"), (80, "B"), (70, "C"), (55, "D"), (0, "F")):
        if score >= threshold:
            return letter
    return "F"


def quick_wins(result: AuditResult, max_hours: float = 2.0, limit: int = 5) -> list[Finding]:
    """High-severity findings that are cheap to fix — the door-opener.

    'I can fix this in an afternoon' is a far easier yes than 'you need a
    rebuild', and it's how a $2,500 sprint becomes a $20,000 overhaul later.
    """
    candidates = [
        f
        for f in result.findings
        if f.severity in ("critical", "high") and f.effort_hours <= max_hours
    ]
    candidates.sort(key=lambda f: (f.rank, f.effort_hours))
    return candidates[:limit]


def headline_finding(result: AuditResult) -> Finding | None:
    """The single finding to lead with — the one that goes in the subject line.

    Prefers findings that carry a hard number. "Your homepage takes 2.3 seconds
    to respond" lands; "no Referrer-Policy header" does not, however true.
    """
    if not result.findings:
        return None

    def rank(finding: Finding) -> float:
        base = SEVERITY_WEIGHT.get(finding.severity, 1.0)
        base *= HEADLINE_CATEGORY_WEIGHT.get(finding.category, 1.0)
        if _numeric_metrics(finding):
            base *= 1.5  # a measurable claim is worth far more in a cold open
        if finding.confidence == "medium":
            base *= 0.7
        return base

    return max(result.findings, key=rank)


def deal_fit(result: AuditResult, budget: BudgetSignal | None = None) -> tuple[int, list[str]]:
    """0–100: how likely this prospect is to become paying work, and why.

    Weighted toward *payable* work rather than merely broken sites — see
    `BudgetSignal` for why the funnel arithmetic forces that.
    """
    if not result.ok:
        return 0, ["Site did not respond to the scan — nothing to assess."]

    budget = budget or budget_signal(result)
    reasons: list[str] = []
    counts = result.severity_counts

    # 1. Pain (0-32). Real, severe, provable problems.
    pain_raw = counts["critical"] * 11 + counts["high"] * 6.5 + counts["medium"] * 2.0
    pain = min(32.0, pain_raw)
    if counts["critical"]:
        reasons.append(f"{counts['critical']} critical issue(s) — urgent and easy to demonstrate")
    elif counts["high"] >= 2:
        reasons.append(f"{counts['high']} high-severity issues to lead with")

    # 2. Quick wins (0-18). Something cheap and severe to open on.
    wins = quick_wins(result)
    quick = min(18.0, len(wins) * 6.5)
    if wins:
        reasons.append(
            f"{len(wins)} severe issue(s) fixable in ≤2h — a credible first offer"
        )

    # 3. Commercial intent (0-16). Are they trying to collect leads?
    codes = {f.code for f in result.findings}
    intent = 0.0
    if "CONV_NO_FORM" not in codes:
        intent += 8
    if "CONV_NO_PHONE" not in codes:
        intent += 4
    if "CONV_NO_CONTACT_ROUTE" not in codes:
        intent += 4
    if intent >= 12:
        reasons.append("Site actively collects leads — conversion work has a clear payoff")
    elif intent == 0:
        reasons.append("No visible lead capture — may not be a commercial site")

    # 4. Reachability (0-10). Can you actually contact a human?
    reach = 10.0 if "CONV_NO_CONTACT_ROUTE" not in codes else 3.0

    # 5. Ability to pay (0-24). The dominant term, per the funnel model.
    ability = budget.score * 0.24
    if budget.tier == "enterprise":
        reasons.append("Strong spend signals — can plausibly sign a five-figure engagement")
    elif budget.tier == "established":
        reasons.append("Moderate spend signals — a mid-four-figure engagement is realistic")
    else:
        reasons.append("Few spend signals — likely a small budget, expect a low-price deal")

    score = pain + quick + intent + reach + ability

    # Penalty: a healthy site is a bad prospect regardless of the above.
    health = health_score(result)
    if health >= 90:
        score *= 0.35
        reasons.append("Site is already in good shape — little to sell")
    elif health >= 80:
        score *= 0.7

    # Penalty: catastrophically broken often means abandoned, not buying.
    if health <= 15 and intent == 0:
        score *= 0.5
        reasons.append("Severely broken with no lead capture — likely dormant")

    return max(0, min(100, round(score))), reasons


def recommend_package(
    result: AuditResult, budget: BudgetSignal | None = None
) -> tuple[Package, str | None]:
    """Pick the package the findings actually justify.

    Scoped by what the audit found, not by what you'd like to charge. Quoting an
    overhaul for a site that needs two header changes is how you lose a deal you
    had already won.
    """
    budget = budget or budget_signal(result)
    codes = {f.code for f in result.findings}
    counts = result.severity_counts
    # Scaled, not raw: what matters is the work to land these fixes across the
    # whole site, which is what you'd actually have to deliver.
    hours = scaled_effort_hours(result)

    # Only a missing viewport is genuinely structural: there is no responsive
    # layout to patch, so the templates get rebuilt. Missing HTTPS looks just as
    # alarming but is a certificate install — the check itself estimates three
    # hours. Treating the two alike quotes $20,000 for an afternoon's work, and
    # a prospect who gets a second opinion never calls back.
    needs_rebuild = "MOB_NO_VIEWPORT" in codes

    # Effort leads, severity follows. One cheap critical finding is a quick win,
    # not a sprint; severity says how *urgent* the work is, hours say how *much*.
    if needs_rebuild or hours > 40 or counts["critical"] >= 3:
        chosen = PACKAGES["overhaul"]
    elif hours > 12 or counts["critical"] >= 2 or counts["high"] >= 3:
        chosen = PACKAGES["fix_sprint"]
    elif hours > 3 or counts["critical"] >= 1 or counts["high"] >= 1 or counts["medium"] >= 3:
        chosen = PACKAGES["quick_win"]
    else:
        chosen = PACKAGES["retainer"]

    return _cap_to_tier(chosen, budget.tier)


def assess(result: AuditResult) -> Assessment:
    """Full verdict for one scanned site."""
    health = health_score(result)
    budget = budget_signal(result)
    fit, reasons = deal_fit(result, budget)
    package, scope_note = recommend_package(result, budget)
    return Assessment(
        domain=result.domain,
        health_score=health,
        deal_fit=fit,
        grade=grade_for(health),
        package=package,
        headline=headline_finding(result),
        budget=budget,
        scaled_hours=scaled_effort_hours(result),
        scope_note=scope_note,
        quick_wins=quick_wins(result),
        fit_reasons=reasons,
    )


def rank_prospects(results: list[AuditResult]) -> list[tuple[AuditResult, Assessment]]:
    """Sort a batch by deal fit, best first. This is your send order."""
    pairs = [(r, assess(r)) for r in results]
    # Expected value, not raw fit: a 60-fit prospect on a $20,000 package is a
    # better use of the next hour than a 90-fit prospect on a $2,500 one.
    pairs.sort(key=lambda p: (-p[1].expected_value, -p[1].deal_fit))
    return pairs


def _numeric_metrics(finding: Finding) -> dict[str, float]:
    return {
        k: float(v)
        for k, v in finding.metrics.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
