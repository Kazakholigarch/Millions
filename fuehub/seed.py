#!/usr/bin/env python3
"""Seed demo data: the FueHub clinic, a staff login, a couple weeks of open
consultation slots, and a dozen-odd leads across every channel and
language, deliberately spread across the whole funnel (fresh enquiries
still waiting in the queue, a clinical escalation, a photo-triggered
review, a lead recovered by the follow-up sequence, a booked consultation,
a paid deposit) so the dashboard tells a real story instead of five
identical rows.

    cd fuehub && python seed.py

Safe to re-run: it no-ops once the clinic/staff/leads already exist.
"""
from __future__ import annotations

import datetime as dt

from app import create_app
from app.channels.base import InboundMessage, InboundPhoto
from app.extensions import db
from app.models import Clinic, Message, StaffUser
from app.services import booking_service, reply_service
from app.services.lead_service import ingest_inbound

ADMIN_EMAIL = "admin@fuehub.example"
ADMIN_PASSWORD = "changeme123"


def _lead(clinic, channel, external_id, body, *, name=None, email=None, phone=None, handle=None, photo=False):
    inbound = InboundMessage(
        channel=channel,
        external_id=external_id,
        body=body,
        contact_name=name,
        contact_email=email,
        contact_phone=phone,
        contact_handle=handle,
        photos=[InboundPhoto(data=b"\xff\xd8\xff\xe0 fake jpeg bytes for demo", content_type="image/jpeg", filename="hairline.jpg")]
        if photo
        else [],
    )
    return ingest_inbound(clinic=clinic, inbound=inbound)


def _pending_draft(lead):
    return next((m for m in lead.messages if m.author_type == "ai_draft" and m.status == "pending_review"), None)


def _respond(lead, staff, body=None, response_minutes=3):
    message = _pending_draft(lead) or next(m for m in lead.messages if m.status in ("pending_review", "needs_clinician"))
    result = reply_service.send_reply(message=message, staff=staff, body=body)
    # Backdate so Analytics shows a believable response time instead of
    # "0.0 min" for every row -- the seed script approves everything
    # instantly, a real staff member won't.
    lead.first_response_at = lead.first_inbound_at + dt.timedelta(minutes=response_minutes)
    db.session.commit()
    return result


