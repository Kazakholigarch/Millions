#!/usr/bin/env python3
"""Millions Agent — point-and-click web UI.

Run this instead of main.py for a browser-based experience with checkboxes
instead of typed commands:

    python3 app.py

Then open the forwarded port (in GitHub Codespaces, a popup or the "Ports"
tab will offer an "Open in Browser" link — usually port 5000).
"""
from __future__ import annotations

from flask import Flask, render_template, request

from agent.data_sources import fetch_crypto_history, fetch_stock_history
from agent.signals import evaluate

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


@app.route("/", methods=["GET", "POST"])
def index():
    signals = []
    errors = []
    submitted = request.method == "POST"

    if submitted:
        crypto_ids = request.form.getlist("crypto") + _split_custom(
            request.form.get("custom_crypto", "")
        )
        tickers = request.form.getlist("stocks") + _split_custom(
            request.form.get("custom_stocks", "")
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


def _split_custom(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
