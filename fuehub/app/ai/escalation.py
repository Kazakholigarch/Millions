from __future__ import annotations

"""Rule-based clinical-escalation detector.

Anything genuinely clinical -- assessing a specific hair loss pattern,
medical history, medication interactions, candidacy -- must go to a real
clinician instead of being answered by the AI. This is deliberately a
keyword/phrase matcher rather than a model call: it's the gate that decides
whether the AI drafter runs *at all* for a given inbound message, so it
needs to fail closed (over-escalate) rather than risk letting a clinical
question through to an AI-drafted answer. The AI drafter's own system
prompt (app/ai/draft.py) repeats the same instruction as defense in depth.
"""

CLINICAL_KEYWORDS: dict[str, list[str]] = {
    "en": [
        "medical history", "medication", "medicine i take", "on medication",
        "blood thinner", "diabetes", "diabetic", "pregnant", "pregnancy",
        "allerg", "am i a candidate", "am i suitable", "suitable for me",
        "candidacy", "assess my hair", "my hair loss pattern", "norwood",
        "scarring", "scar tissue", "infection", "side effect", "minoxidil",
        "finasteride", "propecia", "interact with", "health condition",
        "autoimmune", "psoriasis", "blood pressure", "heart condition",
        "surgery risk", "am i a good candidate",
    ],
    "de": [
        "krankengeschichte", "medikament", "blutverdünner", "diabetes",
        "schwanger", "allergi", "bin ich geeignet", "eignung", "kandidat",
        "meine haarausfall", "haarausfallmuster", "norwood", "vernarbung",
        "narbengewebe", "infektion", "nebenwirkung", "minoxidil",
        "finasterid", "wechselwirkung", "erkrankung", "autoimmun",
        "blutdruck", "herzerkrankung",
    ],
    "ar": [
        "التاريخ الطبي", "دواء", "أدوية", "مميع الدم", "سكري", "حامل",
        "حساسية", "هل أنا مرشح", "مناسب لي", "نمط تساقط شعري", "تندب",
        "ندبة", "عدوى", "اثار جانبية", "آثار جانبية", "مينوكسيديل",
        "فيناستيرايد", "تفاعل دوائي", "حالة صحية", "مناعة ذاتية",
        "ضغط الدم", "مرض القلب",
    ],
    "ru": [
        "история болезни", "лекарств", "препарат", "разжижающие кровь",
        "диабет", "беременн", "аллерги", "подхожу ли я", "кандидат",
        "моя модель облысения", "норвуд", "рубц", "шрам", "инфекция",
        "побочн", "миноксидил", "финастерид", "взаимодействие",
        "заболевание", "аутоиммун", "давлени", "сердечн",
    ],
}


def needs_clinical_escalation(text: str) -> list[str]:
    """Return the list of matched trigger phrases (empty if none). The
    caller treats a non-empty list as "route to a clinician, don't
    AI-draft"."""
    if not text:
        return []
    lowered = text.lower()
    matches = []
    for keywords in CLINICAL_KEYWORDS.values():
        for kw in keywords:
            if kw in lowered:
                matches.append(kw)
    return matches
