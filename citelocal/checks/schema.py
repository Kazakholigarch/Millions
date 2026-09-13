"""Check: structured data an AI assistant can resolve into an entity.

Two things drive citation for a local business:

* A `LocalBusiness` node (ideally a specific subtype) with complete NAP data.
  This is what lets an assistant answer "what's their number" or "are they open
  now" with confidence instead of hedging or skipping the business.
* An `FAQPage` node. Pages carrying FAQ schema are markedly more likely to be
  cited, because the Q&A shape maps directly onto how people query assistants.
"""
from __future__ import annotations

from ..fetch import Fetcher
from ..html_utils import flatten_json_ld, parse, types_of
from ..models import CheckResult, Effort, Fix, Status
from ..vocab import is_local_business_type, schema_type_for

CHECK_ID = "structured_data"
CHECK_NAME = "Structured data (LocalBusiness + FAQ schema)"
CATEGORY = "Foundations"

# Fields that make a LocalBusiness node genuinely useful, with the weight each
# carries toward this check's score.
CORE_FIELDS: dict[str, tuple[float, str]] = {
    "name": (1.0, "Business name"),
    "address": (1.5, "Full postal address"),
    "telephone": (1.2, "Phone number"),
    "url": (0.6, "Canonical website URL"),
}

RECOMMENDED_FIELDS: dict[str, tuple[float, str]] = {
    "openingHoursSpecification": (0.9, "Opening hours (structured)"),
    "geo": (0.6, "Latitude/longitude"),
    "image": (0.4, "Business image"),
    "sameAs": (0.9, "Links to your profiles elsewhere (GBP, Yelp, Facebook)"),
    "aggregateRating": (0.8, "Review rating"),
    "areaServed": (0.7, "Service area"),
    "description": (0.5, "Description"),
    "priceRange": (0.3, "Price range"),
}

ADDRESS_PARTS = ("streetAddress", "addressLocality", "addressRegion", "postalCode")