def run() -> None:
    app = create_app()
    with app.app_context():
        clinic = Clinic.query.filter_by(slug="fuehub").first()
        if clinic is None:
            clinic = Clinic(slug="fuehub", name="FueHub Hair Clinic", timezone="Europe/Istanbul")
            db.session.add(clinic)
            db.session.commit()
            print(f"Created clinic '{clinic.slug}'.")

        admin = StaffUser.query.filter_by(clinic_id=clinic.id, email=ADMIN_EMAIL).first()
        if admin is None:
            admin = StaffUser(clinic_id=clinic.id, email=ADMIN_EMAIL, name="Ayla Demir", role="admin")
            admin.set_password(ADMIN_PASSWORD)
            db.session.add(admin)
            db.session.commit()
            print(f"Staff login -> {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

        if clinic.slots.count() == 0:
            specs = []
            for day_offset, hours, label in [
                (1, (9, 11, 15), "Dr. Yilmaz - video consult"),
                (2, (10, 13), "Dr. Kaya - in-clinic"),
                (4, (9, 11, 14, 16), "Dr. Yilmaz - video consult"),
                (7, (10, 13, 15), "Dr. Kaya - in-clinic"),
            ]:
                base = (dt.datetime.utcnow() + dt.timedelta(days=day_offset)).replace(minute=0, second=0, microsecond=0)
                for h in hours:
                    start = base.replace(hour=h)
                    specs.append((start, start + dt.timedelta(minutes=30), label))
            booking_service.create_slots(clinic, specs)
            print(f"Added {len(specs)} open consultation slots over the next week.")

        if clinic.leads.count() > 0:
            print("Leads already present -- skipping demo lead seeding.")
            return

        # -- fresh enquiries, still sitting in the approve/edit queue --------
        # Budget + date + urgency language -> this one should sort to the
        # top of the queue as "hot".
        _lead(clinic, "whatsapp", "+905551110001", name="James Carter",
              body="Hi, how much would a hair transplant cost for around 3000 grafts? I'm looking "
              "to come in November, budget is around 3000 euros, and I'd like to book as soon as "
              "possible.")

        _lead(clinic, "instagram", "ig_user_882910", handle="ig_user_882910",
              body="Hallo! Was ist der Unterschied zwischen FUE und DHI? Und wie lange muss ich bleiben?")

        _lead(clinic, "whatsapp", "+79031234567", name="Dmitri Volkov",
              body="Здравствуйте, сколько будет стоить пересадка на 2500 графтов?")

        hot_unanswered = _lead(clinic, "instagram", "ig_user_551209", handle="ig_user_551209",
              body="Hi! How soon can I get an appointment? I need this done ASAP, I fly out in 10 days.")
        hot_unanswered.last_inbound_at -= dt.timedelta(days=3)  # looks overdue for a follow-up nudge

        # -- clinical escalation: flagged straight to a clinician, no AI draft --
        _lead(clinic, "whatsapp", "+491701234567", name="Michael Weber",
              body="Ich habe Diabetes und nehme Blutverdünner -- bin ich trotzdem ein Kandidat für "
              "eine Haartransplantation?")

        # -- photo sent: routed for human review, AI still answers the FAQ part --
        _lead(clinic, "website", "patient.photos@example.com", name="Tom Richards",
              email="patient.photos@example.com", photo=True,
              body="Here's a photo of my hairline. How much would FUE cost for something like this?")

        # -- already responded by staff, nothing booked yet -------------------
        responded_only = _lead(clinic, "email", "lucas.martin@example.com", name="Lucas Martin",
              email="lucas.martin@example.com",
              body="Hi, what's included in the all-inclusive package?")
        _respond(responded_only, admin, response_minutes=12)

        # -- responded, then booked a consultation -----------------------------
        booked = _lead(clinic, "website", "fatima.a@example.com", name="Fatima Al-Sayed",
              email="fatima.a@example.com",
              body="مرحباً، أرغب في معرفة تفاصيل الاستشارة المجانية. هل يمكن الحجز في أقرب وقت؟")
        _respond(booked, admin, response_minutes=4)
        booking_service.book_slot(slot=booking_service.list_upcoming_slots(clinic, limit=1)[0], lead=booked, staff=admin)

        # -- responded, booked, AND paid the deposit -- the full funnel -------
        converted = _lead(clinic, "whatsapp", "+905321239988", name="Klaus Richter",
              body="Guten Tag, ich möchte gerne einen Beratungstermin vereinbaren.")
        _respond(converted, admin, response_minutes=2)
        booking_service.book_slot(slot=booking_service.list_upcoming_slots(clinic, limit=1)[0], lead=converted, staff=admin)
        booking_service.mark_deposit_paid(lead=converted, staff=admin)

        # -- went quiet after the ack, got nudged, came back on their own ------
        recovered = _lead(clinic, "email", "sergey.k@example.com", name="Sergey K.",
              email="sergey.k@example.com",
              body="Здравствуйте! Подскажите, пожалуйста, что входит в пакет для иностранных "
              "пациентов? Нужен отель и трансфер.")
        recovered.follow_up_stage = 1  # simulate: the day-2 nudge already went out
        db.session.commit()
        recovered = _lead(clinic, "email", "sergey.k@example.com",
              body="Извините за задержку! Да, хотел бы записаться на консультацию.")
        _respond(recovered, admin, response_minutes=7)
        booking_service.book_slot(slot=booking_service.list_upcoming_slots(clinic, limit=1)[0], lead=recovered, staff=admin)

        # -- nudged once, hasn't come back yet (shows the sequence mid-flight) -
        nudged_waiting = _lead(clinic, "instagram", "ig_user_339102", handle="ig_user_339102",
              body="مرحباً، أريد معرفة تفاصيل أكثر عن تقنية DHI.")
        nudged_waiting.follow_up_stage = 1
        nudged_waiting.last_inbound_at -= dt.timedelta(days=3)
        db.session.commit()

        lead_count = clinic.leads.count()
        message_count = Message.query.filter_by(clinic_id=clinic.id).count()
        db.session.commit()
        print(f"Seeded {lead_count} demo leads ({message_count} messages) across all four channels.")


if __name__ == "__main__":
    run()
