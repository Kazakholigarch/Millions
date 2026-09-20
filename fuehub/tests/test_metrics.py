import datetime as dt

from app.channels.base import InboundMessage
from app.extensions import db
from app.models import StaffUser
from app.services import booking_service, metrics_service, reply_service
from app.services.lead_service import ingest_inbound


def _staff(clinic, email="m@test.com"):
    s = StaffUser(clinic_id=clinic.id, email=email, name="M", role="staff")
    s.set_password("x")
    db.session.add(s)
    db.session.commit()
    return s


def _open_slot(clinic, days_ahead=1):
    start = dt.datetime.utcnow() + dt.timedelta(days=days_ahead)
    (slot,) = booking_service.create_slots(clinic, [(start, start + dt.timedelta(minutes=30), None)])
    return slot


def test_funnel_counts_progress_through_stages(app, clinic):
    staff = _staff(clinic)
    lead = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="How much for 3000 grafts?")
    )

    funnel = metrics_service.funnel(clinic)
    assert funnel == {"enquired": 1, "responded": 0, "consultation_booked": 0, "deposit_paid": 0}

    draft = next(m for m in lead.messages if m.author_type == "ai_draft")
    reply_service.send_reply(message=draft, staff=staff)
    assert metrics_service.funnel(clinic)["responded"] == 1

    booking_service.book_slot(slot=_open_slot(clinic), lead=lead, staff=staff)
    assert metrics_service.funnel(clinic)["consultation_booked"] == 1

    booking_service.mark_deposit_paid(lead=lead, staff=staff)
    assert metrics_service.funnel(clinic)["deposit_paid"] == 1


def test_response_time_breakdown_by_language_and_channel(app, clinic):
    staff = _staff(clinic)
    lead = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="email", external_id="a@b.com", body="How much does it cost?")
    )
    draft = next(m for m in lead.messages if m.author_type == "ai_draft")
    reply_service.send_reply(message=draft, staff=staff)

    rows = metrics_service.response_time_breakdown(clinic)
    assert len(rows) == 1
    assert rows[0]["language"] == "en"
    assert rows[0]["channel"] == "email"
    assert rows[0]["count"] == 1
    assert rows[0]["avg_minutes"] >= 0


def test_recovered_bookings_only_counts_leads_that_came_back_after_a_nudge(app, clinic):
    staff = _staff(clinic)
    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="How much?"))

    assert metrics_service.recovered_bookings(clinic)["nudged_and_replied"] == 0

    lead.follow_up_stage = 1  # simulate: they'd already received one nudge
    db.session.commit()

    # they reply on their own -- ingest_inbound should flag this as recovered
    ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Ok let's talk"))

    recovered = metrics_service.recovered_bookings(clinic)
    assert recovered["nudged_and_replied"] == 1
    assert recovered["recovered_bookings"] == 0

    booking_service.book_slot(slot=_open_slot(clinic), lead=lead, staff=staff)
    assert metrics_service.recovered_bookings(clinic)["recovered_bookings"] == 1
