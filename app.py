#!/usr/bin/env python3
"""Millions — point-and-click web UI.

Two tools live here:

    /        the market-analysis agent (crypto/stock technical signals)
    /engine  the revenue engine dashboard (see STRATEGY.md)

Run it with:

    python3 app.py

Then open the forwarded port (in GitHub Codespaces, a popup or the "Ports"
tab will offer an "Open in Browser" link — usually port 5000).
"""
from __future__ import annotations

from flask import Flask, render_template, request

from agent.data_sources import fetch_crypto_history, fetch_stock_history
from agent.signals import evaluate
from engine.fetch import Fetcher
from engine.outreach import compose
from engine.pipeline import daily_brief, status
from engine.scan import scan
from engine.score import assess
from engine.storage import Store

app = Flask(__name__)

# Common assets as checkboxes so most people never need to type anything.
CRYPTO_OPTIONS = [
    ("bitcoin", "Bitcoin (BTC)"),
    ("ethereum", "Ethereum (ETH)"),
    ("solana", "Solana (SOL)"),
    ("dogecoin", "Dogecoin (DOGE)"),
    ("cardano", "Cardano (ADA)"),
]

STOCK_OPTIONS = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("TSLA", "Tesla"),
    ("NVDA", "Nvidia"),
    ("GOOGL", "Alphabet (Google)"),
]


@app.route("/", methods=["GET"])
def index():
    # Using GET (a query string) instead of POST here is deliberate: some
    # browsers/proxies (notably Safari through GitHub Codespaces' forwarded
    # URLs) mishandle POSTed form responses and offer to "download" the page
    # instead of rendering it. GET avoids that entirely and, as a bonus,
    # makes a given analysis linkable/bookmarkable.
    signals = []
    errors = []
    submitted = bool(request.args)

    if submitted:
        crypto_ids = request.args.getlist("crypto") + _split_custom(
            request.args.get("custom_crypto", "")
        )
        tickers = request.args.getlist("stocks") + _split_custom(
            request.args.get("custom_stocks", "")
        )

        for coin_id in crypto_ids:
            try:
                history = fetch_crypto_history(coin_id)
                signals.append(evaluate(history))
            except Exception as exc:  # noqa: BLE001 - surface per-asset failures
                errors.append(f"crypto '{coin_id}': {exc}")

        for ticker in tickers:
            try:
                history = fetch_stock_history(ticker)
                signals.append(evaluate(history))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"stock '{ticker}': {exc}")

    return render_template(
        "index.html",
        crypto_options=CRYPTO_OPTIONS,
        stock_options=STOCK_OPTIONS,
        signals=signals,
        errors=errors,
        submitted=submitted,
    )


@app.route("/engine", methods=["GET"])
def engine_dashboard():
    """The revenue engine: the plan, today's number, and a one-box scanner.

    GET rather than POST for the same reason as the page above — a forwarded
    Codespaces URL mishandles POSTed responses — with the bonus that a scan
    result is a shareable link.
    """
    store = Store()
    model = store.model()
    prospects = store.load_prospects()

    context = {
        "model": model,
        "req": model.requirements(),
        "state": status(prospects, model, store.started_on()),
        "brief": daily_brief(prospects, model, store.started_on()),
        "prospects": sorted(prospects, key=lambda p: -p.weighted_value)[:25],
        "result": None,
        "assessment": None,
        "draft": None,
        "error": None,
        "scanned_url": request.args.get("url", "").strip(),
    }

    if context["scanned_url"]:
        fetcher = Fetcher(min_delay=0.5)
        try:
            result = scan(context["scanned_url"], fetcher=fetcher, link_sample=5)
        finally:
            fetcher.close()

        if not result.ok:
            context["error"] = f"Could not scan {result.domain}: {result.error}"
        else:
            store.save_scan(result)
            assessment = assess(result)
            context["result"] = result
            context["assessment"] = assessment
            if result.findings:
                try:
                    context["draft"] = compose(result, assessment, store.sender(), "cold_email")
                except ValueError as exc:
                    context["error"] = str(exc)

    return render_template("engine.html", **context)


def _split_custom(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
