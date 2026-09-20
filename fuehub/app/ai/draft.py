from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.escalation import needs_clinical_escalation
from app.ai.faq import detect_topics
from app.ai.redact import redact_pii


@dataclass
class DraftResult:
    needs_clinician: bool
    draft_text: str | None
    matched_topics: set[str] = field(default_factory=set)
    escalation_reasons: list[str] = field(default_factory=list)


def draft_reply_for_message(*, clinic, lead, message_text: str, ai_client) -> DraftResult:
    """The core AI-drafting gate. Anything clinical never reaches the AI
    client at all -- it's routed to a clinician instead. Everything else is
    redacted of contact-identifying details before it goes to the AI
    client, per the data-minimization requirement."""
    escalation_reasons = needs_clinical_escalation(message_text)
    if escalation_reasons:
        return DraftResult(needs_clinician=True, draft_text=None, escalation_reasons=escalation_reasons)

    redacted_text = redact_pii(message_text)
    topics = detect_topics(redacted_text)

    available_slots = []
    if "consultation" in topics:
        from app.services.booking_service import list_upcoming_slots

        available_slots = list_upcoming_slots(clinic, limit=3)

    draft_text = ai_client.draft(
        clinic=clinic,
        lead=lead,
        language=lead.language,
        conversation_text=redacted_text,
        topics=topics,
        available_slots=available_slots,
    )
    return DraftResult(needs_clinician=False, draft_text=draft_text, matched_topics=topics)
