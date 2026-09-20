"""Formats AssetAnalysis objects into a human-readable terminal report."""
from __future__ import annotations

from .analysis import AssetAnalysis

_VERDICT_MARKERS = {
    "BULLISH": "[+]",
    "BEARISH": "[-]",
    "NEUTRAL": "[=]",
}


def render(analyses: list[AssetAnalysis]) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  MILLIONS AGENT — market analysis report")
    lines.append("  (educational signals, not financial advice)")
    lines.append("=" * 60)

    for a in analyses:
        sig = a.signal
        marker = _VERDICT_MARKERS.get(sig.verdict, "[?]")
        lines.append("")
        lines.append(f"{marker} {sig.symbol.upper()} ({sig.kind})  →  {sig.verdict}")
        lines.append(f"    price: ${sig.price:,.2f}")
        for reason in sig.reasons:
            lines.append(f"    - {reason}")
        for reason in sig.fundamental_reasons:
            lines.append(f"    - [fundamentals] {reason}")

        if a.news:
            lines.append("    Recent headlines:")
            for item in a.news[:3]:
                by = f" ({item.publisher})" if item.publisher else ""
                lines.append(f"      * {item.title}{by}")

        lines.append(f"    Note: {a.narrative}")

        if a.scored_history:
            lines.append(f"    Past signals just scored ({len(a.scored_history)}):")
            for s in a.scored_history:
                lines.append(
                    f"      * {s.timestamp[:10]} was {s.old_verdict} -> {s.outcome} "
                    f"({s.forward_return_pct:+.1f}% since)"
                )

        if a.track_record and a.track_record.total_scored:
            lines.append(
                f"    Track record for {sig.symbol.upper()}: "
                f"{a.track_record.correct}/{a.track_record.total_scored} correct "
                f"({a.track_record.accuracy_pct:.0f}%)"
            )

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
