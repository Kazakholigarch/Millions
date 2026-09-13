"""CiteLocal web app.

Deliberately templateless: the results page is produced by the same
`render_html` used for the downloadable deliverable, so what an agency sees on
screen is exactly what its client receives. There is no second code path to
drift out of sync.

    python3 -m citelocal.web        # then open http://localhost:5000
"""
from __future__ import annotations

import json
import os
from html import escape

from flask import Flask, Response, request

from .audit import audit
from .cli import to_dict
from .llm_probe import PROVIDERS, available_providers, build_prompts
from .models import Business
from .report_html import _CSS, render_html

app = Flask(__name__)

_FORM_CSS = (
    _CSS
    + """
form { display: grid; gap: 18px; }
.row { display: grid; gap: 18px; grid-template-columns: 1fr 1fr; }
@media (max-width: 620px) { .row { grid-template-columns: 1fr; } }
label { display: block; font-weight: 600; font-size: 14px; margin-bottom: 6px; }
label .hint { font-weight: 400; color: var(--text-soft); font-size: 13px; }
input[type=text], select {
  width: 100%; padding: 11px 13px; font-size: 15px; color: var(--text);
  background: var(--bg); border: 1px solid var(--border); border-radius: 9px;
  font-family: inherit;
}
input[type=text]:focus, select:focus {
  outline: 2px solid var(--accent); outline-offset: -1px; border-color: var(--accent);
}
fieldset { border: 1px solid var(--border); border-radius: 12px; padding: 18px 20px; margin: 0; }
legend { font-weight: 650; padding: 0 8px; font-size: 15px; }
.check-row { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; }
.check-row input { margin-top: 4px; }
.check-row label { margin: 0; font-weight: 500; }
button[type=submit] {
  padding: 14px 26px; font-size: 16px; font-weight: 650; color: #fff;
  background: var(--accent); border: 0; border-radius: 9px; cursor: pointer;
  font-family: inherit; justify-self: start;
}
button[type=submit]:hover { filter: brightness(1.08); }
.lede { color: var(--text-soft); font-size: 17px; margin: 0 0 32px; max-width: 62ch; }
.notice { background: var(--surface); border: 1px solid var(--border);
          border-radius: 10px; padding: 14px 16px; font-size: 14px;
          color: var(--text-soft); }
.notice code { background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }
.prompt-list { margin: 8px 0 0; padding-left: 20px; color: var(--text-soft); font-size: 14px; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; margin: 0 0 28px; }
.actions a { display: inline-block; padding: 10px 18px; border-radius: 8px;
             border: 1px solid var(--border); background: var(--surface);
             color: var(--text); text-decoration: none; font-size: 14px; font-weight: 600; }
.actions a:hover { border-color: var(--accent); color: var(--accent); }
.error { border-left: 4px solid var(--fail); background: var(--fail-bg);
         padding: 14px 18px; border-radius: 0 10px 10px 0; margin-bottom: 24px; }
@media print { .actions, form { display: none; } }
"""
)


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_FORM_CSS}</style></head>"
        f'<body><div class="wrap">{body}</div></body></html>'
    )


