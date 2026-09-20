from __future__ import annotations

import datetime as dt

from app.extensions import db


class AuditLog(db.Model):
    """Who did what, on which lead. Exists so "real access control behind
    the staff dashboard" is verifiable, not just claimed -- every
    approve/edit/send/book/deposit action is attributed to a staff user."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff_users.id"), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id"), nullable=True)

    action = db.Column(db.String(60), nullable=False)
    detail = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)
