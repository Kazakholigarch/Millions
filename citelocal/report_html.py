"""Client-ready HTML report.

This is the deliverable an agency puts in front of a business owner, so it is
written to be read by a non-technical reader, printed to PDF cleanly, and
re-branded without editing code (pass `brand`).
"""
from __future__ import annotations

from html import escape

from .audit import blocking_issue
from .models import AuditResult, Effort, Status

_STATUS_LABEL = {
    Status.PASS: "Pass",
    Status.WARN: "Needs work",
    Status.FAIL: "Failing",
    Status.SKIP: "Not checked",
}

_EFFORT_LABEL = {
    Effort.LOW: "Minutes",
    Effort.MEDIUM: "A few hours",
    Effort.HIGH: "Ongoing work",
}

_CSS = """
:root {
  --bg: #ffffff;
  --surface: #f7f8fa;
  --surface-2: #eef0f4;
  --border: #dfe3ea;
  --text: #14171f;
  --text-soft: #5a6273;
  --accent: #1d4ed8;
  --pass: #0f7a4d;
  --pass-bg: #e6f5ee;
  --warn: #96620a;
  --warn-bg: #fdf3e0;
  --fail: #b3251e;
  --fail-bg: #fdecea;
  --skip: #6a7180;
  --skip-bg: #f0f1f4;
  --code-bg: #12151c;
  --code-text: #e8ecf4;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1116;
    --surface: #171a21;
    --surface-2: #1e222b;
    --border: #2b303b;
    --text: #eef1f6;
    --text-soft: #a4adbd;
    --accent: #7aa2ff;
    --pass: #59d09a;
    --pass-bg: #11291f;
    --warn: #e5b055;
    --warn-bg: #2c2312;
    --fail: #f08279;
    --fail-bg: #2e1715;
    --skip: #9aa2b1;
    --skip-bg: #1d2128;
    --code-bg: #080a0e;
    --code-text: #e8ecf4;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1116; --surface: #171a21; --surface-2: #1e222b; --border: #2b303b;
  --text: #eef1f6; --text-soft: #a4adbd; --accent: #7aa2ff;
  --pass: #59d09a; --pass-bg: #11291f; --warn: #e5b055; --warn-bg: #2c2312;
  --fail: #f08279; --fail-bg: #2e1715; --skip: #9aa2b1; --skip-bg: #1d2128;
  --code-bg: #080a0e; --code-text: #e8ecf4;
}

* { box-sizing: border-box; }
/* The action plan embeds long verification URLs. Without this they overflow
   their paragraph as one unbreakable inline box and scroll the whole page
   sideways on a phone. Snippets opt out below — they scroll instead. */
body, p, li, td, th { overflow-wrap: anywhere; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 860px; margin: 0 auto; padding: 48px 16px 96px; }

header.masthead { border-bottom: 2px solid var(--text); padding-bottom: 20px; margin-bottom: 36px; }
.brand { font-size: 13px; letter-spacing: .14em; text-transform: uppercase;
         color: var(--text-soft); font-weight: 600; }
h1 { font-size: 30px; line-height: 1.2; margin: 10px 0 6px; letter-spacing: -.02em; }
.subject-meta { color: var(--text-soft); font-size: 15px; }
.subject-meta a { color: var(--accent); }

/* Score */
.scorecard {
  display: flex; gap: 28px; align-items: center; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 14px; padding: 26px 28px; margin-bottom: 32px;
}
.gauge { position: relative; width: 132px; height: 132px; flex: 0 0 132px; }
.gauge svg { transform: rotate(-90deg); }
.gauge .value {
  position: absolute; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.gauge .num { font-size: 38px; font-weight: 700; letter-spacing: -.03em; line-height: 1; }
.gauge .den { font-size: 12px; color: var(--text-soft); margin-top: 3px; }
.score-copy { flex: 1 1 300px; min-width: 240px; }
.score-copy .grade { font-size: 13px; text-transform: uppercase; letter-spacing: .12em;
                     color: var(--text-soft); font-weight: 600; }
.score-copy .verdict { font-size: 19px; font-weight: 600; margin: 6px 0 10px; line-height: 1.35; }
.tallies { display: flex; gap: 8px; flex-wrap: wrap; }
.tally { font-size: 13px; padding: 4px 10px; border-radius: 20px; font-weight: 600; }

/* Blocker callout */
.blocker {
  border-left: 4px solid var(--fail); background: var(--fail-bg);
  padding: 18px 22px; border-radius: 0 10px 10px 0; margin-bottom: 32px;
}
.blocker h2 { margin: 0 0 6px; font-size: 17px; color: var(--fail); }
.blocker p { margin: 0 0 6px; }

h2.section { font-size: 13px; text-transform: uppercase; letter-spacing: .14em;
             color: var(--text-soft); margin: 44px 0 16px; font-weight: 700; }

/* Checks */
.check { border: 1px solid var(--border); border-radius: 12px; margin-bottom: 14px;
         overflow: hidden; background: var(--surface); }
.check-head { display: flex; align-items: baseline; gap: 12px; padding: 16px 20px; flex-wrap: wrap; }
.pill { font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
        padding: 3px 9px; border-radius: 5px; white-space: nowrap; }
.pill.pass { background: var(--pass-bg); color: var(--pass); }
.pill.warn { background: var(--warn-bg); color: var(--warn); }
.pill.fail { background: var(--fail-bg); color: var(--fail); }
.pill.skip { background: var(--skip-bg); color: var(--skip); }
.check-title { font-weight: 650; font-size: 16px; flex: 1 1 auto; }
.check-pct { color: var(--text-soft); font-size: 13px; font-variant-numeric: tabular-nums; }
.check-body { padding: 0 20px 18px; }
.check-summary { color: var(--text-soft); margin: 0 0 12px; }
.findings { margin: 0; padding-left: 20px; }
.findings li { margin-bottom: 7px; }
.findings li::marker { color: var(--text-soft); }

/* Competitors */
.comp-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 15px; }
.comp-table th { text-align: left; font-size: 12px; text-transform: uppercase;
                 letter-spacing: .08em; color: var(--text-soft); padding: 6px 10px 6px 0;
                 border-bottom: 1px solid var(--border); }
.comp-table td { padding: 7px 10px 7px 0; border-bottom: 1px solid var(--border); }
.comp-table td.count { font-variant-numeric: tabular-nums; color: var(--text-soft);
                       width: 1%; white-space: nowrap; }

/* Action plan */
.fix { border: 1px solid var(--border); border-left: 3px solid var(--accent);
       border-radius: 0 12px 12px 0; padding: 18px 22px; margin-bottom: 14px;
       background: var(--surface); }
.fix-head { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; margin-bottom: 8px; }
.fix-num { font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
.fix-title { font-weight: 650; font-size: 17px; flex: 1 1 auto; }
.fix-meta { font-size: 12px; color: var(--text-soft); display: flex; gap: 10px; flex-wrap: wrap; }
.fix-meta span { background: var(--surface-2); padding: 2px 8px; border-radius: 4px; }
.fix p { margin: 0 0 10px; }
.fix .where { font-size: 14px; color: var(--text-soft); }
/* The snippet is the one thing that must not reflow — a wrapped line of JSON-LD
   is no longer safe to paste — so it scrolls inside its own box. max-width and
   min-width:0 keep that scroll box from widening the page on narrow screens. */
pre { background: var(--code-bg); color: var(--code-text); padding: 16px 18px;
      border-radius: 9px; overflow-x: auto; font-size: 13px; line-height: 1.55;
      margin: 12px 0 0; max-width: 100%; min-width: 0; }
pre code { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
           display: block; width: max-content; min-width: 100%;
           overflow-wrap: normal; white-space: pre; }
.fix, .check { min-width: 0; }

footer { margin-top: 56px; padding-top: 22px; border-top: 1px solid var(--border);
         color: var(--text-soft); font-size: 13px; }

@media print {
  body { background: #fff; color: #000; }
  .wrap { max-width: none; padding: 0; }
  .check, .fix, .scorecard { break-inside: avoid; }
  pre { white-space: pre-wrap; word-break: break-word; }
}
@media (max-width: 600px) {
  .wrap { padding: 28px 16px 64px; }
  h1 { font-size: 24px; }
  .scorecard { gap: 18px; padding: 20px; }
}
"""


