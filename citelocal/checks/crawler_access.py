"""Check: can AI assistants actually read this site?

This is the check that most SEO audits miss and that most often explains total
invisibility. A site can have perfect content and still be absent from AI
answers because its robots.txt (or a CDN bot-blocking rule) locks out the
crawlers that build AI retrieval indexes.

The distinction that matters, and that generic "block AI bots" advice gets
wrong: blocking a *training* crawler costs you nothing in visibility, while
blocking a *retrieval/citation* crawler makes you uncitable.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..fetch import Fetcher
from ..models import CheckResult, Effort, Fix, Status
from ..robots import RobotsFile


@dataclass(frozen=True)
class Bot:
    token: str
    operator: str
    purpose: str
    # weight: how much blocking this bot damages AI *visibility* specifically.
    # Training-only crawlers are near zero because opting out of training does
    # not remove you from answers.
    weight: float
    note: str = ""


# Ordered roughly by how much each one matters to being cited in AI answers.
RETRIEVAL_BOTS: tuple[Bot, ...] = (
    Bot(
        token="OAI-SearchBot",
        operator="OpenAI",
        purpose="Builds ChatGPT's search index — the source of ChatGPT citations",
        weight=1.0,
        note="Blocking this removes you from ChatGPT search results entirely.",
    ),
    Bot(
        token="ChatGPT-User",
        operator="OpenAI",
        purpose="Fetches your page live when a ChatGPT user's question needs it",
        weight=0.9,
        note="Blocking this stops ChatGPT reading your page on demand.",
    ),
    Bot(
        token="PerplexityBot",
        operator="Perplexity",
        purpose="Builds Perplexity's index for cited answers",
        weight=0.8,
    ),
    Bot(
        token="Perplexity-User",
        operator="Perplexity",
        purpose="Live page fetch for a Perplexity user's query",
        weight=0.6,
    ),
    Bot(
        token="Claude-SearchBot",
        operator="Anthropic",
        purpose="Builds Claude's search index",
        weight=0.7,
    ),
    Bot(
        token="Claude-User",
        operator="Anthropic",
        purpose="Live page fetch for a Claude user's query",
        weight=0.6,
    ),
    Bot(
        token="Googlebot",
        operator="Google",
        purpose="Powers Google Search AND AI Overviews",
        weight=1.0,
        note="AI Overviews are served from the Googlebot index, not Google-Extended.",
    ),
    Bot(
        token="Bingbot",
        operator="Microsoft",
        purpose="Powers Bing and Microsoft Copilot, and feeds other assistants",
        weight=0.8,
    ),
    Bot(
        token="DuckAssistBot",
        operator="DuckDuckGo",
        purpose="Powers DuckDuckGo's AI answers",
        weight=0.3,
    ),
    Bot(
        token="Applebot",
        operator="Apple",
        purpose="Powers Siri and Spotlight suggestions",
        weight=0.4,
    ),
    Bot(
        token="meta-externalagent",
        operator="Meta",
        purpose="Feeds Meta AI answers across WhatsApp, Instagram, and Facebook",
        weight=0.5,
        note="Relevant for local businesses whose customers ask Meta AI in WhatsApp.",
    ),
    Bot(
        token="Amazonbot",
        operator="Amazon",
        purpose="Powers Alexa answers",
        weight=0.3,
    ),
)

# Blocking these affects model training, not whether you get cited today.
# We report them for completeness but they carry no scoring weight.
TRAINING_BOTS: tuple[Bot, ...] = (
    Bot(
        token="GPTBot",
        operator="OpenAI",
        purpose="Training crawler; also contributes to OpenAI's retrieval corpus",
        weight=0.5,
        note="Mixed-purpose: mostly training, but worth allowing for visibility.",
    ),
    Bot(
        token="ClaudeBot",
        operator="Anthropic",
        purpose="Training crawler",
        weight=0.2,
    ),
    Bot(
        token="Google-Extended",
        operator="Google",
        purpose="Gemini grounding and Vertex AI training",
        weight=0.4,
        note="Does NOT affect AI Overviews, but does affect Gemini app answers.",
    ),
    Bot(
        token="Applebot-Extended",
        operator="Apple",
        purpose="Apple Intelligence training",
        weight=0.1,
    ),
    Bot(
        token="CCBot",
        operator="Common Crawl",
        purpose="Open crawl corpus used to train many models",
        weight=0.2,
    ),
)

ALL_BOTS = RETRIEVAL_BOTS + TRAINING_BOTS

CHECK_ID = "crawler_access"
CHECK_NAME = "AI crawler access (robots.txt)"
CATEGORY = "Foundations"

# Bot-blocking services that override robots.txt at the edge. If a site sits
# behind one of these with AI bot blocking on, robots.txt can look perfect
# while every AI crawler still gets a 403.
EDGE_BLOCK_HINTS = {
    "cloudflare": "Cloudflare",
    "sucuri": "Sucuri",
    "akamai": "Akamai",
    "fastly": "Fastly",
    "incapsula": "Imperva/Incapsula",
    "x-sucuri-id": "Sucuri",
}


def run(business, fetcher: Fetcher) -> CheckResult:
    robots_response = fetcher.get_path(business.website, "/robots.txt")
    home = fetcher.get(business.website)

    # A missing robots.txt means "crawl freely", but an unreachable *site* means
    # we learned nothing. Scoring those the same would hand a dead domain a
    # clean bill of health, which is the most misleading result the tool could
    # produce.
    if not home.ok and robots_response.status_code is None:
        return CheckResult.skipped(
            CHECK_ID,
            CHECK_NAME,
            CATEGORY,
            f"Could not reach the site ({home.error or robots_response.error}) — "
            "crawler access could not be determined.",
        )

    findings: list[str] = []
    fixes: list[Fix] = []

    # A robots.txt endpoint that serves HTML is misconfigured: crawlers get a
    # page they cannot parse, which is usually harmless but worth flagging.
    served_html = robots_response.ok and (
        "<html" in robots_response.text[:2000].lower()
        or "<!doctype" in robots_response.text[:2000].lower()
    )

    if robots_response.ok and not served_html:
        robots = RobotsFile(robots_response.text)
    elif served_html:
        robots = RobotsFile("", missing=True)
        findings.append(
            "/robots.txt returns an HTML page instead of a plain-text robots file — "
            "crawlers cannot read directives from it."
        )
    elif robots_response.status_code == 404:
        robots = RobotsFile("", missing=True)
        findings.append("No robots.txt found (404). All crawlers are allowed by default.")
    else:
        robots = RobotsFile("", missing=True)
        findings.append(
            f"Could not fetch /robots.txt ({robots_response.error or 'unknown error'}). "
            "Treating as permissive, but verify manually."
        )

    blocked_retrieval: list[tuple[Bot, str]] = []
    blocked_training: list[tuple[Bot, str]] = []
    earned = 0.0
    possible = 0.0

    for bot in RETRIEVAL_BOTS:
        decision = robots.check(bot.token)
        possible += bot.weight
        if decision.allowed:
            earned += bot.weight
        else:
            blocked_retrieval.append((bot, decision.reason))

    for bot in TRAINING_BOTS:
        decision = robots.check(bot.token)
        possible += bot.weight
        if decision.allowed:
            earned += bot.weight
        else:
            blocked_training.append((bot, decision.reason))

    for bot, reason in blocked_retrieval:
        findings.append(f"BLOCKED — {bot.token} ({bot.operator}): {bot.purpose}. {reason}")
    for bot, reason in blocked_training:
        findings.append(f"Blocked — {bot.token} ({bot.operator}): {bot.purpose}. {reason}")

    # Detect a blanket disallow, the single most damaging misconfiguration.
    wildcard_decision = robots.check("SomeUnknownAIBot")
    if not wildcard_decision.allowed:
        findings.append(
            "The catch-all 'User-agent: *' group disallows crawling, so any AI "
            "crawler not named explicitly is blocked too."
        )

    if blocked_retrieval:
        blocked_names = ", ".join(bot.token for bot, _ in blocked_retrieval)
        fixes.append(
            Fix(
                title=f"Unblock AI retrieval crawlers: {blocked_names}",
                detail=(
                    "These crawlers build the indexes AI assistants cite from. While "
                    "they are disallowed, this site cannot appear as a source in those "
                    "assistants' answers no matter how good the content is. Allowing "
                    "them is separate from allowing model training — the training-only "
                    "crawlers can stay blocked if that is a deliberate policy."
                ),
                effort=Effort.LOW,
                impact=1.0,
                snippet=_robots_snippet(),
                snippet_language="text",
                reference="Add to robots.txt at the site root",
            )
        )

    if served_html:
        fixes.append(
            Fix(
                title="Serve robots.txt as plain text",
                detail=(
                    "/robots.txt currently returns HTML. Crawlers expect "
                    "'text/plain'; an HTML response means your directives are "
                    "ignored entirely."
                ),
                effort=Effort.LOW,
                impact=0.5,
            )
        )

    # Edge/WAF detection: robots.txt may be clean while the CDN blocks bots.
    edge_vendor = _detect_edge(home.headers) or _detect_edge(robots_response.headers)
    if edge_vendor:
        findings.append(
            f"Site appears to sit behind {edge_vendor}. Bot-management rules there can "
            "return 403 to AI crawlers even when robots.txt allows them — verify in the "
            f"{edge_vendor} dashboard that AI crawler blocking is off."
        )
        fixes.append(
            Fix(
                title=f"Verify {edge_vendor} is not blocking AI crawlers at the edge",
                detail=(
                    f"{edge_vendor} ships bot-management features that can block AI "
                    "crawlers independently of robots.txt, and several enable some form "
                    "of AI bot blocking by default. Check the bot/WAF rules and allow "
                    "the retrieval crawlers listed in this report. This is invisible to "
                    "a robots.txt audit, so it is worth confirming directly."
                ),
                effort=Effort.LOW,
                impact=0.75,
            )
        )

    if not robots.sitemaps and not robots.missing:
        findings.append("robots.txt declares no Sitemap: line.")
        fixes.append(
            Fix(
                title="Declare your sitemap in robots.txt",
                detail=(
                    "A Sitemap: line helps crawlers discover every page worth citing, "
                    "including service and location pages that answer local queries."
                ),
                effort=Effort.LOW,
                impact=0.25,
                snippet=f"Sitemap: {business.website.rstrip('/')}/sitemap.xml",
                snippet_language="text",
            )
        )

    score = earned / possible if possible else 1.0

    if blocked_retrieval:
        status = Status.FAIL
        summary = (
            f"{len(blocked_retrieval)} AI retrieval crawler(s) blocked — "
            "this site cannot be cited by those assistants."
        )
    elif blocked_training or served_html:
        status = Status.WARN
        summary = "Retrieval crawlers are allowed, but some AI crawler access is restricted."
    else:
        status = Status.PASS
        summary = "All major AI crawlers can access the site."
        findings.insert(0, "No AI crawler is disallowed in robots.txt.")

    return CheckResult(
        id=CHECK_ID,
        name=CHECK_NAME,
        category=CATEGORY,
        status=status,
        score=score,
        weight=3.0,  # highest weight: a block here nullifies everything else
        summary=summary,
        findings=findings,
        fixes=fixes,
        evidence={
            "robots_status": robots_response.status_code,
            "robots_found": not robots.missing,
            "sitemaps": robots.sitemaps,
            "blocked_retrieval": [bot.token for bot, _ in blocked_retrieval],
            "blocked_training": [bot.token for bot, _ in blocked_training],
            "edge_vendor": edge_vendor,
        },
    )


def _detect_edge(headers: dict[str, str]) -> str | None:
    joined = " ".join(f"{k} {v}" for k, v in headers.items()).lower()
    for hint, vendor in EDGE_BLOCK_HINTS.items():
        if hint in joined:
            return vendor
    return None


def _robots_snippet() -> str:
    lines = [
        "# Allow AI assistants to read and cite this site.",
        "# These crawlers build retrieval indexes used to answer user questions.",
        "",
    ]
    for bot in RETRIEVAL_BOTS:
        lines.append(f"# {bot.operator}: {bot.purpose}")
        lines.append(f"User-agent: {bot.token}")
        lines.append("Allow: /")
        lines.append("")
    return "\n".join(lines).rstrip()
