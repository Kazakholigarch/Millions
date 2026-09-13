"""Scoring, pricing and prospect ranking.

The bug these tests exist to prevent: ranking by how *broken* a site is rather
than by how much it is worth working on. That version of the tool sends you to
the worst prospect on the list first.
"""
from __future__ import annotations

import pytest

from engine.checks import Finding
from engine.scan import AuditResult
from engine.score import (
    PACKAGES,
    assess,
    budget_signal,
    deal_fit,
    grade_for,
    headline_finding,
    health_score,
    quick_wins,
    rank_prospects,
    recommend_package,
    scale_multiplier,
    scaled_effort_hours,
)


def finding(code, category="seo", severity="medium", hours=1.0, metrics=None, confidence="high"):
    return Finding(
        code=code, title=code.replace("_", " ").title(), category=category, severity=severity,
        evidence="measured something", impact="costs money", fix="fix it",
        effort_hours=hours, confidence=confidence, metrics=metrics or {},
    )


def result(findings=(), **overrides) -> AuditResult:
    audit = AuditResult(
        url="https://x.com/", domain="x.com", scanned_at="2026-01-01T00:00:00+00:00",
        ok=True, **overrides,
    )
    audit.findings = list(findings)
    return audit


# -- health score ------------------------------------------------------------


def test_a_clean_site_scores_full_marks():
    assert health_score(result()) == 100


def test_a_failed_scan_scores_zero():
    assert health_score(AuditResult(url="", domain="x", scanned_at="", ok=False)) == 0


def test_severity_drives_the_deduction():
    critical = health_score(result([finding("A", severity="critical")]))
    high = health_score(result([finding("B", severity="high")]))
    low = health_score(result([finding("C", severity="low")]))
    assert critical < high < low < 100


def test_heuristic_findings_cost_less_than_measured_ones():
    measured = health_score(result([finding("A", severity="high")]))
    heuristic = health_score(result([finding("A", severity="high", confidence="medium")]))
    assert heuristic > measured


def test_one_category_cannot_sink_the_whole_score():
    """Twelve low-severity SEO nits must not outrank having no HTTPS."""
    nitpicks = result([finding(f"SEO_{i}", "seo", "medium") for i in range(12)])
    catastrophe = result([finding("SEC_NO_HTTPS", "security", "critical")])
    assert health_score(nitpicks) > health_score(catastrophe) - 40
    assert health_score(nitpicks) >= 70


def test_score_never_goes_negative():
    """Damage across every category saturates the floor rather than going below it."""
    from engine.checks import CATEGORIES

    disaster = result(
        [finding(f"X{c}{i}", c, "critical") for c in CATEGORIES for i in range(8)]
    )
    assert health_score(disaster) == 0


def test_the_per_category_cap_bounds_a_single_category():
    """Forty critical performance findings deduct the cap, not forty times the weight."""
    from engine.score import MAX_DEDUCTION_PER_CATEGORY

    piled_on = result([finding(f"X{i}", "performance", "critical") for i in range(40)])
    assert health_score(piled_on) == 100 - MAX_DEDUCTION_PER_CATEGORY


@pytest.mark.parametrize("score,grade", [(95, "A"), (85, "B"), (75, "C"), (60, "D"), (10, "F")])
def test_grade_boundaries(score, grade):
    assert grade_for(score) == grade


# -- headline selection ------------------------------------------------------


def test_headline_prefers_a_finding_with_a_hard_number():
    """'Your server takes 2.1s' opens a conversation; 'no Referrer-Policy' doesn't."""
    numeric = finding("PERF_TTFB_SLOW", "performance", "high", metrics={"ttfb_ms": 2100})
    vague = finding("SEC_NO_REFERRER_POLICY", "security", "high")
    assert headline_finding(result([vague, numeric])).code == "PERF_TTFB_SLOW"


def test_headline_prefers_severity_over_everything():
    minor = finding("SEO_NO_LANG", "seo", "low", metrics={"x": 5})
    major = finding("MOB_NO_VIEWPORT", "mobile", "critical")
    assert headline_finding(result([minor, major])).code == "MOB_NO_VIEWPORT"


