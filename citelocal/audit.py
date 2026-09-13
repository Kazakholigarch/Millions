"""Audit orchestration: run the checks and assemble a result."""
from __future__ import annotations

from . import llm_probe
from .checks import content, crawler_access, presence, schema
from .fetch import Fetcher, normalize_url
from .models import AuditResult, Business, CheckResult, Status

# Order matters for the report: foundations first, because a crawler block
# makes every downstream fix pointless until it is cleared.
SITE_CHECKS = (crawler_access, schema, content, presence)


def audit(
    business: Business,
    *,
    run_probe: bool = True,
    providers: list[str] | None = None,
    probe_mode: str = "grounded",
    prompt_limit: int = 6,
) -> AuditResult:
    """Run a full AI-visibility audit.

    The site checks need no credentials. The live probe needs an LLM API key and
    is skipped cleanly when none is configured.
    """
    business.website = normalize_url(business.website)
    checks: list[CheckResult] = []
    site_error: str | None = None

    with Fetcher() as fetcher:
        # Probe the homepage once up front. If the site is unreachable, every
        # site check would skip and the score would collapse to a meaningless
        # value, so record the failure and let the report lead with it.
        home = fetcher.get(business.website)
        if not home.ok:
            site_error = home.error or "unknown error"

        for module in SITE_CHECKS:
            try:
                checks.append(module.run(business, fetcher))
            except Exception as exc:  # noqa: BLE001 - a broken check must not kill the audit
                checks.append(
                    CheckResult.skipped(
                        module.CHECK_ID,
                        module.CHECK_NAME,
                        module.CATEGORY,
                        f"Check failed to run: {type(exc).__name__}: {exc}",
                    )
                )

    if run_probe:
        report = llm_probe.probe(
            business,
            providers=providers,
            prompts=llm_probe.build_prompts(business, limit=prompt_limit),
            mode=probe_mode,
        )
        checks.append(llm_probe.to_check(business, report))
    else:
        checks.append(
            CheckResult.skipped(
                llm_probe.CHECK_ID,
                llm_probe.CHECK_NAME,
                llm_probe.CATEGORY,
                "Live probe disabled for this run.",
            )
        )

    return AuditResult(business=business, checks=_ordered(checks), site_error=site_error)


def _ordered(checks: list[CheckResult]) -> list[CheckResult]:
    """Worst-first within the declared check order, so the report leads with problems."""
    order = {module.CHECK_ID: index for index, module in enumerate(SITE_CHECKS)}
    order[llm_probe.CHECK_ID] = -1  # the probe is the headline finding
    return sorted(checks, key=lambda c: (c.status.rank, order.get(c.id, 99)))


def blocking_issue(result: AuditResult) -> CheckResult | None:
    """The one failure that makes other work pointless, if present.

    A robots.txt block is qualitatively different from the other findings:
    until it is cleared, no amount of content or schema work can produce a
    citation. The report calls this out separately.
    """
    for check in result.checks:
        if check.id == crawler_access.CHECK_ID and check.status is Status.FAIL:
            return check
    return None
