from __future__ import annotations

import json

"""Topic detection and the offline/"fake" FAQ drafter.

The five FAQ categories here are exactly the ones the AI is allowed to
answer per the product spec: cost ranges by graft count, FUE vs DHI, what
the international-patient package includes, typical length of stay, and
what the free consultation involves. Everything else either isn't
recognized (falls back to a clarifying question) or was already stopped
upstream by app.ai.escalation before reaching here.
"""

TOPIC_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "cost": {
        "en": ["cost", "price", "how much", "€", "$", "expensive", "afford", "budget"],
        "de": ["kosten", "preis", "wie teuer", "wieviel kostet", "budget"],
        "ar": ["تكلفة", "سعر", "كم", "ميزانية"],
        "ru": ["стоимост", "цена", "сколько стоит", "бюджет"],
    },
    "technique": {
        "en": ["fue", "dhi", "difference", "which technique", "which method"],
        "de": ["fue", "dhi", "unterschied", "welche methode"],
        "ar": ["فيو", "دي اتش اي", "الفرق", "أي تقنية"],
        "ru": ["fue", "dhi", "разниц", "какая методика"],
    },
    "package": {
        "en": ["package", "include", "hotel", "transfer", "translator", "flight", "all-inclusive"],
        "de": ["paket", "enthalten", "hotel", "transfer", "dolmetscher", "flug"],
        "ar": ["حزمة", "يشمل", "فندق", "نقل", "مترجم", "طيران"],
        "ru": ["пакет", "включ", "отель", "трансфер", "переводчик", "перелет"],
    },
    "stay": {
        "en": ["how many days", "how long", "stay", "duration", "nights"],
        "de": ["wie lange", "wie viele tage", "aufenthalt", "nächte"],
        "ar": ["كم يوم", "كم يوما", "مدة", "ليالي"],
        "ru": ["сколько дней", "как долго", "продолжительность", "ночей"],
    },
    "consultation": {
        "en": ["consultation", "free consult", "video call", "book", "appointment"],
        "de": ["beratung", "kostenlose beratung", "termin", "videoanruf"],
        "ar": ["استشارة", "استشارة مجانية", "حجز", "موعد"],
        "ru": ["консультация", "бесплатная консультация", "записаться", "видеозвонок"],
    },
}

GREETING = {
    "en": "Thanks for your message!",
    "de": "Danke für Ihre Nachricht!",
    "ar": "شكراً لرسالتك!",
    "ru": "Спасибо за ваше сообщение!",
}

TOPIC_TEXT: dict[str, dict[str, str]] = {
    "cost": {
        "en": "For {clinic_name}, typical pricing by graft count is: {ranges}. Your exact quote "
        "depends on your graft count, which a specialist can estimate for free from a couple of "
        "photos or during your consultation.",
        "de": "Bei {clinic_name} liegen die üblichen Preise je nach Graft-Anzahl bei: {ranges}. "
        "Der genaue Preis hängt von Ihrer individuellen Graft-Anzahl ab, die ein Spezialist "
        "kostenlos anhand von ein paar Fotos oder in Ihrer Beratung einschätzen kann.",
        "ar": "بالنسبة لـ {clinic_name}، تتراوح الأسعار المعتادة حسب عدد البصيلات كالتالي: "
        "{ranges}. يعتمد السعر النهائي على عدد البصيلات الذي يمكن لأخصائي تقديره مجاناً من بضع "
        "صور أو خلال استشارتك.",
        "ru": "В {clinic_name} типичные цены в зависимости от количества графтов: {ranges}. "
        "Точная стоимость зависит от количества графтов, которое специалист может бесплатно "
        "оценить по нескольким фото или на консультации.",
    },
    "technique": {
        "en": "FUE: {fue} DHI: {dhi} Both are offered at {clinic_name}; a specialist can "
        "recommend which suits your case.",
        "de": "FUE: {fue} DHI: {dhi} Beide Verfahren werden bei {clinic_name} angeboten; ein "
        "Spezialist kann Ihnen die passende Methode empfehlen.",
        "ar": "FUE: {fue} DHI: {dhi} تتوفر كلتا التقنيتين في {clinic_name}؛ يمكن لأخصائي أن "
        "ينصحك بالأنسب لحالتك.",
        "ru": "FUE: {fue} DHI: {dhi} Обе методики доступны в {clinic_name}; специалист "
        "порекомендует, что подходит именно вам.",
    },
    "package": {
        "en": "Our international-patient package includes: {package}.",
        "de": "Unser Paket für internationale Patienten umfasst: {package}.",
        "ar": "تشمل حزمتنا للمرضى الدوليين: {package}.",
        "ru": "Наш пакет для иностранных пациентов включает: {package}.",
    },
    "stay": {
        "en": "Most patients stay {stay}.",
        "de": "Die meisten Patienten bleiben {stay}.",
        "ar": "يبقى معظم المرضى {stay}.",
        "ru": "Большинство пациентов остаются {stay}.",
    },
    "consultation": {
        "en": "{consultation} Would you like me to check available times?",
        "de": "{consultation} Soll ich verfügbare Termine für Sie prüfen?",
        "ar": "{consultation} هل تود أن أتحقق من المواعيد المتاحة؟",
        "ru": "{consultation} Хотите, я проверю доступное время?",
    },
}

