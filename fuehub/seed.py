#!/usr/bin/env python3
"""Seed demo data: the FueHub clinic, a staff login, a few open
consultation slots, and a handful of leads across every channel and
language so the dashboard has something to show.

    cd fuehub && python seed.py
"""
from __future__ import annotations

import datetime as dt

from app import create_app
from app.channels.base import InboundMessage
from app.extensions import db
from app.models import Clinic, StaffUser
from app.services import booking_service
from app.services.lead_service import ingest_inbound

DEMO_MESSAGES = [
    (
        "whatsapp", "+905551110001", "James Carter", None, None,
        "Hi, how much would a hair transplant cost for around 3000 grafts? I'm looking to come "
        "in November, budget is around 3000 euros.",
    ),
    (
        "instagram", "ig_user_882910", None, None, "ig_user_882910",
        "Hallo! Was ist der Unterschied zwischen FUE und DHI? Und wie lange muss ich bleiben?",
    ),
    (
        "email", "sergey.k@example.com", "Sergey K.", "sergey.k@example.com", None,
        "Здравствуйте! Подскажите, пожалуйста, что входит в пакет для иностранных пациентов? "
        "Нужен отель и трансфер, и хотелось бы записаться на консультацию как можно скорее.",
    ),
    (
        "website", "fatima.a@example.com", "Fatima Al-Sayed", "fatima.a@example.com", None,
        "مرحباً، أرغب في معرفة تفاصيل الاستشارة المجانية. هل يمكن الحجز في أقرب وقت؟",
    ),
    (
        "whatsapp", "+491701234567", "Michael Weber", None, None,
        "Ich habe Diabetes und nehme Blutverdünner -- bin ich trotzdem ein Kandidat für eine "
        "Haartransplantation?",
    ),
]


def run() -> None:
    app = create_app()
    with app.app_context():
        clinic = Clinic.query.filter_by(slug="fuehub").first()
        if clinic is None:
            clinic = Clinic(slug="fuehub", name="FueHub Hair Clinic", timezone="Europe/Istanbul")
            db.session.add(clinic)
            db.session.commit()
            print(f"Created clinic '{clinic.slug}'.")

        if not StaffUser.query.filter_by(clinic_id=clinic.id, email="admin@fuehub.example").first():
            admin = StaffUser(clinic_id=clinic.id, email="admin@fuehub.example", name="Ayla Demir", role="admin")
            admin.set_password("changeme123")
            db.session.add(admin)
            db.session.commit()
            print("Staff login -> admin@fuehub.example / changeme123")

        if clinic.slots.count() == 0:
            base = (dt.datetime.utcnow() + dt.timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
            specs = [
                (base + dt.timedelta(hours=h), base + dt.timedelta(hours=h, minutes=30), "Dr. Yilmaz - video consult")
                for h in (9, 11, 14)
            ]
            booking_service.create_slots(clinic, specs)
            print(f"Added {len(specs)} open consultation slots.")

        if clinic.leads.count() == 0:
            for channel, external_id, name, email, handle, body in DEMO_MESSAGES:
                inbound = InboundMessage(
                    channel=channel,
                    external_id=external_id,
                    body=body,
                    contact_name=name,
                    contact_email=email,
                    contact_handle=handle,
                )
                ingest_inbound(clinic=clinic, inbound=inbound)
            print(f"Seeded {len(DEMO_MESSAGES)} demo leads across website/email/WhatsApp/Instagram.")
        else:
            print("Leads already present -- skipping demo lead seeding.")


if __name__ == "__main__":
    run()