@app.get("/")
def form() -> Response:
    keys = available_providers()
    sample = build_prompts(
        Business(name="", website="", city="Austin", region="TX", category="plumber"), limit=3
    )

    if keys:
        labels = ", ".join(str(PROVIDERS[k]["label"]) for k in keys)
        probe_notice = (
            f'<div class="notice">Live probe available via <strong>{escape(labels)}</strong>. '
            "Each question is a real API call, so a six-question probe across one "
            "provider costs a few cents.</div>"
        )
        probe_default = "checked"
    else:
        probe_notice = (
            '<div class="notice">No LLM API key detected, so the live probe is '
            "unavailable. Every site check below still runs. To enable it, set "
            "<code>ANTHROPIC_API_KEY</code>, <code>OPENAI_API_KEY</code>, or "
            "<code>PERPLEXITY_API_KEY</code> and restart.</div>"
        )
        probe_default = ""

    body = f"""
<header class="masthead">
  <div class="brand">CiteLocal</div>
  <h1>AI visibility audit</h1>
</header>
<p class="lede">Find out whether AI assistants can see, understand and recommend a
local business — and get the exact fixes, ready to paste. Produces a
client-ready report you can hand over as-is.</p>

<form method="post" action="/audit">
  <div class="row">
    <div>
      <label for="name">Business name</label>
      <input type="text" id="name" name="name" required placeholder="Precision Plumbing">
    </div>
    <div>
      <label for="site">Website</label>
      <input type="text" id="site" name="site" required placeholder="precisionplumbing.com">
    </div>
  </div>
  <div class="row">
    <div>
      <label for="category">Category <span class="hint">plain language</span></label>
      <input type="text" id="category" name="category" placeholder="emergency plumber">
    </div>
    <div>
      <label for="phone">Public phone <span class="hint">optional</span></label>
      <input type="text" id="phone" name="phone" placeholder="(512) 555-0142">
    </div>
  </div>
  <div class="row">
    <div>
      <label for="city">City</label>
      <input type="text" id="city" name="city" placeholder="Austin">
    </div>
    <div>
      <label for="region">State / region</label>
      <input type="text" id="region" name="region" placeholder="TX">
    </div>
  </div>

  <fieldset>
    <legend>Live visibility probe</legend>
    <div class="check-row">
      <input type="checkbox" id="probe" name="probe" value="1" {probe_default}
             {"" if keys else "disabled"}>
      <label for="probe">Ask assistants the questions your customers ask, and record
        who gets recommended instead</label>
    </div>
    {probe_notice}
    <p style="margin:14px 0 0;font-size:14px;font-weight:600;">Questions like:</p>
    <ul class="prompt-list">
      {"".join(f"<li>{escape(p)}</li>" for p in sample)}
    </ul>
  </fieldset>

  <div class="row">
    <div>
      <label for="mode">Probe mode</label>
      <select id="mode" name="mode">
        <option value="grounded">Grounded — assistants search the web (what users see today)</option>
        <option value="memory">Memory — no search (tests built-in model knowledge)</option>
      </select>
    </div>
    <div>
      <label for="brand">Report branding <span class="hint">white-label</span></label>
      <input type="text" id="brand" name="brand" placeholder="Your agency name">
    </div>
  </div>

  <button type="submit">Run audit</button>
</form>
"""
    return Response(_page("CiteLocal — AI visibility audit", body), mimetype="text/html")


@app.post("/audit")
def run_audit() -> Response:
    form_data = request.form
    name = (form_data.get("name") or "").strip()
    site = (form_data.get("site") or "").strip()

    if not name or not site:
        body = (
            '<div class="error"><strong>Business name and website are both '
            'required.</strong></div><p><a href="/">Back to the form</a></p>'
        )
        return Response(_page("CiteLocal — error", body), mimetype="text/html", status=400)

    business = Business(
        name=name,
        website=site,
        city=(form_data.get("city") or "").strip(),
        region=(form_data.get("region") or "").strip(),
        category=(form_data.get("category") or "").strip(),
        phone=(form_data.get("phone") or "").strip(),
    )
    brand = (form_data.get("brand") or "").strip() or "CiteLocal"

    result = audit(
        business,
        run_probe=bool(form_data.get("probe")) and bool(available_providers()),
        probe_mode=form_data.get("mode") or "grounded",
    )

    report = render_html(result, brand=brand)

    # Splice an action bar in after <body> so the on-screen page offers download
    # and print without altering the report markup itself.
    actions = (
        '<div class="wrap" style="padding-bottom:0">'
        '<div class="actions">'
        '<a href="/">New audit</a>'
        '<a href="#" onclick="window.print();return false">Print / save as PDF</a>'
        "</div></div>"
    )
    report = report.replace("<body>", "<body>" + actions, 1)
    # The report is standalone HTML, so the action bar needs the form CSS too.
    report = report.replace("</style>", "</style><style>" + _ACTION_CSS + "</style>", 1)
    return Response(report, mimetype="text/html")


_ACTION_CSS = """
.actions { display: flex; gap: 12px; flex-wrap: wrap; margin: 24px 0 0; }
.actions a { display: inline-block; padding: 10px 18px; border-radius: 8px;
             border: 1px solid var(--border); background: var(--surface);
             color: var(--text); text-decoration: none; font-size: 14px; font-weight: 600; }
.actions a:hover { border-color: var(--accent); color: var(--accent); }
@media print { .actions { display: none; } }
"""


@app.post("/api/audit")
def api_audit() -> Response:
    """JSON endpoint, so an agency can wire this into its own reporting stack."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    site = (payload.get("website") or payload.get("site") or "").strip()
    if not name or not site:
        return Response(
            json.dumps({"error": "name and website are required"}),
            mimetype="application/json",
            status=400,
        )

    business = Business(
        name=name,
        website=site,
        city=(payload.get("city") or "").strip(),
        region=(payload.get("region") or "").strip(),
        category=(payload.get("category") or "").strip(),
        phone=(payload.get("phone") or "").strip(),
    )
    result = audit(
        business,
        run_probe=bool(payload.get("probe", False)),
        probe_mode=payload.get("mode") or "grounded",
    )
    return Response(json.dumps(to_dict(result), indent=2), mimetype="application/json")


def main() -> None:
    port = int(os.environ.get("PORT", "5000"))
    print(f"CiteLocal running on http://localhost:{port}")
    if not available_providers():
        print("(no LLM API key set — site checks only; live probe disabled)")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
