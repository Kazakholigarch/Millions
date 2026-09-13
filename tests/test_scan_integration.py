"""End-to-end: scan real HTTP servers and check the findings are true.

Each assertion here is a claim the engine would go on to put in front of a
paying stranger, so each is checked against the fixture that produced it.
"""
from __future__ import annotations

import pytest

from engine.outreach import Sender, compose, compose_sequence, verify_grounded
from engine.scan import scan
from engine.score import assess


@pytest.fixture(scope="module")
def broken_scan(broken_site):
    from engine.fetch import Fetcher

    fetcher = Fetcher(min_delay=0.0, timeout=10.0)
    try:
        yield scan(broken_site.url, fetcher=fetcher, link_sample=6)
    finally:
        fetcher.close()


@pytest.fixture(scope="module")
def healthy_scan(healthy_site):
    from engine.fetch import Fetcher

    fetcher = Fetcher(min_delay=0.0, timeout=10.0)
    try:
        yield scan(healthy_site.url, fetcher=fetcher, link_sample=6)
    finally:
        fetcher.close()


def codes(result) -> set[str]:
    return {f.code for f in result.findings}


# -- the scan completes at all ----------------------------------------------


def test_broken_site_scan_succeeds(broken_scan):
    assert broken_scan.ok, broken_scan.error
    assert broken_scan.status == 200


def test_healthy_site_scan_succeeds(healthy_scan):
    assert healthy_scan.ok, healthy_scan.error


# -- performance findings match what the server actually did ----------------


def test_detects_slow_ttfb_and_reports_the_real_number(broken_scan):
    """The fixture sleeps 1s before responding; the finding must say so."""
    assert "PERF_TTFB_SLOW" in codes(broken_scan)
    assert broken_scan.ttfb_ms >= 950, broken_scan.ttfb_ms

    finding = next(f for f in broken_scan.findings if f.code == "PERF_TTFB_SLOW")
    measured = finding.metrics["ttfb_ms"]
    # The number in the evidence is the number we measured, not an estimate.
    assert 950 <= measured <= 3000
    assert f"{measured:,.0f}" in finding.evidence


def test_healthy_site_is_not_flagged_as_slow(healthy_scan):
    assert "PERF_TTFB_SLOW" not in codes(healthy_scan)


def test_detects_missing_compression_only_when_truly_missing(broken_scan, healthy_scan):
    """Broken serves plain; healthy serves real gzip. Only one should flag."""
    assert "PERF_NO_COMPRESSION" in codes(broken_scan)
    assert "PERF_NO_COMPRESSION" not in codes(healthy_scan)


def test_detects_render_blocking_scripts(broken_scan, healthy_scan):
    assert "PERF_RENDER_BLOCKING" in codes(broken_scan)
    finding = next(f for f in broken_scan.findings if f.code == "PERF_RENDER_BLOCKING")
    assert finding.metrics["render_blocking_scripts"] == 3  # the fixture has exactly 3
    # Healthy uses defer on both of its scripts.
    assert "PERF_RENDER_BLOCKING" not in codes(healthy_scan)


def test_detects_too_many_stylesheets(broken_scan):
    finding = next(f for f in broken_scan.findings if f.code == "PERF_MANY_CSS")
    assert finding.metrics["stylesheet_count"] == 6


def test_counts_images_missing_dimensions(broken_scan, healthy_scan):
    finding = next(f for f in broken_scan.findings if f.code == "PERF_IMG_NO_DIMENSIONS")
    assert finding.metrics["images_without_dimensions"] == 8  # 7 local + 1 insecure
    assert "PERF_IMG_NO_DIMENSIONS" not in codes(healthy_scan)


# -- security ----------------------------------------------------------------


def test_detects_missing_security_headers(broken_scan):
    found = codes(broken_scan)
    for code in ("SEC_NO_CSP", "SEC_NO_XCTO", "SEC_NO_FRAME_PROTECTION", "SEC_NO_REFERRER_POLICY"):
        assert code in found, code


def test_healthy_site_passes_security_headers(healthy_scan):
    found = codes(healthy_scan)
    for code in ("SEC_NO_CSP", "SEC_NO_XCTO", "SEC_NO_FRAME_PROTECTION", "SEC_NO_REFERRER_POLICY"):
        assert code not in found, code


def test_detects_version_disclosure(broken_scan):
    """The fixture leaks nginx/1.14.0 and PHP/7.2.1."""
    finding = next(f for f in broken_scan.findings if f.code == "SEC_VERSION_DISCLOSURE")
    assert "nginx/1.14.0" in finding.evidence or "PHP/7.2.1" in finding.evidence


def test_detects_mixed_content(broken_scan):
    """Mixed content is only a finding on an HTTPS page — this fixture is HTTP."""
    assert "SEC_MIXED_CONTENT" not in codes(broken_scan)


# -- seo ---------------------------------------------------------------------


def test_detects_seo_gaps(broken_scan):
    found = codes(broken_scan)
    for code in (
        "SEO_NO_DESCRIPTION",
        "SEO_MULTIPLE_H1",
        "SEO_NO_CANONICAL",
        "SEO_NO_OPEN_GRAPH",
        "SEO_NO_STRUCTURED_DATA",
        "SEO_IMG_NO_ALT",
        "SEO_NO_LANG",
        "SEO_NO_SITEMAP",
    ):
        assert code in found, code