def test_no_findings_means_no_headline():
    assert headline_finding(result()) is None


# -- quick wins --------------------------------------------------------------


def test_quick_wins_are_severe_and_cheap():
    cheap_severe = finding("A", severity="high", hours=1.0)
    cheap_minor = finding("B", severity="low", hours=0.5)
    dear_severe = finding("C", severity="critical", hours=12.0)
    wins = quick_wins(result([cheap_severe, cheap_minor, dear_severe]))
    assert [w.code for w in wins] == ["A"]


# -- budget signal -----------------------------------------------------------


def test_no_spend_signals_scores_zero():
    audit = result([finding("SEO_NO_STRUCTURED_DATA"), finding("SEC_NO_CSP")])
    assert budget_signal(audit).score == 0
    assert budget_signal(audit).tier == "small"


def test_cdn_and_martech_and_scale_raise_the_signal():
    audit = result(
        [finding("SEO_NO_STRUCTURED_DATA"), finding("SEC_NO_CSP")],
        cdn="Cloudflare", analytics=["Google Analytics / GTM", "Segment"],
        sitemap_urls=2400, internal_link_count=140,
    )
    signal = budget_signal(audit)
    assert signal.tier == "enterprise"
    assert any("Cloudflare" in s for s in signal.signals)
    assert any("2,400" in s for s in signal.signals)


def test_absent_findings_count_as_prior_investment():
    """No CSP finding means they *have* a CSP — someone did security work."""
    audit = result([])  # nothing missing at all
    assert budget_signal(audit).score > 0


# -- deal fit ----------------------------------------------------------------


def test_a_healthy_site_is_a_poor_prospect():
    """Nothing to sell, however pleasant the site."""
    fit, reasons = deal_fit(result([finding("SEC_NO_REFERRER_POLICY", "security", "low")]))
    assert fit < 45
    assert any("good shape" in r for r in reasons)


def test_a_failed_scan_is_not_a_prospect():
    fit, _ = deal_fit(AuditResult(url="", domain="x", scanned_at="", ok=False))
    assert fit == 0


def test_ability_to_pay_lifts_an_otherwise_identical_prospect():
    findings = [
        finding("PERF_TTFB_SLOW", "performance", "critical", 8.0, {"ttfb_ms": 2000}),
        finding("PERF_NO_COMPRESSION", "performance", "high", 1.0),
    ]
    poor = result(findings)
    rich = result(findings, cdn="Fastly", analytics=["Segment", "Hotjar"],
                  sitemap_urls=1800, internal_link_count=120)
    assert deal_fit(rich)[0] > deal_fit(poor)[0]


# -- scope scaling -----------------------------------------------------------


def test_scale_multiplier_tracks_site_size():
    assert scale_multiplier(result(sitemap_urls=5)) == 1.0
    assert scale_multiplier(result(sitemap_urls=150)) == 1.8
    assert scale_multiplier(result(sitemap_urls=3000)) == 3.2


def test_scaled_effort_exceeds_raw_effort_on_large_sites():
    findings = [finding("A", hours=10.0)]
    small = result(findings, sitemap_urls=5)
    large = result(findings, sitemap_urls=3000)
    assert scaled_effort_hours(small) == 10.0
    assert scaled_effort_hours(large) == 32.0


# -- package selection -------------------------------------------------------


def test_structural_damage_justifies_an_overhaul():
    audit = result(
        [finding("MOB_NO_VIEWPORT", "mobile", "critical", 12.0)],
        cdn="Cloudflare", analytics=["Segment"], sitemap_urls=900, internal_link_count=100,
    )
    package, note = recommend_package(audit)
    assert package.key == "overhaul"
    assert note is None


def test_a_small_prospect_is_not_quoted_an_overhaul():
    """They may need one. They will not buy one. Lead with what they can buy."""
    audit = result([finding("MOB_NO_VIEWPORT", "mobile", "critical", 12.0)])
    package, note = recommend_package(audit)
    assert package.key == "fix_sprint"
    assert note is not None and "phase one" in note


