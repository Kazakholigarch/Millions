from __future__ import annotations

import datetime as dt

from app.extensions import db


class AvailabilitySlot(db.Model):
    """A real, bookable consultation slot. Booking pulls from this table
    directly (from inside the conversation/queue), instead of ending in a
    vague "we'll call you back".

    This is an internal availability model, not a Google/Outlook Calendar
    integration -- staff manage slots in the dashboard. Swapping in an
    external calendar provider later means implementing the same
    list/hold/book interface against that API; nothing else in the app
    would need to change (see app/services/booking_service.py).
    """

    __tablename__ = "availability_slots"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    staff_label = db.Column(db.String(120), nullable=True)  # e.g. "Dr. Yilmaz - video consult"

    is_booked = db.Column(db.Boolean, nullable=False, default=False)
    booked_lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True)
    booked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AvailabilitySlot {self.start_time.isoformat() if self.start_time else '?'}>"
