"""Technical indicators computed from a price series.

These are standard, well-known formulas (SMA, RSI, momentum) — nothing exotic.
They describe past price behavior; they don't predict the future.
"""
from __future__ import annotations

import pandas as pd


def sma(closes: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return closes.rolling(window=window, min_periods=window).mean()


def rsi(closes: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index (0-100). >70 = overbought, <30 = oversold."""
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=window, min_periods=window).mean()
    avg_loss = loss.rolling(window=window, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    result = 100 - (100 / (1 + rs))
    # Where avg_loss is 0 but avg_gain isn't, RSI is 100 (pure upward moves).
    result = result.where(avg_loss != 0, 100.0)
    return result


def momentum(closes: pd.Series, window: int = 10) -> pd.Series:
    """Percent change over the last `window` periods."""
    return closes.pct_change(periods=window) * 100
