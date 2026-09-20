from __future__ import annotations

import datetime as dt

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.constants import StaffRole
from app.extensions import db


class StaffUser(db.Model, UserMixin):
    __tablename__ = "staff_users"
    __table_args__ = (db.Index("ix_staff_clinic_email", "clinic_id", "email", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    clinic_id = db.Column(db.Integer, db.ForeignKey("clinics.id"), nullable=False)

    email = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=StaffRole.STAFF)
    is_active_staff = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=dt.datetime.utcnow)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    # Flask-Login integration
    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.is_active_staff

    def get_id(self) -> str:  # type: ignore[override]
        # Flask-Login ids must be globally unique across the whole app, not
        # just per clinic, since the session cookie has no other tenant hint.
        return str(self.id)

    @property
    def is_admin(self) -> bool:
        return self.role == StaffRole.ADMIN
