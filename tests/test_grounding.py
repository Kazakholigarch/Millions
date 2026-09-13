"""The anti-fabrication guarantee.

If these tests pass and the engine still sends an invented number to a
prospect, the guarantee is worthless. So the negative cases matter more than
the positive ones here.
"""
from __future__ import annotations

import pytest

from engine.checks import Finding
from engine.outreach import (
    Draft,
    Sender,
    UngroundedClaimError,
    allowed_numbers,
    compose,
    extract_numbers,
    verify_grounded,
)
from engine.scan import AuditResult
from engine.score import assess


def make_result(**overrides) -> AuditResult:
    result = AuditResult(
        url="https://acme.com/", domain="acme.com", scanned_at="2026-01-01T00:00:00+00:00",
        ok=True, ttfb_ms=1840.0, html_kb=182.0, word_count=310, images_total=12,
        **overrides,
    )
    result.findings = [
        Finding(
            code="PERF_TTFB_SLOW", title="Slow server", category="performance", severity="critical",
            evidence="Time to first byte measured at 1,840 ms (a healthy target is under 800 ms).",
            impact="Time to first byte is pure waiting before anything renders.",
            fix="Add caching and a CDN", effort_hours=8.0,
            metrics={"ttfb_ms": 1840, "ttfb_target_ms": 800},
        ),
        Finding(
            code="PERF_NO_COMPRESSION", title="No compression", category="performance", severity="high",
            evidence="The server returned 182 KB of HTML with no Content-Encoding header.",
            impact="Compression typically cuts HTML transfer size by roughly 70%.",
            fix="Enable gzip or brotli", effort_hours=1.0,
            metrics={"html_kb": 182, "estimated_saving_kb": 127},
        ),
    ]
    return result


def draft_with(body: str, subject: str = "test") -> Draft:
    return Draft(variant="cold_email", subject=subject, body=body, domain="acme.com")


# -- extraction --------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("costs $40,000 a year", [40000.0]),
        ("a 2.4% conversion rate", [2.4]),
        ("1,840 ms and 182 KB", [1840.0, 182.0]),
        ("no numbers at all", []),
    ],
)
def test_extract_numbers_finds_claims(text, expected):
    assert [value for _, value in extract_numbers(text)] == expected


def test_extract_numbers_ignores_urls_and_emails():
    text = "See https://cal.com/you/15min or mail me at bob99@x7.com about the 42 issues"
    assert [value for _, value in extract_numbers(text)] == [42.0]


def test_extract_numbers_honours_the_ignore_list():
    assert extract_numbers("24hourplumbing.com has 7 issues", ignore=["24hourplumbing.com"]) == [
        ("7", 7.0)
    ]


def test_url_stripping_happens_before_ignore_substitution():
    """Regression: stripping the bare host first orphans the port.

    `http://127.0.0.1:8080/` with `127.0.0.1` removed becomes `http:// :8080/`,
    which the URL pattern no longer matches — leaking 8080 as a phantom claim.
    """
    found = extract_numbers("served at http://127.0.0.1:8080/ today", ignore=["127.0.0.1"])
    assert found == []


# -- the allowed set ---------------------------------------------------------


def test_measured_values_are_allowed():
    result = make_result()
    allowed = allowed_numbers(result, assess(result))
    assert 1840 in allowed
    assert 182 in allowed


def test_unit_converted_values_are_allowed():
    """1,840 ms rendered as 1.8 s is the same measurement."""
    assert 1.8 in allowed_numbers(make_result())


def test_benchmark_numbers_in_reviewed_check_copy_are_allowed():
    """The 70% in the compression impact copy is reviewed, not invented."""
    assert 70.0 in allowed_numbers(make_result())


def test_arbitrary_numbers_are_not_allowed():
    allowed = allowed_numbers(make_result())
    for invented in (40000.0, 2.4, 99.0, 12345.0):
        assert invented not in allowed


# -- verification ------------------------------------------------------------


def test_real_measurements_pass():
    result = make_result()
    grounded, unsourced = verify_grounded(
        draft_with("Your server takes 1,840 ms and ships 182 KB."), result, assess(result)
    )
    assert grounded, unsourced


@pytest.mark.parametrize(
    "fabrication",
    [
        "This is costing you about $40,000 a year.",
        "Your conversion rate is 2.4%, below the 3.1% average.",
        "I can fix this for 99 dollars.",
        "Your homepage takes 9,999 ms to respond.",
        "You are losing 250 customers a month.",
    ],
)
def test_fabricated_numbers_are_caught(fabrication):
    result = make_result()
    grounded, unsourced = verify_grounded(draft_with(fabrication), result, assess(result))
    assert not grounded, f"fabrication slipped through: {fabrication}"
    assert unsourced


def test_senders_own_address_is_not_a_claim():
    """A ZIP code in your CAN-SPAM footer is not a claim about the prospect."""
    result = make_result()
    sender = Sender(phone="555-0142", address="1 Main St, Springfield, IL 62701")
    grounded, unsourced = verify_grounded(
        draft_with(f"Hi.\n\n{sender.signoff}\n{sender.address}"), result, assess(result), sender
    )
    assert grounded, unsourced


def test_prospect_domain_with_digits_is_not_a_claim():
    result = make_result()
    result.domain = "24hourplumbing.com"
    grounded, unsourced = verify_grounded(
        draft_with("I looked at 24hourplumbing.com today."), result, assess(result)
    )
    assert grounded, unsourced


# -- strict mode -------------------------------------------------------------


def test_strict_mode_raises_on_ungrounded_output(monkeypatch):
    """If a composer template ever invents a figure, strict mode must stop it."""
    import engine.outreach as outreach

    result = make_result()
    assessment = assess(result)

    def leaky(res, ass, sender, contact_name):
        return Draft(
            variant="cold_email", subject="hi",
            body="This is costing you $40,000 a year.", domain=res.domain,
        )

    monkeypatch.setitem(
        outreach.compose.__globals__, "_cold_email", leaky
    )
    with pytest.raises(UngroundedClaimError, match="40,000"):
        compose(result, assessment, Sender(), "cold_email", strict=True)


def test_non_strict_mode_flags_rather_than_raises(monkeypatch):
    import engine.outreach as outreach

    result = make_result()

    def leaky(res, ass, sender, contact_name):
        return Draft(variant="cold_email", subject="hi", body="You lose $40,000.", domain=res.domain)

    monkeypatch.setitem(outreach.compose.__globals__, "_cold_email", leaky)
    draft = compose(result, assess(result), Sender(), "cold_email")
    assert not draft.grounded
    assert "$40,000" in draft.unsourced


def test_compose_refuses_a_scan_with_no_findings():
    empty = make_result()
    empty.findings = []
    with pytest.raises(ValueError, match="nothing to write about"):
        compose(empty, assess(empty), Sender())
