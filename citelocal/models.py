"""Core data types for a CiteLocal AI-visibility audit.

The audit model is deliberately simple: a `Business` goes in, a list of
`CheckResult`s comes out, and each result carries its own `Fix` objects so the
report can be assembled without the renderer knowing anything about individual
checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

# Status ordering matters for report sorting: worst first.
class Status(str, Enum):
    FAIL = "fail"
    WARN = "warn"
    PASS = "pass"
    SKIP = "skip"

    @property
    def rank(self) -> int:
        return {"fail": 0, "warn": 1, "pass": 2, "skip": 3}[self.value]


class Effort(str, Enum):
    """How much work a fix is for the business (or its agency)."""

    LOW = "low"  # paste a snippet, flip a setting — minutes
    MEDIUM = "medium"  # write some content, claim a listing — hours
    HIGH = "high"  # ongoing work — weeks


@dataclass
class Fix:
    """A concrete, actionable remediation step.

    `snippet` is what makes the product more than a scoreboard: where we can
    generate the exact code or text to paste, we do.
    """

    title: str
    detail: str
    effort: Effort
    impact: float  # 0..1, used to rank the action plan
    snippet: str | None = None
    snippet_language: str = "html"
    reference: str | None = None


@dataclass
class CheckResult:
    """Outcome of one diagnostic check."""

    id: str
    name: str
    category: str
    status: Status
    score: float  # 0..1, fraction of this check's weight earned
    weight: float  # relative importance in the overall score
    summary: str
    findings: list[str] = field(default_factory=list)
    fixes: list[Fix] = field(default_factory=list)
    evidence: dict[str, object] = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight

    @classmethod
    def skipped(cls, check_id: str, name: str, category: str, reason: str) -> CheckResult:
        """A check that could not run. Skipped checks are excluded from scoring."""
        return cls(
            id=check_id,
            name=name,
            category=category,
            status=Status.SKIP,
            score=0.0,
            weight=0.0,
            summary=reason,
        )


@dataclass
class Business:
    """The subject of an audit."""

    name: str
    website: str
    city: str = ""
    region: str = ""  # state / province
    category: str = ""  # "plumber", "dental practice", "med spa", ...
    phone: str = ""

    @property
    def location(self) -> str:
        parts = [p for p in (self.city, self.region) if p]
        return ", ".join(parts)

    @property
    def descriptor(self) -> str:
        """Human label used in generated prompts and report headers."""
        bits = [self.category or "business"]
        if self.location:
            bits.append(f"in {self.location}")
        return " ".join(bits)


@dataclass
class AuditResult:
    business: Business
    checks: list[CheckResult]
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Set when the site itself could not be loaded. A score computed from zero
    # successful checks would read as a perfect result, so callers must show
    # this instead of the score.
    site_error: str | None = None

    @property
    def reachable(self) -> bool:
        return self.site_error is None

    @property
    def scored_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status is not Status.SKIP and c.weight > 0]

    @property
    def score(self) -> int:
        """Overall AI-visibility score, 0-100."""
        scored = self.scored_checks
        total_weight = sum(c.weight for c in scored)
        if not total_weight:
            return 0
        return round(100 * sum(c.weighted_score for c in scored) / total_weight)

    @property
    def grade(self) -> str:
        score = self.score
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 65:
            return "C"
        if score >= 50:
            return "D"
        return "F"

    @property
    def verdict(self) -> str:
        """One-line summary an agency can read aloud on a sales call."""
        if self.site_error:
            return f"Site could not be loaded ({self.site_error}) — audit incomplete."
        score = self.score
        if score >= 90:
            return "Strong AI visibility foundation — maintain and monitor."
        if score >= 80:
            return "Good foundation with specific gaps worth closing."
        if score >= 65:
            return "Partially visible to AI assistants — several high-impact gaps."
        if score >= 50:
            return "Weak AI visibility — AI assistants have little reason to cite you."
        return "Effectively invisible to AI assistants — urgent fixes needed."

    def by_status(self, status: Status) -> list[CheckResult]:
        return [c for c in self.checks if c.status is status]

    @property
    def action_plan(self) -> list[Fix]:
        """All fixes across all checks, highest impact first."""
        fixes: list[Fix] = []
        for check in self.checks:
            fixes.extend(check.fixes)
        return sorted(fixes, key=lambda f: -f.impact)
