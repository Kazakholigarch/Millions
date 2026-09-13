#!/usr/bin/env python3
"""Millions Agent — CLI entrypoint.

Fetches live crypto/stock data, computes technical signals, and prints a
report. This tool does not place trades and does not require API keys.

Examples:
    python3 main.py --crypto bitcoin,ethereum --stocks AAPL,MSFT
    python3 main.py --crypto solana
    python3 main.py --stocks TSLA --stock-period 1y
"""
from __future__ import annotations

import argparse
import sys

from agent.data_sources import fetch_crypto_history, fetch_stock_history
from agent.report import render
from agent.signals import evaluate


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Millions Agent: crypto/stock signal report")
    parser.add_argument(
        "--crypto",
        default="",
        help="Comma-separated CoinGecko coin ids, e.g. bitcoin,ethereum,solana",
    )
    parser.add_argument(
        "--stocks",
        default="",
        help="Comma-separated stock tickers, e.g. AAPL,MSFT,TSLA",
    )
    parser.add_argument(
        "--crypto-days",
        type=int,
        default=90,
        help="Days of crypto history to analyze (default: 90)",
    )
    parser.add_argument(
        "--stock-period",
        default="6mo",
        help="yfinance period for stock history, e.g. 3mo, 6mo, 1y (default: 6mo)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    crypto_ids = [c.strip() for c in args.crypto.split(",") if c.strip()]
    tickers = [t.strip() for t in args.stocks.split(",") if t.strip()]

    if not crypto_ids and not tickers:
        print("Nothing to analyze. Pass --crypto and/or --stocks.", file=sys.stderr)
        print("Example: python3 main.py --crypto bitcoin --stocks AAPL", file=sys.stderr)
        return 1

    signals = []
    errors = []

    for coin_id in crypto_ids:
        try:
            history = fetch_crypto_history(coin_id, days=args.crypto_days)
            signals.append(evaluate(history))
        except Exception as exc:  # noqa: BLE001 - surface any fetch/parse failure per-asset
            errors.append(f"crypto '{coin_id}': {exc}")

    for ticker in tickers:
        try:
            history = fetch_stock_history(ticker, period=args.stock_period)
            signals.append(evaluate(history))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"stock '{ticker}': {exc}")

    if signals:
        print(render(signals))

    if errors:
        print("\nErrors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    return 0 if signals else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
