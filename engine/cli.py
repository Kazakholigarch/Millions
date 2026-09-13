"""Command line for the revenue engine.

The commands map onto the daily loop in STRATEGY.md §3:

    money plan            what the target actually demands of you
    money run urls.txt    scan a list, rank it, draft the openers
    money today           what to do now, and whether you're behind
    money report <domain> the deliverable a prospect asked for
    money stage <d> won   move the pipeline

`today` is the one to run every morning. It is the whole model reduced to a
number you can either hit or not.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .audit_report import render_html, render_markdown
from .fetch import Fetcher, domain_of, normalize_url
from .outreach import VARIANTS, compose, compose_sequence
from .pipeline import STAGES, FunnelModel, Prospect, daily_brief, observed_yield, status
from .scan import scan, scan_many
from .score import assess, rank_prospects
from .storage import Store

# -- output helpers ----------------------------------------------------------

_COLOR = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text


def bold(t: str) -> str:
    return _c(t, "1")


def dim(t: str) -> str:
    return _c(t, "2")


def red(t: str) -> str:
    return _c(t, "31")


def green(t: str) -> str:
    return _c(t, "32")


def yellow(t: str) -> str:
    return _c(t, "33")


def cyan(t: str) -> str:
    return _c(t, "36")


SEVERITY_COLOR = {"critical": red, "high": yellow, "medium": cyan, "low": dim}


def rule(title: str = "", width: int = 74) -> str:
    if not title:
        return dim("─" * width)
    return bold(f"── {title} ") + dim("─" * max(0, width - len(title) - 4))


def money(value: float) -> str:
    return f"${value:,.0f}"


# -- commands ----------------------------------------------------------------


def cmd_init(args, store: Store) -> int:
    config = store.load_config()
    sender = config.get("sender", {})
    for field in ("name", "company", "email", "phone", "calendar_link", "address"):
        current = sender.get(field, "")
        prompt = f"{field.replace('_', ' ').title()}"
        prompt += f" [{current}]: " if current else ": "
        try:
            entered = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if entered:
            sender[field] = entered
    config["sender"] = sender
    config.setdefault("started_on", date.today().isoformat())
    config.setdefault(
        "model",
        {"target_revenue": args.target, "days": args.days, "avg_deal_value": args.deal},
    )
    store.save_config(config)
    print(green(f"\nSaved to {store.config_path}"))
    print(dim("Run 'money plan' to see what your target demands."))
    return 0


def cmd_scan(args, store: Store) -> int:
    urls = _collect_urls(args.urls, args.file)
    if not urls:
        print(red("No URLs given."), file=sys.stderr)
        return 1

    print(rule(f"Scanning {len(urls)} site(s)"))
    fetcher = Fetcher(min_delay=args.delay, obey_robots=not args.ignore_robots)
    results = []
    try:
        for index, raw in enumerate(urls, 1):
            print(dim(f"  [{index}/{len(urls)}] {raw} ..."), end="\r")
            result = scan(raw, fetcher=fetcher, link_sample=args.links)
            store.save_scan(result)
            results.append(result)
            print(" " * 70, end="\r")
            _print_scan_line(result)
    finally:
        fetcher.close()

    if args.queue:
        _queue_prospects(store, results, args.min_fit)
    print()
    _print_ranking(results)
    return 0


def cmd_run(args, store: Store) -> int:
    """Scan a list, rank it, queue the good ones, draft the openers."""
    urls = _collect_urls(args.urls, args.file)
    if not urls:
        print(red("No URLs given."), file=sys.stderr)
        return 1

    print(rule(f"Full pass over {len(urls)} site(s)"))
    fetcher = Fetcher(min_delay=args.delay, obey_robots=not args.ignore_robots)
    try:
        results = scan_many(urls, fetcher=fetcher, link_sample=args.links, on_result=_print_scan_line)
    finally:
        fetcher.close()

    for result in results:
        store.save_scan(result)

    queued = _queue_prospects(store, results, args.min_fit)
    sender = store.sender()
    drafted = 0
    for result in results:
        assessment = assess(result)
        if not result.ok or assessment.deal_fit < args.min_fit or not result.findings:
            continue
        try:
            draft = compose(result, assessment, sender, "cold_email")
        except ValueError:
            continue
        store.save_draft(result.domain, "cold_email", draft.full)
        drafted += 1
        if not draft.grounded:
            print(red(f"  ! {result.domain}: ungrounded figures {draft.unsourced} — do not send"))

    print()
    print(rule("Result"))
    print(f"  Scanned   {len(results)}")
    print(f"  Queued    {queued} (deal fit ≥ {args.min_fit})")
    print(f"  Drafted   {drafted} opener(s) → {store.drafts_dir}/")
    print()
    _print_ranking(results)
    print()
    print(dim("Review every draft before sending. Then: money stage <domain> sent"))
    return 0


def cmd_report(args, store: Store) -> int:
    result = _load_scan(store, args.domain)
    if result is None:
        print(red(f"No saved scan for {args.domain}. Run: money scan {args.domain}"), file=sys.stderr)
        return 1

    assessment = assess(result)
    wrote = []
    if args.format in ("html", "both"):
        wrote.append(store.save_report(result.domain, "html", render_html(result, assessment)))
    if args.format in ("md", "both"):
        wrote.append(store.save_report(result.domain, "md", render_markdown(result, assessment)))

    if args.stdout:
        print(render_markdown(result, assessment))
        return 0

    for path in wrote:
        print(green(f"Wrote {path}"))
    print(dim("Open the HTML in a browser and print to PDF to send it."))
    return 0


def cmd_outreach(args, store: Store) -> int:
    result = _load_scan(store, args.domain)
    if result is None:
        print(red(f"No saved scan for {args.domain}. Run: money scan {args.domain}"), file=sys.stderr)
        return 1
    if not result.ok or not result.findings:
        print(red(f"{args.domain}: scan found nothing to write about."), file=sys.stderr)
        return 1

    assessment = assess(result)
    prospect = store.get_prospect(result.domain)
    contact = args.name or (prospect.contact_name if prospect else None)
    sender = store.sender()

    drafts = (
        compose_sequence(result, assessment, sender, contact)
        if args.all
        else [compose(result, assessment, sender, args.variant, contact)]
    )

    for draft in drafts:
        print()
        print(rule(draft.variant))
        print(draft.full)
        if draft.grounded:
            print()
            print(green("  ✓ every figure traces to a measurement"))
        else:
            print()
            print(red(f"  ✗ UNGROUNDED: {draft.unsourced} — do not send as-is"))
        if args.save:
            store.save_draft(result.domain, draft.variant, draft.full)
    if args.save:
        print()
        print(green(f"Saved to {store.drafts_dir}/"))
    return 0


def cmd_add(args, store: Store) -> int:
    url = normalize_url(args.url)
    prospect = Prospect(
        domain=domain_of(url),
        url=url,
        company=args.company or "",
        contact_name=args.name or "",
        email=args.email or "",
        stage="scanned",
    )
    saved = store.upsert_prospect(prospect)
    print(green(f"Added {saved.domain} at stage '{saved.stage}'"))
    return 0


def cmd_stage(args, store: Store) -> int:
    prospects = store.load_prospects()
    target = next((p for p in prospects if p.domain == domain_of(normalize_url(args.domain))), None)
    if target is None:
        print(red(f"No prospect for {args.domain}. Run: money add {args.domain}"), file=sys.stderr)
        return 1

    previous = target.stage
    target.advance(args.stage, note=args.note or "", value=args.value)
    store.save_prospects(prospects)

    line = f"{target.domain}: {previous} → {bold(args.stage)}"
    if args.stage == "won":
        line += green(f"  {money(target.deal_value)} booked")
    print(line)
    return 0


def cmd_pipeline(args, store: Store) -> int:
    prospects = store.load_prospects()
    if not prospects:
        print(dim("Pipeline is empty. Run: money run urls.txt"))
        return 0

    model = store.model()
    state = status(prospects, model, store.started_on())

    print(rule("Pipeline"))
    for stage in STAGES:
        group = [p for p in prospects if p.stage == stage]
        if not group:
            continue
        value = sum(p.deal_value for p in group)
        suffix = f"  {money(value)}" if value else ""
        print(f"  {stage:<12} {len(group):>4}{dim(suffix)}")

    print()
    print(rule("Money"))
    print(f"  Booked              {green(money(state.booked_revenue))}")
    print(f"  Weighted pipeline   {money(state.weighted_pipeline)}")
    print(f"  Projected total     {bold(money(state.projected_revenue))}")
    print(f"  Gap to target       {money(state.gap_to_target)}")

    measured = observed_yield(prospects)
    if measured is not None:
        print()
        print(
            dim(f"  Measured scan→prospect yield: {measured:.1%} ")
            + dim(f"(model assumes {model.scan_to_prospect_yield:.0%})")
        )

    if args.verbose:
        print()
        print(rule("Detail"))
        for prospect in sorted(prospects, key=lambda p: -p.weighted_value):
            print(
                f"  {prospect.domain:<28} {prospect.stage:<12} fit {prospect.deal_fit:>3}  "
                f"{money(prospect.deal_value):>9}  {dim('w ' + money(prospect.weighted_value))}"
            )
    return 0


def cmd_plan(args, store: Store) -> int:
    model = store.model()
    if args.target:
        model.target_revenue = args.target
    if args.days:
        model.days = args.days
    if args.deal:
        model.avg_deal_value = args.deal

    requirements = model.requirements()
    print(rule(f"{money(model.target_revenue)} in {model.days} days"))
    print(f"  Assumed rates      {dim(requirements.rates)}")
    print(f"  Average deal       {money(model.avg_deal_value)}")
    print()
    print(f"  Deals to close     {bold(str(requirements.deals_needed))}")
    print(f"  Calls to hold      {requirements.calls_needed}  ({requirements.calls_per_week}/week)")
    print(f"  Replies to earn    {requirements.replies_needed}")
    print(f"  Messages to send   {requirements.sends_needed}")
    print(f"  Sites to scan      {requirements.scans_needed}")
    print()
    print(
        f"  {dim('Send window is')} {requirements.send_days} days "
        + dim(f"({model.days} − {model.sales_cycle_days}-day sales cycle;")
    )
    print(dim("  a message sent after that closes too late to count in this window)"))
    print()
    verdict = {
        "comfortable": green,
        "demanding but achievable": green,
        "at the limit": yellow,
        "not achievable at these rates": red,
    }[requirements.feasibility]
    print(f"  {bold('PER DAY:')} {bold(str(requirements.sends_per_day))} sends, "
          f"{requirements.scans_per_day} scans   {verdict('[' + requirements.feasibility + ']')}")

    for warning in requirements.warnings:
        print()
        print(yellow(f"  ! {warning}"))

    if args.scenarios:
        print()
        print(rule("If your rates land differently"))
        for name, req in model.scenarios().items():
            colour = red if "not achievable" in req.feasibility else green
            print(f"  {name:<13} {req.sends_per_day:>4}/day   {colour(req.feasibility)}")
        print()
        print(rule("Sensitivity to average deal value"))
        for value in (2500, 6500, 10000, 15000, 20000, 25000):
            probe = FunnelModel(
                target_revenue=model.target_revenue, days=model.days, avg_deal_value=value,
                rates=model.rates, sales_cycle_days=model.sales_cycle_days,
            ).requirements()
            colour = red if "not achievable" in probe.feasibility else green
            print(
                f"  {money(value):>8} deals → {probe.deals_needed:>2} deals, "
                f"{probe.sends_per_day:>4}/day   {colour(probe.feasibility)}"
            )
        print()
        print(dim("  Deal value is the dominant lever. Raising it beats sending more."))
    return 0


def cmd_today(args, store: Store) -> int:
    prospects = store.load_prospects()
    model = store.model()
    brief = daily_brief(prospects, model, store.started_on())
    state = brief["status"]

    print(rule(f"Day {state.days_elapsed + 1} of {model.days}"))
    pace = green("on pace") if state.on_pace else red(f"{state.send_deficit} sends behind")
    print(f"  Sent so far     {state.sends_done} / {state.sends_expected} expected   {pace}")
    print(f"  Booked          {green(money(state.booked_revenue))}"
          f"   {dim('projected ' + money(state.projected_revenue))}")
    print(f"  Days remaining  {state.days_remaining}")
    print()
    print(rule("Do this today"))
    if brief["actions"]:
        for action in brief["actions"]:
            print(f"  • {action}")
    else:
        print(dim("  Nothing queued. Run: money run urls.txt"))
    return 0


# -- helpers -----------------------------------------------------------------


def _load_scan(store: Store, raw: str):
    """Look a scan up however the user spelled it.

    Every command must accept the same spellings — `example.com`,
    `https://example.com/`, `www.example.com` — or `money report <x>` fails on
    the exact string that `money scan <x>` just succeeded with.
    """
    found = store.load_scan(raw)
    if found is not None:
        return found
    try:
        return store.load_scan(domain_of(normalize_url(raw)))
    except ValueError:
        return None


def _print_scan_line(result) -> None:
    if not result.ok:
        print(f"  {red('✗')} {result.domain:<30} {dim(str(result.error))}")
        return
    assessment = assess(result)
    counts = result.severity_counts
    severity_bits = " ".join(
        SEVERITY_COLOR[s](f"{counts[s]}{s[0].upper()}") for s in ("critical", "high", "medium", "low") if counts[s]
    )
    fit = green if assessment.deal_fit >= 60 else (yellow if assessment.deal_fit >= 45 else dim)
    print(
        f"  {green('✓')} {result.domain:<30} health {assessment.health_score:>3} "
        f"fit {fit(f'{assessment.deal_fit:>3}')}  {severity_bits:<28} "
        f"{dim(assessment.package.name)} {dim(money(assessment.package.price))}"
    )


def _print_ranking(results) -> None:
    ranked = [(r, a) for r, a in rank_prospects(results) if r.ok]
    if not ranked:
        return
    print(rule("Send order (by expected value)"))
    for index, (result, assessment) in enumerate(ranked[:20], 1):
        print(
            f"  {index:>2}. {result.domain:<30} EV {bold(money(assessment.expected_value)):>12}  "
            f"{dim(assessment.budget.tier)}  {dim(assessment.package.name)}"
        )
    total = sum(a.expected_value for _, a in ranked)
    print()
    print(f"  Total expected value of this batch: {bold(money(total))}")


def _queue_prospects(store: Store, results, min_fit: int) -> int:
    queued = 0
    for result in results:
        if not result.ok:
            continue
        assessment = assess(result)
        prospect = Prospect(
            domain=result.domain,
            url=result.url,
            stage="queued" if assessment.deal_fit >= min_fit else "scanned",
            deal_value=float(assessment.package.price),
            package=assessment.package.key,
            health_score=assessment.health_score,
            deal_fit=assessment.deal_fit,
        )
        store.upsert_prospect(prospect)
        if assessment.deal_fit >= min_fit:
            queued += 1
    return queued


def _collect_urls(inline: list[str], file: str | None) -> list[str]:
    urls = list(inline or [])
    if file:
        path = Path(file)
        if not path.exists():
            print(red(f"No such file: {file}"), file=sys.stderr)
            return []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                urls.append(line)
    seen, unique = set(), []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


# -- parser ------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="money",
        description="Find businesses with provable, expensive defects — and prove it.",
        epilog="Start with: money plan --scenarios",
    )
    parser.add_argument("--store", default=".engine", help="state directory (default: .engine)")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_scan_flags(p):
        p.add_argument("urls", nargs="*", help="URLs or domains")
        p.add_argument("-f", "--file", help="file with one URL per line")
        p.add_argument("--delay", type=float, default=1.0, help="seconds between requests per host")
        p.add_argument("--links", type=int, default=8, help="internal links to status-check")
        p.add_argument("--min-fit", type=int, default=45, help="deal-fit threshold to queue")
        p.add_argument(
            "--ignore-robots",
            action="store_true",
            help="ignore robots.txt (don't — it is how you get blocklisted)",
        )

    p = sub.add_parser("init", help="set up your sender details and target")
    p.add_argument("--target", type=float, default=100000.0)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--deal", type=float, default=15000.0)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("scan", help="audit one or more sites")
    add_scan_flags(p)
    p.add_argument("--queue", action="store_true", help="add good prospects to the pipeline")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("run", help="scan, rank, queue and draft in one pass")
    add_scan_flags(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="generate the client-facing audit")
    p.add_argument("domain")
    p.add_argument("--format", choices=("html", "md", "both"), default="both")
    p.add_argument("--stdout", action="store_true", help="print Markdown instead of writing files")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("outreach", help="draft grounded outreach")
    p.add_argument("domain")
    p.add_argument("--variant", choices=VARIANTS, default="cold_email")
    p.add_argument("--all", action="store_true", help="the whole follow-up sequence")
    p.add_argument("--name", help="contact's first name")
    p.add_argument("--save", action="store_true")
    p.set_defaults(func=cmd_outreach)

    p = sub.add_parser("add", help="add a prospect by hand")
    p.add_argument("url")
    p.add_argument("--company")
    p.add_argument("--name")
    p.add_argument("--email")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("stage", help="move a prospect along the pipeline")
    p.add_argument("domain")
    p.add_argument("stage", choices=STAGES)
    p.add_argument("--value", type=float, help="deal value")
    p.add_argument("--note")
    p.set_defaults(func=cmd_stage)

    p = sub.add_parser("pipeline", help="show the board")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_pipeline)

    p = sub.add_parser("plan", help="what the target demands of you")
    p.add_argument("--target", type=float)
    p.add_argument("--days", type=int)
    p.add_argument("--deal", type=float, help="average deal value")
    p.add_argument("--scenarios", action="store_true", help="show sensitivity analysis")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("today", help="the daily brief")
    p.set_defaults(func=cmd_today)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = Store(args.store)
    try:
        return args.func(args, store)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
