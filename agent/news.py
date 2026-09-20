"""Recent headlines for a stock, via Yahoo Finance (free, no API key).

This surfaces headlines as context for a human to read — it does not try to
score sentiment from the text. Turning a headline into a reliable "bullish"
or "bearish" signal needs real NLP/judgment, which is exactly what the
optional LLM narrative (agent/narrative.py) is for; treat plain headlines
here as reading material, not a verdict.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NewsItem:
    title: str
    publisher: str | None
    link: str | None


def fetch_stock_news(ticker: str, limit: int = 5) -> list[NewsItem]:
    """Fetch recent headlines for a stock ticker via yfinance."""
    import yfinance as yf  # imported lazily, matches data_sources.py's pattern

    raw_items = yf.Ticker(ticker).get_news(count=limit) or []

    items: list[NewsItem] = []
    for raw in raw_items[:limit]:
        # yfinance wraps each article under a "content" key as of recent versions;
        # fall back to the flat shape older versions used, so either works.
        content = raw.get("content", raw)
        title = content.get("title")
        if not title:
            continue
        publisher = (content.get("provider") or {}).get("displayName") or content.get("publisher")
        link = (content.get("canonicalUrl") or {}).get("url") or content.get("link")
        items.append(NewsItem(title=title, publisher=publisher, link=link))

    return items