def render_html(result: AuditResult, brand: str = "CiteLocal") -> str:
    business = result.business
    score = result.score

    parts: list[str] = []
    parts.append(_head(f"AI Visibility Audit — {business.name}"))
    parts.append('<div class="wrap">')

    # Masthead
    parts.append('<header class="masthead">')
    parts.append(f'<div class="brand">{escape(brand)} · AI Visibility Audit</div>')
    parts.append(f"<h1>{escape(business.name)}</h1>")
    meta = [
        f'<a href="{escape(business.website)}">{escape(_pretty_url(business.website))}</a>'
    ]
    if business.descriptor:
        meta.append(escape(business.descriptor))
    meta.append(f"{result.generated_at:%d %B %Y}")
    parts.append(f'<div class="subject-meta">{" &middot; ".join(meta)}</div>')
    parts.append("</header>")

    # Scorecard — or an unreachable-site notice, since a score built from zero
    # successful checks would read as a perfect result.
    if result.site_error:
        parts.append('<div class="blocker">')
        parts.append("<h2>Site could not be loaded</h2>")
        parts.append(f"<p><strong>{escape(result.site_error)}</strong></p>")
        parts.append(
            "<p>No score can be calculated. Confirm the URL is correct, and check "
            "whether the site blocks non-browser clients — a site that refuses this "
            "audit may also be refusing the AI crawlers, which would itself explain "
            "an absence from AI answers.</p>"
        )
        parts.append("</div>")
    else:
        parts.append('<div class="scorecard">')
        parts.append(_gauge(score))
        parts.append('<div class="score-copy">')
        parts.append(
            f'<div class="grade">AI visibility score &middot; grade {result.grade}</div>'
        )
        parts.append(f'<div class="verdict">{escape(result.verdict)}</div>')
        parts.append('<div class="tallies">')
        for status in (Status.FAIL, Status.WARN, Status.PASS, Status.SKIP):
            count = len(result.by_status(status))
            if count:
                klass = status.value
                parts.append(
                    f'<span class="tally pill {klass}">{count} '
                    f"{escape(_STATUS_LABEL[status].lower())}</span>"
                )
        parts.append("</div></div></div>")

    # Blocking issue
    blocker = blocking_issue(result)
    if blocker:
        parts.append('<div class="blocker">')
        parts.append("<h2>Blocking issue — fix this first</h2>")
        parts.append(f"<p><strong>{escape(blocker.summary)}</strong></p>")
        parts.append(
            "<p>Until AI crawlers can read this site, no amount of content or "
            "structured-data work can produce a citation. Everything else in this "
            "report is downstream of this fix.</p>"
        )
        parts.append("</div>")

    # What we tested
    parts.append('<h2 class="section">What we tested</h2>')
    for check in result.checks:
        parts.append(_check_block(check))

    # Action plan
    plan = result.action_plan
    if plan:
        parts.append('<h2 class="section">Action plan — highest impact first</h2>')
        for index, fix in enumerate(plan, start=1):
            parts.append(_fix_block(index, fix))

    parts.append(_footer(brand))
    parts.append("</div></body></html>")
    return "\n".join(parts)


