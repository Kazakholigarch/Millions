"""The client-facing deliverable — Markdown and standalone HTML.

This is the artifact a prospect asked for when they replied "send it". It has
one job beyond conveying information: to look like it came from someone worth
paying. A report that reads as a mail-merge undoes the credibility the
measurement just bought.

Two honesty rules are load-bearing here:

* The **scope section is not boilerplate.** This scan reads a homepage and a few
  probes. Saying so plainly is what stops "you missed X" from becoming a refund
  conversation, and a prospect who sees you describe your own limits accurately
  is more inclined to believe the rest.
* **No invented figures.** Same rule as `outreach`. Effort hours are estimates
  and are labelled as estimates.
"""
from __future__ import annotations

import html
from datetime import datetime

from .checks import CATEGORIES
from .scan import AuditResult
from .score import Assessment, assess

SEVERITY_LABEL = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}
SEVERITY_BLURB = {
    "critical": "Costing you money or visibility right now. Fix first.",
    "high": "Material impact on revenue, traffic or trust.",
    "medium": "Worth fixing — meaningful but not urgent.",
    "low": "Polish. Cheap to do while you're in there.",
}
CATEGORY_LABEL = {
    "performance": "Speed",
    "security": "Security",
    "seo": "Search visibility",
    "mobile": "Mobile",
    "conversion": "Turning visitors into customers",
    "trust": "Credibility",
}

def _phase_note(result: AuditResult, assessment: Assessment) -> str | None:
    """Say plainly when the quoted package is phase one rather than everything.

    Without this the report states a total effort figure and then quotes a
    package scoped well below it, which reads as either a mistake or a
    lowball. Naming it as a first phase is honest about what the money buys
    and names the follow-on engagement at the same time.
    """
    if assessment.scaled_hours <= assessment.package.scope_hours:
        return None
    remaining = round(assessment.scaled_hours - assessment.package.scope_hours, 1)
    return (
        f"This covers roughly {assessment.package.scope_hours} hours — the critical "
        f"and high-severity findings first. The full list above totals about "
        f"{assessment.scaled_hours} hours, so the remaining ~{remaining} hours of "
        "medium and low-severity work would follow in a second phase or under a "
        "monthly retainer."
    )


SCOPE_NOTE = (
    "This audit measures the homepage as a browser receives it, plus robots.txt, "
    "the XML sitemap, the HTTP-to-HTTPS redirect, a sample of internal links and "
    "a missing-page probe. It does not execute JavaScript, log into anything, or "
    "crawl the full site — so issues that only appear after login, deeper in the "
    "site, or in client-rendered content are out of scope here. Every figure "
    "quoted was measured directly at the time of the scan."
)
ESTIMATE_NOTE = (
    "Effort figures are estimates for scoping, not quotes. Actual time depends on "
    "the stack and on how much of it can be changed safely."
)


def render_markdown(result: AuditResult, assessment: Assessment | None = None) -> str:
    """The audit as Markdown — good for email, issues, or pasting into a doc."""
    assessment = assessment or assess(result)
    lines: list[str] = []

    lines += [
        f"# Site audit — {result.domain}",
        "",
        f"**Scanned** {_pretty_date(result.scanned_at)}  ",
        f"**Health score** {assessment.health_score}/100 (grade {assessment.grade})  ",
        f"**Issues found** {len(result.findings)}  ",
        f"**Estimated effort to clear** {assessment.scaled_hours} hours",
        "",
    ]

    if not result.ok:
        lines += [f"> The scan could not complete: {result.error}", ""]
        return "\n".join(lines)

    lines += ["## What we measured", "", _measurements_table(result), ""]

    counts = result.severity_counts
    lines += [
        "## Summary",
        "",
        f"We found **{counts['critical']} critical**, **{counts['high']} high**, "
        f"**{counts['medium']} medium** and **{counts['low']} low** severity issues.",
        "",
    ]

    if assessment.headline:
        lines += [
            "The single most valuable thing to fix first:",
            "",
            f"> **{assessment.headline.title}** — {assessment.headline.evidence}",
            "",
        ]

    if assessment.quick_wins:
        lines += ["### Quick wins", "", "Severe, but cheap to fix:", ""]
        for win in assessment.quick_wins:
            lines.append(f"- **{win.title}** — {win.fix} *(~{win.effort_hours}h)*")
        lines.append("")

    lines += ["## Findings", ""]
    for severity in ("critical", "high", "medium", "low"):
        group = result.by_severity(severity)
        if not group:
            continue
        lines += [
            f"### {SEVERITY_LABEL[severity]} ({len(group)})",
            "",
            f"*{SEVERITY_BLURB[severity]}*",
            "",
        ]
        for finding in group:
            lines += [
                f"#### {finding.title}",
                "",
                f"- **What we measured:** {finding.evidence}",
                f"- **Why it matters:** {finding.impact}",
                f"- **How to fix it:** {finding.fix}",
                f"- **Estimated effort:** {finding.effort_hours}h"
                + ("  *(heuristic — worth confirming)*" if finding.confidence == "medium" else ""),
                "",
            ]

    package = assessment.package
    lines += [
        "## Recommended next step",
        "",
        f"**{package.name}** — ${package.price:,}",
        "",
        package.summary,
        "",
    ]
    for item in package.includes:
        lines.append(f"- {item}")
    phase = _phase_note(result, assessment)
    if phase:
        lines += ["", f"*{phase}*"]
    lines += ["", "## Scope and method", "", SCOPE_NOTE, "", ESTIMATE_NOTE, ""]
    if result.notes:
        lines += ["**Notes from this scan:**", ""] + [f"- {n}" for n in result.notes] + [""]
    return "\n".join(lines)


