"""Check: the off-site sources assistants actually read.

An assistant's confidence in recommending a local business comes mostly from
corroboration across independent sources, not from the business's own site.
The sources that matter most for local recommendations are the business
directories (Google Business Profile, Yelp, BBB, Angi, Nextdoor) plus
community discussion, where Reddit carries outsized weight.

What this check can prove from the site alone: whether the business connects
itself to those profiles at all, and whether the phone number it publishes is
internally consistent. Confirming each listing exists and matches requires
visiting it, so the check emits the exact URLs to verify rather than guessing.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from ..fetch import Fetcher
from ..html_utils import flatten_json_ld, parse
from ..models import CheckResult, Effort, Fix, Status

CHECK_ID = "citation_sources"
CHECK_NAME = "Off-site citation sources"
CATEGORY = "Authority"

# Domain fragment -> (label, weight toward this check).
# Weights reflect how much each source influences local AI recommendations.
PROFILE_SOURCES: dict[str, tuple[str, float]] = {
    "google.com/maps": ("Google Business Profile", 1.5),
    "g.page": ("Google Business Profile", 1.5),
    "goo.gl/maps": ("Google Business Profile", 1.5),
    "yelp.com": ("Yelp", 1.2),
    "bbb.org": ("Better Business Bureau", 0.9),
    "facebook.com": ("Facebook Page", 0.7),
    "nextdoor.com": ("Nextdoor", 0.8),
    "angi.com": ("Angi", 0.7),
    "homeadvisor.com": ("HomeAdvisor", 0.6),
    "thumbtack.com": ("Thumbtack", 0.5),
    "trustpilot.com": ("Trustpilot", 0.5),
    "instagram.com": ("Instagram", 0.3),
    "linkedin.com": ("LinkedIn", 0.3),
    "healthgrades.com": ("Healthgrades", 0.6),
    "zocdoc.com": ("Zocdoc", 0.6),
    "tripadvisor.com": ("Tripadvisor", 0.5),
    "houzz.com": ("Houzz", 0.5),
    "avvo.com": ("Avvo", 0.6),
}

# Sources every local business should be on, checked for explicitly.
ESSENTIAL = ("Google Business Profile", "Yelp", "Better Business Bureau")

PHONE_PATTERN = re.compile(r"(?:\+?\d{1,2}[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})")


def run(business, fetcher: Fetcher) -> CheckResult:
    home = fetcher.get(business.website)
    if not home.ok:
        return CheckResult.skipped(
            CHECK_ID,
            CHECK_NAME,
            CATEGORY,
            f"Could not load {business.website} ({home.error}) — citations not checked.",
        )

    page = parse(home.text)
    findings: list[str] = []
    fixes: list[Fix] = []

    # Collect every outbound URL: footer links plus schema sameAs entries.
    urls = [href for href, _ in page.links]
    for node in flatten_json_ld(page.json_ld):
        same_as = node.get("sameAs")
        if isinstance(same_as, str):
            urls.append(same_as)
        elif isinstance(same_as, list):
            urls.extend(u for u in same_as if isinstance(u, str))

    found: dict[str, str] = {}
    for url in urls:
        lowered = url.lower()
        for fragment, (label, _) in PROFILE_SOURCES.items():
            if fragment in lowered and label not in found:
                found[label] = url

    earned = sum(
        weight
        for label, weight in {v[0]: v[1] for v in PROFILE_SOURCES.values()}.items()
        if label in found
    )
    # Score against the essentials plus a reasonable spread, not every source.
    possible = sum(
        weight for label, weight in {v[0]: v[1] for v in PROFILE_SOURCES.values()}.items()
        if label in ESSENTIAL
    ) + 2.0

    if found:
        findings.append("Profiles linked from the site: " + ", ".join(sorted(found)) + ".")
    else:
        findings.append(
            "The site links to no external business profiles. Assistants use those "
            "links to connect your site to your listings as one entity."
        )

    missing_essential = [label for label in ESSENTIAL if label not in found]
    if missing_essential:
        findings.append(
            "Not linked from the site: " + ", ".join(missing_essential) + "."
        )
        fixes.append(
            Fix(
                title="Link your directory profiles from the site and in sameAs",
                detail=(
                    "Add footer links to "
                    + ", ".join(missing_essential)
                    + ", and list the same URLs in the LocalBusiness sameAs array. This "
                    "is how an assistant confirms that the site, the map listing and the "
                    "review profiles are the same business rather than three "
                    "possibly-different ones."
                ),
                effort=Effort.LOW,
                impact=0.7,
                snippet=_same_as_snippet(found),
                snippet_language="json",
            )
        )

    # -- Internal NAP consistency -----------------------------------------
    schema_phones = _schema_phones(page)
    text_phones = {_normalize_phone(m.group(0)) for m in PHONE_PATTERN.finditer(page.text)}
    text_phones.discard("")

    if schema_phones and text_phones and not (schema_phones & text_phones):
        findings.append(
            f"Phone number mismatch: structured data says {sorted(schema_phones)[0]} "
            f"but the page text shows {sorted(text_phones)[0]}. Conflicting NAP data "
            "lowers an assistant's confidence and can suppress the recommendation."
        )
        fixes.append(
            Fix(
                title="Resolve the conflicting phone numbers on your own site",
                detail=(
                    "Structured data and visible text publish different numbers. Pick "
                    "the correct one and make it identical everywhere — site, schema, "
                    "Google Business Profile, Yelp, and every other listing. NAP "
                    "consistency is a documented input to whether assistants recommend "
                    "a business."
                ),
                effort=Effort.LOW,
                impact=0.8,
            )
        )
    elif len(text_phones) > 2:
        findings.append(
            f"{len(text_phones)} different phone numbers appear on the homepage. If these "
            "are not deliberate (separate departments), consolidate to one."
        )

    # -- Manual verification list ------------------------------------------
    # Confirming a listing exists and matches means opening it, so hand the
    # auditor ready-made search URLs instead of a vague "check your listings".
    verify_urls = _verification_urls(business)
    fixes.append(
        Fix(
            title="Verify NAP consistency across the listings assistants read",
            detail=(
                "Open each link and confirm the business name, address and phone are "
                "character-for-character identical to your site. Assistants "
                "cross-reference these; any disagreement reduces confidence. Reddit is "
                "on the list because it is one of the most-cited sources for business "
                "recommendations — an unanswered thread about your trade in your city "
                "is a gap worth a genuine, non-spammy reply.\n\n"
                + "\n".join(f"  - {label}: {url}" for label, url in verify_urls)
            ),
            effort=Effort.MEDIUM,
            impact=0.85,
        )
    )

    if "Nextdoor" not in found:
        fixes.append(
            Fix(
                title="Claim a Nextdoor business page",
                detail=(
                    "Nextdoor is neighbour-level recommendation data and is read by "
                    "assistants answering local questions. It is under-claimed by most "
                    "local businesses, which makes it cheap visibility."
                ),
                effort=Effort.MEDIUM,
                impact=0.45,
            )
        )

    score = max(0.0, min(1.0, earned / possible)) if possible else 0.0

    if not found or len(missing_essential) == len(ESSENTIAL):
        status = Status.FAIL
        summary = "No directory profiles connected to the site."
    elif missing_essential:
        status = Status.WARN
        summary = f"Missing links to {len(missing_essential)} essential source(s)."
    else:
        status = Status.PASS
        summary = "Core directory profiles are linked and connected."

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
            "profiles_found": found,
            "missing_essential": missing_essential,
            "schema_phones": sorted(schema_phones),
            "text_phones": sorted(text_phones)[:5],
            "verify_urls": dict(verify_urls),
        },
    )


def _schema_phones(page) -> set[str]:
    phones: set[str] = set()
    for node in flatten_json_ld(page.json_ld):
        value = node.get("telephone")
        if isinstance(value, str):
            normalized = _normalize_phone(value)
            if normalized:
                phones.add(normalized)
    return phones


def _normalize_phone(raw: str) -> str:
    """Reduce to the last 10 digits so formatting differences don't false-positive."""
    digits = re.sub(r"\D", "", raw or "")
    return digits[-10:] if len(digits) >= 10 else ""


