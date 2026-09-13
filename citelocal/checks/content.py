"""Check: is the page's content shaped so an assistant can lift an answer from it?

Assistants do not rank pages, they extract passages. A homepage that says
"Quality you can trust since 1994" gives them nothing to quote. A page that
states the service, the city, the response time and the price range in plain
sentences gives them five quotable facts.

This check looks for the concrete, extractable signals — entity clarity
(does the page say what it is and where), question-shaped headings, and
whether contact details appear as text rather than only inside an image or
a phone-link icon.
"""
from __future__ import annotations

import re

from ..fetch import Fetcher, domain_of
from ..html_utils import parse
from ..models import CheckResult, Effort, Fix, Status

CHECK_ID = "answer_readiness"
CHECK_NAME = "Answer readiness (extractable content)"
CATEGORY = "Content"

# Enough prose that an assistant has something to work with. Local homepages
# are often almost entirely images and a hero line.
THIN_CONTENT_WORDS = 300
GOOD_CONTENT_WORDS = 600

PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
)

# Marketing filler that occupies the slot where a fact should be.
VAGUE_PHRASES = (
    "quality you can trust",
    "second to none",
    "unmatched quality",
    "we go the extra mile",
    "your satisfaction is our",
    "state of the art",
    "one stop shop",
    "committed to excellence",
    "customer satisfaction is our top priority",
)


