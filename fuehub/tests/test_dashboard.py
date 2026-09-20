from app.channels.base import InboundMessage
from app.extensions import db
from app.models import Clinic
from app.services.lead_service import ingest_inbound
from tests.conftest import _extract_csrf


def test_unauthenticated_request_redirects_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_wrong_password_is_rejected(client, staff):
    login_page = client.get("/login")
    csrf = _extract_csrf(login_page.data)
    response = client.post("/login", data={"email": staff.email, "password": "wrong", "csrf_token": csrf})
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_queue_lists_pending_items_after_login(app, clinic, logged_in_client):
    ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="How much for 3000 grafts?")
    )
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert b"queue-card" in response.data


def test_post_without_csrf_token_is_rejected(app, clinic, logged_in_client):
    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))
    draft = next(m for m in lead.messages if m.author_type == "ai_draft")
    response = logged_in_client.post(f"/queue/{draft.id}/send", data={"body": "hello"})
    assert response.status_code == 400


def test_staff_cannot_reach_another_clinics_lead(app, clinic, logged_in_client):
    other = Clinic(slug="other-clinic", name="Other Clinic")
    db.session.add(other)
    db.session.commit()
    other_lead = ingest_inbound(clinic=other, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))

    response = logged_in_client.get(f"/leads/{other_lead.id}")
    assert response.status_code == 404


def test_approve_and_send_marks_message_sent_with_edits(app, clinic, logged_in_client):
    lead = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="How much for FUE?")
    )
    draft = next(m for m in lead.messages if m.author_type == "ai_draft")
    csrf = _extract_csrf(logged_in_client.get("/").data)

    response = logged_in_client.post(
        f"/queue/{draft.id}/send", data={"body": "Edited reply text", "csrf_token": csrf}, follow_redirects=True
    )
    assert response.status_code == 200
    assert draft.status == "sent"
    assert draft.body == "Edited reply text"


def test_discard_removes_item_from_queue(app, clinic, logged_in_client):
    lead = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1", body="Hi"))
    draft = next(m for m in lead.messages if m.author_type == "ai_draft")
    csrf = _extract_csrf(logged_in_client.get("/").data)

    logged_in_client.post(f"/queue/{draft.id}/discard", data={"csrf_token": csrf}, follow_redirects=True)
    assert draft.status == "discarded"

    response = logged_in_client.get("/")
    assert str(draft.id).encode() not in response.data or b"Queue is empty" in response.data
