"""End-to-end tests for the CiteLocal audit engine.

Runs the real audit pipeline — real HTTP, real parsing, real scoring — against
locally served fixture sites, so the checks are exercised the way they will be
in production rather than through mocks.

    python3 tests/test_audit.py
"""
from __future__ import annotations

import http.server
import os
import socket
import sys
import threading
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from citelocal.audit import audit, blocking_issue  # noqa: E402
from citelocal.checks import content, crawler_access, presence, schema  # noqa: E402
from citelocal.html_utils import parse  # noqa: E402
from citelocal.models import Business, Status  # noqa: E402
from citelocal.robots import RobotsFile  # noqa: E402
from citelocal.vocab import schema_type_for  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

_failures: list[str] = []
_passes = 0


def check(condition: bool, label: str) -> None:
    global _passes
    if condition:
        _passes += 1
        print(f"  ok   {label}")
    else:
        _failures.append(label)
        print(f"  FAIL {label}")


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence per-request logging
        pass


def serve(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Serve `directory` on a free localhost port; returns (server, base_url)."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    handler = partial(_QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{port}"


def get_check(result, check_id: str):
    matches = [c for c in result.checks if c.id == check_id]
    if not matches:
        raise AssertionError(f"check {check_id} missing from result")
    return matches[0]


# ---------------------------------------------------------------------------
def test_robots_parsing() -> None:
    print("\nrobots.txt parsing")

    robots = RobotsFile(
        "User-agent: GPTBot\nDisallow: /\n\n"
        "User-agent: *\nAllow: /\nDisallow: /admin/\n\n"
        "Sitemap: https://example.com/sitemap.xml\n"
    )
    check(not robots.check("GPTBot").allowed, "named bot blocked by its own group")
    check(robots.check("PerplexityBot").allowed, "unnamed bot falls through to '*'")
    check(not robots.check("PerplexityBot", "/admin/page").allowed, "'*' Disallow honoured")
    check(robots.sitemaps == ["https://example.com/sitemap.xml"], "sitemap captured")

    # Stacked agents share one rule block.
    stacked = RobotsFile("User-agent: A\nUser-agent: B\nDisallow: /\n")
    check(
        not stacked.check("A").allowed and not stacked.check("B").allowed,
        "stacked user-agents share rules",
    )

    # A User-agent line after rules starts a new group.
    split = RobotsFile("User-agent: A\nDisallow: /\nUser-agent: B\nAllow: /\n")
    check(
        not split.check("A").allowed and split.check("B").allowed,
        "user-agent after rules opens a new group",
    )

    # Empty Disallow means allow everything.
    empty = RobotsFile("User-agent: *\nDisallow:\n")
    check(empty.check("GPTBot").allowed, "empty Disallow permits crawling")

    # Longest-prefix match, Allow wins ties.
    longest = RobotsFile("User-agent: *\nDisallow: /blog/\nAllow: /blog/public/\n")
    check(not longest.check("X", "/blog/private").allowed, "longer Disallow applies")
    check(longest.check("X", "/blog/public/post").allowed, "more specific Allow wins")

    # Missing robots.txt is permissive.
    check(RobotsFile("", missing=True).check("GPTBot").allowed, "missing robots.txt allows all")

    # Case-insensitive agent matching, and suffix tolerance.
    case = RobotsFile("User-agent: gptbot\nDisallow: /\n")
    check(not case.check("GPTBot").allowed, "agent match is case-insensitive")
    check(not case.check("GPTBot/1.2").allowed, "versioned agent token still matches")

    # A decision reports the rule that caused it.
    decision = robots.check("GPTBot")
    check("Disallow" in decision.reason and "line" in decision.reason, "decision explains itself")


def test_vocab() -> None:
    print("\ncategory to schema.org type")
    cases = {
        "plumber": "Plumber",
        "emergency plumber": "Plumber",
        "HVAC contractor": "HVACBusiness",
        "dental practice": "Dentist",
        "med spa": "DaySpa",
        "auto repair shop": "AutoRepair",
        "family law attorney": "Attorney",
        "": "LocalBusiness",
        "artisanal widget whittler": "LocalBusiness",
    }
    for category, expected in cases.items():
        actual = schema_type_for(category)
        check(actual == expected, f"{category or '(empty)'!r} -> {expected} (got {actual})")


def test_invisible_site() -> None:
    print("\nfixture: invisible site (blocks AI crawlers, no schema, thin content)")
    server, base = serve(FIXTURES / "invisible")
    try:
        result = audit(
            Business(
                name="Summit Plumbing",
                website=base,
                city="Denver",
                region="CO",
                category="plumber",
            ),
            run_probe=False,
        )

        crawler = get_check(result, crawler_access.CHECK_ID)
        check(crawler.status is Status.FAIL, "crawler access fails")
        blocked = crawler.evidence["blocked_retrieval"]
        check("OAI-SearchBot" in blocked, "OAI-SearchBot detected as blocked")
        check("PerplexityBot" in blocked, "PerplexityBot detected as blocked")
        check("Googlebot" not in blocked, "Googlebot correctly not reported blocked")
        check(blocking_issue(result) is not None, "blocking issue surfaced")

        structured = get_check(result, schema.CHECK_ID)
        check(structured.status is Status.FAIL, "structured data fails")
        check(
            any("Plumber" in (f.snippet or "") for f in structured.fixes),
            "generated snippet uses the Plumber type",
        )

        readiness = get_check(result, content.CHECK_ID)
        check(readiness.status is Status.FAIL, "answer readiness fails")
        check(
            len(readiness.evidence["vague_phrases"]) >= 3,
            f"marketing filler detected ({len(readiness.evidence['vague_phrases'])} phrases)",
        )
        check(
            not readiness.evidence["has_phone_in_text"],
            "phone-in-image case detected (no number in text)",
        )

        citations = get_check(result, presence.CHECK_ID)
        check(citations.status is Status.FAIL, "citation sources fails")

        check(result.score < 35, f"overall score is low ({result.score})")
        check(result.grade == "F", f"grade is F (got {result.grade})")
        check(len(result.action_plan) >= 6, "action plan has substance")
        check(
            result.action_plan[0].impact >= 0.9,
            "highest-impact fix is ranked first",
        )
    finally:
        server.shutdown()


def test_optimized_site() -> None:
    print("\nfixture: optimized site (allows retrieval bots, full schema, rich content)")
    server, base = serve(FIXTURES / "optimized")
    try:
        result = audit(
            Business(
                name="Precision Plumbing",
                website=base,
                city="Austin",
                region="TX",
                category="plumber",
                phone="(512) 555-0142",
            ),
            run_probe=False,
        )

        crawler = get_check(result, crawler_access.CHECK_ID)
        check(crawler.status is Status.PASS, "crawler access passes")
        check(crawler.evidence["blocked_retrieval"] == [], "no retrieval bot blocked")
        check(bool(crawler.evidence["sitemaps"]), "sitemap detected")
        check(blocking_issue(result) is None, "no blocking issue")

        structured = get_check(result, schema.CHECK_ID)
        check(structured.status is Status.PASS, "structured data passes")
        check(structured.evidence["has_faq"], "FAQPage detected")
        check("Plumber" in structured.evidence["types_found"], "specific type detected")
        check(structured.score > 0.85, f"structured data scores high ({structured.score:.2f})")

        readiness = get_check(result, content.CHECK_ID)
        check(readiness.status is Status.PASS, "answer readiness passes")
        check(
            len(readiness.evidence["question_headings"]) >= 4,
            "question headings detected",
        )
        check(readiness.evidence["has_phone_in_text"], "phone found in text")
        check(len(readiness.evidence["service_pages"]) >= 3, "service pages detected")

        citations = get_check(result, presence.CHECK_ID)
        check(citations.status is Status.PASS, "citation sources passes")
        found = citations.evidence["profiles_found"]
        check("Google Business Profile" in found, "GBP link detected")
        check("Yelp" in found, "Yelp link detected")
        check("Better Business Bureau" in found, "BBB link detected")
        check("Nextdoor" in found, "Nextdoor link detected")

        check(result.score >= 85, f"overall score is high ({result.score})")
        check(result.grade in ("A", "B"), f"grade is A or B (got {result.grade})")
    finally:
        server.shutdown()


def test_partial_site() -> None:
    print("\nfixture: partial site (Organization only, string address, phone mismatch)")
    server, base = serve(FIXTURES / "partial")
    try:
        result = audit(
            Business(
                name="Lakeside Dental Care",
                website=base,
                city="Seattle",
                region="WA",
                category="dental practice",
            ),
            run_probe=False,
        )

        structured = get_check(result, schema.CHECK_ID)
        check(structured.status is Status.FAIL, "Organization-only markup fails local check")
        check(
            any("Organization" in f for f in structured.findings),
            "Organization-only case explained",
        )
        check(not structured.evidence["has_faq"], "missing FAQ detected")
        check(structured.evidence["desired_type"] == "Dentist", "Dentist type recommended")
        check(
            any("trailing comma" in f for f in structured.findings),
            "invalid JSON-LD syntax reported",
        )

        citations = get_check(result, presence.CHECK_ID)
        check(
            any("mismatch" in f.lower() for f in citations.findings),
            "phone mismatch between schema and text detected",
        )

        # robots.txt is absent here, which is permissive rather than broken.
        crawler = get_check(result, crawler_access.CHECK_ID)
        check(crawler.status is Status.PASS, "absent robots.txt treated as permissive")
        check(
            any("404" in f for f in crawler.findings),
            "missing robots.txt reported as 404",
        )

        check(30 <= result.score <= 75, f"score lands mid-range ({result.score})")
    finally:
        server.shutdown()


def test_unreachable_site() -> None:
    print("\nunreachable site must not score well")
    # Bind and immediately release a port so nothing is listening on it.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]

    result = audit(
        Business(name="Ghost Co", website=f"http://127.0.0.1:{dead_port}", category="plumber"),
        run_probe=False,
    )
    check(not result.reachable, "site_error recorded")
    check(result.score == 0, f"score is 0, not 100 (got {result.score})")
    check("could not" in result.verdict.lower(), "verdict explains the failure")
    check(
        all(c.status is Status.SKIP for c in result.checks),
        "all checks skip rather than pass",
    )


def test_html_report_renders() -> None:
    print("\nHTML report rendering")
    from citelocal.report import render
    from citelocal.report_html import render_html

    server, base = serve(FIXTURES / "invisible")
    try:
        result = audit(
            Business(
                name="Summit Plumbing", website=base, city="Denver",
                region="CO", category="plumber",
            ),
            run_probe=False,
        )
        html = render_html(result, brand="Northstar Digital")
        check(html.startswith("<!DOCTYPE html>"), "HTML report has a doctype")
        check("Northstar Digital" in html, "brand name applied (white-label)")
        check("Summit Plumbing" in html, "business name present")
        check("Blocking issue" in html, "blocking issue rendered")
        check("prefers-color-scheme" in html, "dark mode supported")
        check("@media print" in html, "print stylesheet present")
        check("&lt;script" in html, "snippet HTML is escaped, not injected")
        check(html.count("</div>") >= 10, "report has structure")

        text = render(result, show_snippets=True)
        check("CITELOCAL" in text, "terminal report renders")
        check("ACTION PLAN" in text, "terminal action plan renders")

        # Prose must wrap. Snippets are excluded: breaking a line of JSON-LD to
        # fit a terminal would corrupt the thing the client is meant to paste.
        prose = render(result, show_snippets=False)
        overlong = [line for line in prose.splitlines() if len(line) > 80]
        if overlong:
            print(f"       longest: {len(overlong[0])} chars: {overlong[0][:90]}")
        check(not overlong, f"prose lines wrap to 80 columns ({len(overlong)} over)")
    finally:
        server.shutdown()


def test_snippet_validity() -> None:
    print("\ngenerated snippets are valid")
    import json
    import re

    business = Business(
        name="Acme Plumbing", website="https://acme.example", city="Austin",
        region="TX", category="plumber", phone="(512) 555-0100",
    )

    for label, builder in (
        ("LocalBusiness", schema.build_local_business_jsonld),
        ("FAQPage", schema.build_faq_jsonld),
    ):
        snippet = builder(business)
        inner = re.sub(r"</?script[^>]*>", "", snippet).strip()
        try:
            payload = json.loads(inner)
            valid = isinstance(payload, dict) and "@context" in payload
        except json.JSONDecodeError as exc:
            valid = False
            print(f"       {label} JSON error: {exc}")
        check(valid, f"{label} snippet is parseable JSON with @context")

    # The generated snippet must survive our own parser, since clients paste it
    # back into pages we then re-audit.
    page = parse(f"<html><head>{schema.build_local_business_jsonld(business)}</head></html>")
    check(not page.json_ld_errors, "generated snippet parses cleanly in our own parser")
    check(len(page.json_ld) == 1, "generated snippet yields one JSON-LD block")


def main() -> int:
    test_robots_parsing()
    test_vocab()
    test_invisible_site()
    test_optimized_site()
    test_partial_site()
    test_unreachable_site()
    test_html_report_renders()
    test_snippet_validity()

    print("\n" + "=" * 62)
    if _failures:
        print(f"{len(_failures)} FAILED, {_passes} passed")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    print(f"All {_passes} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
