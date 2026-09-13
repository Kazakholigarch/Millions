"""Data fetching for crypto (CoinGecko) and stocks (Yahoo Finance via yfinance).

Both sources are free and require no API key, so this runs out of the box.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import requests

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


@dataclass
class PriceHistory:
    symbol: str
    kind: str  # "crypto" or "stock"
    closes: pd.Series  # indexed by date, most recent last


def fetch_crypto_history(coin_id: str, days: int = 90) -> PriceHistory:
    """Fetch daily close prices for a coin from CoinGecko.

    coin_id examples: "bitcoin", "ethereum", "solana" (CoinGecko's slug, not ticker).
    """
    url = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    prices = data.get("prices", [])
    if not prices:
        raise ValueError(f"No price data returned for '{coin_id}'")

    idx = [dt.datetime.fromtimestamp(p[0] / 1000, tz=dt.timezone.utc) for p in prices]
    vals = [p[1] for p in prices]
    closes = pd.Series(vals, index=pd.DatetimeIndex(idx), name=coin_id)
    return PriceHistory(symbol=coin_id, kind="crypto", closes=closes)


def fetch_stock_history(ticker: str, period: str = "6mo") -> PriceHistory:
    """Fetch daily close prices for a stock ticker via yfinance."""
    import yfinance as yf  # imported lazily so crypto-only usage doesn't need it

    df = yf.Ticker(ticker).history(period=period, interval="1d")
    if df.empty:
        raise ValueError(f"No price data returned for '{ticker}'")

    closes = df["Close"]
    closes.name = ticker
    return PriceHistory(symbol=ticker, kind="stock", closes=closes)
