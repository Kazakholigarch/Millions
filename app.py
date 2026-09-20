#!/usr/bin/env python3
"""Millions Agent — point-and-click web UI.

Run this instead of main.py for a browser-based experience with checkboxes
instead of typed commands:

    python3 app.py

Then open the forwarded port (in GitHub Codespaces, a popup or the "Ports"
tab will offer an "Open in Browser" link — usually port 5000).

Optional: set ANTHROPIC_API_KEY in the environment before running this to
upgrade the writeup style to an AI-generated narrative. Everything works
without it — the verdict itself never depends on the API key, only the
prose explaining it does.
"""
from __future__ import annotations

from flask import Flask, render_template, request

from agent.analysis import analyze_crypto, analyze_stock, overall_track_record

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
    analyses = []
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
                analyses.append(analyze_crypto(coin_id))
            except Exception as exc:  # noqa: BLE001 - surface per-asset failures
                errors.append(f"crypto '{coin_id}': {exc}")

        for ticker in tickers:
            try:
                analyses.append(analyze_stock(ticker))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"stock '{ticker}': {exc}")

    track_record = overall_track_record()

    return render_template(
        "index.html",
        crypto_options=CRYPTO_OPTIONS,
        stock_options=STOCK_OPTIONS,
        analyses=analyses,
        errors=errors,
        submitted=submitted,
        track_record=track_record,
    )


def _split_custom(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
