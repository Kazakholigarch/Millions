from __future__ import annotations

from app.constants import DEFAULT_LANGUAGE

"""Fixed, pre-translated templates for the two message types that must go
out instantly/automatically without an AI call in the loop: the
first-contact acknowledgment and the capped follow-up nudges. Using fixed
translations (not live machine translation) for these is deliberate --
they're short, legally/brand sensitive, sent to every single enquirer, and
worth getting right once by a human translator rather than regenerating.

AI-drafted FAQ replies are different (see app/ai/draft.py): those are
free-form and go through the approve/edit queue before anything sends.

Add a language: add an entry to each dict below and to
app.constants.SUPPORTED_LANGUAGES / the clinic's supported_languages.
Missing a language here falls back to English rather than sending nothing.
"""

ACK_TEMPLATES: dict[str, str] = {
    "en": (
        "Hi{name_suffix}, thank you for reaching out to {clinic_name}! We've received your "
        "message and a specialist will follow up with you shortly. If you can, feel free to "
        "share a photo of your hairline/crown in the meantime -- it helps us prepare."
    ),
    "de": (
        "Hallo{name_suffix}, vielen Dank für Ihre Nachricht an {clinic_name}! Wir haben Ihre "
        "Anfrage erhalten und ein Spezialist wird sich in Kürze bei Ihnen melden. Gerne können "
        "Sie schon jetzt ein Foto Ihres Haaransatzes/Oberkopfs senden -- das hilft uns bei der "
        "Vorbereitung."
    ),
    "ar": (
        "مرحباً{name_suffix}، شكراً لتواصلك مع {clinic_name}! لقد استلمنا رسالتك وسيتواصل معك "
        "أحد المختصين قريباً. يمكنك أيضاً إرسال صورة لمقدمة الشعر أو قمة الرأس إن أمكن، فهذا "
        "يساعدنا في التحضير."
    ),
    "ru": (
        "Здравствуйте{name_suffix}! Спасибо, что обратились в {clinic_name}. Мы получили ваше "
        "сообщение, и в ближайшее время с вами свяжется специалист. Если удобно, пришлите фото "
        "линии роста волос/макушки -- это поможет нам подготовиться."
    ),
}

# {days} is filled with the elapsed gap so the message stays honest about timing.
FOLLOWUP_TEMPLATES: dict[str, dict[int, str]] = {
    "en": {
        1: "Hi again{name_suffix} -- just checking in on your hair transplant enquiry with "
        "{clinic_name}. Still happy to answer questions about cost, technique or timing, or to "
        "book your free consultation whenever suits you.",
        2: "Hi{name_suffix}, last check-in from us -- your enquiry with {clinic_name} is still "
        "open whenever you're ready. No pressure at all, and we're here if anything changes.",
    },
    "de": {
        1: "Hallo nochmal{name_suffix} -- wir wollten kurz nachfragen, ob Sie noch Fragen zu "
        "Ihrer Haartransplantations-Anfrage bei {clinic_name} haben. Gerne klären wir Kosten, "
        "Technik oder Termine, oder vereinbaren direkt Ihre kostenlose Beratung.",
        2: "Hallo{name_suffix}, dies ist unsere letzte Nachfrage -- Ihre Anfrage bei "
        "{clinic_name} bleibt offen, ganz ohne Druck. Melden Sie sich gerne, wenn Sie bereit sind.",
    },
    "ar": {
        1: "مرحباً مجدداً{name_suffix} -- أردنا الاطمئنان بخصوص استفسارك عن زراعة الشعر مع "
        "{clinic_name}. يسعدنا الإجابة عن أي سؤال حول التكلفة أو التقنية أو المواعيد، أو حجز "
        "استشارتك المجانية.",
        2: "مرحباً{name_suffix}، هذه آخر رسالة متابعة منا -- يبقى استفسارك مع {clinic_name} "
        "مفتوحاً دون أي إلزام، وسنكون هنا عندما تكون جاهزاً.",
    },
    "ru": {
        1: "Здравствуйте снова{name_suffix} -- хотели уточнить, остались ли у вас вопросы по "
        "поводу пересадки волос в {clinic_name}. С радостью расскажем о стоимости, технике или "
        "сроках, либо запишем вас на бесплатную консультацию.",
        2: "Здравствуйте{name_suffix}, это последнее напоминание -- ваш запрос в {clinic_name} "
        "остаётся открытым, без всякого давления. Будем на связи, когда вам будет удобно.",
    },
}


def render_ack(language: str, clinic_name: str, contact_name: str | None) -> str:
    template = ACK_TEMPLATES.get(language) or ACK_TEMPLATES[DEFAULT_LANGUAGE]
    name_suffix = f" {contact_name}" if contact_name else ""
    return template.format(clinic_name=clinic_name, name_suffix=name_suffix)


def render_followup(language: str, stage: int, clinic_name: str, contact_name: str | None) -> str:
    stage_templates = FOLLOWUP_TEMPLATES.get(language) or FOLLOWUP_TEMPLATES[DEFAULT_LANGUAGE]
    template = stage_templates.get(stage) or stage_templates[max(stage_templates)]
    name_suffix = f" {contact_name}" if contact_name else ""
    return template.format(clinic_name=clinic_name, name_suffix=name_suffix)