def render_html(result: AuditResult, assessment: Assessment | None = None) -> str:
    """Standalone HTML — no external assets, prints cleanly to PDF."""
    assessment = assessment or assess(result)
    e = html.escape
    counts = result.severity_counts

    if not result.ok:
        body = f'<p class="error">The scan could not complete: {e(str(result.error))}</p>'
        return _HTML_SHELL.format(
            domain=e(result.domain), css=_CSS, scanned=_pretty_date(result.scanned_at),
            score="—", grade="—", score_class="grade-f", body=body,
        )

    parts: list[str] = []

    parts.append('<section class="cards">')
    for label, value in (
        ("Critical", counts["critical"]),
        ("High", counts["high"]),
        ("Medium", counts["medium"]),
        ("Low", counts["low"]),
    ):
        cls = f"card sev-{label.lower()}" if value else "card sev-none"
        parts.append(f'<div class="{cls}"><span class="num">{value}</span><span class="lbl">{label}</span></div>')
    parts.append(
        f'<div class="card"><span class="num">{assessment.scaled_hours}h</span>'
        '<span class="lbl">Est. effort</span></div></section>'
    )

    parts.append("<h2>What we measured</h2><table class=\"metrics\"><tbody>")
    for label, value in _measurement_rows(result):
        parts.append(f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>")
    parts.append("</tbody></table>")

    if assessment.headline:
        h = assessment.headline
        parts.append(
            f'<div class="headline"><h2>Fix this first</h2><h3>{e(h.title)}</h3>'
            f"<p class=\"evidence\">{e(h.evidence)}</p><p>{e(h.impact)}</p></div>"
        )

    if assessment.quick_wins:
        parts.append('<h2>Quick wins</h2><p class="sub">Severe, but cheap to fix.</p><ul class="wins">')
        for win in assessment.quick_wins:
            parts.append(f"<li><strong>{e(win.title)}</strong> — {e(win.fix)} <em>(~{win.effort_hours}h)</em></li>")
        parts.append("</ul>")

    parts.append("<h2>All findings</h2>")
    for severity in ("critical", "high", "medium", "low"):
        group = result.by_severity(severity)
        if not group:
            continue
        parts.append(
            f'<h3 class="sevhead sev-{severity}">{SEVERITY_LABEL[severity]} '
            f'<span class="count">{len(group)}</span></h3>'
            f'<p class="sub">{e(SEVERITY_BLURB[severity])}</p>'
        )
        for finding in group:
            flag = ' <span class="tag">heuristic</span>' if finding.confidence == "medium" else ""
            parts.append(
                f'<article class="finding sev-{severity}">'
                f"<h4>{e(finding.title)}{flag}</h4>"
                f'<dl><dt>Measured</dt><dd class="evidence">{e(finding.evidence)}</dd>'
                f"<dt>Why it matters</dt><dd>{e(finding.impact)}</dd>"
                f"<dt>Fix</dt><dd>{e(finding.fix)}</dd>"
                f"<dt>Effort</dt><dd>{finding.effort_hours}h (estimate)</dd></dl></article>"
            )

    package = assessment.package
    includes = "".join(f"<li>{e(i)}</li>" for i in package.includes)
    phase = _phase_note(result, assessment)
    phase_html = f'<p class="phase">{e(phase)}</p>' if phase else ""
    parts.append(
        f'<div class="package"><h2>Recommended next step</h2>'
        f"<h3>{e(package.name)} — ${package.price:,}</h3><p>{e(package.summary)}</p>"
        f"<ul>{includes}</ul>{phase_html}</div>"
    )

    notes = ""
    if result.notes:
        notes = "<ul>" + "".join(f"<li>{e(n)}</li>" for n in result.notes) + "</ul>"
    parts.append(
        f'<div class="scope"><h2>Scope and method</h2><p>{e(SCOPE_NOTE)}</p>'
        f"<p>{e(ESTIMATE_NOTE)}</p>{notes}</div>"
    )

    return _HTML_SHELL.format(
        domain=e(result.domain),
        css=_CSS,
        scanned=_pretty_date(result.scanned_at),
        score=assessment.health_score,
        grade=assessment.grade,
        score_class=f"grade-{assessment.grade.lower()}",
        body="".join(parts),
    )


# -- shared helpers ----------------------------------------------------------


def _measurement_rows(result: AuditResult) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if result.ttfb_ms is not None:
        rows.append(("Server response time", f"{result.ttfb_ms:,.0f} ms"))
    if result.total_ms is not None:
        rows.append(("HTML download time", f"{result.total_ms / 1000:,.2f} s"))
    if result.html_kb is not None:
        rows.append(("HTML size", f"{result.html_kb:,.1f} KB"))
    rows.append(("Words on the page", f"{result.word_count:,}"))
    rows.append(("Images", f"{result.images_total:,}"))
    if result.links_checked:
        rows.append(("Internal links checked", f"{result.links_checked} ({result.broken_links} broken)"))
    if result.sitemap_urls:
        rows.append(("URLs in sitemap", f"{result.sitemap_urls:,}"))
    rows.append(("Analytics detected", ", ".join(result.analytics) if result.analytics else "none"))
    if result.cdn:
        rows.append(("CDN / host", result.cdn))
    by_category = [
        f"{CATEGORY_LABEL.get(c, c)}: {len(result.by_category(c))}"
        for c in CATEGORIES
        if result.by_category(c)
    ]
    if by_category:
        rows.append(("Issues by area", " · ".join(by_category)))
    return rows


def _measurements_table(result: AuditResult) -> str:
    rows = _measurement_rows(result)
    out = ["| Measurement | Value |", "| --- | --- |"]
    out += [f"| {label} | {value} |" for label, value in rows]
    return "\n".join(out)


def _pretty_date(raw: str) -> str:
    try:
        return datetime.fromisoformat(raw).strftime("%d %B %Y, %H:%M UTC")
    except (ValueError, TypeError):
        return raw


_CSS = """
:root{--ink:#15181d;--muted:#5b6472;--line:#e3e7ed;--bg:#fff;--soft:#f7f9fb;
--crit:#b4232a;--high:#c2600d;--med:#9a7b09;--low:#5b6472;--accent:#1c4fd8}
*{box-sizing:border-box}
body{margin:0;background:var(--soft);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
.page{max-width:820px;margin:0 auto;padding:48px 24px 80px}
header{border-bottom:3px solid var(--ink);padding-bottom:24px;margin-bottom:32px}
.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}
h1{font-size:34px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em}
.scanned{color:var(--muted);font-size:14px;margin:0}
.scorebox{display:flex;align-items:baseline;gap:10px;margin-top:20px}
.scorebox .val{font-size:46px;font-weight:700;letter-spacing:-.03em;line-height:1}
.scorebox .of{color:var(--muted);font-size:15px}
.badge{margin-left:auto;font-size:26px;font-weight:700;width:52px;height:52px;border-radius:50%;
display:grid;place-items:center;color:#fff}
.grade-a{background:#1f7a43}.grade-b{background:#4a8a2b}.grade-c{background:#9a7b09}
.grade-d{background:#c2600d}.grade-f{background:#b4232a}
h2{font-size:21px;margin:40px 0 14px;letter-spacing:-.01em}
h3{font-size:17px;margin:26px 0 8px}
h4{font-size:16px;margin:0 0 10px}
p{margin:0 0 14px}
.sub{color:var(--muted);font-size:14px;margin:-4px 0 16px}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0 8px}
.card{flex:1 1 92px;background:#fff;border:1px solid var(--line);border-radius:10px;
padding:14px 12px;text-align:center}
.card .num{display:block;font-size:26px;font-weight:700;line-height:1.1}
.card .lbl{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);margin-top:4px}
.card.sev-critical{border-color:var(--crit)}.card.sev-critical .num{color:var(--crit)}
.card.sev-high{border-color:var(--high)}.card.sev-high .num{color:var(--high)}
.card.sev-medium{border-color:var(--med)}.card.sev-medium .num{color:var(--med)}
.card.sev-none .num{color:var(--muted)}
table.metrics{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);
border-radius:10px;overflow:hidden;font-size:14.5px}
table.metrics th,table.metrics td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line)}
table.metrics th{font-weight:600;color:var(--muted);width:46%}
table.metrics tr:last-child th,table.metrics tr:last-child td{border-bottom:0}
.headline{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);
border-radius:10px;padding:20px 22px;margin:28px 0}
.headline h2{margin:0 0 6px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
.headline h3{margin:0 0 10px}
.evidence{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;font-size:13.5px;
background:var(--soft);padding:9px 12px;border-radius:6px;border:1px solid var(--line)}
ul.wins{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 16px 16px 34px;margin:0}
ul.wins li{margin-bottom:8px}ul.wins li:last-child{margin-bottom:0}
.sevhead{display:flex;align-items:center;gap:10px;margin-top:34px;padding-bottom:6px;
border-bottom:2px solid var(--line)}
.sevhead .count{font-size:12px;background:var(--ink);color:#fff;border-radius:20px;padding:2px 9px}
.sevhead.sev-critical{color:var(--crit);border-color:var(--crit)}
.sevhead.sev-high{color:var(--high);border-color:var(--high)}
.sevhead.sev-medium{color:var(--med)}
.finding{background:#fff;border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin-bottom:12px}
.finding.sev-critical{border-left:4px solid var(--crit)}
.finding.sev-high{border-left:4px solid var(--high)}
.finding.sev-medium{border-left:4px solid var(--med)}
.finding.sev-low{border-left:4px solid var(--low)}
.finding dl{margin:0;display:grid;grid-template-columns:120px 1fr;gap:7px 14px;font-size:14.5px}
.finding dt{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;
letter-spacing:.06em;padding-top:3px}
.finding dd{margin:0}
.tag{font-size:10px;text-transform:uppercase;letter-spacing:.08em;background:var(--soft);
border:1px solid var(--line);color:var(--muted);border-radius:4px;padding:2px 6px;vertical-align:middle}
.package{background:var(--ink);color:#fff;border-radius:12px;padding:26px 28px;margin:40px 0 0}
.package h2{margin:0 0 4px;color:#fff;font-size:13px;letter-spacing:.12em;text-transform:uppercase;opacity:.65}
.package h3{margin:0 0 10px;font-size:23px}
.package p{opacity:.85}
.package ul{margin:0;padding-left:20px}.package li{margin-bottom:6px;opacity:.9}
.package .phase{margin:16px 0 0;padding-top:14px;border-top:1px solid rgba(255,255,255,.18);
font-size:13.5px;opacity:.75}
.scope{margin-top:40px;padding-top:22px;border-top:1px solid var(--line);color:var(--muted);font-size:13.5px}
.scope h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 10px}
.error{background:#fff;border-left:4px solid var(--crit);padding:16px 20px;border-radius:8px}
@media print{body{background:#fff}.page{padding:0;max-width:none}
.finding,.card,table.metrics,.headline,ul.wins{break-inside:avoid}
.package{background:#fff;color:var(--ink);border:2px solid var(--ink)}
.package h2{color:var(--ink)}}
@media(max-width:560px){.page{padding:28px 16px 60px}h1{font-size:26px}
.finding dl{grid-template-columns:1fr;gap:2px 0}
.finding dt{padding-top:8px}}
"""

_HTML_SHELL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site audit — {domain}</title>
<style>{css}</style></head>
<body><div class="page">
<header>
<p class="eyebrow">Technical site audit</p>
<h1>{domain}</h1>
<p class="scanned">Scanned {scanned}</p>
<div class="scorebox">
<span class="val">{score}</span><span class="of">/ 100 health score</span>
<span class="badge {score_class}">{grade}</span>
</div>
</header>
{body}
</div></body></html>"""