def test_a_clean_site_gets_offered_a_retainer():
    package, _ = recommend_package(result())
    assert package.key == "retainer"


def test_every_package_is_priced_and_scoped():
    for key, package in PACKAGES.items():
        assert package.price > 0, key
        assert package.scope_hours > 0, key
        assert package.summary, key


# -- ranking -----------------------------------------------------------------


def test_ranking_is_by_expected_value_not_raw_damage():
    """Regression: the broken-but-broke prospect must not rank first.

    A tiny site with catastrophic problems and no budget once sorted above a
    large site with a real budget, because the damage was worse. That sends you
    to the worst prospect on the list first.
    """
    tiny_catastrophe = result(
        [finding(f"X{i}", "performance", "critical", 8.0) for i in range(5)],
        sitemap_urls=0, internal_link_count=3,
    )
    tiny_catastrophe.domain = "tiny.com"

    big_fixable = result(
        [
            finding("PERF_TTFB_SLOW", "performance", "critical", 8.0, {"ttfb_ms": 1900}),
            finding("PERF_NO_COMPRESSION", "performance", "high", 1.0),
            finding("TRUST_BROKEN_LINKS", "trust", "high", 2.0, {"broken_links": 3}),
        ],
        cdn="Fastly", analytics=["Segment", "Hotjar"], sitemap_urls=2400, internal_link_count=140,
    )
    big_fixable.domain = "big.com"

    ranked = rank_prospects([tiny_catastrophe, big_fixable])
    assert ranked[0][0].domain == "big.com"
    assert ranked[0][1].expected_value > ranked[1][1].expected_value


def test_expected_value_combines_price_and_fit():
    audit = result([finding("A", severity="high", hours=2.0)])
    assessment = assess(audit)
    assert assessment.expected_value == pytest.approx(
        assessment.package.price * assessment.deal_fit / 100
    )


def test_assessment_serialises():
    data = assess(result([finding("A", severity="high")])).to_dict()
    for key in ("domain", "health_score", "deal_fit", "package_price", "budget_tier", "expected_value"):
        assert key in data


def test_missing_https_alone_is_not_an_overhaul():
    """Regression: a cert install is ~3 hours, not a $20,000 rebuild.

    SEC_NO_HTTPS reads as alarming as a missing viewport but is nothing like
    it in scope. Quoting an overhaul for it loses the deal on the second
    opinion.
    """
    audit = result(
        [finding("SEC_NO_HTTPS", "security", "critical", 3.0),
         finding("SEC_VERSION_DISCLOSURE", "security", "low", 0.5)],
        sitemap_urls=340, internal_link_count=40,
    )
    package, _ = recommend_package(audit)
    assert package.key == "quick_win", package.key


def test_missing_viewport_still_is_an_overhaul():
    """There is no responsive layout to patch — the templates get rebuilt."""
    audit = result([finding("MOB_NO_VIEWPORT", "mobile", "critical", 12.0)],
                   cdn="Fastly", sitemap_urls=900, internal_link_count=100)
    assert recommend_package(audit)[0].key == "overhaul"


def test_a_pile_of_cheap_criticals_still_escalates():
    audit = result([finding(f"X{i}", "performance", "critical", 1.0) for i in range(3)],
                   cdn="Fastly", sitemap_urls=900, internal_link_count=100)
    assert recommend_package(audit)[0].key == "overhaul"


def test_report_declares_phase_scoping_when_the_package_is_capped():
    """The report must not state 60 hours of work and quote a 24-hour package
    without saying which is which."""
    from engine.audit_report import render_markdown

    audit = result(
        [finding(f"X{i}", "performance", "high", 6.0) for i in range(9)],
        sitemap_urls=10, internal_link_count=8,
    )
    assessment = assess(audit)
    assert assessment.scaled_hours > assessment.package.scope_hours
    markdown = render_markdown(audit, assessment)
    assert "second phase" in markdown


def test_report_omits_the_phase_note_when_the_package_covers_everything():
    from engine.audit_report import render_markdown

    audit = result([finding("A", "seo", "medium", 1.0)])
    assert "second phase" not in render_markdown(audit)
