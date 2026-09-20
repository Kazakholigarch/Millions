from __future__ import annotations

import datetime as dt
import urllib.request
import uuid
from pathlib import Path

from flask import current_app

from app.ai.client import get_ai_client
from app.ai.draft import draft_reply_for_message
from app.ai.language import detect_language
from app.ai.templates import render_ack
from app.channels.base import (
    InboundMessage,
    InboundPhoto,
    get_adapter,
    get_media_download_headers,
    resolve_reply_target,
)
from app.constants import (
    LeadStatus,
    MessageAuthor,
    MessageDirection,
    MessageStatus,
    advance_lead_status,
)
from app.extensions import db
from app.models import Attachment, Clinic, Lead, Message
from app.scoring.urgency import score_lead_text

"""The inbound pipeline: normalize -> dedupe/create lead -> store message +
photos -> score -> instant localized ack (first contact only) -> AI draft
or clinical escalation, landing in the approve/edit queue. Every inbound
webhook (website, email, WhatsApp, Instagram) funnels through
`ingest_inbound` so there's exactly one place this logic lives.
"""


def ingest_inbound(*, clinic: Clinic, inbound: InboundMessage) -> Lead:
    lead = Lead.query.filter_by(
        clinic_id=clinic.id, channel=inbound.channel, external_id=inbound.external_id
    ).first()
    is_new_lead = lead is None
    now = dt.datetime.utcnow()

    if is_new_lead:
        lead = Lead(
            clinic_id=clinic.id,
            channel=inbound.channel,
            external_id=inbound.external_id,
            contact_name=inbound.contact_name,
            contact_phone=inbound.contact_phone,
            contact_email=inbound.contact_email,
            contact_handle=inbound.contact_handle,
            language=detect_language(inbound.body),
            first_message=inbound.body,
            status=LeadStatus.NEW,
            first_inbound_at=now,
            last_inbound_at=now,
        )
        db.session.add(lead)
        db.session.flush()  # assign lead.id before it's used by messages/attachments below
    else:
        lead.last_inbound_at = now
        lead.contact_name = lead.contact_name or inbound.contact_name
        lead.contact_phone = lead.contact_phone or inbound.contact_phone
        lead.contact_email = lead.contact_email or inbound.contact_email
        lead.contact_handle = lead.contact_handle or inbound.contact_handle
        if lead.follow_up_stage > 0:
            # They came back on their own after a nudge -- that's the
            # recovered-booking metric's raw material.
            lead.recovered_by_followup = True
        lead.follow_up_stage = 0

    inbound_message = Message(
        lead_id=lead.id,
        clinic_id=clinic.id,
        direction=MessageDirection.INBOUND,
        channel=inbound.channel,
        author_type=MessageAuthor.ENQUIRER,
        body=inbound.body,
        language=lead.language,
        status=MessageStatus.SENT,
        sent_at=now,
    )
    db.session.add(inbound_message)
    db.session.flush()

    if inbound.photos:
        lead.has_photos = True
        lead.requires_clinical_review = True
        for photo in inbound.photos:
            attachment = _save_attachment(clinic, lead, photo)
            attachment.message_id = inbound_message.id
            db.session.add(attachment)

    _rescore(lead)

    if is_new_lead:
        _send_auto_ack(clinic, lead)

    _queue_ai_or_escalation(clinic, lead, inbound.body)

    db.session.commit()
    return lead


def _rescore(lead: Lead) -> None:
    combined_text = " ".join(
        m.body for m in lead.messages.filter_by(direction=MessageDirection.INBOUND)
    )
    result = score_lead_text(combined_inbound_text=combined_text, has_photos=lead.has_photos)
    lead.urgency_score = result.score
    lead.urgency_band = result.band
    lead.score_reasons = result.reasons


def _send_auto_ack(clinic: Clinic, lead: Lead) -> None:
    clinic_name = (clinic.knowledge_base or {}).get("clinic_display_name", clinic.name)
    ack_text = render_ack(lead.language, clinic_name, lead.contact_name)

    adapter = get_adapter(lead.channel, clinic=clinic, config=current_app.config)
    adapter.send_text(to=resolve_reply_target(lead), body=ack_text)

    now = dt.datetime.utcnow()
    db.session.add(
        Message(
            lead_id=lead.id,
            clinic_id=clinic.id,
            direction=MessageDirection.OUTBOUND,
            channel=lead.channel,
            author_type=MessageAuthor.AUTO_ACK,
            body=ack_text,
            language=lead.language,
            ai_generated=False,
            status=MessageStatus.SENT,
            sent_at=now,
        )
    )
    lead.status = LeadStatus.ACKNOWLEDGED
    lead.last_outbound_at = now


def _queue_ai_or_escalation(clinic: Clinic, lead: Lead, message_text: str) -> Message:
    ai_client = get_ai_client(current_app.config)
    result = draft_reply_for_message(clinic=clinic, lead=lead, message_text=message_text, ai_client=ai_client)

    if result.needs_clinician:
        lead.requires_clinical_review = True
        queue_message = Message(
            lead_id=lead.id,
            clinic_id=clinic.id,
            direction=MessageDirection.OUTBOUND,
            channel=lead.channel,
            author_type=MessageAuthor.STAFF,
            body="",
            language=lead.language,
            ai_generated=False,
            status=MessageStatus.NEEDS_CLINICIAN,
        )
    else:
        queue_message = Message(
            lead_id=lead.id,
            clinic_id=clinic.id,
            direction=MessageDirection.OUTBOUND,
            channel=lead.channel,
            author_type=MessageAuthor.AI_DRAFT,
            body=result.draft_text or "",
            original_ai_draft=result.draft_text,
            language=lead.language,
            ai_generated=True,
            status=MessageStatus.PENDING_REVIEW,
        )

    db.session.add(queue_message)
    lead.status = advance_lead_status(lead.status, LeadStatus.AWAITING_REVIEW)
    return queue_message


_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _save_attachment(clinic: Clinic, lead: Lead, photo: InboundPhoto) -> Attachment:
    upload_root = Path(current_app.config["UPLOAD_DIR"])
    lead_dir = upload_root / clinic.slug / str(lead.id)
    lead_dir.mkdir(parents=True, exist_ok=True)

    if photo.data is not None:
        suffix = Path(photo.filename).suffix if photo.filename else _EXT_BY_CONTENT_TYPE.get(
            (photo.content_type or "").lower(), ".jpg"
        )
        dest = lead_dir / f"{uuid.uuid4().hex}{suffix or '.jpg'}"
        dest.write_bytes(photo.data)
        return Attachment(
            lead_id=lead.id,
            file_path=str(dest.relative_to(upload_root)),
            content_type=photo.content_type,
            kind="photo",
        )

    if photo.url:
        try:
            headers = get_media_download_headers(lead.channel, clinic=clinic, config=current_app.config)
            request = urllib.request.Request(photo.url, headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                data = response.read()
            dest = lead_dir / f"{uuid.uuid4().hex}{_EXT_BY_CONTENT_TYPE.get((photo.content_type or '').lower(), '.jpg')}"
            dest.write_bytes(data)
            file_path = str(dest.relative_to(upload_root))
        except Exception:
            # No network access, or the provider's media URL needs an auth
            # header we haven't wired up for this channel yet -- keep the
            # reference so staff can still open it rather than losing the
            # signal entirely.
            file_path = f"external-reference::{photo.url}"
        return Attachment(lead_id=lead.id, file_path=file_path, content_type=photo.content_type, kind="photo")

    raise ValueError("InboundPhoto has neither data nor url")
