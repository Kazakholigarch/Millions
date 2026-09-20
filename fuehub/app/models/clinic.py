from __future__ import annotations

import datetime as dt

from app.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
from app.extensions import db


def _default_languages() -> list[str]:
    return list(SUPPORTED_LANGUAGES)


def _default_knowledge_base() -> dict:
    """Per-clinic facts the AI drafter is grounded in. Living on the tenant
    row (not in code) is what lets a second clinic plug in without a
    rewrite -- onboarding a clinic means filling this in, not branching
    application logic."""
    return {
        "clinic_display_name": "FueHub Hair Clinic",
        "locations": ["Istanbul, Turkey"],
        "cost_ranges": [
            {"grafts": "1500-2500", "price_eur": "1800-2600"},
            {"grafts": "2500-3500", "price_eur": "2600-3400"},
            {"grafts": "3500-4500", "price_eur": "3400-4200"},
        ],
        # Free-text facts are keyed by language (en/de/ar/ru) rather than a
        # single string: the offline "fake" AI provider (app/ai/faq.py)
        # quotes these verbatim inside an already-translated sentence, so an
        # untranslated field would leak English into e.g. an Arabic reply.
        # A clinic that only fills in "en" still works -- lookups fall back
        # to it -- but won't read as natively translated for other
        # languages until it's filled in. The real AI provider (Claude)
        # translates on the fly and doesn't have this limitation.
        "techniques": {
            "FUE": {
                "en": "Follicular Unit Extraction: individual follicles are removed one by one "
                "with a small punch tool and implanted by hand. No linear scar, faster healing.",
                "de": "Follicular Unit Extraction: einzelne Follikel werden nacheinander mit "
                "einem kleinen Stanzwerkzeug entnommen und von Hand eingesetzt. Keine lineare "
                "Narbe, schnellere Heilung.",
                "ar": "استخراج الوحدات البصيلية: تُستخرج البصيلات واحدة تلو الأخرى بأداة ثقب "
                "صغيرة وتُزرع يدوياً. بدون ندبة خطية، وشفاء أسرع.",
                "ru": "Фолликулярная экстракция (FUE): фолликулы извлекаются по одному "
                "небольшим инструментом-панчем и имплантируются вручную. Без линейного шрама, "
                "быстрее заживление.",
            },
            "DHI": {
                "en": "Direct Hair Implantation: follicles are extracted the same way as FUE but "
                "implanted immediately with a pen-like Choi implanter, without pre-made "
                "incisions. Allows denser, more precise placement; typically a higher price "
                "than FUE.",
                "de": "Direct Hair Implantation: Follikel werden wie bei FUE entnommen, aber "
                "sofort mit einem stiftartigen Choi-Implanter ohne vorgefertigte Schnitte "
                "eingesetzt. Ermöglicht dichtere, präzisere Platzierung; meist teurer als FUE.",
                "ar": "الزراعة المباشرة: تُستخرج البصيلات بنفس طريقة FUE لكنها تُزرع فوراً "
                "بواسطة قلم تشوي دون شقوق مسبقة. يتيح كثافة ودقة أعلى، وسعره أعلى عادةً من FUE.",
                "ru": "Прямая имплантация волос (DHI): фолликулы извлекаются как при FUE, но "
                "сразу имплантируются ручкой Choi без предварительных надрезов. Позволяет более "
                "плотную и точную посадку; обычно дороже FUE.",
            },
        },
        "package_includes": {
            "en": [
                "Airport pickup and drop-off", "Hotel for the duration of the stay",
                "Private translator/patient coordinator",
                "All clinical fees (procedure, medication, PRP if included)", "Post-op check-up",
            ],
            "de": [
                "Flughafentransfer (Abholung und Rückfahrt)", "Hotel für die Dauer des Aufenthalts",
                "Privater Übersetzer/Patientenbetreuer",
                "Alle klinischen Kosten (Eingriff, Medikamente, ggf. PRP)", "Nachuntersuchung",
            ],
            "ar": [
                "الاستقبال والتوصيل من/إلى المطار", "فندق لمدة الإقامة",
                "مترجم خاص/منسق مرضى",
                "جميع الرسوم الطبية (العملية، الأدوية، PRP إن وجد)", "فحص ما بعد العملية",
            ],
            "ru": [
                "Трансфер из/в аэропорт", "Отель на весь период пребывания",
                "Личный переводчик/координатор пациента",
                "Все клинические расходы (процедура, медикаменты, PRP при наличии)",
                "Послеоперационный осмотр",
            ],
        },
        "typical_stay_days": {
            "en": "3-4 days (procedure day, 1-2 rest/check-up days, wash demo before flying home)",
            "de": "3-4 Tage (Tag des Eingriffs, 1-2 Ruhe-/Kontrolltage, Wasch-Demo vor dem "
            "Rückflug)",
            "ar": "3-4 أيام (يوم العملية، يوم أو يومان للراحة والفحص، وتوضيح لطريقة الغسل قبل "
            "السفر)",
            "ru": "3-4 дня (день процедуры, 1-2 дня отдыха/осмотра, демонстрация мытья головы "
            "перед вылетом)",
        },
        "free_consultation_details": {
            "en": "A free video or in-person consultation with a specialist: photo review, "
            "graft estimate, technique recommendation and a firm price quote. No obligation.",
            "de": "Eine kostenlose Video- oder Vor-Ort-Beratung mit einem Spezialisten: "
            "Fotobewertung, Graft-Schätzung, Technikempfehlung und ein verbindliches "
            "Preisangebot. Unverbindlich.",
            "ar": "استشارة مجانية عبر الفيديو أو حضورياً مع أخصائي: مراجعة الصور، تقدير عدد "
            "البصيلات، التوصية بالتقنية المناسبة، وعرض سعر نهائي. دون أي التزام.",
            "ru": "Бесплатная видео- или очная консультация со специалистом: анализ фото, "
            "оценка количества графтов, рекомендация по технике и точная цена. Без обязательств.",
        },
    }


class Clinic(db.Model):
    __tablename__ = "clinics"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    timezone = db.Column(db.String(64), nullable=False, default="Europe/Istanbul")

    supported_languages = db.Column(db.JSON, nullable=False, default=_default_languages)
    default_language = db.Column(db.String(8), nullable=False, default=DEFAULT_LANGUAGE)

    knowledge_base = db.Column(db.JSON, nullable=False, default=_default_knowledge_base)

    # Per-channel credentials/config, e.g. {"whatsapp": {...}, "instagram": {...}}.
    # For a real multi-clinic deployment this belongs in a secrets manager,
    # not a plaintext DB column -- flagged here as the extension point.
    channel_config = db.Column(db.JSON, nullable=False, default=dict)

    auto_send_followups = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    staff = db.relationship("StaffUser", backref="clinic", lazy="dynamic")
    leads = db.relationship("Lead", backref="clinic", lazy="dynamic")
    slots = db.relationship("AvailabilitySlot", backref="clinic", lazy="dynamic")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Clinic {self.slug}>"