def _verification_urls(business) -> list[tuple[str, str]]:
    name = quote_plus(business.name)
    name_and_place = quote_plus(f"{business.name} {business.location}".strip())
    category_and_place = quote_plus(
        f"{business.category} {business.location}".strip() or business.name
    )

    return [
        ("Google Business Profile", f"https://www.google.com/search?q={name_and_place}"),
        ("Google Maps", f"https://www.google.com/maps/search/{name_and_place}"),
        ("Yelp", f"https://www.yelp.com/search?find_desc={name}"),
        ("Better Business Bureau", f"https://www.bbb.org/search?find_text={name}"),
        ("Bing Places", f"https://www.bing.com/search?q={name_and_place}"),
        ("Apple Maps listing", f"https://duckduckgo.com/?q={name_and_place}+apple+maps"),
        (
            "Reddit discussion in your category",
            f"https://www.reddit.com/search/?q={category_and_place}",
        ),
        (
            "Reddit mentions of your business",
            f"https://www.reddit.com/search/?q={name}",
        ),
        ("Nextdoor", "https://business.nextdoor.com/en-us/small-business"),
    ]


def _same_as_snippet(found: dict[str, str]) -> str:
    lines = ['  "sameAs": [']
    entries = [
        found.get("Google Business Profile", "[https://www.google.com/maps/place/your-listing]"),
        found.get("Yelp", "[https://www.yelp.com/biz/your-listing]"),
        found.get("Better Business Bureau", "[https://www.bbb.org/us/your-listing]"),
        found.get("Facebook Page", "[https://www.facebook.com/your-page]"),
    ]
    for index, entry in enumerate(entries):
        comma = "," if index < len(entries) - 1 else ""
        lines.append(f'    "{entry}"{comma}')
    lines.append("  ]")
    return "\n".join(lines)
