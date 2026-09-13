"""CiteLocal command-line interface.

    python3 -m citelocal.cli --name "Acme Plumbing" --site acmeplumbing.com \
        --city Austin --region TX --category plumber
"""
from __future__ import annotations

import argparse
import json
import sys

from .audit import audit
from .models import Business
from .report import render
from .report_html import render_html


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="citelocal",
        description="Audit a local business's visibility to AI assistants.",
    )
    parser.add_argument("--name", required=True, help="Business name")
    parser.add_argument("--site", required=True, help="Website, e.g. acmeplumbing.com")
    parser.add_argument("--city", default="", help="City, e.g. Austin")
    parser.add_argument("--region", default="", help="State/province, e.g. TX")
    parser.add_argument(
        "--category", default="", help="Plain-language category, e.g. plumber"
    )
    parser.add_argument("--phone", default="", help="Public phone number")
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="Skip the live LLM probe (site checks only, no API key needed)",
    )
    parser.add_argument(
        "--providers",
        default="",
        help="Comma-separated probe providers: anthropic,openai,perplexity "
        "(default: every provider with an API key set)",
    )
    parser.add_argument(
        "--mode",
        choices=("grounded", "memory"),
        default="grounded",
        help="grounded: assistants search the web first (what users see today). "
        "memory: no search, tests the model's built-in knowledge.",
    )
    parser.add_argument(
        "--prompts",
        type=int,
        default=6,
        help="Number of local-intent questions to test (default: 6)",
    )
    parser.add_argument("--snippets", action="store_true", help="Print code snippets inline")
    parser.add_argument("--html", metavar="PATH", help="Write the client-ready HTML report here")
    parser.add_argument("--json", metavar="PATH", help="Write raw results as JSON here")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    business = Business(
        name=args.name,
        website=args.site,
        city=args.city,
        region=args.region,
        category=args.category,
        phone=args.phone,
    )

    providers = [p.strip() for p in args.providers.split(",") if p.strip()] or None

    result = audit(
        business,
        run_probe=not args.no_probe,
        providers=providers,
        probe_mode=args.mode,
        prompt_limit=args.prompts,
    )

    print(render(result, show_snippets=args.snippets))

    if args.html:
        with open(args.html, "w", encoding="utf-8") as handle:
            handle.write(render_html(result))
        print(f"\nHTML report written to {args.html}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(to_dict(result), handle, indent=2)
        print(f"JSON written to {args.json}")

    return 0


def to_dict(result) -> dict:
    """Serializable view of an audit, for storage or an API response."""
    return {
        "business": {
            "name": result.business.name,
            "website": result.business.website,
            "city": result.business.city,
            "region": result.business.region,
            "category": result.business.category,
        },
        "generated_at": result.generated_at.isoformat(),
        "score": result.score,
        "grade": result.grade,
        "verdict": result.verdict,
        "checks": [
            {
                "id": check.id,
                "name": check.name,
                "category": check.category,
                "status": check.status.value,
                "score": round(check.score, 3),
                "weight": check.weight,
                "summary": check.summary,
                "findings": check.findings,
                "evidence": check.evidence,
                "fixes": [
                    {
                        "title": fix.title,
                        "detail": fix.detail,
                        "effort": fix.effort.value,
                        "impact": fix.impact,
                        "snippet": fix.snippet,
                        "reference": fix.reference,
                    }
                    for fix in check.fixes
                ],
            }
            for check in result.checks
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
