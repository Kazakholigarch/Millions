"""Turns a Signal into an investor-style writeup.

Two modes:
  - Rule-based (default, always works, no API key): a templated summary of
    the checklist — what looks good, what doesn't, and why.
  - AI-enhanced (optional): if ANTHROPIC_API_KEY is set in the environment,
    sends the same structured data to Claude and asks for a short narrative
    in the voice of a disciplined value investor. This is strictly an
    upgrade to the writing, not a different or "smarter" verdict — the
    underlying BULLISH/BEARISH/NEUTRAL call and its weights are unchanged;
    an LLM is not more accurate at predicting prices than the checklist is,
    it's just better at explaining one in plain English.

Neither mode is investment advice. Both describe a snapshot of public data
using a simple, fixed checklist — not a prediction.
"""
from __future__ import annotations

import os

from .news import NewsItem
from .signals import Signal


def build_narrative(signal: Signal, news: list[NewsItem] | None = None) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return _ai_narrative(signal, news or [], api_key)
        except Exception:
            pass  # fall through to the rule-based version if the API call fails
    return _rule_based_narrative(signal, news or [])


def _rule_based_narrative(signal: Signal, news: list[NewsItem]) -> str:
    lines = []
    lines.append(f"{signal.symbol.upper()} checklist verdict: {signal.verdict}.")

    if signal.reasons:
        lines.append("Technicals: " + "; ".join(signal.reasons) + ".")

    if signal.fundamental_reasons:
        lines.append("Fundamentals: " + "; ".join(signal.fundamental_reasons) + ".")
    elif signal.kind == "stock":
        lines.append("Fundamentals: not available for this ticker.")

    if news:
        lines.append(
            "Recent headlines to read yourself (not scored, just context): "
            + "; ".join(n.title for n in news[:3])
            + "."
        )

    lines.append(
        "This is a fixed checklist snapshot, not a prediction — verify anything "
        "material before acting on it."
    )
    return " ".join(lines)


def _ai_narrative(signal: Signal, news: list[NewsItem], api_key: str) -> str:
    import requests

    fundamentals_summary = "; ".join(signal.fundamental_reasons) or "no fundamentals available"
    technicals_summary = "; ".join(signal.reasons) or "no technicals available"
    news_summary = "; ".join(n.title for n in news[:5]) or "no recent headlines fetched"

    prompt = f"""You are a disciplined, skeptical value investor reviewing {signal.symbol.upper()}.

Checklist-based verdict (already computed, do not change it): {signal.verdict}
Technical picture: {technicals_summary}
Fundamentals: {fundamentals_summary}
Recent headlines: {news_summary}

Write a short (3-5 sentence) plain-English investor note explaining whether \
this looks attractive right now and why, referencing the specific numbers \
above. Be balanced — name real risks, not just the positives. Do not \
invent numbers that weren't given to you. End by reminding the reader this \
is not financial advice."""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["content"][0]["text"].strip()
