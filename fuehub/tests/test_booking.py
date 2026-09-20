import datetime as dt

import pytest

from app.channels.base import InboundMessage
from app.extensions import db
from app.models import Clinic
from app.services import booking_service
from app.services.lead_service import ingest_inbound


def _open_slot(clinic, days_ahead=1):
    start = dt.datetime.utcnow() + dt.timedelta(days=days_ahead)
    (slot,) = booking_service.create_slots(clinic, [(start, start + dt.timedelta(minutes=30), None)])
    return slot


def test_cannot_double_book_a_slot(app, clinic):
    lead1 = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))
    lead2 = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+2", body="Hi"))
    slot = _open_slot(clinic)

    booking_service.book_slot(slot=slot, lead=lead1)
    with pytest.raises(ValueError):
        booking_service.book_slot(slot=slot, lead=lead2)


def test_cannot_book_a_slot_belonging_to_another_clinic(app, clinic):
    other = Clinic(slug="other", name="Other Clinic")
    db.session.add(other)
    db.session.commit()

    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))
    slot = _open_slot(other)

    with pytest.raises(ValueError):
        booking_service.book_slot(slot=slot, lead=lead)


def test_booking_sets_lead_milestones(app, clinic):
    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))
    slot = _open_slot(clinic)

    assert lead.consultation_booked_at is None
    booking_service.book_slot(slot=slot, lead=lead)

    assert lead.consultation_booked_at is not None
    assert lead.consultation_slot_id == slot.id
    assert slot.is_booked is True


def test_list_upcoming_slots_excludes_booked_and_past(app, clinic):
    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))

    past_start = dt.datetime.utcnow() - dt.timedelta(days=1)
    (past,) = booking_service.create_slots(clinic, [(past_start, past_start + dt.timedelta(minutes=30), None)])
    booked = _open_slot(clinic, days_ahead=1)
    open_slot = _open_slot(clinic, days_ahead=2)
    booking_service.book_slot(slot=booked, lead=lead)

    upcoming = booking_service.list_upcoming_slots(clinic, limit=10)
    assert past not in upcoming
    assert booked not in upcoming
    assert open_slot in upcoming
