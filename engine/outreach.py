"""Drafting outreach that is grounded in measurement — and proving that it is.

This module exists because of one failure mode. The moment you are producing 57
personalised messages a day, the temptation is to let a template invent a
plausible-sounding number: "this is costing you about $40,000 a year". You do
not know that. You have never seen their revenue. A prospect who catches it is
gone, correctly, and they tell people.

So the composer never writes a number of its own. It interpolates only from
values the scanner recorded, and `verify_grounded()` re-reads the finished draft
and traces every numeric claim back to a measurement. A draft that cannot be
traced raises. That check is not decoration — it is the property the whole
strategy in STRATEGY.md rests on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .checks import Finding
from .scan import AuditResult
from .score import Assessment

VARIANTS = ("cold_email", "linkedin", "followup_1", "followup_2", "breakup")


class UngroundedClaimError(ValueError):
    """A draft contained a number that traces back to no measurement."""


@dataclass
class Sender:
    """You. The address is not optional — CAN-SPAM requires a real one."""

    name: str = "Your Name"
    company: str = "Your Studio"
    email: str = "you@example.com"
    phone: str = ""
    calendar_link: str = "https://cal.com/you/15min"
    address: str = "123 Example St, Your City, ST 00000"

    @property
    def signoff(self) -> str:
        lines = [self.name, self.company, self.email]
        if self.phone:
            lines.append(self.phone)
        return "\n".join(lines)


@dataclass
class Draft:
    variant: str
    subject: str
    body: str
    domain: str
    cites: list[str] = field(default_factory=list)  # finding codes referenced
    grounded: bool = True
    unsourced: list[str] = field(default_factory=list)

    @property
    def full(self) -> str:
        return f"Subject: {self.subject}\n\n{self.body}"

    def to_dict(self) -> dict:
        return {
            "variant": self.variant,
            "subject": self.subject,
            "body": self.body,
            "domain": self.domain,
            "cites": self.cites,
            "grounded": self.grounded,
            "unsourced": self.unsourced,
        }


# =============================================================================
# Grounding
# =============================================================================

# Numbers stripped before extraction: URLs, emails, and anything inside them.
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
# A numeric literal, optionally with thousands separators, decimals, $ or %.
_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def authored_copy_numbers(result: AuditResult) -> set[float]:
    """Numbers that appear in the static check copy in `checks.py`.

    This is a deliberate trust boundary, and it is worth being precise about
    where it sits. The threat this module defends against is the *per-prospect*
    composition step inventing a figure — that text is generated fresh for every
    one of 57 daily sends and nobody reads it before it goes out.

    The strings in `checks.py` are the opposite: written once, reviewed once,
    and in version control. When one of them cites a published benchmark ("text
    compression typically cuts transfer size by roughly 70%"), that is a
    reviewed claim, not an invented one, and the composer quoting it verbatim is
    fine. A fabricated number *there* shows up in a diff, which is exactly where
    you want it to show up.
    """
    allowed: set[float] = set()
    for finding in result.findings:
        for text in (finding.evidence, finding.impact, finding.fix, finding.title):
            for _, value in extract_numbers(text):
                allowed.add(value)
                allowed.add(round(value))
                allowed.add(round(value, 1))
    return allowed


def allowed_numbers(result: AuditResult, assessment: Assessment | None = None) -> set[float]:
    """Every number a draft about this scan is permitted to contain.

    Three sources, in descending order of how much they're worth trusting:
    measurements the scanner actually took, figures we set ourselves (package
    price and scope), and benchmark numbers quoted from reviewed check copy.
    Anything else is a fabrication and fails.
    """
    allowed: set[float] = set()

    def add(value) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        allowed.add(number)
        allowed.add(round(number))
        allowed.add(round(number, 1))
        # A draft may legitimately render 1840 ms as "1.8 s".
        if number >= 1000:
            allowed.add(round(number / 1000, 1))

    for value in result.all_metrics.values():
        add(value)
    for finding in result.findings:
        for value in finding.metrics.values():
            add(value)
        add(finding.effort_hours)

    if assessment is not None:
        add(assessment.health_score)
        add(assessment.deal_fit)
        add(assessment.package.price)
        add(assessment.package.scope_hours)

    allowed |= authored_copy_numbers(result)
    return allowed


def extract_numbers(text: str, ignore: list[str] | None = None) -> list[tuple[str, float]]:
    """Pull numeric claims out of prose, skipping digits that aren't claims.

    Order matters here and is easy to get wrong. URLs must be removed *before*
    any bare-hostname substitution, or stripping `127.0.0.1` out of
    `http://127.0.0.1:8080/` leaves `http:// :8080/`, the URL pattern no longer
    matches, and the port survives as a phantom numeric claim.
    """
    cleaned = _EMAIL_RE.sub(" ", _URL_RE.sub(" ", text))
    for token in ignore or []:
        if token:
            cleaned = cleaned.replace(token, " ")

    found: list[tuple[str, float]] = []
    for token in _NUMBER_RE.findall(cleaned):
        raw = token
        normalized = token.replace("$", "").replace(",", "").replace("%", "")
        try:
            found.append((raw, float(normalized)))
        except ValueError:
            continue
    return found


def verify_grounded(
    draft: Draft,
    result: AuditResult,
    assessment: Assessment | None = None,
    sender: Sender | None = None,
) -> tuple[bool, list[str]]:
    """Check every number in the draft against recorded measurements.

    Returns (grounded, unsourced_tokens). Tolerance is 1% to allow for rounding
    on the way into prose.
    """
    allowed = allowed_numbers(result, assessment)
    text = f"{draft.subject}\n{draft.body}"

    # Digits that are identity, not claims:
    #  - the prospect's own domain (24hourplumbing.com, or an IP-addressed host)
    #  - your phone and postal address, which CAN-SPAM requires in the footer
    ignore = [result.domain]
    if sender is not None:
        ignore += [sender.phone, sender.address, sender.email, sender.calendar_link]

    unsourced: list[str] = []
    for raw, value in extract_numbers(text, ignore=ignore):
        if any(abs(value - candidate) <= max(0.01, abs(candidate) * 0.01) for candidate in allowed):
            continue
        unsourced.append(raw)

    return (not unsourced), unsourced


def _guard(draft: Draft, result: AuditResult, assessment: Assessment, sender: Sender) -> Draft:
    """Attach the verification verdict to a draft. Never silently passes."""
    grounded, unsourced = verify_grounded(draft, result, assessment, sender)
    draft.grounded = grounded
    draft.unsourced = unsourced
    return draft


# =============================================================================
# Composition
# =============================================================================


def compose(
    result: AuditResult,
    assessment: Assessment,
    sender: Sender | None = None,
    variant: str = "cold_email",
    contact_name: str | None = None,
    strict: bool = False,
) -> Draft:
    """Draft one grounded outreach message.

    With strict=True an ungrounded draft raises instead of returning flagged —
    use that in any automated send path.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; expected one of {', '.join(VARIANTS)}")

    sender = sender or Sender()
    if not result.ok or not result.findings:
        raise ValueError(f"nothing to write about: {result.domain} produced no findings")

    builder = {
        "cold_email": _cold_email,
        "linkedin": _linkedin,
        "followup_1": _followup_1,
        "followup_2": _followup_2,
        "breakup": _breakup,
    }[variant]

    draft = _guard(builder(result, assessment, sender, contact_name), result, assessment, sender)

    if strict and not draft.grounded:
        raise UngroundedClaimError(
            f"{result.domain}: draft cites unsourced number(s) {draft.unsourced}. "
            "Every figure must trace to a recorded measurement."
        )
    return draft


def compose_sequence(
    result: AuditResult,
    assessment: Assessment,
    sender: Sender | None = None,
    contact_name: str | None = None,
) -> list[Draft]:
    """The full touch sequence, in send order."""
    return [
        compose(result, assessment, sender, variant, contact_name)
        for variant in ("cold_email", "followup_1", "followup_2", "breakup")
    ]


def _greeting(contact_name: str | None) -> str:
    return f"Hi {contact_name}," if contact_name else "Hi,"


def _footer(sender: Sender) -> str:
    # CAN-SPAM: accurate identification, a real postal address, a working
    # opt-out. Also the difference between landing in an inbox and a blocklist.
    return (
        f"{sender.signoff}\n"
        f"{sender.address}\n\n"
        "Not useful? Reply 'no thanks' and I won't contact you again."
    )


def _cold_email(
    result: AuditResult, assessment: Assessment, sender: Sender, contact_name: str | None
) -> Draft:
    headline = assessment.headline
    assert headline is not None

    cites = [headline.code]
    lines = [
        _greeting(contact_name),
        "",
        f"I ran a technical check on {result.domain} this morning and found something "
        "worth flagging.",
        "",
        f"{headline.evidence}",
        "",
        headline.impact,
        "",
    ]

    supporting = [f for f in result.findings if f.code != headline.code][:2]
    if supporting:
        lines.append("While I was in there I also noticed:")
        for finding in supporting:
            lines.append(f"  • {finding.evidence}")
            cites.append(finding.code)
        lines.append("")

    wins = [w for w in assessment.quick_wins if w.code != headline.code][:1]
    if wins:
        lines.append(
            f"The good news is the first one is quick — {wins[0].fix.rstrip('.')}. "
            "That is an afternoon of work, not a project."
        )
        cites.append(wins[0].code)
    else:
        lines.append(f"The fix is straightforward: {headline.fix.rstrip('.')}.")
    lines.append("")

    lines += [
        "Want the full write-up? I put together a short report on what I found, "
        "ranked by what it's costing you. No charge and no obligation — reply "
        "'send it' and it's yours.",
        "",
        _footer(sender),
    ]

    return Draft(
        variant="cold_email",
        subject=_subject_for(result, headline),
        body="\n".join(lines),
        domain=result.domain,
        cites=cites,
    )


def _linkedin(
    result: AuditResult, assessment: Assessment, sender: Sender, contact_name: str | None
) -> Draft:
    headline = assessment.headline
    assert headline is not None
    body = (
        f"{_greeting(contact_name)} I was looking at {result.domain} and ran a quick "
        f"technical check.\n\n{headline.evidence}\n\n"
        f"{_first_sentence(headline.impact)}\n\n"
        "Happy to send over the full list of what I found — no charge. Want it?"
    )
    return Draft(
        variant="linkedin",
        subject=f"Quick note about {result.domain}",
        body=body,
        domain=result.domain,
        cites=[headline.code],
    )


def _followup_1(
    result: AuditResult, assessment: Assessment, sender: Sender, contact_name: str | None
) -> Draft:
    headline = assessment.headline
    assert headline is not None
    # Lead with a *different* finding: repeating the first one reads as a nag,
    # while a new measurement reads as someone who actually did the work.
    alternate = next(
        (f for f in result.findings if f.code != headline.code and f.severity in ("critical", "high")),
        None,
    )
    cites = [headline.code]

    lines = [_greeting(contact_name), "", f"Following up on {result.domain}."]
    if alternate is not None:
        lines += ["", "Another one from the same scan:", "", alternate.evidence, "", alternate.impact]
        cites.append(alternate.code)
    else:
        lines += ["", f"The issue I mentioned is still live: {headline.evidence}"]

    lines += [
        "",
        "The full report covers everything I found, ranked by impact. Say the word "
        "and I'll send it across.",
        "",
        _footer(sender),
    ]
    return Draft(
        variant="followup_1",
        subject=f"Re: {_subject_for(result, headline)}",
        body="\n".join(lines),
        domain=result.domain,
        cites=cites,
    )


def _followup_2(
    result: AuditResult, assessment: Assessment, sender: Sender, contact_name: str | None
) -> Draft:
    package = assessment.package
    counts = result.severity_counts
    severe = counts["critical"] + counts["high"]
    cites = [f.code for f in result.findings[:3]]

    lines = [
        _greeting(contact_name),
        "",
        f"Last useful thing I'll send about {result.domain}.",
        "",
        f"The scan turned up {severe} issues I'd class as serious, and roughly "
        f"{result.total_effort_hours} hours of work to clear them.",
        "",
        f"That's what my {package.name} covers — {package.summary} Fixed price, "
        f"${package.price:,}, with before-and-after numbers on every item so you "
        "can see exactly what changed.",
        "",
        f"If it's useful: {sender.calendar_link}",
        "",
        _footer(sender),
    ]
    return Draft(
        variant="followup_2",
        subject=f"{result.domain}: the full list, and what it'd take to fix",
        body="\n".join(lines),
        domain=result.domain,
        cites=cites,
    )


def _breakup(
    result: AuditResult, assessment: Assessment, sender: Sender, contact_name: str | None
) -> Draft:
    headline = assessment.headline
    assert headline is not None
    lines = [
        _greeting(contact_name),
        "",
        f"I'll stop here — you're clearly busy, and I'd rather not be noise.",
        "",
        "For what it's worth, the report is written and it's yours whenever you "
        "want it. No catch, and no need to buy anything.",
        "",
        f"The one thing I'd fix regardless of who does it: {headline.fix.rstrip('.')}.",
        "",
        "Good luck with it either way.",
        "",
        _footer(sender),
    ]
    return Draft(
        variant="breakup",
        subject=f"Closing the loop on {result.domain}",
        body="\n".join(lines),
        domain=result.domain,
        cites=[headline.code],
    )


def _subject_for(result: AuditResult, headline: Finding) -> str:
    """Subject lines lead with the measurement where there is one.

    A number in the subject is the thing that survives a two-second inbox scan;
    it is also the clearest possible signal that the sender looked at *their*
    site rather than mail-merging a list.
    """
    primary = _primary_metric(headline)
    if primary is not None:
        key, value = primary
        if key.endswith("_ms"):
            return f"{result.domain} responds in {value / 1000:,.1f}s"
        if key.endswith("_kb"):
            return f"{result.domain}: {value:,.0f} KB homepage"
        if key.endswith("_pct"):
            return f"{result.domain}: {value:,.0f}% of images missing alt text"
        return f"{result.domain}: {value:,.0f} {_metric_noun(key)}"
    return f"Found something on {result.domain}"


_METRIC_NOUNS = {
    "render_blocking_scripts": "render-blocking scripts",
    "broken_links": "broken links",
    "images_without_dimensions": "images without dimensions",
    "images_missing_alt": "images missing alt text",
    "legacy_format_images": "unoptimised images",
    "mixed_content_resources": "insecure resources",
    "missing_og_tags": "missing social tags",
    "stylesheet_count": "blocking stylesheets",
    "redirect_hops": "redirect hops",
    "word_count": "words on the homepage",
    "estimated_saving_kb": "KB of avoidable transfer",
}


def _primary_metric(finding: Finding) -> tuple[str, float] | None:
    """The metric worth putting in a subject line — prefer a named noun."""
    numeric = {
        k: float(v)
        for k, v in finding.metrics.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }
    if not numeric:
        return None
    for key in _METRIC_NOUNS:
        if key in numeric:
            return key, numeric[key]
    for key, value in numeric.items():
        # Threshold/target metrics describe the ideal, not their site.
        if any(suffix in key for suffix in ("_target", "_min", "_max")):
            continue
        return key, value
    return None


def _metric_noun(key: str) -> str:
    return _METRIC_NOUNS.get(key, key.replace("_", " "))


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0] if parts else text
