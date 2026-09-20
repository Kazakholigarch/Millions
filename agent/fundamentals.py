"""Fundamental data for stocks — the numbers a value investor actually reads.

Crypto doesn't have earnings/balance sheets, so this module is stock-only.
Everything here comes from yfinance's `.info`, which pulls from Yahoo
Finance and can have gaps for smaller/foreign tickers — every field is
optional and the rest of the app degrades gracefully when one is missing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Fundamentals:
    ticker: str
    name: str | None
    pe_ratio: float | None          # price / earnings — how expensive vs profit
    forward_pe: float | None
    price_to_book: float | None     # price vs net asset value
    debt_to_equity: float | None    # leverage — higher = more financial risk
    profit_margin: float | None     # net income / revenue, as a fraction
    revenue_growth: float | None    # yoy revenue growth, as a fraction
    free_cash_flow: float | None    # cash actually generated, in dollars
    return_on_equity: float | None  # profitability vs shareholder equity
    market_cap: float | None
    dividend_yield: float | None


def fetch_fundamentals(ticker: str) -> Fundamentals:
    """Fetch key fundamental metrics for a stock ticker via yfinance."""
    import yfinance as yf  # imported lazily, matches data_sources.py's pattern

    info = yf.Ticker(ticker).get_info()

    return Fundamentals(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName"),
        pe_ratio=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        price_to_book=info.get("priceToBook"),
        debt_to_equity=info.get("debtToEquity"),
        profit_margin=info.get("profitMargins"),
        revenue_growth=info.get("revenueGrowth"),
        free_cash_flow=info.get("freeCashflow"),
        return_on_equity=info.get("returnOnEquity"),
        market_cap=info.get("marketCap"),
        dividend_yield=info.get("dividendYield"),
    )


def evaluate_fundamentals(f: Fundamentals) -> tuple[dict[str, str], list[str]]:
    """A plain value-investing checklist: is this business cheap, profitable,
    growing, and not drowning in debt? Thresholds are generic rules of thumb,
    not sector-adjusted — read the reasons, don't just trust the label.

    Returns (indicator_directions, reasons) in the same shape signals.py
    uses for technical indicators, so both can be combined and weighted
    the same way by the tracker's learned accuracy.
    """
    directions: dict[str, str] = {}
    reasons: list[str] = []

    if f.pe_ratio is not None:
        if f.pe_ratio <= 0:
            directions["pe_ratio"] = "bearish"
            reasons.append("P/E is negative (company isn't profitable)")
        elif f.pe_ratio < 25:
            directions["pe_ratio"] = "bullish"
            reasons.append(f"P/E of {f.pe_ratio:.1f} is reasonable (not richly valued)")
        elif f.pe_ratio > 40:
            directions["pe_ratio"] = "bearish"
            reasons.append(f"P/E of {f.pe_ratio:.1f} is high (priced for a lot of future growth)")
        else:
            reasons.append(f"P/E of {f.pe_ratio:.1f} is moderate")

    if f.debt_to_equity is not None:
        if f.debt_to_equity < 100:
            directions["debt_to_equity"] = "bullish"
            reasons.append(f"debt/equity of {f.debt_to_equity:.0f} is manageable")
        elif f.debt_to_equity > 200:
            directions["debt_to_equity"] = "bearish"
            reasons.append(f"debt/equity of {f.debt_to_equity:.0f} is high leverage")
        else:
            reasons.append(f"debt/equity of {f.debt_to_equity:.0f} is moderate")

    if f.profit_margin is not None:
        if f.profit_margin > 0.10:
            directions["profit_margin"] = "bullish"
            reasons.append(f"profit margin of {f.profit_margin*100:.1f}% is healthy")
        elif f.profit_margin < 0:
            directions["profit_margin"] = "bearish"
            reasons.append("company is currently unprofitable")

    if f.revenue_growth is not None:
        if f.revenue_growth > 0.05:
            directions["revenue_growth"] = "bullish"
            reasons.append(f"revenue growing {f.revenue_growth*100:.1f}% year-over-year")
        elif f.revenue_growth < 0:
            directions["revenue_growth"] = "bearish"
            reasons.append(f"revenue shrinking {abs(f.revenue_growth)*100:.1f}% year-over-year")

    if f.free_cash_flow is not None:
        if f.free_cash_flow > 0:
            directions["free_cash_flow"] = "bullish"
            reasons.append("generating positive free cash flow")
        else:
            directions["free_cash_flow"] = "bearish"
            reasons.append("burning cash (negative free cash flow)")

    if f.return_on_equity is not None:
        if f.return_on_equity > 0.15:
            directions["return_on_equity"] = "bullish"
            reasons.append(f"return on equity of {f.return_on_equity*100:.1f}% is strong")
        elif f.return_on_equity < 0:
            directions["return_on_equity"] = "bearish"
            reasons.append("negative return on equity")

    return directions, reasons