def run(business, fetcher: Fetcher) -> CheckResult:
    home = fetcher.get(business.website)
    if not home.ok:
        return CheckResult.skipped(
            CHECK_ID,
            CHECK_NAME,
            CATEGORY,
            f"Could not load {business.website} ({home.error}) — content not checked.",
        )

    page = parse(home.text)
    text_lower = page.text.lower()

    findings: list[str] = []
    fixes: list[Fix] = []
    earned = 0.0
    possible = 0.0

    # -- Substance ---------------------------------------------------------
    possible += 1.5
    words = page.word_count
    if words >= GOOD_CONTENT_WORDS:
        earned += 1.5
        findings.append(f"Homepage has {words} words of readable text.")
    elif words >= THIN_CONTENT_WORDS:
        earned += 0.75
        findings.append(
            f"Homepage has {words} words — workable, but thin for answering "
            "specific questions."
        )
    else:
        findings.append(
            f"Homepage has only {words} words of readable text. There is very little "
            "for an assistant to extract."
        )
        fixes.append(
            Fix(
                title="Add substantive, factual homepage copy",
                detail=(
                    f"The homepage carries {words} words. Assistants quote passages, so "
                    "a page that is mostly imagery and a tagline cannot be cited. Write "
                    "plainly what you do, the towns you cover, your hours, your typical "
                    "response time and your price range. Aim for 600+ words of real "
                    "information, not filler."
                ),
                effort=Effort.MEDIUM,
                impact=0.7,
            )
        )

    # -- Entity clarity: does the page state category and location? ---------
    possible += 2.0
    category_words = [w for w in (business.category or "").lower().split() if len(w) > 3]
    has_category = (
        any(w in text_lower for w in category_words) if category_words else True
    )
    has_city = business.city.lower() in text_lower if business.city else True

    if has_category and has_city:
        earned += 2.0
        findings.append("Homepage text states both what the business does and where.")
    else:
        missing = []
        if not has_category:
            missing.append(f"the service category ('{business.category}')")
        if not has_city:
            missing.append(f"the city ('{business.city}')")
        findings.append(
            "Homepage text does not clearly state " + " or ".join(missing) + "."
        )
        if has_category or has_city:
            earned += 0.7
        fixes.append(
            Fix(
                title="State the service and city explicitly in body text",
                detail=(
                    "Assistants match questions like "
                    f"\"{business.category or 'service'} in {business.city or 'your city'}\" "
                    "against text that actually contains those words together. Put a "
                    "plain sentence near the top of the page: "
                    f"\"{business.name} is a {business.category or '[service]'} serving "
                    f"{business.location or '[city]'} and the surrounding area.\" "
                    "Do not rely on the logo or an image to carry this."
                ),
                effort=Effort.LOW,
                impact=0.75,
            )
        )

    # -- Question-shaped headings -----------------------------------------
    possible += 1.5
    questions = page.question_headings()
    if len(questions) >= 3:
        earned += 1.5
        findings.append(f"{len(questions)} question-style heading(s) found — good extraction shape.")
    elif questions:
        earned += 0.6
        findings.append(
            f"Only {len(questions)} question-style heading(s). More Q&A structure gives "
            "assistants cleaner passages to quote."
        )
    else:
        findings.append(
            "No question-style headings. Headings phrased as the questions customers "
            "ask are the passages assistants extract most readily."
        )
        fixes.append(
            Fix(
                title="Restructure headings as customer questions",
                detail=(
                    "Replace label headings ('Our Services', 'About Us') with the "
                    "question the section answers ('How much does a water heater "
                    "replacement cost?', 'Do you offer same-day service?'). Answer in "
                    "the first two sentences beneath each one — assistants quote the "
                    "opening of a section far more often than the middle."
                ),
                effort=Effort.MEDIUM,
                impact=0.65,
            )
        )

    # -- Contact details as text ------------------------------------------
    possible += 1.0
    phone_in_text = bool(PHONE_PATTERN.search(page.text))
    if phone_in_text:
        earned += 1.0
        findings.append("A phone number appears in the page text.")
    else:
        findings.append(
            "No phone number found in readable text. If the number only exists inside "
            "an image or a click-to-call icon, assistants cannot report it."
        )
        fixes.append(
            Fix(
                title="Put the phone number in text, not only in an image or icon",
                detail=(
                    "Assistants answering \"what's their number\" read text. A number "
                    "rendered inside a logo or graphic is invisible to them. Add it as "
                    "plain text in the header and footer, wrapped in a tel: link."
                ),
                effort=Effort.LOW,
                impact=0.6,
                snippet=(
                    f'<a href="tel:{(business.phone or "+15550000000").replace(" ", "")}">'
                    f'{business.phone or "(555) 000-0000"}</a>'
                ),
            )
        )

    # -- Title and meta description ---------------------------------------
    possible += 1.0
    title = page.title.strip()
    description = page.meta.get("description", "").strip()
    title_ok = bool(title) and len(title) >= 15
    if title_ok and business.city and business.city.lower() not in title.lower():
        findings.append(
            f"Page title does not mention '{business.city}' — local intent queries "
            "match titles that name the place."
        )
        earned += 0.4
    elif title_ok:
        earned += 0.6
    else:
        findings.append("Page title is missing or too short to be descriptive.")

    if description:
        earned += 0.4
    else:
        findings.append("No meta description.")
        fixes.append(
            Fix(
                title="Write a factual meta description",
                detail=(
                    "Assistants and search snippets both use it. One sentence naming "
                    "the service, the city and the single most useful fact "
                    "(response time, hours, or specialty)."
                ),
                effort=Effort.LOW,
                impact=0.3,
                snippet=(
                    f'<meta name="description" content="{business.name} — '
                    f'{business.category or "[service]"} in {business.location or "[city]"}. '
                    '[Response time or specialty]. Call '
                    f'{business.phone or "[phone]"}.">'
                ),
            )
        )

    # -- Service and location pages ---------------------------------------
    possible += 1.0
    site_domain = domain_of(business.website)
    internal = [
        (href, anchor)
        for href, anchor in page.links
        if not href.startswith(("mailto:", "tel:", "#", "javascript:"))
        and (href.startswith("/") or site_domain in href)
    ]
    service_like = [
        (href, anchor)
        for href, anchor in internal
        if re.search(r"service|repair|install|treatment|pricing|areas?|location", href, re.I)
    ]
    if len(service_like) >= 3:
        earned += 1.0
        findings.append(f"{len(service_like)} service/location page(s) linked from the homepage.")
    elif service_like:
        earned += 0.5
        findings.append(
            f"Only {len(service_like)} service/location page(s) found. Individual pages "
            "per service and per town are what match specific local questions."
        )
    else:
        findings.append(
            "No distinct service or location pages found. A single homepage cannot "
            "match the many specific questions customers ask."
        )
        fixes.append(
            Fix(
                title="Create one page per core service and per town served",
                detail=(
                    "Assistants answer narrow questions ('emergency drain unblocking in "
                    f"{business.city or '[town]'}'). A page whose title and opening "
                    "paragraph match that exact intent is far more likely to be cited "
                    "than a homepage that mentions everything. Start with your three "
                    "highest-margin services and your three biggest towns."
                ),
                effort=Effort.HIGH,
                impact=0.6,
            )
        )

    # -- Filler language ---------------------------------------------------
    found_vague = [p for p in VAGUE_PHRASES if p in text_lower]
    if found_vague:
        findings.append(
            "Generic marketing filler found ("
            + "; ".join(f'"{p}"' for p in found_vague[:3])
            + "). These phrases occupy space where a citable fact could be."
        )

    score = max(0.0, min(1.0, earned / possible)) if possible else 0.0

    if score < 0.45:
        status = Status.FAIL
        summary = "Content gives assistants little they can quote."
    elif score < 0.75:
        status = Status.WARN
        summary = "Content is partly extractable but missing key facts."
    else:
        status = Status.PASS
        summary = "Content is well shaped for AI extraction."

    return CheckResult(
        id=CHECK_ID,
        name=CHECK_NAME,
        category=CATEGORY,
        status=status,
        score=score,
        weight=2.0,
        summary=summary,
        findings=findings,
        fixes=fixes,
        evidence={
            "word_count": words,
            "question_headings": questions[:10],
            "has_phone_in_text": phone_in_text,
            "title": title,
            "service_pages": [h for h, _ in service_like][:10],
            "vague_phrases": found_vague,
        },
    )
