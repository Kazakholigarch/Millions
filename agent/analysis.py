"""Orchestrates a full analysis: fetch data, weight indicators by their
learned track record, score any past signals that have matured, and build
a narrative. This is what main.py and app.py both call — one place owns
the "how everything fits together" logic so the CLI and web UI can't drift
out of sync.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import tracker
from .data_sources import fetch_crypto_history, fetch_stock_history
from .fundamentals import Fundamentals, fetch_fundamentals
from .narrative import build_narrative
from .news import NewsItem, fetch_stock_news
from .signals import Signal, evaluate
from .tracker import ScoredSignal, TrackRecord

# All indicator names that can ever appear, so we always ask the tracker for
# a weight on every one of them (unknown ones default to a neutral 0.5).
ALL_INDICATOR_NAMES = [
    "price_vs_sma20",
    "sma20_vs_sma50",
    "rsi14",
    "momentum10",
    "pe_ratio",
    "debt_to_equity",
    "profit_margin",
    "revenue_growth",
    "free_cash_flow",
    "return_on_equity",
]


@dataclass
class AssetAnalysis:
    signal: Signal
    narrative: str
    news: list[NewsItem] = field(default_factory=list)
    scored_history: list[ScoredSignal] = field(default_factory=list)
    track_record: TrackRecord | None = None


def analyze_crypto(coin_id: str, days: int = 90) -> AssetAnalysis:
    history = fetch_crypto_history(coin_id, days=days)
    weights = tracker.get_weights(ALL_INDICATOR_NAMES)
    signal = evaluate(history, weights=weights)

    tracker.log_signal(signal.symbol, signal.kind, signal.price, signal.verdict, signal.indicator_directions)
    scored_history = tracker.score_due_signals(signal.symbol, signal.price)
    track_record = tracker.get_track_record(signal.symbol)

    narrative = build_narrative(signal, news=None)

    return AssetAnalysis(
        signal=signal, narrative=narrative, news=[], scored_history=scored_history, track_record=track_record
    )


def analyze_stock(ticker_symbol: str, period: str = "6mo") -> AssetAnalysis:
    history = fetch_stock_history(ticker_symbol, period=period)

    fundamentals: Fundamentals | None
    try:
        fundamentals = fetch_fundamentals(ticker_symbol)
    except Exception:
        fundamentals = None  # some tickers (foreign listings, ETFs) have thin data — degrade gracefully

    weights = tracker.get_weights(ALL_INDICATOR_NAMES)
    signal = evaluate(history, weights=weights, fundamentals=fundamentals)

    tracker.log_signal(signal.symbol, signal.kind, signal.price, signal.verdict, signal.indicator_directions)
    scored_history = tracker.score_due_signals(signal.symbol, signal.price)
    track_record = tracker.get_track_record(signal.symbol)

    try:
        news = fetch_stock_news(ticker_symbol)
    except Exception:
        news = []

    narrative = build_narrative(signal, news=news)

    return AssetAnalysis(
        signal=signal, narrative=narrative, news=news, scored_history=scored_history, track_record=track_record
    )


def overall_track_record() -> TrackRecord:
    """Track record across every symbol ever analyzed, for a dashboard-level view."""
    return tracker.get_track_record(symbol=None)
