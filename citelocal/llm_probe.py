"""Live visibility probe: ask assistants the questions customers ask.

This is the evidence half of the product. The diagnostic checks explain *why* a
business is hard to cite; this module demonstrates *that* it is not being cited,
by putting real local-intent questions to real assistants and recording who gets
named instead.

Two modes, because they answer different questions:

* ``memory`` — no web search. Tests whether the business exists in the model's
  parametric knowledge at all.
* ``grounded`` — the assistant searches the web first. Tests whether the
  business gets cited in the answers users actually receive today.

Every provider is optional. With no API keys configured the probe returns a
skipped result and the rest of the audit still runs, so the tool is useful
before anyone has spent a cent on inference.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests

from .models import CheckResult, Effort, Fix, Status

CHECK_ID = "live_visibility"
CHECK_NAME = "Live AI visibility probe"
CATEGORY = "Visibility"

DEFAULT_TIMEOUT = 90

# Suffixes to strip when deciding whether two business names refer to the same
# business. "Acme Plumbing LLC" and "Acme Plumbing" must match.
_NAME_NOISE = re.compile(
    r"\b(llc|l\.l\.c|inc|incorporated|co|company|corp|corporation|ltd|limited|"
    r"plc|pllc|pc|group|holdings|services|service|solutions|and sons|& sons)\b",
    re.IGNORECASE,
)


@dataclass
class ProbeAnswer:
    prompt: str
    provider: str
    mode: str
    text: str
    mentioned: bool
    rank: int | None  # 1-based position in the recommendation list, if found
    competitors: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ProbeReport:
    answers: list[ProbeAnswer] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def ran(self) -> int:
        return len([a for a in self.answers if a.error is None])

    @property
    def hits(self) -> int:
        return len([a for a in self.answers if a.mentioned])

    @property
    def visibility_rate(self) -> float:
        return self.hits / self.ran if self.ran else 0.0

    @property
    def competitor_counts(self) -> list[tuple[str, int]]:
        """Competitors ranked by how often assistants recommended them."""
        counts: dict[str, int] = {}
        for answer in self.answers:
            # Count each competitor once per answer.
            for name in set(answer.competitors):
                counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


# --------------------------------------------------------------------------
# Prompt generation
# --------------------------------------------------------------------------
def build_prompts(business, limit: int = 6) -> list[str]:
    """Generate local-intent prompts in the shape real buyers use.

    These deliberately avoid the business name: we are testing discovery, not
    whether the model can look up a name it was handed.
    """
    category = business.category or "local service provider"
    place = business.location or "my area"

    candidates = [
        f"I need a {category} in {place}. Who are the best options?",
        f"Who is the most reputable {category} in {place}?",
        f"Recommend a few reliable {category} companies in {place}.",
        f"Who should I call for emergency {category} service in {place}?",
        f"What are the top-rated {category} businesses near {place}?",
        f"I'm looking for an affordable {category} in {place} with good reviews. Suggestions?",
        f"Which {category} in {place} do people recommend most?",
        f"Best {category} in {place} for same-day service?",
    ]
    return candidates[:limit]


_LIST_INSTRUCTION = (
    "Answer as you normally would for a person asking this. "
    "Include a numbered list of specific named businesses you would recommend, "
    "one per line, with the business name first. If you do not know of specific "
    "named businesses, say so plainly instead of inventing names."
)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
def _anthropic(prompt: str, grounded: bool, model: str | None = None) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    body: dict[str, object] = {
        "model": model or os.environ.get("CITELOCAL_ANTHROPIC_MODEL", "claude-sonnet-5"),
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": f"{prompt}\n\n{_LIST_INSTRUCTION}"}],
    }
    if grounded:
        body["tools"] = [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}
        ]

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    # Content is a list of blocks; tool blocks are interleaved with text blocks.
    return "\n".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    ).strip()


def _openai(prompt: str, grounded: bool, model: str | None = None) -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")

    chosen = model or os.environ.get("CITELOCAL_OPENAI_MODEL", "gpt-4o-mini")
    body: dict[str, object] = {
        "model": chosen,
        "messages": [{"role": "user", "content": f"{prompt}\n\n{_LIST_INSTRUCTION}"}],
        "max_tokens": 1200,
    }
    if grounded:
        # Only the -search-preview models accept web_search_options; for others
        # the caller gets ungrounded output, which we label accordingly.
        if "search" in chosen:
            body["web_search_options"] = {}

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json=body,
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return (payload["choices"][0]["message"].get("content") or "").strip()


def _perplexity(prompt: str, grounded: bool, model: str | None = None) -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not key:
        raise RuntimeError("PERPLEXITY_API_KEY not set")

    response = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {key}", "content-type": "application/json"},
        json={
            "model": model or os.environ.get("CITELOCAL_PERPLEXITY_MODEL", "sonar"),
            "messages": [{"role": "user", "content": f"{prompt}\n\n{_LIST_INSTRUCTION}"}],
        },
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    return (payload["choices"][0]["message"].get("content") or "").strip()


# Perplexity always searches, so it has no meaningful ungrounded mode.
PROVIDERS: dict[str, dict[str, object]] = {
    "anthropic": {"call": _anthropic, "env": "ANTHROPIC_API_KEY", "label": "Claude", "grounded": True},
    "openai": {"call": _openai, "env": "OPENAI_API_KEY", "label": "ChatGPT", "grounded": True},
    "perplexity": {
        "call": _perplexity,
        "env": "PERPLEXITY_API_KEY",
        "label": "Perplexity",
        "grounded": True,
        "always_grounded": True,
    },
}


def available_providers() -> list[str]:
    return [name for name, spec in PROVIDERS.items() if os.environ.get(str(spec["env"]))]


# --------------------------------------------------------------------------
# Response analysis
# --------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    text = name.lower()
    text = re.sub(r"[^\w\s&]", " ", text)
    text = _NAME_NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def distinctive_tokens(name: str) -> list[str]:
    """Tokens that identify the business, ignoring generic trade words."""
    generic = {
        "plumbing", "plumber", "electric", "electrical", "hvac", "heating",
        "cooling", "air", "roofing", "roof", "dental", "dentistry", "clinic",
        "salon", "spa", "law", "legal", "auto", "repair", "the", "and", "of",
        "for", "your", "best", "pro", "professional", "quality", "service",
        "services", "home", "family", "brothers", "sons", "construction",
    }
    return [t for t in normalize_name(name).split() if t not in generic and len(t) > 2]


def mentions_business(text: str, business_name: str) -> bool:
    """Does this answer name the business?

    Requires the distinctive part of the name, so a plumber called
    "Precision Plumbing" is not matched by an answer that merely says
    "plumbing".
    """
    haystack = normalize_name(text)
    full = normalize_name(business_name)
    if full and full in haystack:
        return True

    tokens = distinctive_tokens(business_name)
    if not tokens:
        return bool(full) and full in haystack
    # All distinctive tokens must appear for a multi-token name; a single
    # distinctive token must appear as a whole word.
    if len(tokens) == 1:
        return re.search(rf"\b{re.escape(tokens[0])}\b", haystack) is not None
    return all(re.search(rf"\b{re.escape(t)}\b", haystack) for t in tokens)


_LIST_LINE = re.compile(r"^\s*(?:(\d{1,2})[.)]|[-*•])\s+(.*)$")
_EMPHASIS = re.compile(r"\*\*|__|(?<!\w)[*_](?!\w)")
# A colon or pipe needs no leading space ("Name: detail"), but a dash does, so
# that hyphenated names like "Jean-Luc Plumbing" survive intact.
_SEPARATOR = re.compile(r"\s*[:|]\s+|\s+[-–—]\s+|(?<=[a-z)])\.\s+|,\s+(?=[a-z])")

# Lines that are commentary rather than a recommendation.
_NOT_A_NAME = (
    "i don", "i do not", "i cannot", "i can not", "note", "disclaimer",
    "however", "keep in mind", "important", "caveat", "please", "make sure",
    "check ", "verify", "always ", "consider ",
)


def extract_recommendations(text: str) -> list[str]:
    """Pull named businesses out of a recommendation list."""
    names: list[str] = []
    for line in text.splitlines():
        match = _LIST_LINE.match(line)
        if not match:
            continue
        body = match.group(2)
        body = re.sub(r"\[\d+\]", "", body)  # drop citation markers
        body = _EMPHASIS.sub("", body).strip()  # bold/italic anywhere in the line
        # The name is whatever precedes the first separator or sentence end.
        name = _SEPARATOR.split(body, maxsplit=1)[0]
        # Drop a trailing "(4.8 stars)" style parenthetical, then punctuation.
        name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
        name = name.strip(" .,:;–—-").strip()
        if 2 < len(name) <= 70 and not name.lower().startswith(_NOT_A_NAME):
            names.append(name)
    return names


def find_rank(text: str, business_name: str) -> int | None:
    """1-based position of the business in the recommendation list."""
    for index, name in enumerate(extract_recommendations(text), start=1):
        if mentions_business(name, business_name):
            return index
    return None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def probe(
    business,
    providers: list[str] | None = None,
    prompts: list[str] | None = None,
    mode: str = "grounded",
) -> ProbeReport:
    report = ProbeReport()
    chosen = providers if providers is not None else available_providers()
    chosen = [p for p in chosen if p in PROVIDERS]

    if not chosen:
        report.skipped_reason = (
            "No LLM API key configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or "
            "PERPLEXITY_API_KEY to run the live visibility probe."
        )
        return report

    prompt_list = prompts if prompts is not None else build_prompts(business)
    grounded = mode == "grounded"

    for provider in chosen:
        spec = PROVIDERS[provider]
        call = spec["call"]
        report.providers_used.append(str(spec["label"]))
        effective_mode = "grounded" if (grounded or spec.get("always_grounded")) else "memory"

        for prompt in prompt_list:
            try:
                text = call(prompt, grounded)  # type: ignore[operator]
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the probe
                report.answers.append(
                    ProbeAnswer(
                        prompt=prompt,
                        provider=str(spec["label"]),
                        mode=effective_mode,
                        text="",
                        mentioned=False,
                        rank=None,
                        error=_short_error(exc),
                    )
                )
                continue

            recommendations = extract_recommendations(text)
            mentioned = mentions_business(text, business.name)
            report.answers.append(
                ProbeAnswer(
                    prompt=prompt,
                    provider=str(spec["label"]),
                    mode=effective_mode,
                    text=text,
                    mentioned=mentioned,
                    rank=find_rank(text, business.name),
                    competitors=[
                        name
                        for name in recommendations
                        if not mentions_business(name, business.name)
                    ],
                )
            )

    return report


def to_check(business, report: ProbeReport) -> CheckResult:
    """Turn a probe report into a scored check for the audit."""
    if report.skipped_reason:
        return CheckResult.skipped(CHECK_ID, CHECK_NAME, CATEGORY, report.skipped_reason)

    if not report.ran:
        errors = {a.error for a in report.answers if a.error}
        return CheckResult.skipped(
            CHECK_ID,
            CHECK_NAME,
            CATEGORY,
            "Every probe request failed: " + "; ".join(sorted(e for e in errors if e)),
        )

    findings: list[str] = []
    fixes: list[Fix] = []
    rate = report.visibility_rate

    findings.append(
        f"Asked {report.ran} local-intent question(s) across "
        f"{', '.join(report.providers_used)}. "
        f"{business.name} was named in {report.hits} of them "
        f"({rate * 100:.0f}%)."
    )

    ranks = [a.rank for a in report.answers if a.rank]
    if ranks:
        findings.append(
            f"When named, average position in the recommendation list was "
            f"{sum(ranks) / len(ranks):.1f}."
        )

    competitors = report.competitor_counts
    if competitors:
        top = ", ".join(f"{name} ({count}x)" for name, count in competitors[:8])
        findings.append(f"Recommended instead: {top}.")

    misses = [a for a in report.answers if a.error is None and not a.mentioned]
    for answer in misses[:3]:
        findings.append(f'Not mentioned for "{answer.prompt}" ({answer.provider}).')

    failed = [a for a in report.answers if a.error]
    if failed:
        findings.append(f"{len(failed)} probe request(s) failed: {failed[0].error}")

    if rate == 0:
        competitor_names = ", ".join(name for name, _ in competitors[:5]) or "other businesses"
        fixes.append(
            Fix(
                title="Close the visibility gap against the competitors being named",
                detail=(
                    f"Across {report.ran} buyer-intent questions, assistants never "
                    f"named {business.name}; they named {competitor_names} instead. "
                    "Work the Foundations and Authority fixes in this report first "
                    "(crawler access, then structured data, then directory "
                    "consistency), then re-run this probe to measure movement. "
                    "Treat the competitors above as the benchmark: whatever sources "
                    "cite them are the sources you need to appear in."
                ),
                effort=Effort.HIGH,
                impact=0.9,
            )
        )

    if rate == 0:
        status, summary = Status.FAIL, "Never recommended in any tested question."
    elif rate < 0.4:
        status, summary = Status.WARN, f"Recommended in only {rate * 100:.0f}% of questions."
    else:
        status, summary = Status.PASS, f"Recommended in {rate * 100:.0f}% of questions."

    return CheckResult(
        id=CHECK_ID,
        name=CHECK_NAME,
        category=CATEGORY,
        status=status,
        score=min(1.0, rate * 1.25),  # ~80% presence counts as full marks
        weight=3.0,
        summary=summary,
        findings=findings,
        fixes=fixes,
        evidence={
            "questions_asked": report.ran,
            "times_mentioned": report.hits,
            "visibility_rate": round(rate, 3),
            "providers": report.providers_used,
            "top_competitors": competitors[:10],
            "prompts": [a.prompt for a in report.answers],
        },
    )


def _short_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        detail = exc.response.text[:200].replace("\n", " ")
        return f"HTTP {code}: {detail}"
    if isinstance(exc, requests.Timeout):
        return "request timed out"
    return f"{type(exc).__name__}: {str(exc)[:160]}"
