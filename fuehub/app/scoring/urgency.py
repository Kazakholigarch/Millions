from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.constants import UrgencyBand

"""Rule-based urgency/intent scoring so hot leads jump the approve/edit
queue ahead of routine ones. Recomputed on every inbound message against
the lead's full inbound text (not just the first message) -- a lead that
mentions a travel date three messages in should re-rank just as much as
one that mentions it up front.
"""

_BUDGET_RE = re.compile(
    r"[€$£]\s?\d{2,6}|\d{2,6}\s?(eur|usd|euros?|dollars?)|\bbudget\b|\bбюджет\w*\b|\bميزاني\w*\b|\bbütçe\w*\b",
    re.IGNORECASE,
)

_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|october|november|december|"
    "januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember|"
    "январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр"
)
_DATE_RE = re.compile(
    rf"\b\d{{1,2}}[/.\-]\d{{1,2}}([/.\-]\d{{2,4}})?\b|\b({_MONTH_NAMES})\b|"
    r"\b(next week|next month|this week|in \d+ (days|weeks))\b|"
    r"\b(nächste woche|nächsten monat|diese woche)\b|"
    r"\b(на следующей неделе|в следующем месяце|на этой неделе)\b",
    re.IGNORECASE,
)

_URGENCY_RE = re.compile(
    r"\b(asap|urgent|how soon|right away|immediately|as soon as possible)\b|"
    r"\b(so schnell wie möglich|dringend|sofort)\b|"
    r"\b(как можно скорее|срочно|немедленно)\b|"
    r"(في أقرب وقت|عاجل|حالاً)",
    re.IGNORECASE,
)

_GRAFT_INTEREST_RE = re.compile(
    r"\bgraft|\bкол-во графт|графт|\bبصيل|\bfue\b|\bdhi\b|\bhow much\b|\bcost\b|\bpreis\b|"
    r"\bkosten\b|\bсколько стоит\b|\bتكلفة\b",
    re.IGNORECASE,
)


@dataclass
class ScoreResult:
    score: int
    band: str
    reasons: list[str] = field(default_factory=list)


def score_lead_text(*, combined_inbound_text: str, has_photos: bool) -> ScoreResult:
    text = combined_inbound_text or ""
    score = 0
    reasons: list[str] = []

    if has_photos:
        score += 25
        reasons.append("Sent photos")

    if _BUDGET_RE.search(text):
        score += 20
        reasons.append("Mentioned budget/price figure")

    if _DATE_RE.search(text):
        score += 20
        reasons.append("Mentioned a specific date/timeframe")

    if _URGENCY_RE.search(text):
        score += 25
        reasons.append('Used urgency language ("how soon", "asap"...)')

    if _GRAFT_INTEREST_RE.search(text):
        score += 10
        reasons.append("Asked about graft count/cost/technique")

    score = min(score, 100)

    if score >= 65:
        band = UrgencyBand.HOT
    elif score >= 35:
        band = UrgencyBand.WARM
    else:
        band = UrgencyBand.ROUTINE

    return ScoreResult(score=score, band=band, reasons=reasons)
