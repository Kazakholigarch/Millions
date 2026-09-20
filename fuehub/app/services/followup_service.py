from __future__ import annotations

import datetime as dt

from flask import current_app

from app.ai.templates import render_followup
from app.channels.base import get_adapter, resolve_reply_target
from app.constants import LeadStatus, MessageAuthor, MessageDirection, MessageStatus
from app.extensions import db
from app.models import Clinic, Lead, Message

"""Capped automatic follow-up: a nudge at day 2, another at day 6, then
stop. This is the piece that recovers the revenue that would otherwise
leak away in the gap between "enquired" and "someone finally replied a
week later" -- so it runs on a schedule, not on-demand.

The "quiet" clock is anchored to `last_inbound_at` (the enquirer's last
word), which stays fixed while they stay silent -- so nudge #2 lands 6
days after they went quiet, not 6 days after nudge #1. A lead is only a
candidate once we've actually replied since their last message (ball is
in their court); if a new message from them is still sitting unanswered
in the queue, nudging would be redundant with the pending draft.
"""

TERMINAL_STATUSES = (LeadStatus.CONSULTATION_BOOKED, LeadStatus.DEPOSIT_PAID, LeadStatus.CLOSED_LOST)


def run_followup_tick(*, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.utcnow()
    sent = 0
    for clinic in Clinic.query.filter_by(auto_send_followups=True).all():
        candidates = (
            Lead.query.filter_by(clinic_id=clinic.id)
            .filter(Lead.follow_up_stage < 2)
            .filter(~Lead.status.in_(TERMINAL_STATUSES))
            .filter(Lead.last_outbound_at.isnot(None))
            .all()
        )
        for lead in candidates:
            if _send_due_nudge(clinic, lead, now):
                sent += 1
    return sent


def _send_due_nudge(clinic: Clinic, lead: Lead, now: dt.datetime) -> bool:
    if not lead.last_outbound_at or lead.last_outbound_at < lead.last_inbound_at:
        return False  # they messaged again and it's still unanswered -- not "quiet"

    nudge_days = current_app.config["FOLLOWUP_NUDGE_DAYS"]
    next_stage = lead.follow_up_stage + 1
    if next_stage > len(nudge_days):
        return False

    days_quiet = (now - lead.last_inbound_at).days
    if days_quiet < nudge_days[next_stage - 1]:
        return False

    clinic_name = (clinic.knowledge_base or {}).get("clinic_display_name", clinic.name)
    text = render_followup(lead.language, next_stage, clinic_name, lead.contact_name)

    adapter = get_adapter(lead.channel, clinic=clinic, config=current_app.config)
    adapter.send_text(to=resolve_reply_target(lead), body=text)

    db.session.add(
        Message(
            lead_id=lead.id,
            clinic_id=clinic.id,
            direction=MessageDirection.OUTBOUND,
            channel=lead.channel,
            author_type=MessageAuthor.AUTO_FOLLOWUP,
            body=text,
            language=lead.language,
            ai_generated=False,
            status=MessageStatus.SENT,
            sent_at=now,
        )
    )
    lead.follow_up_stage = next_stage
    lead.last_outbound_at = now
    db.session.commit()
    return True
