from __future__ import annotations

import datetime as dt

from app.constants import DEFAULT_LANGUAGE, LeadStatus, UrgencyBand
from app.extensions import db


class Lead(db.Model):
    """One inbound enquirer, deduped by (clinic, channel, external_id).

    Deliberately minimal: only what's needed to run the active conversation.
    No CRM-style history of every field change, no marketing profile.
    """

    __tablename__ = "leads"
    __table_args__ = (
        db.Index("ix_leads_dedupe", "clinic_id", "channel", "external_id", unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    channel = db.Column(db.String(20), nullable=False)
    # Channel-native identifier used for de-duplication and for sending
    # replies back: phone number (WhatsApp), email address (email), IG
    # user id (Instagram), form session token (website).
    external_id = db.Column(db.String(200), nullable=False)

    contact_name = db.Column(db.String(200), nullable=True)
    contact_phone = db.Column(db.String(40), nullable=True)
    contact_email = db.Column(db.String(200), nullable=True)
    contact_handle = db.Column(db.String(200), nullable=True)

    language = db.Column(db.String(8), nullable=False, default=DEFAULT_LANGUAGE)
    first_message = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(30), nullable=False, default=LeadStatus.NEW)

    urgency_score = db.Column(db.Integer, nullable=False, default=0)
    urgency_band = db.Column(db.String(10), nullable=False, default=UrgencyBand.ROUTINE)
    score_reasons = db.Column(db.JSON, nullable=False, default=list)

    has_photos = db.Column(db.Boolean, nullable=False, default=False)
    requires_clinical_review = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    first_inbound_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    last_inbound_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    first_response_at = db.Column(db.DateTime, nullable=True)  # first substantive (non-ack) reply
    last_outbound_at = db.Column(db.DateTime, nullable=True)

    # Capped follow-up sequence: 0 = none sent, 1 = day-2 nudge sent, 2 = day-6 nudge sent (final).
    follow_up_stage = db.Column(db.Integer, nullable=False, default=0)
    # True if the enquirer replied after a nudge and the lead went on to book --
    # this is the "recovered booking" the whole follow-up sequence exists for.
    recovered_by_followup = db.Column(db.Boolean, nullable=False, default=False)

    consultation_slot_id = db.Column(db.Integer, db.ForeignKey("availability_slots.id"), nullable=True)
    consultation_booked_at = db.Column(db.DateTime, nullable=True)
    deposit_paid_at = db.Column(db.DateTime, nullable=True)

    messages = db.relationship(
        "Message", backref="lead", lazy="dynamic", order_by="Message.created_at",
        cascade="all, delete-orphan",
    )
    attachments = db.relationship(
        "Attachment", backref="lead", lazy="dynamic", cascade="all, delete-orphan",
    )
    consultation_slot = db.relationship("AvailabilitySlot", foreign_keys=[consultation_slot_id])

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Lead {self.id} {self.channel}:{self.external_id}>"

    @property
    def display_name(self) -> str:
        return self.contact_name or self.contact_handle or self.contact_phone or self.contact_email or f"Lead #{self.id}"
