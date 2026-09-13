"""Formats Signal objects into a human-readable terminal report."""
from __future__ import annotations

from .signals import Signal

_VERDICT_MARKERS = {
    "BULLISH": "[+]",
    "BEARISH": "[-]",
    "NEUTRAL": "[=]",
}


def render(signals: list[Signal]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  MILLIONS AGENT — market analysis report")
    lines.append("  (educational signals, not financial advice)")
    lines.append("=" * 60)

    for sig in signals:
        marker = _VERDICT_MARKERS.get(sig.verdict, "[?]")
        lines.append("")
        lines.append(f"{marker} {sig.symbol.upper()} ({sig.kind})  →  {sig.verdict}")
        lines.append(f"    price: ${sig.price:,.2f}")
        for reason in sig.reasons:
            lines.append(f"    - {reason}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