def _head(title: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title>"
        f"<style>{_CSS}</style>"
        "</head><body>"
    )


def _gauge(score: int) -> str:
    """Donut gauge. Colour tracks severity so the number reads at a glance."""
    radius = 58
    circumference = 2 * 3.14159265 * radius
    filled = circumference * min(100, max(0, score)) / 100
    colour = "var(--fail)" if score < 50 else "var(--warn)" if score < 80 else "var(--pass)"
    return f"""<div class="gauge">
  <svg width="132" height="132" viewBox="0 0 132 132" aria-hidden="true">
    <circle cx="66" cy="66" r="{radius}" fill="none" stroke="var(--border)" stroke-width="11"/>
    <circle cx="66" cy="66" r="{radius}" fill="none" stroke="{colour}" stroke-width="11"
            stroke-linecap="round" stroke-dasharray="{filled:.1f} {circumference:.1f}"/>
  </svg>
  <div class="value"><div class="num">{score}</div><div class="den">out of 100</div></div>
</div>"""


def _check_block(check) -> str:
    klass = check.status.value
    label = _STATUS_LABEL[check.status]
    pct = "" if check.status is Status.SKIP else f'<span class="check-pct">{round(check.score * 100)}%</span>'

    out = ['<div class="check">']
    out.append('<div class="check-head">')
    out.append(f'<span class="pill {klass}">{escape(label)}</span>')
    out.append(f'<span class="check-title">{escape(check.name)}</span>')
    out.append(pct)
    out.append("</div>")
    out.append('<div class="check-body">')
    out.append(f'<p class="check-summary">{escape(check.summary)}</p>')

    if check.findings:
        out.append('<ul class="findings">')
        for finding in check.findings:
            out.append(f"<li>{escape(finding)}</li>")
        out.append("</ul>")

    # The competitor table is the most persuasive object in the report, so it
    # gets real presentation rather than being buried in a findings bullet.
    competitors = check.evidence.get("top_competitors") or []
    if competitors:
        out.append(
            '<table class="comp-table"><thead><tr>'
            "<th>Recommended instead of you</th><th>Times named</th>"
            "</tr></thead><tbody>"
        )
        for name, count in competitors:
            out.append(
                f'<tr><td>{escape(str(name))}</td><td class="count">{count}&times;</td></tr>'
            )
        out.append("</tbody></table>")

    out.append("</div></div>")
    return "\n".join(out)


def _fix_block(index: int, fix) -> str:
    out = ['<div class="fix">']
    out.append('<div class="fix-head">')
    out.append(f'<span class="fix-num">{index}</span>')
    out.append(f'<span class="fix-title">{escape(fix.title)}</span>')
    out.append("</div>")
    out.append(
        f'<div class="fix-meta"><span>Effort: {escape(_EFFORT_LABEL[fix.effort])}</span>'
        f"<span>Impact: {fix.impact:.0%}</span></div>"
    )
    for paragraph in fix.detail.split("\n\n"):
        if paragraph.strip():
            out.append(f"<p>{escape(paragraph.strip())}</p>")
    if fix.reference:
        out.append(f'<p class="where"><strong>Where:</strong> {escape(fix.reference)}</p>')
    if fix.snippet:
        out.append(f"<pre><code>{escape(fix.snippet)}</code></pre>")
    out.append("</div>")
    return "\n".join(out)


def _footer(brand: str) -> str:
    return (
        "<footer>"
        f"<p><strong>{escape(brand)}</strong> — AI visibility audit. Findings are based "
        "on publicly documented behaviour of AI search crawlers, schema.org structured "
        "data, and live sampling of assistant responses.</p>"
        "<p>Assistant answers vary between runs and over time. These checks improve the "
        "conditions for being cited; no tool can guarantee placement in an AI answer.</p>"
        "</footer>"
    )


def _pretty_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")
