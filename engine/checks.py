"""The checks. Each one produces a *measured number*, not an opinion.

This is the load-bearing module. The entire strategy in STRATEGY.md rests on
one property: when we tell a stranger their site has a problem, the problem is
real and the number is one we actually observed. That is what separates a 8%
reply rate from a 0.1% reply rate, and it is what keeps this from being spam.

So two rules hold throughout:

1. **Evidence is measured.** Every `Finding.evidence` string states something we
   observed over the wire, and every number in it is also recorded in
   `Finding.metrics` so `outreach.verify_grounded` can trace it back.

2. **Impact is never a fabricated dollar figure.** We do not know a prospect's
   revenue, conversion rate, or margin, so we never say "this costs you
   $40,000/year". We describe the mechanism and cite published benchmarks as
   benchmarks. A prospect who catches you inventing their numbers is gone, and
   they're right to go.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .htmlparse import PageDoc

# -- thresholds --------------------------------------------------------------
# Tunable in one place. Defaults are deliberately conservative: we would rather
# miss a marginal finding than put a weak one in front of a prospect.

TTFB_SLOW_MS = 800.0
TTFB_CRITICAL_MS = 1800.0
TOTAL_SLOW_MS = 3000.0
HTML_HEAVY_BYTES = 100 * 1024
HTML_CRITICAL_BYTES = 300 * 1024
TITLE_MIN, TITLE_MAX = 15, 60
DESC_MIN, DESC_MAX = 70, 160
THIN_CONTENT_WORDS = 200
MANY_STYLESHEETS = 5
RENDER_BLOCK_WARN = 1
LEGACY_IMAGE_WARN = 5

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CATEGORIES = ("performance", "security", "seo", "mobile", "conversion", "trust")


@dataclass
class Finding:
    """One defect, with the measurement that proves it."""

    code: str
    title: str
    category: str
    severity: str  # critical | high | medium | low
    evidence: str  # what we measured, stated as fact
    impact: str  # the mechanism by which it costs money — never invented numbers
    fix: str
    effort_hours: float
    confidence: str = "high"  # high | medium
    # Raw measurements behind `evidence`. This is what makes outreach
    # verifiable: a number in a draft must appear here.
    metrics: dict[str, float | int | str] = field(default_factory=dict)

    @property
    def rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity, 9)


@dataclass
class ScanContext:
    """Everything one scan observed, handed to every check."""

    url: str
    final_url: str
    domain: str
    status: int | None
    headers: dict[str, str]
    html_bytes: int
    ttfb_ms: float | None
    total_ms: float | None
    redirect_chain: list[tuple[int, str]]
    doc: PageDoc
    analytics: list[str] = field(default_factory=list)
    robots_present: bool = False
    robots_status: int | None = None
    sitemap_present: bool = False
    sitemap_urls: int = 0
    http_redirects_to_https: bool | None = None  # None = not probed
    soft_404: bool | None = None
    broken_links: list[tuple[str, int | None]] = field(default_factory=list)
    links_checked: int = 0

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lowered:
                return value
        return None

    @property
    def is_https(self) -> bool:
        return self.final_url.startswith("https://")


CHECKS: list = []


def check(fn):
    """Register a check. Each returns a list of Findings (often empty)."""
    CHECKS.append(fn)
    return fn


def run_all(ctx: ScanContext) -> list[Finding]:
    """Run every check and return findings sorted by severity then category."""
    findings: list[Finding] = []
    for fn in CHECKS:
        try:
            findings.extend(fn(ctx) or [])
        except Exception:
            # One brittle check must never lose the other thirty-nine findings.
            continue
    findings.sort(key=lambda f: (f.rank, f.category, f.code))
    return findings


# =============================================================================
# Performance
# =============================================================================


@check
def slow_ttfb(ctx: ScanContext) -> list[Finding]:
    if ctx.ttfb_ms is None or ctx.ttfb_ms < TTFB_SLOW_MS:
        return []
    critical = ctx.ttfb_ms >= TTFB_CRITICAL_MS
    return [
        Finding(
            code="PERF_TTFB_SLOW",
            title="Server takes too long to respond",
            category="performance",
            severity="critical" if critical else "high",
            evidence=(
                f"Time to first byte measured at {ctx.ttfb_ms:,.0f} ms "
                f"(a healthy target is under {TTFB_SLOW_MS:,.0f} ms)."
            ),
            impact=(
                "Time to first byte is pure waiting before anything renders — no "
                "amount of front-end work hides it. It is also a confirmed Google "
                "ranking input, so it costs traffic as well as patience."
            ),
            fix=(
                "Profile the slowest server-side query or template render, add "
                "caching at the page or fragment level, and put a CDN in front of "
                "the origin."
            ),
            effort_hours=8.0 if critical else 5.0,
            metrics={"ttfb_ms": round(ctx.ttfb_ms), "ttfb_target_ms": TTFB_SLOW_MS},
        )
    ]


@check
def slow_total_load(ctx: ScanContext) -> list[Finding]:
    if ctx.total_ms is None or ctx.total_ms < TOTAL_SLOW_MS:
        return []
    return [
        Finding(
            code="PERF_TOTAL_SLOW",
            title="Homepage HTML takes seconds to transfer",
            category="performance",
            severity="high",
            evidence=(
                f"The homepage HTML took {ctx.total_ms / 1000:,.1f} s to download "
                f"({ctx.html_bytes / 1024:,.0f} KB) on a fast connection."
            ),
            impact=(
                "This is the document alone, before images, CSS or JavaScript. "
                "A real visitor on mobile data waits considerably longer than this "
                "measurement suggests."
            ),
            fix="Reduce HTML payload, enable compression, and serve from a CDN edge.",
            effort_hours=4.0,
            metrics={
                "total_load_s": round(ctx.total_ms / 1000, 1),
                "html_kb": round(ctx.html_bytes / 1024),
            },
        )
    ]


@check
def heavy_html(ctx: ScanContext) -> list[Finding]:
    if ctx.html_bytes < HTML_HEAVY_BYTES:
        return []
    critical = ctx.html_bytes >= HTML_CRITICAL_BYTES
    return [
        Finding(
            code="PERF_HTML_HEAVY",
            title="HTML document is oversized",
            category="performance",
            severity="high" if critical else "medium",
            evidence=(
                f"The homepage HTML is {ctx.html_bytes / 1024:,.0f} KB "
                f"(a lean page is under {HTML_HEAVY_BYTES / 1024:,.0f} KB)."
            ),
            impact=(
                "Oversized HTML delays first paint on every visit, and the cost "
                "lands hardest on mobile users, who are usually the majority."
            ),
            fix=(
                "Strip inlined base64 assets and dead markup; move large inline "
                "styles and scripts to cacheable external files."
            ),
            effort_hours=5.0,
            metrics={"html_kb": round(ctx.html_bytes / 1024)},
        )
    ]


@check
def no_compression(ctx: ScanContext) -> list[Finding]:
    encoding = (ctx.header("content-encoding") or "").lower()
    if any(alg in encoding for alg in ("gzip", "br", "deflate", "zstd")):
        return []
    # Below a few KB compression saves little and some servers skip it by design.
    if ctx.html_bytes < 4096:
        return []
    saved = int(ctx.html_bytes * 0.7)  # ~70% is typical for HTML with gzip
    return [
        Finding(
            code="PERF_NO_COMPRESSION",
            title="Text compression is not enabled",
            category="performance",
            severity="high",
            evidence=(
                f"The server returned {ctx.html_bytes / 1024:,.0f} KB of HTML with no "
                "Content-Encoding header, despite the request advertising gzip and "
                "brotli support."
            ),
            impact=(
                "Text compression is typically a one-line server change that cuts "
                "HTML transfer size by roughly 70%. Leaving it off means every "
                "visitor downloads several times more than they need to."
            ),
            fix="Enable gzip or brotli for text/html, CSS, JS and JSON at the web server or CDN.",
            effort_hours=1.0,
            metrics={
                "html_kb": round(ctx.html_bytes / 1024),
                "estimated_saving_kb": round(saved / 1024),
            },
        )
    ]


@check
def render_blocking_scripts(ctx: ScanContext) -> list[Finding]:
    blocking = ctx.doc.render_blocking_scripts
    if len(blocking) < RENDER_BLOCK_WARN:
        return []
    return [
        Finding(
            code="PERF_RENDER_BLOCKING",
            title="Scripts block the page from rendering",
            category="performance",
            severity="high" if len(blocking) >= 3 else "medium",
            evidence=(
                f"{len(blocking)} external script(s) load in <head> without async or "
                f"defer, e.g. {_short_url(blocking[0].src)}."
            ),
            impact=(
                "The browser stops building the page until each of these downloads "
                "and executes. The visitor stares at a blank screen for the duration."
            ),
            fix="Add defer (or async where order does not matter) to non-critical head scripts.",
            effort_hours=2.0,
            metrics={"render_blocking_scripts": len(blocking)},
        )
    ]


@check
def missing_image_dimensions(ctx: ScanContext) -> list[Finding]:
    missing = ctx.doc.images_missing_dimensions
    if len(missing) < 3:
        return []
    return [
        Finding(
            code="PERF_IMG_NO_DIMENSIONS",
            title="Images have no width/height, so the layout jumps",
            category="performance",
            severity="medium",
            evidence=(
                f"{len(missing)} of {len(ctx.doc.images)} images declare no width and "
                "height attributes."
            ),
            impact=(
                "The browser cannot reserve space before an image loads, so content "
                "shifts under the cursor as the page settles. This is the classic "
                "cause of mis-taps on mobile and it is a scored Core Web Vital (CLS)."
            ),
            fix="Add explicit width and height (or a CSS aspect-ratio) to every <img>.",
            effort_hours=2.5,
            metrics={
                "images_without_dimensions": len(missing),
                "images_total": len(ctx.doc.images),
            },
        )
    ]


@check
def legacy_image_formats(ctx: ScanContext) -> list[Finding]:
    legacy = [
        i for i in ctx.doc.images if urlparse(i.src).path.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if len(legacy) < LEGACY_IMAGE_WARN:
        return []
    return [
        Finding(
            code="PERF_IMG_LEGACY_FORMAT",
            title="Images are served in dated formats",
            category="performance",
            severity="medium",
            evidence=f"{len(legacy)} images are served as JPEG or PNG rather than WebP or AVIF.",
            impact=(
                "WebP and AVIF typically deliver the same visual quality at a "
                "fraction of the bytes. This is usually the single largest "
                "available reduction in page weight."
            ),
            fix="Convert to WebP/AVIF with <picture> fallbacks, or enable CDN image optimisation.",
            effort_hours=3.0,
            metrics={"legacy_format_images": len(legacy)},
        )
    ]


@check
def no_lazy_loading(ctx: ScanContext) -> list[Finding]:
    images = ctx.doc.images
    if len(images) < 10:
        return []
    lazy = [i for i in images if i.lazy]
    if lazy:
        return []
    return [
        Finding(
            code="PERF_IMG_NO_LAZY",
            title="Every image loads immediately, including off-screen ones",
            category="performance",
            severity="medium",
            evidence=f"{len(images)} images on the page and none use loading=\"lazy\".",
            impact=(
                "Images far below the fold compete for bandwidth with the content "
                "the visitor is actually looking at."
            ),
            fix='Add loading="lazy" to below-the-fold images (leave hero images eager).',
            effort_hours=1.5,
            metrics={"images_total": len(images), "lazy_images": 0},
        )
    ]


@check
def redirect_chain(ctx: ScanContext) -> list[Finding]:
    hops = len(ctx.redirect_chain)
    if hops < 2:
        return []
    return [
        Finding(
            code="PERF_REDIRECT_CHAIN",
            title="Requests pass through a redirect chain",
            category="performance",
            severity="medium",
            evidence=(
                f"Loading {ctx.url} passes through {hops} redirects before reaching "
                f"{_short_url(ctx.final_url)}."
            ),
            impact=(
                "Each hop is a full round trip added to every first visit, and "
                "chained redirects dilute the ranking signal passed to the final URL."
            ),
            fix="Collapse the chain so the entry URL redirects once, directly to the final target.",
            effort_hours=1.5,
            metrics={"redirect_hops": hops},
        )
    ]


@check
def too_many_stylesheets(ctx: ScanContext) -> list[Finding]:
    count = len(ctx.doc.stylesheets)
    if count <= MANY_STYLESHEETS:
        return []
    return [
        Finding(
            code="PERF_MANY_CSS",
            title="Many separate stylesheets block rendering",
            category="performance",
            severity="medium",
            evidence=f"The page requests {count} separate CSS files, each render-blocking.",
            impact=(
                "CSS blocks rendering by design. Every extra file is another request "
                "the browser must finish before it can show anything."
            ),
            fix="Bundle and minify CSS; inline critical styles and load the rest asynchronously.",
            effort_hours=3.0,
            metrics={"stylesheet_count": count},
        )
    ]


@check
def no_cache_headers(ctx: ScanContext) -> list[Finding]:
    cache_control = ctx.header("cache-control")
    if cache_control or ctx.header("etag") or ctx.header("last-modified"):
        return []
    return [
        Finding(
            code="PERF_NO_CACHE_HEADERS",
            title="No caching or validation headers",
            category="performance",
            severity="medium",
            evidence=(
                "The homepage response carries no Cache-Control, ETag or "
                "Last-Modified header."
            ),
            impact=(
                "Browsers and CDNs have no way to revalidate cheaply, so returning "
                "visitors re-download content that has not changed."
            ),
            fix="Set Cache-Control with a sensible max-age and emit ETags for static responses.",
            effort_hours=2.0,
            confidence="medium",
            metrics={},
        )
    ]


# =============================================================================
# Security
# =============================================================================


@check
def no_https(ctx: ScanContext) -> list[Finding]:
    if ctx.is_https:
        return []
    return [
        Finding(
            code="SEC_NO_HTTPS",
            title="Site does not serve over HTTPS",
            category="security",
            severity="critical",
            evidence=f"The site resolved to {_short_url(ctx.final_url)} over plain HTTP.",
            impact=(
                "Every major browser labels plain HTTP pages 'Not secure' in the "
                "address bar, and does so most prominently on pages with a form. "
                "Visitors see that warning before they see the offer."
            ),
            fix="Install a TLS certificate (Let's Encrypt is free) and redirect all HTTP to HTTPS.",
            effort_hours=3.0,
            metrics={"scheme": "http"},
        )
    ]


@check
def http_not_redirected(ctx: ScanContext) -> list[Finding]:
    if ctx.http_redirects_to_https is not False:
        return []
    if not ctx.is_https:
        return []  # already reported by no_https
    return [
        Finding(
            code="SEC_HTTP_NO_REDIRECT",
            title="The insecure HTTP version stays reachable",
            category="security",
            severity="high",
            evidence=(
                f"http://{ctx.domain} served content without redirecting to HTTPS, "
                "even though an HTTPS version exists."
            ),
            impact=(
                "Traffic that lands on the HTTP address stays unencrypted and is "
                "open to interception on shared networks. It also splits SEO "
                "authority across two versions of the same site."
            ),
            fix="Add a permanent 301 redirect from all HTTP URLs to their HTTPS equivalents.",
            effort_hours=1.0,
            metrics={"http_redirects_to_https": 0},
        )
    ]


def _missing_header_finding(
    ctx: ScanContext,
    header: str,
    code: str,
    title: str,
    severity: str,
    impact: str,
    fix: str,
    hours: float,
) -> list[Finding]:
    if ctx.header(header):
        return []
    return [
        Finding(
            code=code,
            title=title,
            category="security",
            severity=severity,
            evidence=f"The response carries no {header} header.",
            impact=impact,
            fix=fix,
            effort_hours=hours,
            metrics={},
        )
    ]


@check
def no_hsts(ctx: ScanContext) -> list[Finding]:
    if not ctx.is_https:
        return []
    return _missing_header_finding(
        ctx,
        "Strict-Transport-Security",
        "SEC_NO_HSTS",
        "No HSTS header",
        "medium",
        "Without HSTS a visitor's first request each session can be downgraded to "
        "HTTP before the redirect fires, which is the window an attacker on the "
        "same network needs.",
        "Send Strict-Transport-Security: max-age=31536000; includeSubDomains.",
        0.5,
    )


@check
def no_csp(ctx: ScanContext) -> list[Finding]:
    return _missing_header_finding(
        ctx,
        "Content-Security-Policy",
        "SEC_NO_CSP",
        "No Content-Security-Policy",
        "medium",
        "A CSP is the main defence against cross-site scripting and against "
        "third-party scripts silently exfiltrating form data — which matters most "
        "on checkout and contact pages.",
        "Roll out a CSP in report-only mode first, then enforce once reports are clean.",
        6.0,
    )


@check
def no_content_type_options(ctx: ScanContext) -> list[Finding]:
    return _missing_header_finding(
        ctx,
        "X-Content-Type-Options",
        "SEC_NO_XCTO",
        "No X-Content-Type-Options header",
        "low",
        "Browsers may MIME-sniff responses and execute an uploaded file as script.",
        "Send X-Content-Type-Options: nosniff.",
        0.25,
    )


@check
def no_frame_protection(ctx: ScanContext) -> list[Finding]:
    csp = (ctx.header("content-security-policy") or "").lower()
    if ctx.header("x-frame-options") or "frame-ancestors" in csp:
        return []
    return [
        Finding(
            code="SEC_NO_FRAME_PROTECTION",
            title="Page can be embedded in a frame by anyone",
            category="security",
            severity="medium",
            evidence="No X-Frame-Options header and no CSP frame-ancestors directive.",
            impact=(
                "An attacker can load the site invisibly inside their own page and "
                "trick visitors into clicking its controls (clickjacking)."
            ),
            fix="Send X-Frame-Options: SAMEORIGIN, or a CSP frame-ancestors directive.",
            effort_hours=0.25,
            metrics={},
        )
    ]


@check
def no_referrer_policy(ctx: ScanContext) -> list[Finding]:
    return _missing_header_finding(
        ctx,
        "Referrer-Policy",
        "SEC_NO_REFERRER_POLICY",
        "No Referrer-Policy header",
        "low",
        "Full URLs — including any tokens or IDs in a query string — leak to every "
        "third-party resource the page loads.",
        "Send Referrer-Policy: strict-origin-when-cross-origin.",
        0.25,
    )


@check
def mixed_content(ctx: ScanContext) -> list[Finding]:
    insecure = ctx.doc.insecure_resources
    if not insecure:
        return []
    return [
        Finding(
            code="SEC_MIXED_CONTENT",
            title="Secure page loads insecure resources",
            category="security",
            severity="high",
            evidence=(
                f"{len(insecure)} resource(s) load over plain http:// on an HTTPS "
                f"page, e.g. {_short_url(insecure[0])}."
            ),
            impact=(
                "Browsers block or downgrade mixed content, so these resources may "
                "simply not appear — and the padlock is withdrawn regardless."
            ),
            fix="Serve every subresource over HTTPS, or proxy the ones you do not control.",
            effort_hours=2.0,
            metrics={"mixed_content_resources": len(insecure)},
        )
    ]


@check
def version_disclosure(ctx: ScanContext) -> list[Finding]:
    disclosed = []
    for header in ("Server", "X-Powered-By", "X-AspNet-Version", "X-Generator"):
        value = ctx.header(header)
        if value and any(ch.isdigit() for ch in value):
            disclosed.append(f"{header}: {value}")
    if not disclosed:
        return []
    return [
        Finding(
            code="SEC_VERSION_DISCLOSURE",
            title="Response headers disclose software versions",
            category="security",
            severity="low",
            evidence="Headers reveal exact versions — " + "; ".join(disclosed[:2]) + ".",
            impact=(
                "Version strings let an attacker skip reconnaissance and go straight "
                "to known exploits for that exact build."
            ),
            fix="Suppress or generalise version banners at the web server or reverse proxy.",
            effort_hours=0.5,
            metrics={"disclosing_headers": len(disclosed)},
        )
    ]


# =============================================================================
# SEO / discoverability
# =============================================================================


@check
def title_problems(ctx: ScanContext) -> list[Finding]:
    title = ctx.doc.title
    if not title:
        return [
            Finding(
                code="SEO_NO_TITLE",
                title="Homepage has no <title>",
                category="seo",
                severity="critical",
                evidence="The homepage does not declare a <title> element.",
                impact=(
                    "The title is the clickable headline in every search result and "
                    "the browser tab label. Without one, search engines invent one."
                ),
                fix="Write a 50–60 character title containing the primary service and location.",
                effort_hours=0.5,
                metrics={"title_length": 0},
            )
        ]
    n = len(title)
    if TITLE_MIN <= n <= TITLE_MAX:
        return []
    too_short = n < TITLE_MIN
    return [
        Finding(
            code="SEO_TITLE_LENGTH",
            title="Title tag is poorly sized for search results",
            category="seo",
            severity="medium",
            evidence=(
                f"The homepage title is {n} characters "
                f"(\"{_truncate(title, 70)}\"); the useful range is "
                f"{TITLE_MIN}–{TITLE_MAX}."
            ),
            impact=(
                "Titles beyond roughly 60 characters are truncated in results, and "
                "very short ones waste the most valuable text on the page."
            ),
            fix=f"Rewrite to {TITLE_MIN}–{TITLE_MAX} characters, front-loading the main keyword.",
            effort_hours=0.5,
            metrics={"title_length": n, "title_min": TITLE_MIN, "title_max": TITLE_MAX},
        )
        if not too_short
        else Finding(
            code="SEO_TITLE_LENGTH",
            title="Title tag is too short to work hard",
            category="seo",
            severity="medium",
            evidence=(
                f"The homepage title is only {n} characters (\"{_truncate(title, 70)}\")."
            ),
            impact="A short title leaves the strongest ranking and click-through field mostly empty.",
            fix=f"Expand to {TITLE_MIN}–{TITLE_MAX} characters with the service and location.",
            effort_hours=0.5,
            metrics={"title_length": n, "title_min": TITLE_MIN, "title_max": TITLE_MAX},
        )
    ]


@check
def description_problems(ctx: ScanContext) -> list[Finding]:
    desc = ctx.doc.meta_description
    if not desc:
        return [
            Finding(
                code="SEO_NO_DESCRIPTION",
                title="No meta description",
                category="seo",
                severity="high",
                evidence="The homepage declares no meta description.",
                impact=(
                    "Google falls back to scraping arbitrary page text for the "
                    "snippet under the search result. That snippet is the sales "
                    "pitch, and right now nobody is writing it."
                ),
                fix=f"Write a {DESC_MIN}–{DESC_MAX} character description with a clear call to action.",
                effort_hours=0.5,
                metrics={"description_length": 0},
            )
        ]
    n = len(desc)
    if DESC_MIN <= n <= DESC_MAX:
        return []
    return [
        Finding(
            code="SEO_DESCRIPTION_LENGTH",
            title="Meta description is outside the displayed range",
            category="seo",
            severity="low",
            evidence=f"The meta description is {n} characters; search results display roughly {DESC_MIN}–{DESC_MAX}.",
            impact="Text beyond the limit is cut mid-sentence; well short of it wastes the space.",
            fix=f"Rewrite to {DESC_MIN}–{DESC_MAX} characters.",
            effort_hours=0.5,
            metrics={"description_length": n, "description_min": DESC_MIN, "description_max": DESC_MAX},
        )
    ]


@check
def h1_problems(ctx: ScanContext) -> list[Finding]:
    count = len(ctx.doc.h1s)
    if count == 1:
        return []
    if count == 0:
        return [
            Finding(
                code="SEO_NO_H1",
                title="Homepage has no H1 heading",
                category="seo",
                severity="medium",
                evidence="No <h1> element was found on the homepage.",
                impact=(
                    "The H1 tells both search engines and screen readers what the "
                    "page is about. Without one, neither has a primary signal."
                ),
                fix="Add exactly one H1 stating the main offer.",
                effort_hours=0.5,
                metrics={"h1_count": 0},
            )
        ]
    return [
        Finding(
            code="SEO_MULTIPLE_H1",
            title="Multiple H1 headings compete",
            category="seo",
            severity="low",
            evidence=f"The homepage declares {count} separate <h1> elements.",
            impact="Several competing top-level headings dilute the page's main topic signal.",
            fix="Keep one H1 and demote the rest to H2.",
            effort_hours=0.5,
            metrics={"h1_count": count},
        )
    ]


@check
def noindex_set(ctx: ScanContext) -> list[Finding]:
    sources = []
    if ctx.doc.meta_robots and "noindex" in ctx.doc.meta_robots.lower():
        sources.append(f'meta robots "{ctx.doc.meta_robots}"')
    header = ctx.header("x-robots-tag")
    if header and "noindex" in header.lower():
        sources.append(f'X-Robots-Tag "{header}"')
    if not sources:
        return []
    return [
        Finding(
            code="SEO_NOINDEX",
            title="Homepage tells search engines not to index it",
            category="seo",
            severity="critical",
            evidence="The homepage carries a noindex directive via " + " and ".join(sources) + ".",
            impact=(
                "This instructs Google to remove the page from search entirely. It "
                "is almost always a staging setting that shipped to production by "
                "accident — and it makes the site invisible to organic search."
            ),
            fix="Remove the noindex directive and request re-indexing in Search Console.",
            effort_hours=0.5,
            metrics={"noindex_sources": len(sources)},
        )
    ]


@check
def no_canonical(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.canonical:
        return []
    return [
        Finding(
            code="SEO_NO_CANONICAL",
            title="No canonical URL declared",
            category="seo",
            severity="low",
            evidence="The homepage declares no rel=canonical link.",
            impact=(
                "Without a canonical, the same page reachable at several URLs "
                "(with/without www, with tracking parameters) splits its ranking "
                "authority across duplicates."
            ),
            fix="Add a self-referencing rel=canonical to every page.",
            effort_hours=1.0,
            metrics={},
        )
    ]


@check
def no_robots_txt(ctx: ScanContext) -> list[Finding]:
    if ctx.robots_present:
        return []
    return [
        Finding(
            code="SEO_NO_ROBOTS_TXT",
            title="No robots.txt",
            category="seo",
            severity="low",
            evidence=(
                f"/robots.txt returned {ctx.robots_status if ctx.robots_status else 'no response'}."
            ),
            impact=(
                "Crawlers get no guidance on what to skip, and there is nowhere to "
                "advertise the sitemap."
            ),
            fix="Publish a robots.txt that allows crawling and lists the sitemap URL.",
            effort_hours=0.5,
            metrics={},
        )
    ]


@check
def no_sitemap(ctx: ScanContext) -> list[Finding]:
    if ctx.sitemap_present:
        return []
    return [
        Finding(
            code="SEO_NO_SITEMAP",
            title="No XML sitemap found",
            category="seo",
            severity="medium",
            evidence="No sitemap was found at /sitemap.xml or referenced in robots.txt.",
            impact=(
                "Search engines have to discover every page by following links. "
                "Pages that are not well linked internally may never be crawled."
            ),
            fix="Generate an XML sitemap, reference it from robots.txt, submit it in Search Console.",
            effort_hours=1.5,
            metrics={},
        )
    ]


@check
def no_open_graph(ctx: ScanContext) -> list[Finding]:
    og = ctx.doc.og
    if og.get("og:title") and og.get("og:image"):
        return []
    missing = [t for t in ("og:title", "og:description", "og:image") if not og.get(t)]
    return [
        Finding(
            code="SEO_NO_OPEN_GRAPH",
            title="Links shared on social media render as bare URLs",
            category="seo",
            severity="medium",
            evidence=f"Missing Open Graph tags: {', '.join(missing)}.",
            impact=(
                "Whenever anyone shares the site in a message, a post, or a Slack "
                "channel, it appears as a naked link with no image or headline. "
                "This is word-of-mouth traffic actively being suppressed."
            ),
            fix="Add og:title, og:description and a 1200×630 og:image to every page.",
            effort_hours=2.0,
            metrics={"missing_og_tags": len(missing)},
        )
    ]


@check
def no_structured_data(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.jsonld_types:
        return []
    return [
        Finding(
            code="SEO_NO_STRUCTURED_DATA",
            title="No structured data",
            category="seo",
            severity="medium",
            evidence="No JSON-LD structured data was found on the homepage.",
            impact=(
                "Structured data is what produces star ratings, opening hours, "
                "prices and FAQ expanders in search results. Without it the listing "
                "is a plain blue link next to competitors with rich ones."
            ),
            fix="Add JSON-LD (Organization or LocalBusiness, plus Product/FAQ where they apply).",
            effort_hours=3.0,
            metrics={},
        )
    ]


@check
def images_missing_alt(ctx: ScanContext) -> list[Finding]:
    missing = ctx.doc.images_missing_alt
    total = len(ctx.doc.images)
    if total == 0 or len(missing) < 3:
        return []
    pct = len(missing) / total * 100
    return [
        Finding(
            code="SEO_IMG_NO_ALT",
            title="Images have no alt text",
            category="seo",
            severity="medium",
            evidence=f"{len(missing)} of {total} images ({pct:.0f}%) have missing or empty alt text.",
            impact=(
                "Screen readers announce nothing for these images, which is both an "
                "accessibility gap with legal exposure and a lost ranking signal."
            ),
            fix="Write descriptive alt text for meaningful images; use alt=\"\" for decorative ones.",
            effort_hours=2.0,
            metrics={
                "images_missing_alt": len(missing),
                "images_total": total,
                "images_missing_alt_pct": round(pct),
            },
        )
    ]


@check
def thin_content(ctx: ScanContext) -> list[Finding]:
    words = ctx.doc.word_count
    if words >= THIN_CONTENT_WORDS:
        return []
    return [
        Finding(
            code="SEO_THIN_CONTENT",
            title="Homepage has very little text",
            category="seo",
            severity="medium",
            evidence=f"The homepage contains roughly {words} words of body text.",
            impact=(
                "There is almost nothing for search engines to match a query "
                "against, and little for a visitor to read before deciding."
            ),
            fix="Expand with the services offered, the areas served, and proof (reviews, case studies).",
            effort_hours=4.0,
            confidence="medium",
            metrics={"word_count": words, "word_count_target": THIN_CONTENT_WORDS},
        )
    ]


@check
def no_lang_attribute(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.lang:
        return []
    return [
        Finding(
            code="SEO_NO_LANG",
            title="No language declared on <html>",
            category="seo",
            severity="low",
            evidence="The <html> element has no lang attribute.",
            impact="Screen readers may use the wrong pronunciation, and translation tools guess.",
            fix='Add lang="en" (or the correct language) to the <html> element.',
            effort_hours=0.25,
            metrics={},
        )
    ]


# =============================================================================
# Mobile
# =============================================================================


@check
def no_viewport(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.viewport:
        return []
    return [
        Finding(
            code="MOB_NO_VIEWPORT",
            title="Site is not mobile-responsive",
            category="mobile",
            severity="critical",
            evidence="The homepage declares no viewport meta tag.",
            impact=(
                "Phones render the desktop layout zoomed out, so text is unreadable "
                "and buttons are unhittable without pinch-zooming. Mobile is the "
                "majority of traffic for most local businesses, and Google indexes "
                "the mobile version first."
            ),
            fix='Add <meta name="viewport" content="width=device-width, initial-scale=1"> and responsive CSS.',
            effort_hours=12.0,
            metrics={},
        )
    ]


@check
def viewport_blocks_zoom(ctx: ScanContext) -> list[Finding]:
    viewport = (ctx.doc.viewport or "").lower().replace(" ", "")
    if not viewport:
        return []
    blocks = "user-scalable=no" in viewport or "maximum-scale=1" in viewport
    if not blocks:
        return []
    return [
        Finding(
            code="MOB_VIEWPORT_NO_ZOOM",
            title="Pinch-to-zoom is disabled",
            category="mobile",
            severity="low",
            evidence=f'The viewport is set to "{ctx.doc.viewport}", which prevents zooming.',
            impact=(
                "Visitors who need larger text cannot get it. This is a recognised "
                "accessibility failure under WCAG."
            ),
            fix="Remove user-scalable=no and maximum-scale from the viewport tag.",
            effort_hours=0.25,
            metrics={},
        )
    ]


# =============================================================================
# Conversion
# =============================================================================


@check
def no_analytics(ctx: ScanContext) -> list[Finding]:
    if ctx.analytics:
        return []
    return [
        Finding(
            code="CONV_NO_ANALYTICS",
            title="No analytics or conversion tracking detected",
            category="conversion",
            severity="high",
            evidence="No analytics or attribution script was detected on the homepage.",
            impact=(
                "There is no way to know how many visitors arrive, where they come "
                "from, or where they give up. Every marketing decision is being made "
                "without data, and no improvement can be proven after the fact."
            ),
            fix="Install a privacy-friendly analytics tool and define the key conversion events.",
            effort_hours=3.0,
            confidence="medium",
            metrics={"analytics_tools_found": 0},
        )
    ]


@check
def no_phone_number(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.phones:
        return []
    return [
        Finding(
            code="CONV_NO_PHONE",
            title="No phone number on the homepage",
            category="conversion",
            severity="medium",
            evidence="No phone number was found in the homepage text.",
            impact=(
                "For service businesses the phone call is usually the highest-intent "
                "conversion available. A visitor ready to call has to go hunting."
            ),
            fix="Put a click-to-call number in the header, visible without scrolling.",
            effort_hours=1.0,
            confidence="medium",
            metrics={},
        )
    ]


@check
def no_contact_route(ctx: ScanContext) -> list[Finding]:
    has_form = any(f.looks_like_lead_capture for f in ctx.doc.forms)
    if has_form or ctx.doc.emails or ctx.doc.has_contact_path:
        return []
    return [
        Finding(
            code="CONV_NO_CONTACT_ROUTE",
            title="No obvious way to get in touch",
            category="conversion",
            severity="high",
            evidence=(
                "No contact form, no email address and no link to a contact page "
                "was found on the homepage."
            ),
            impact=(
                "A visitor who wants to buy has no route to say so. Traffic that "
                "cannot convert is traffic paid for and thrown away."
            ),
            fix="Add a short contact form and a visible email address above the fold.",
            effort_hours=3.0,
            metrics={"forms_found": len(ctx.doc.forms)},
        )
    ]


@check
def no_form_at_all(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.forms:
        return []
    return [
        Finding(
            code="CONV_NO_FORM",
            title="No form anywhere on the homepage",
            category="conversion",
            severity="medium",
            evidence="The homepage contains no <form> element of any kind.",
            impact=(
                "There is no way to capture a lead from a visitor who is interested "
                "but not ready to phone — which is most of them."
            ),
            fix="Add a two-field enquiry form (name + email) or a newsletter capture.",
            effort_hours=2.0,
            confidence="medium",
            metrics={"forms_found": 0},
        )
    ]


# =============================================================================
# Trust
# =============================================================================


@check
def broken_links(ctx: ScanContext) -> list[Finding]:
    if not ctx.broken_links:
        return []
    count = len(ctx.broken_links)
    first_url, first_status = ctx.broken_links[0]
    return [
        Finding(
            code="TRUST_BROKEN_LINKS",
            title="Homepage links lead to dead pages",
            category="trust",
            severity="high" if count >= 3 else "medium",
            evidence=(
                f"{count} of {ctx.links_checked} internal links checked returned an "
                f"error, e.g. {_short_url(first_url)} returned "
                f"{first_status if first_status else 'no response'}."
            ),
            impact=(
                "Dead links read as neglect to a visitor deciding whether to trust "
                "the business with money, and they waste crawl budget."
            ),
            fix="Fix or remove the broken targets and add a link check to the deploy pipeline.",
            effort_hours=2.0,
            metrics={"broken_links": count, "links_checked": ctx.links_checked},
        )
    ]


@check
def soft_404(ctx: ScanContext) -> list[Finding]:
    if ctx.soft_404 is not True:
        return []
    return [
        Finding(
            code="TRUST_SOFT_404",
            title="Missing pages return HTTP 200 instead of 404",
            category="trust",
            severity="medium",
            evidence="A request for a URL that does not exist returned HTTP 200 rather than 404.",
            impact=(
                "Search engines index unlimited non-existent URLs as real pages, "
                "diluting the site and wasting crawl budget."
            ),
            fix="Return a real 404 status for unknown URLs, with a helpful error page.",
            effort_hours=1.5,
            metrics={},
        )
    ]


@check
def no_favicon(ctx: ScanContext) -> list[Finding]:
    if ctx.doc.has_favicon:
        return []
    return [
        Finding(
            code="TRUST_NO_FAVICON",
            title="No favicon",
            category="trust",
            severity="low",
            evidence="No favicon or touch icon link was declared.",
            impact=(
                "The site shows a blank placeholder in tabs and bookmarks — a small "
                "but constant signal of an unfinished site."
            ),
            fix="Add a favicon and an apple-touch-icon.",
            effort_hours=0.5,
            metrics={},
        )
    ]


# -- helpers -----------------------------------------------------------------


def _short_url(url: str | None, limit: int = 60) -> str:
    if not url:
        return "(none)"
    return url if len(url) <= limit else url[: limit - 1] + "…"


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
