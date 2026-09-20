from __future__ import annotations

import re

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db as _db
from app.models import Clinic, StaffUser


@pytest.fixture()
def app():
    application = create_app(TestConfig)
    ctx = application.app_context()
    ctx.push()
    yield application
    ctx.pop()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def clinic(app):
    c = Clinic(slug="testclinic", name="Test Clinic", timezone="Europe/Istanbul")
    _db.session.add(c)
    _db.session.commit()
    return c


@pytest.fixture()
def staff(app, clinic):
    s = StaffUser(clinic_id=clinic.id, email="staff@test.com", name="Staff Member", role="admin")
    s.set_password("testpass123")
    _db.session.add(s)
    _db.session.commit()
    return s


@pytest.fixture()
def logged_in_client(client, staff):
    login_page = client.get("/login")
    csrf = _extract_csrf(login_page.data)
    client.post(
        "/login",
        data={"email": staff.email, "password": "testpass123", "csrf_token": csrf},
        follow_redirects=False,
    )
    return client


def _extract_csrf(html_bytes: bytes) -> str:
    match = re.search(rb'name="csrf_token" value="([^"]*)"', html_bytes)
    return match.group(1).decode() if match else ""
