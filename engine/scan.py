"""Orchestrates one full site audit.

A scan is deliberately shallow — homepage, robots.txt, sitemap, a 404 probe and
a sample of internal links. Depth is not what sells. One measured, undeniable
number on the page a prospect looks at every day does more than a crawl of
10,000 URLs, and it finishes in seconds so you can do several hundred of them.
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

from .checks import Finding, ScanContext, run_all
from .fetch import Fetcher, detect_cdn, domain_of, normalize_url
from .htmlparse import detect_analytics, parse

# A path that should not exist. If this returns 200, the site soft-404s.
SOFT_404_PROBE = "/millions-audit-probe-404-check"
DEFAULT_LINK_SAMPLE = 8


@dataclass
class AuditResult:
    """Everything one scan learned. JSON-serialisable for storage."""

    url: str
    domain: str
    scanned_at: str
    ok: bool
    final_url: str = ""
    status: int | None = None
    error: str | None = None

    title: str | None = None
    ttfb_ms: float | None = None
    total_ms: float | None = None
    html_kb: float | None = None
    word_count: int = 0
    analytics: list[str] = field(default_factory=list)
    cdn: str | None = None
    sitemap_urls: int = 0
    internal_link_count: int = 0
    images_total: int = 0
    links_checked: int = 0
    broken_links: int = 0
    scan_duration_s: float = 0.0

    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -- convenience views -------------------------------------------------

    def by_severity(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    def by_category(self, category: str) -> list[Finding]:
        return [f for f in self.findings if f.category == category]

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            if finding.severity in counts:
                counts[finding.severity] += 1
        return counts

    @property
    def severe_count(self) -> int:
        """Critical + high. The number you quote when you say "serious issues"."""
        counts = self.severity_counts
        return counts["critical"] + counts["high"]

    @property
    def total_effort_hours(self) -> float:
        return round(sum(f.effort_hours for f in self.findings), 1)

    @property
    def all_metrics(self) -> dict[str, float | int | str]:
        """Every measurement recorded, flattened. The grounding source of truth."""
        merged: dict[str, float | int | str] = {}
        for finding in self.findings:
            merged.update(finding.metrics)
        for key, value in (
            ("ttfb_ms", round(self.ttfb_ms) if self.ttfb_ms else None),
            ("total_load_s", round(self.total_ms / 1000, 1) if self.total_ms else None),
            ("html_kb", round(self.html_kb) if self.html_kb else None),
            ("word_count", self.word_count),
            ("images_total", self.images_total),
            ("links_checked", self.links_checked),
            ("sitemap_urls", self.sitemap_urls),
            ("internal_links", self.internal_link_count),
            ("broken_links", self.broken_links),
            ("findings_total", len(self.findings)),
            ("severe_count", self.severe_count),
            ("total_effort_hours", self.total_effort_hours),
        ):
            if value is not None:
                merged[key] = value
        merged.update({f"count_{k}": v for k, v in self.severity_counts.items()})
        return merged

    def to_dict(self) -> dict:
        data = asdict(self)
        data["findings"] = [asdict(f) for f in self.findings]
        data["severity_counts"] = self.severity_counts
        data["total_effort_hours"] = self.total_effort_hours
        return data

    @classmethod
    def from_dict(cls, data: dict) -> AuditResult:
        data = dict(data)
        data.pop("severity_counts", None)
        data.pop("total_effort_hours", None)
        raw_findings = data.pop("findings", [])
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        result = cls(**{k: v for k, v in data.items() if k in known})
        result.findings = [Finding(**f) for f in raw_findings]
        return result


def scan(
    raw_url: str,
    fetcher: Fetcher | None = None,
    link_sample: int = DEFAULT_LINK_SAMPLE,
    check_links: bool = True,
) -> AuditResult:
    """Audit one site. Never raises — a failed scan comes back as a result."""
    started = time.monotonic()
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        url = normalize_url(raw_url)
    except ValueError as exc:
        return AuditResult(
            url=raw_url, domain=raw_url, scanned_at=now, ok=False, error=str(exc)
        )

    result = AuditResult(url=url, domain=domain_of(url), scanned_at=now, ok=False)

    try:
        robots = fetcher.robots_for(url)
        home = fetcher.get(url)

        if not home.ok:
            result.error = home.error or f"HTTP {home.status}"
            result.status = home.status
            result.final_url = home.final_url or url
            if home.blocked_by_robots:
                result.notes.append("Skipped: robots.txt disallows automated fetching.")
            return result

        doc = parse(home.text, home.final_url or url)
        analytics = detect_analytics(doc)

        sitemap_present, sitemap_urls = _probe_sitemap(fetcher, url, robots.sitemaps)
        http_to_https = _probe_http_redirect(fetcher, result.domain) if home.final_url.startswith("https://") else None
        soft_404 = _probe_soft_404(fetcher, url)
        broken, checked = (
            _check_links(fetcher, doc.internal_links, link_sample) if check_links else ([], 0)
        )

        ctx = ScanContext(
            url=url,
            final_url=home.final_url or url,
            domain=result.domain,
            status=home.status,
            headers=home.headers,
            html_bytes=home.bytes_len,
            ttfb_ms=home.ttfb_ms,
            total_ms=home.total_ms,
            redirect_chain=home.redirect_chain,
            doc=doc,
            analytics=analytics,
            robots_present=robots.present,
            robots_status=robots.status,
            sitemap_present=sitemap_present,
            sitemap_urls=sitemap_urls,
            http_redirects_to_https=http_to_https,
            soft_404=soft_404,
            broken_links=broken,
            links_checked=checked,
        )

        result.ok = True
        result.status = home.status
        result.final_url = home.final_url or url
        result.title = doc.title
        result.ttfb_ms = home.ttfb_ms
        result.total_ms = home.total_ms
        result.html_kb = round(home.bytes_len / 1024, 1)
        result.word_count = doc.word_count
        result.analytics = analytics
        result.cdn = detect_cdn(home.headers)
        result.sitemap_urls = sitemap_urls
        result.internal_link_count = len(doc.internal_links)
        result.images_total = len(doc.images)
        result.links_checked = checked
        result.broken_links = len(broken)
        result.findings = run_all(ctx)

        if home.truncated:
            result.notes.append("HTML was truncated at the size cap; byte counts are a floor.")

    except Exception as exc:  # a batch of 200 must survive one pathological host
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        result.scan_duration_s = round(time.monotonic() - started, 1)
        if own_fetcher:
            fetcher.close()

    return result


def scan_many(
    urls: list[str],
    fetcher: Fetcher | None = None,
    link_sample: int = DEFAULT_LINK_SAMPLE,
    on_result=None,
) -> list[AuditResult]:
    """Scan a list of sites sequentially, sharing one rate-limited fetcher."""
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    results: list[AuditResult] = []
    try:
        for raw in urls:
            result = scan(raw, fetcher=fetcher, link_sample=link_sample)
            results.append(result)
            if on_result:
                on_result(result)
    finally:
        if own_fetcher:
            fetcher.close()
    return results


# -- probes ------------------------------------------------------------------


def _probe_sitemap(fetcher: Fetcher, url: str, declared: list[str]) -> tuple[bool, int]:
    candidates = list(declared) + [urljoin(url, "/sitemap.xml"), urljoin(url, "/sitemap_index.xml")]
    for candidate in candidates[:3]:
        result = fetcher.get(candidate)
        if result.ok and ("<urlset" in result.text or "<sitemapindex" in result.text):
            return True, result.text.count("<loc>")
    return False, 0


def _probe_http_redirect(fetcher: Fetcher, domain: str) -> bool | None:
    """Does the plain-HTTP address redirect to HTTPS? None if we couldn't tell."""
    result = fetcher.get(f"http://{domain}/", allow_redirects=True)
    if result.error or result.status is None:
        return None
    return result.final_url.startswith("https://")


def _probe_soft_404(fetcher: Fetcher, url: str) -> bool | None:
    result = fetcher.get(urljoin(url, SOFT_404_PROBE))
    if result.error or result.status is None:
        return None
    return result.status == 200


def _check_links(
    fetcher: Fetcher, links: list[str], sample: int
) -> tuple[list[tuple[str, int | None]], int]:
    """Status-check a random sample of internal links.

    Random rather than first-N: the first links on a page are almost always the
    nav, which is the least likely thing to be broken. Sampling the body finds
    the rot.
    """
    if not links or sample <= 0:
        return [], 0
    chosen = links if len(links) <= sample else random.sample(links, sample)
    broken: list[tuple[str, int | None]] = []
    for link in chosen:
        status = fetcher.head_status(link)
        if status is None or status >= 400:
            broken.append((link, status))
    return broken, len(chosen)
