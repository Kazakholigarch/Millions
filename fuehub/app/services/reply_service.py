from __future__ import annotations

import datetime as dt

from flask import current_app

from app.channels.base import get_adapter, resolve_reply_target
from app.constants import LeadStatus, MessageStatus, advance_lead_status
from app.extensions import db
from app.models import AuditLog, Message, StaffUser

"""The approve/edit/send queue. Every AI draft (and every clinician-flagged
item) lands here and nothing goes out to the enquirer until a staff member
acts on it -- full autonomy is something to earn later once there's a
track record, per the product brief.
"""


def send_reply(*, message: Message, staff: StaffUser, body: str | None = None) -> Message:
    """Approve (optionally with edits) and send a queued message. `body`
    is required for a needs_clinician item (there's no AI draft to fall
    back to) and optional for an AI draft (omit to send as-is, pass to
    send an edited version)."""
    if message.status not in (MessageStatus.PENDING_REVIEW, MessageStatus.NEEDS_CLINICIAN):
        raise ValueError(f"message {message.id} is not in the review queue (status={message.status})")

    final_body = (body if body is not None else message.body).strip()
    if not final_body:
        raise ValueError("cannot send an empty reply")

    was_edited = message.status == MessageStatus.PENDING_REVIEW and final_body != (message.original_ai_draft or "")
    message.body = final_body

    lead = message.lead
    clinic = lead.clinic
    adapter = get_adapter(lead.channel, clinic=clinic, config=current_app.config)
    adapter.send_text(to=resolve_reply_target(lead), body=final_body)

    now = dt.datetime.utcnow()
    message.status = MessageStatus.SENT
    message.reviewed_by_id = staff.id
    message.reviewed_at = now
    message.sent_at = now

    if lead.first_response_at is None:
        lead.first_response_at = now
    lead.last_outbound_at = now
    lead.status = advance_lead_status(lead.status, LeadStatus.RESPONDED)

    db.session.add(
        AuditLog(
            clinic_id=clinic.id,
            staff_id=staff.id,
            lead_id=lead.id,
            action="edited_and_sent" if was_edited else "approved_and_sent",
            detail=f"message_id={message.id}",
        )
    )
    db.session.commit()
    return message


def discard_reply(*, message: Message, staff: StaffUser, reason: str = "") -> Message:
    if message.status not in (MessageStatus.PENDING_REVIEW, MessageStatus.NEEDS_CLINICIAN):
        raise ValueError(f"message {message.id} is not in the review queue (status={message.status})")

    message.status = MessageStatus.DISCARDED
    message.reviewed_by_id = staff.id
    message.reviewed_at = dt.datetime.utcnow()

    db.session.add(
        AuditLog(
            clinic_id=message.clinic_id,
            staff_id=staff.id,
            lead_id=message.lead_id,
            action="discarded_draft",
            detail=reason or f"message_id={message.id}",
        )
    )
    db.session.commit()
    return message


def send_manual_message(*, lead, staff: StaffUser, body: str) -> Message:
    """Staff composing a reply from scratch (outside any queued draft) --
    used from the lead detail view."""
    from app.constants import MessageAuthor, MessageDirection

    body = body.strip()
    if not body:
        raise ValueError("cannot send an empty reply")

    clinic = lead.clinic
    adapter = get_adapter(lead.channel, clinic=clinic, config=current_app.config)
    adapter.send_text(to=resolve_reply_target(lead), body=body)

    now = dt.datetime.utcnow()
    message = Message(
        lead_id=lead.id,
        clinic_id=clinic.id,
        direction=MessageDirection.OUTBOUND,
        channel=lead.channel,
        author_type=MessageAuthor.STAFF,
        body=body,
        language=lead.language,
        ai_generated=False,
        status=MessageStatus.SENT,
        reviewed_by_id=staff.id,
        reviewed_at=now,
        sent_at=now,
    )
    db.session.add(message)

    if lead.first_response_at is None:
        lead.first_response_at = now
    lead.last_outbound_at = now
    lead.status = advance_lead_status(lead.status, LeadStatus.RESPONDED)

    db.session.add(
        AuditLog(clinic_id=clinic.id, staff_id=staff.id, lead_id=lead.id, action="manual_reply_sent")
    )
    db.session.commit()
    return message