SLOT_OFFER = {
    "en": "A few times our specialist has free: {slots}. Reply with the option that works and "
    "we'll lock it in.",
    "de": "Unser Spezialist hat unter anderem folgende Termine frei: {slots}. Antworten Sie "
    "einfach mit der passenden Option, wir reservieren sie für Sie.",
    "ar": "تتوفر هذه المواعيد لدى أخصائينا: {slots}. يمكنك الرد بالخيار المناسب وسنقوم بحجزه لك.",
    "ru": "У нашего специалиста есть свободное время: {slots}. Ответьте подходящим вариантом, и "
    "мы его забронируем.",
}

PHOTO_NOTE = {
    "en": "Thanks for the photos -- a specialist will personally review them.",
    "de": "Danke für die Fotos -- ein Spezialist wird sie persönlich prüfen.",
    "ar": "شكراً على الصور -- سيقوم أخصائي بمراجعتها شخصياً.",
    "ru": "Спасибо за фото -- специалист лично их рассмотрит.",
}

FALLBACK = {
    "en": "Could you tell me a bit more? Happy to help with cost, FUE vs DHI, what our package "
    "includes, how long you'd need to stay, or booking a free consultation.",
    "de": "Können Sie mir etwas mehr erzählen? Gerne helfen wir bei Kosten, FUE vs. DHI, unserem "
    "Leistungspaket, der Aufenthaltsdauer oder der Buchung einer kostenlosen Beratung.",
    "ar": "هل يمكنك إخباري بمزيد من التفاصيل؟ يسعدنا مساعدتك بخصوص التكلفة، الفرق بين FUE و DHI، "
    "محتويات باقتنا، مدة الإقامة، أو حجز استشارة مجانية.",
    "ru": "Расскажите, пожалуйста, немного подробнее? С радостью поможем со стоимостью, разницей "
    "FUE и DHI, составом пакета, длительностью пребывания или записью на бесплатную консультацию.",
}


def detect_topics(text: str) -> set[str]:
    lowered = (text or "").lower()
    hits: set[str] = set()
    for topic, lang_map in TOPIC_KEYWORDS.items():
        for keywords in lang_map.values():
            if any(kw in lowered for kw in keywords):
                hits.add(topic)
                break
    return hits


def build_grounding_context(clinic) -> str:
    """Formatted clinic facts handed to a real AI model as grounding, so it
    quotes real numbers instead of inventing them."""
    return json.dumps(clinic.knowledge_base or {}, ensure_ascii=False, indent=2)


def _format_ranges(kb: dict) -> str:
    ranges = kb.get("cost_ranges") or []
    return "; ".join(f"{r.get('grafts')} grafts ≈ €{r.get('price_eur')}" for r in ranges)


def _localized(value, lang: str, default=""):
    """`value` may be a plain string (used as-is for every language) or a
    dict keyed by language code (the shape app/models/clinic.py's default
    knowledge base uses for free text) -- falls back to English, then to
    `default`, so a clinic that only fills in "en" still works."""
    if isinstance(value, dict):
        return value.get(lang) or value.get("en") or default
    return value or default


def format_slot_options(slots: list, timezone: str) -> str:
    """`slots` are AvailabilitySlot rows (start_time stored as naive UTC).
    Formats them in the clinic's local timezone as short, human options so
    a reply can offer real bookable times instead of a vague promise to
    call back."""
    from app.timeutil import to_clinic_local

    labels = [
        f"{to_clinic_local(slot.start_time, timezone).strftime('%a %b %d, %H:%M')} {timezone}"
        for slot in slots
    ]
    return "; ".join(f"({i + 1}) {label}" for i, label in enumerate(labels))


def compose_faq_reply(
    *, language: str, clinic, topics: set[str], has_photos: bool, available_slots: list | None = None
) -> str:
    """Deterministic, offline reply used by the "fake" AI provider (the
    default). Grounded in clinic.knowledge_base so onboarding a second
    clinic with different prices/package contents changes the output
    without touching this code."""
    kb = clinic.knowledge_base or {}
    lang = language if language in TOPIC_TEXT["cost"] else "en"

    parts = [GREETING.get(lang, GREETING["en"])]
    if not topics:
        parts.append(FALLBACK.get(lang, FALLBACK["en"]))
    else:
        for topic in ("cost", "technique", "package", "stay", "consultation"):
            if topic not in topics:
                continue
            template = TOPIC_TEXT[topic].get(lang, TOPIC_TEXT[topic]["en"])
            techniques = kb.get("techniques", {})
            package_items = _localized(kb.get("package_includes", []), lang, default=[])
            parts.append(
                template.format(
                    clinic_name=kb.get("clinic_display_name", clinic.name),
                    ranges=_format_ranges(kb),
                    fue=_localized(techniques.get("FUE"), lang),
                    dhi=_localized(techniques.get("DHI"), lang),
                    package=", ".join(package_items),
                    stay=_localized(kb.get("typical_stay_days"), lang),
                    consultation=_localized(kb.get("free_consultation_details"), lang),
                )
            )
            if topic == "consultation" and available_slots:
                slots_text = format_slot_options(available_slots, clinic.timezone)
                parts.append(SLOT_OFFER.get(lang, SLOT_OFFER["en"]).format(slots=slots_text))

    if has_photos:
        parts.append(PHOTO_NOTE.get(lang, PHOTO_NOTE["en"]))

    return " ".join(parts)
