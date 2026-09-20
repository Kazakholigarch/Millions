from __future__ import annotations

import datetime as dt

from app.constants import LeadStatus
from app.extensions import db
from app.models import AuditLog, AvailabilitySlot, Lead


def list_upcoming_slots(clinic, *, limit: int = 3, now: dt.datetime | None = None) -> list[AvailabilitySlot]:
    now = now or dt.datetime.utcnow()
    return (
        AvailabilitySlot.query.filter_by(clinic_id=clinic.id, is_booked=False)
        .filter(AvailabilitySlot.start_time >= now)
        .order_by(AvailabilitySlot.start_time.asc())
        .limit(limit)
        .all()
    )


def book_slot(*, slot: AvailabilitySlot, lead: Lead, staff=None) -> AvailabilitySlot:
    if slot.is_booked:
        raise ValueError("slot already booked")
    if slot.clinic_id != lead.clinic_id:
        raise ValueError("slot belongs to a different clinic")

    now = dt.datetime.utcnow()
    slot.is_booked = True
    slot.booked_lead_id = lead.id
    slot.booked_at = now

    lead.consultation_slot_id = slot.id
    lead.consultation_booked_at = now
    lead.status = LeadStatus.CONSULTATION_BOOKED

    db.session.add(
        AuditLog(
            clinic_id=lead.clinic_id,
            staff_id=staff.id if staff else None,
            lead_id=lead.id,
            action="consultation_booked",
            detail=f"slot_id={slot.id}",
        )
    )
    db.session.commit()
    return slot


def mark_deposit_paid(*, lead: Lead, staff=None) -> Lead:
    lead.deposit_paid_at = dt.datetime.utcnow()
    lead.status = LeadStatus.DEPOSIT_PAID
    db.session.add(
        AuditLog(
            clinic_id=lead.clinic_id,
            staff_id=staff.id if staff else None,
            lead_id=lead.id,
            action="deposit_marked_paid",
        )
    )
    db.session.commit()
    return lead


def create_slots(clinic, slot_specs: list[tuple[dt.datetime, dt.datetime, str | None]]) -> list[AvailabilitySlot]:
    """Bulk-create availability. Used by the seed script and by staff admin
    tooling; a real deployment would instead sync this from Google/Outlook
    Calendar, but the booking flow below only depends on this table, not on
    how it got populated."""
    slots = [
        AvailabilitySlot(clinic_id=clinic.id, start_time=start, end_time=end, staff_label=label)
        for start, end, label in slot_specs
    ]
    db.session.add_all(slots)
    db.session.commit()
    return slots
