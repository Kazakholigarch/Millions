"""Signal generation from technical indicators, optionally blended with a
fundamentals checklist, weighted by each indicator's own track record.

IMPORTANT: this combines transparent, well-known rules (moving averages,
RSI, momentum, a value-investing checklist) with an adaptive weighting
scheme (agent/tracker.py) that favors indicators with a real history of
being right. It is not financial advice, and a good historical win rate is
not a guarantee of future accuracy — markets change. Treat this as one
research input, never as a command to buy or sell.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .data_sources import PriceHistory
from .fundamentals import Fundamentals
from .indicators import momentum, rsi, sma


@dataclass
class Signal:
    symbol: str
    kind: str
    verdict: str  # "BULLISH", "BEARISH", "NEUTRAL"
    price: float
    sma20: float | None
    sma50: float | None
    rsi14: float | None
    momentum10: float | None
    reasons: list[str]
    indicator_directions: dict[str, str]  # for logging to the tracker
    fundamentals: Fundamentals | None = None
    fundamental_reasons: list[str] = field(default_factory=list)


def technical_directions(history: PriceHistory) -> tuple[dict[str, str], list[str], dict]:
    """Compute the raw technical indicator directions, reasons, and values."""
    closes = history.closes.dropna()
    price = float(closes.iloc[-1])

    sma20 = _last_or_none(sma(closes, 20))
    sma50 = _last_or_none(sma(closes, 50))
    rsi14 = _last_or_none(rsi(closes, 14))
    mom10 = _last_or_none(momentum(closes, 10))

    directions: dict[str, str] = {}
    reasons: list[str] = []

    if sma20 is not None:
        if price > sma20:
            directions["price_vs_sma20"] = "bullish"
            reasons.append(f"price (${price:,.2f}) is above SMA20 (${sma20:,.2f})")
        else:
            directions["price_vs_sma20"] = "bearish"
            reasons.append(f"price (${price:,.2f}) is below SMA20 (${sma20:,.2f})")

    if sma20 is not None and sma50 is not None:
        if sma20 > sma50:
            directions["sma20_vs_sma50"] = "bullish"
            reasons.append("SMA20 is above SMA50 (short-term uptrend)")
        else:
            directions["sma20_vs_sma50"] = "bearish"
            reasons.append("SMA20 is below SMA50 (short-term downtrend)")

    if rsi14 is not None:
        if rsi14 >= 70:
            directions["rsi14"] = "bearish"
            reasons.append(f"RSI14 is {rsi14:.1f} (overbought, pullback risk)")
        elif rsi14 <= 30:
            directions["rsi14"] = "bullish"
            reasons.append(f"RSI14 is {rsi14:.1f} (oversold, bounce potential)")
        else:
            reasons.append(f"RSI14 is {rsi14:.1f} (neutral zone)")

    if mom10 is not None:
        if mom10 > 0:
            directions["momentum10"] = "bullish"
            reasons.append(f"up {mom10:.1f}% over the last 10 periods")
        else:
            directions["momentum10"] = "bearish"
            reasons.append(f"down {abs(mom10):.1f}% over the last 10 periods")

    values = {"price": price, "sma20": sma20, "sma50": sma50, "rsi14": rsi14, "momentum10": mom10}
    return directions, reasons, values


def evaluate(
    history: PriceHistory,
    weights: dict[str, float] | None = None,
    fundamentals: Fundamentals | None = None,
) -> Signal:
    """Build a Signal from price history, optionally weighted by each
    indicator's learned track record and blended with a fundamentals
    checklist (stocks only).

    `weights` maps indicator name -> a 0-1 reliability weight (from
    agent/tracker.py). Any indicator missing from `weights` defaults to 0.5
    (a neutral prior — no track record yet either way).
    """
    weights = weights or {}

    tech_directions, tech_reasons, values = technical_directions(history)

    all_directions = dict(tech_directions)
    fundamental_reasons: list[str] = []

    if fundamentals is not None:
        from .fundamentals import evaluate_fundamentals

        fund_directions, fundamental_reasons = evaluate_fundamentals(fundamentals)
        all_directions.update(fund_directions)

    bullish_score = 0.0
    bearish_score = 0.0
    for name, direction in all_directions.items():
        w = weights.get(name, 0.5)
        if direction == "bullish":
            bullish_score += w
        elif direction == "bearish":
            bearish_score += w

    if abs(bullish_score - bearish_score) < 1e-9:
        verdict = "NEUTRAL"
    elif bullish_score > bearish_score:
        verdict = "BULLISH"
    else:
        verdict = "BEARISH"

    return Signal(
        symbol=history.symbol,
        kind=history.kind,
        verdict=verdict,
        price=values["price"],
        sma20=values["sma20"],
        sma50=values["sma50"],
        rsi14=values["rsi14"],
        momentum10=values["momentum10"],
        reasons=tech_reasons,
        indicator_directions=all_directions,
        fundamentals=fundamentals,
        fundamental_reasons=fundamental_reasons,
    )


def _last_or_none(series) -> float | None:
    series = series.dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])
