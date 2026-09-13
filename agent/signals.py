"""Rule-based signal generation from indicators.

IMPORTANT: this is a simple, transparent rule set for educational purposes.
It is not financial advice and is not a proven profitable strategy. Treat
its output as one input among many, not a command.
"""
from __future__ import annotations

from dataclasses import dataclass

from .data_sources import PriceHistory
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


def evaluate(history: PriceHistory) -> Signal:
    closes = history.closes.dropna()
    price = float(closes.iloc[-1])

    sma20_series = sma(closes, 20)
    sma50_series = sma(closes, 50)
    rsi_series = rsi(closes, 14)
    mom_series = momentum(closes, 10)

    sma20 = _last_or_none(sma20_series)
    sma50 = _last_or_none(sma50_series)
    rsi14 = _last_or_none(rsi_series)
    mom10 = _last_or_none(mom_series)

    reasons: list[str] = []
    bullish_points = 0
    bearish_points = 0

    if sma20 is not None:
        if price > sma20:
            bullish_points += 1
            reasons.append(f"price (${price:,.2f}) is above SMA20 (${sma20:,.2f})")
        else:
            bearish_points += 1
            reasons.append(f"price (${price:,.2f}) is below SMA20 (${sma20:,.2f})")

    if sma20 is not None and sma50 is not None:
        if sma20 > sma50:
            bullish_points += 1
            reasons.append("SMA20 is above SMA50 (short-term uptrend)")
        else:
            bearish_points += 1
            reasons.append("SMA20 is below SMA50 (short-term downtrend)")

    if rsi14 is not None:
        if rsi14 >= 70:
            bearish_points += 1
            reasons.append(f"RSI14 is {rsi14:.1f} (overbought, pullback risk)")
        elif rsi14 <= 30:
            bullish_points += 1
            reasons.append(f"RSI14 is {rsi14:.1f} (oversold, bounce potential)")
        else:
            reasons.append(f"RSI14 is {rsi14:.1f} (neutral zone)")

    if mom10 is not None:
        if mom10 > 0:
            bullish_points += 1
            reasons.append(f"up {mom10:.1f}% over the last 10 periods")
        else:
            bearish_points += 1
            reasons.append(f"down {abs(mom10):.1f}% over the last 10 periods")

    if bullish_points > bearish_points:
        verdict = "BULLISH"
    elif bearish_points > bullish_points:
        verdict = "BEARISH"
    else:
        verdict = "NEUTRAL"

    return Signal(
        symbol=history.symbol,
        kind=history.kind,
        verdict=verdict,
        price=price,
        sma20=sma20,
        sma50=sma50,
        rsi14=rsi14,
        momentum10=mom10,
        reasons=reasons,
    )


def _last_or_none(series) -> float | None:
    series = series.dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])