def run(business, fetcher: Fetcher) -> CheckResult:
    home = fetcher.get(business.website)
    if not home.ok:
        return CheckResult.skipped(
            CHECK_ID,
            CHECK_NAME,
            CATEGORY,
            f"Could not load {business.website} ({home.error}) — structured data not checked.",
        )

    page = parse(home.text)
    nodes = flatten_json_ld(page.json_ld)

    findings: list[str] = list(page.json_ld_errors)
    fixes: list[Fix] = []

    local_nodes = [n for n in nodes if any(is_local_business_type(t) for t in types_of(n))]
    faq_nodes = [n for n in nodes if "FAQPage" in types_of(n)]
    # Organization alone is not enough for local intent, but it is a partial signal.
    strict_local = [
        n for n in local_nodes if any(t != "Organization" for t in types_of(n))
    ]

    earned = 0.0
    possible = sum(w for w, _ in CORE_FIELDS.values())
    possible += sum(w for w, _ in RECOMMENDED_FIELDS.values())
    possible += 2.0  # LocalBusiness node present
    possible += 1.0  # specific subtype
    possible += 1.5  # FAQPage present

    desired_type = schema_type_for(business.category)

    if strict_local:
        earned += 2.0
        node = _best_node(strict_local)
        present_types = types_of(node)
        findings.append(f"LocalBusiness structured data found (@type: {', '.join(present_types)}).")

        if any(t not in ("LocalBusiness", "Organization") for t in present_types):
            earned += 1.0
        else:
            findings.append(
                f"@type is generic. A specific subtype such as '{desired_type}' helps "
                "assistants classify the business for category-specific questions."
            )
            fixes.append(
                Fix(
                    title=f"Use the specific schema type '{desired_type}'",
                    detail=(
                        f"The markup declares the generic '{present_types[0]}'. Changing "
                        f"@type to '{desired_type}' tells assistants what kind of business "
                        "this is, which is what category queries match against."
                    ),
                    effort=Effort.LOW,
                    impact=0.55,
                )
            )

        missing_core: list[str] = []
        for field, (weight, label) in CORE_FIELDS.items():
            if not _has_field(node, field):
                missing_core.append(label)
            elif field == "address":
                # Address is graded rather than pass/fail: a bare string is
                # worth less than a full PostalAddress.
                credit, note = _address_completeness(node.get("address"))
                earned += credit
                if note:
                    findings.append(note)
            else:
                earned += weight

        missing_recommended: list[str] = []
        for field, (weight, label) in RECOMMENDED_FIELDS.items():
            if _has_field(node, field):
                earned += weight
            else:
                missing_recommended.append(label)

        if missing_core:
            findings.append(f"Missing required fields: {', '.join(missing_core)}.")
        if missing_recommended:
            findings.append(f"Missing recommended fields: {', '.join(missing_recommended)}.")

        if missing_core or missing_recommended:
            fixes.append(
                Fix(
                    title="Complete the LocalBusiness structured data",
                    detail=(
                        "Assistants prefer sources whose facts they can state without "
                        "hedging. Missing: "
                        + ", ".join(missing_core + missing_recommended)
                        + ". The snippet below is a complete node built from this "
                        "audit's inputs — fill the bracketed values and replace the "
                        "existing block."
                    ),
                    effort=Effort.LOW,
                    impact=0.7 if missing_core else 0.45,
                    snippet=build_local_business_jsonld(business),
                    reference="Place in <head> of the homepage",
                )
            )
    else:
        has_microdata = any(
            is_local_business_type(t) for t in page.microdata_types
        )
        if local_nodes:
            findings.append(
                "Only an 'Organization' node was found. For local queries, assistants "
                "look for a LocalBusiness type carrying address and service-area data."
            )
        elif has_microdata:
            findings.append(
                "Legacy microdata markup found but no JSON-LD. JSON-LD is the format "
                "Google and the AI crawlers parse most reliably."
            )
        else:
            findings.append("No LocalBusiness structured data found on the homepage.")

        fixes.append(
            Fix(
                title=f"Add {desired_type} structured data to the homepage",
                detail=(
                    "This is the single most mechanical fix in the report. Without it, "
                    "an assistant has to infer the address, phone, hours and service "
                    "area from prose — and will often skip the business rather than "
                    "risk stating something wrong. Paste this into the homepage <head> "
                    "and fill the bracketed values."
                ),
                effort=Effort.LOW,
                impact=0.95,
                snippet=build_local_business_jsonld(business),
                reference="Place in <head> of the homepage",
            )
        )

    if faq_nodes:
        earned += 1.5
        findings.append("FAQPage structured data found.")
    else:
        findings.append(
            "No FAQPage structured data. FAQ markup is one of the strongest "
            "citation signals because its Q&A shape matches how people ask assistants."
        )
        fixes.append(
            Fix(
                title="Add FAQPage structured data",
                detail=(
                    "Publish the questions customers actually ask — pricing, response "
                    "time, service area, emergency availability — as an FAQ with "
                    "FAQPage markup. Each answered question becomes a passage an "
                    "assistant can lift directly into its response."
                ),
                effort=Effort.MEDIUM,
                impact=0.8,
                snippet=build_faq_jsonld(business),
                reference="Place on a /faq page or the homepage",
            )
        )

    if page.json_ld_errors:
        fixes.append(
            Fix(
                title="Fix invalid JSON-LD syntax",
                detail=(
                    "At least one structured-data block has a JSON syntax error. "
                    "Parsers discard the whole block when this happens, so the markup "
                    "delivers nothing even though it is on the page."
                ),
                effort=Effort.LOW,
                impact=0.85,
            )
        )

    score = max(0.0, min(1.0, earned / possible)) if possible else 0.0

    if not strict_local:
        status = Status.FAIL
        summary = "No LocalBusiness structured data — assistants must guess at the basics."
    elif score < 0.65:
        status = Status.WARN
        summary = "Structured data present but incomplete."
    else:
        status = Status.PASS
        summary = "Structured data is present and reasonably complete."

    return CheckResult(
        id=CHECK_ID,
        name=CHECK_NAME,
        category=CATEGORY,
        status=status,
        score=score,
        weight=2.5,
        summary=summary,
        findings=findings,
        fixes=fixes,
        evidence={
            "json_ld_blocks": len(page.json_ld),
            "types_found": sorted({t for n in nodes for t in types_of(n)}),
            "has_faq": bool(faq_nodes),
            "desired_type": desired_type,
        },
    )


