"""Terminal report rendering."""
from __future__ import annotations

from .audit import blocking_issue
from .models import AuditResult, Effort, Status

WIDTH = 74

_MARK = {
    Status.PASS: "PASS",
    Status.WARN: "WARN",
    Status.FAIL: "FAIL",
    Status.SKIP: "SKIP",
}

_EFFORT_LABEL = {
    Effort.LOW: "minutes",
    Effort.MEDIUM: "hours",
    Effort.HIGH: "ongoing",
}


def render(result: AuditResult, *, show_snippets: bool = False) -> str:
    business = result.business
    lines: list[str] = []

    lines.append("=" * WIDTH)
    lines.append("  CITELOCAL — AI VISIBILITY AUDIT")
    lines.append(f"  {business.name}")
    if business.descriptor:
        lines.append(f"  {business.descriptor}")
    lines.append(f"  {business.website}")
    lines.append(f"  {result.generated_at:%Y-%m-%d %H:%M UTC}")
    lines.append("=" * WIDTH)
    lines.append("")
    if result.site_error:
        lines.append("  !! SITE UNREACHABLE — no score can be calculated")
        lines.extend(_wrap(result.verdict, prefix="  "))
        lines.append("")
        lines.append("  Check the URL, or whether the site blocks non-browser")
        lines.append("  clients. A site that refuses this audit may also be")
        lines.append("  refusing AI crawlers, which is worth investigating.")
    else:
        lines.append(f"  AI VISIBILITY SCORE: {result.score}/100  (grade {result.grade})")
        lines.append(f"  {result.verdict}")
    lines.append("")

    blocker = blocking_issue(result)
    if blocker:
        lines.append("-" * WIDTH)
        lines.append("  !! BLOCKING ISSUE — fix this before anything else")
        lines.extend(_wrap(blocker.summary, prefix="  "))
        lines.append(
            "  Until AI crawlers can read the site, no amount of content or"
        )
        lines.append("  schema work can produce a citation.")
        lines.append("-" * WIDTH)
        lines.append("")

    counts = {status: len(result.by_status(status)) for status in Status}
    lines.append(
        f"  {counts[Status.FAIL]} failing · {counts[Status.WARN]} warnings · "
        f"{counts[Status.PASS]} passing · {counts[Status.SKIP]} skipped"
    )
    lines.append("")

    for check in result.checks:
        lines.append("-" * WIDTH)
        mark = _MARK[check.status]
        if check.status is Status.SKIP:
            lines.append(f"[{mark}] {check.name}")
            lines.extend(_wrap(check.summary, prefix="       "))
            lines.append("")
            continue

        pct = round(check.score * 100)
        lines.append(f"[{mark}] {check.name}  ({pct}%)")
        lines.extend(_wrap(check.summary, prefix="       "))
        if check.findings:
            lines.append("")
            for finding in check.findings:
                lines.extend(_wrap(finding, prefix="       - "))
        lines.append("")

    plan = result.action_plan
    if plan:
        lines.append("=" * WIDTH)
        lines.append("  ACTION PLAN — highest impact first")
        lines.append("=" * WIDTH)
        lines.append("")
        for index, fix in enumerate(plan, start=1):
            lines.extend(_wrap(fix.title, prefix=f"  {index}. "))
            lines.append(
                f"     impact {fix.impact:.2f} · effort: {_EFFORT_LABEL[fix.effort]}"
            )
            for paragraph in fix.detail.split("\n"):
                if paragraph.strip():
                    lines.extend(_wrap(paragraph, prefix="     "))
                else:
                    lines.append("")
            if fix.reference:
                lines.append(f"     where: {fix.reference}")
            if fix.snippet:
                if show_snippets:
                    lines.append("")
                    for snippet_line in fix.snippet.splitlines():
                        lines.append(f"       {snippet_line}")
                else:
                    lines.append(
                        "     (paste-ready snippet available — use --snippets or the HTML report)"
                    )
            lines.append("")

    lines.append("=" * WIDTH)
    lines.append("  Signals are based on publicly documented behaviour of AI search")
    lines.append("  crawlers and structured data. Rankings in AI answers are not")
    lines.append("  guaranteed by any change.")
    lines.append("=" * WIDTH)

    return "\n".join(lines)


def _wrap(text: str, prefix: str = "", width: int = WIDTH) -> list[str]:
    """Wrap `text` to `width`, indenting continuation lines under `prefix`."""
    available = max(20, width - len(prefix))
    words = text.split()
    if not words:
        return []

    out: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= available:
            current += " " + word
        else:
            out.append(prefix + current)
            current = word
    out.append(prefix + current)

    # Continuation lines align under the first line's text, not its bullet.
    indent = " " * len(prefix)
    return [out[0]] + [indent + line[len(prefix):] for line in out[1:]]
