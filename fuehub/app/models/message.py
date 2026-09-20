from __future__ import annotations

import datetime as dt

from app.constants import MessageStatus
from app.extensions import db


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)  # denormalized for tenant-scoped queries

    direction = db.Column(db.String(10), nullable=False)  # inbound | outbound
    channel = db.Column(db.String(20), nullable=False)
    author_type = db.Column(db.String(20), nullable=False)  # see MessageAuthor

    body = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(8), nullable=True)

    ai_generated = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default=MessageStatus.SENT)

    # If this message started as an AI draft, keep the original text so
    # edits are visible/auditable even after staff changes it before send.
    original_ai_draft = db.Column(db.Text, nullable=True)

    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("staff_users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)

    attachments = db.relationship("Attachment", backref="message", lazy="dynamic")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Message {self.id} {self.direction}/{self.author_type}>"


class Attachment(db.Model):
    """A photo (or other file) sent by the enquirer. Stored on disk, not in
    the DB, and never forwarded to the AI drafting API -- photos are a
    strong signal (bump urgency, flag for clinical review) but the actual
    assessment is always a human's."""

    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=False)
    message_id = db.Column(db.Integer, db.ForeignKey("messages.id"), nullable=True)

    file_path = db.Column(db.String(500), nullable=False)  # relative path under instance/uploads/
    content_type = db.Column(db.String(100), nullable=True)
    kind = db.Column(db.String(20), nullable=False, default="photo")

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