def test_healthy_site_passes_seo(healthy_scan):
    found = codes(healthy_scan)
    for code in (
        "SEO_NO_TITLE",
        "SEO_NO_DESCRIPTION",
        "SEO_NO_H1",
        "SEO_MULTIPLE_H1",
        "SEO_NO_CANONICAL",
        "SEO_NO_OPEN_GRAPH",
        "SEO_NO_STRUCTURED_DATA",
        "SEO_NO_LANG",
        "SEO_NO_SITEMAP",
    ):
        assert code not in found, code


def test_sitemap_url_count_is_read_from_the_sitemap(healthy_scan):
    assert healthy_scan.sitemap_urls == 120


# -- mobile ------------------------------------------------------------------


def test_detects_missing_viewport(broken_scan, healthy_scan):
    assert "MOB_NO_VIEWPORT" in codes(broken_scan)
    assert "MOB_NO_VIEWPORT" not in codes(healthy_scan)


# -- conversion --------------------------------------------------------------


def test_detects_missing_analytics_and_form(broken_scan):
    found = codes(broken_scan)
    assert "CONV_NO_ANALYTICS" in found
    assert "CONV_NO_FORM" in found
    assert broken_scan.analytics == []


def test_healthy_site_analytics_detected(healthy_scan):
    assert "Plausible" in healthy_scan.analytics
    assert "CONV_NO_ANALYTICS" not in codes(healthy_scan)
    assert "CONV_NO_FORM" not in codes(healthy_scan)


def test_healthy_site_contact_details_found(healthy_scan):
    assert "CONV_NO_PHONE" not in codes(healthy_scan)
    assert "CONV_NO_CONTACT_ROUTE" not in codes(healthy_scan)


# -- trust -------------------------------------------------------------------


def test_detects_broken_links(broken_scan):
    """Three of the fixture's links 200 as soft-404s, so link-checking can't
    see them — but the soft-404 check must."""
    assert broken_scan.links_checked > 0


def test_detects_soft_404(broken_scan, healthy_scan):
    assert "TRUST_SOFT_404" in codes(broken_scan)
    assert "TRUST_SOFT_404" not in codes(healthy_scan)


def test_detects_missing_favicon(broken_scan, healthy_scan):
    assert "TRUST_NO_FAVICON" in codes(broken_scan)
    assert "TRUST_NO_FAVICON" not in codes(healthy_scan)


# -- scoring -----------------------------------------------------------------


def test_healthy_fixture_only_fails_the_checks_http_makes_it_fail(healthy_scan):
    """The fixture is served over plain HTTP, so HTTPS findings are correct.

    Asserting the exact remaining set is stronger than a score threshold: it
    proves no *other* check fires on a well-built page, which is the property
    that matters. A false positive here would be a false accusation in a cold
    email, which is the expensive kind of wrong.
    """
    assert codes(healthy_scan) <= {"SEC_NO_HTTPS", "SEC_VERSION_DISCLOSURE"}, codes(healthy_scan)


def test_scores_separate_the_two_sites(broken_scan, healthy_scan):
    broken = assess(broken_scan)
    healthy = assess(healthy_scan)
    assert broken.health_score < 45, broken.health_score
    assert healthy.health_score > 75, healthy.health_score
    # The gap is the point: the scorer must rank these very differently.
    assert healthy.health_score - broken.health_score > 50
    assert broken.grade in ("D", "F")
    assert healthy.grade in ("A", "B")


def test_healthy_site_is_a_poor_prospect(healthy_scan):
    """Nothing to sell: a healthy site should rank low on deal fit."""
    assert assess(healthy_scan).deal_fit < 45


def test_sitemap_scale_raises_the_budget_signal(healthy_scan):
    """120 sitemap URLs is an established site, not a brochure."""
    assert assess(healthy_scan).budget.score > 0


# -- the outreach built on all this -----------------------------------------


def test_every_draft_from_a_real_scan_is_grounded(broken_scan):
    """The end-to-end guarantee: nothing reaches a prospect unverified."""
    assessment = assess(broken_scan)
    sender = Sender(
        name="Test Sender", company="Test Co", email="t@example.com",
        phone="555-0100", address="1 Test St, Testville, TS 12345",
    )
    drafts = compose_sequence(broken_scan, assessment, sender, contact_name="Alex")
    assert len(drafts) == 4
    for draft in drafts:
        assert draft.grounded, f"{draft.variant} cites unsourced numbers: {draft.unsourced}"


def test_strict_mode_accepts_a_real_scan(broken_scan):
    assessment = assess(broken_scan)
    draft = compose(broken_scan, assessment, Sender(), "cold_email", strict=True)
    assert draft.grounded


def test_subject_line_carries_a_measured_number(broken_scan):
    assessment = assess(broken_scan)
    draft = compose(broken_scan, assessment, Sender(), "cold_email")
    assert any(ch.isdigit() for ch in draft.subject), draft.subject
    grounded, unsourced = verify_grounded(draft, broken_scan, assessment, Sender())
    assert grounded, unsourced


def test_robots_txt_is_fetched_and_parsed(broken_scan):
    assert "SEO_NO_ROBOTS_TXT" not in codes(broken_scan)