def _best_node(nodes: list[dict]) -> dict:
    """Pick the most complete LocalBusiness node when a page declares several."""
    return max(nodes, key=lambda n: sum(1 for f in CORE_FIELDS if _has_field(n, f)))


def _has_field(node: dict, field: str) -> bool:
    value = node.get(field)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _address_completeness(address: object) -> tuple[float, str | None]:
    """Grade the address rather than treating any value as complete.

    Returns (credit out of CORE_FIELDS['address'] weight, optional finding).
    """
    max_weight = CORE_FIELDS["address"][0]
    if isinstance(address, list) and address:
        address = address[0]
    if isinstance(address, str):
        return max_weight * 0.5, (
            "Address is a plain string. A structured PostalAddress with separate "
            "street, city, region and postal code is parsed far more reliably."
        )
    if not isinstance(address, dict):
        return 0.0, "Address field present but not readable as an address."

    present = [p for p in ADDRESS_PARTS if str(address.get(p, "")).strip()]
    if len(present) == len(ADDRESS_PARTS):
        return max_weight, None
    missing = [p for p in ADDRESS_PARTS if p not in present]
    return (
        max_weight * (len(present) / len(ADDRESS_PARTS)),
        f"PostalAddress is missing: {', '.join(missing)}.",
    )


def build_local_business_jsonld(business) -> str:
    """Generate a complete, paste-ready LocalBusiness node."""
    schema_type = schema_type_for(business.category)
    site = business.website.rstrip("/")
    phone = business.phone or "[+1-555-000-0000]"
    city = business.city or "[City]"
    region = business.region or "[ST]"

    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "{schema_type}",
  "@id": "{site}/#business",
  "name": "{business.name}",
  "url": "{site}",
  "telephone": "{phone}",
  "description": "[One sentence: what you do, where, and what makes you the right call.]",
  "image": "{site}/[storefront-or-team-photo.jpg]",
  "priceRange": "[$$]",
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": "[123 Example St]",
    "addressLocality": "{city}",
    "addressRegion": "{region}",
    "postalCode": "[00000]",
    "addressCountry": "US"
  }},
  "geo": {{
    "@type": "GeoCoordinates",
    "latitude": "[00.0000]",
    "longitude": "[-00.0000]"
  }},
  "areaServed": [
    {{ "@type": "City", "name": "{city}" }},
    {{ "@type": "City", "name": "[Nearby town you serve]" }}
  ],
  "openingHoursSpecification": [
    {{
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
      "opens": "08:00",
      "closes": "17:00"
    }},
    {{
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Saturday"],
      "opens": "09:00",
      "closes": "13:00"
    }}
  ],
  "sameAs": [
    "[https://www.google.com/maps/place/your-listing]",
    "[https://www.yelp.com/biz/your-listing]",
    "[https://www.facebook.com/your-page]"
  ]
}}
</script>"""


def build_faq_jsonld(business) -> str:
    """Generate FAQ markup seeded with the questions local buyers actually ask."""
    what = business.category or "your services"
    where = business.location or "[your area]"

    questions = [
        (
            f"How much does {what} cost in {where}?",
            "[Give a real range and what moves it. Assistants skip vague answers, "
            "and a concrete range is the passage they quote.]",
        ),
        (
            f"How quickly can you come out in {where}?",
            "[State a real response time, e.g. same-day for calls before 2pm.]",
        ),
        (
            "What areas do you serve?",
            f"[List {where} and the surrounding towns by name — this is how "
            "you match 'near me' questions for each one.]",
        ),
        (
            "Are you licensed and insured?",
            "[State license number and insurance. Trust signals affect whether an "
            "assistant recommends you over a competitor.]",
        ),
        (
            "Do you offer emergency or after-hours service?",
            "[Answer plainly, with hours and any call-out fee.]",
        ),
    ]

    entities = ",\n".join(
        f"""    {{
      "@type": "Question",
      "name": "{q}",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "{a}"
      }}
    }}"""
        for q, a in questions
    )

    return f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
{entities}
  ]
}}
</script>"""
