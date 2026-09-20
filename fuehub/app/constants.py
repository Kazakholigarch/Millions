"""Plain string constants instead of DB-level enums, so adding a value (a
new channel, a new lead status) is a code change, not a migration."""
from __future__ import annotations


class Channel:
    WEBSITE = "website"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"

    ALL = (WEBSITE, EMAIL, WHATSAPP, INSTAGRAM)


class LeadStatus:
    NEW = "new"                              # inbound received, nothing sent yet
    ACKNOWLEDGED = "acknowledged"             # instant localized ack sent
    AWAITING_REVIEW = "awaiting_review"       # AI draft (or clinician flag) waiting in queue
    RESPONDED = "responded"                   # a substantive reply has been sent
    CONSULTATION_BOOKED = "consultation_booked"
    DEPOSIT_PAID = "deposit_paid"
    CLOSED_LOST = "closed_lost"

    # Order matters: used to render the funnel left-to-right. Funnel *counts*
    # are computed from monotonic milestone timestamps on Lead (see
    # metrics_service), not from this mutable field -- `status` only drives
    # the queue view and can legitimately move back and forth between
    # AWAITING_REVIEW and RESPONDED as a conversation continues.
    FUNNEL_ORDER = (NEW, ACKNOWLEDGED, RESPONDED, CONSULTATION_BOOKED, DEPOSIT_PAID)


# Rank used only to stop an ordinary "reply sent" from *visually* regressing
# a lead that already booked/paid back down to "responded" in the queue.
# Explicit staff actions (book a slot, mark deposit paid, close lost) always
# set status directly and bypass this guard.
_STATUS_RANK = {
    LeadStatus.NEW: 0,
    LeadStatus.ACKNOWLEDGED: 1,
    LeadStatus.AWAITING_REVIEW: 2,
    LeadStatus.RESPONDED: 2,
    LeadStatus.CONSULTATION_BOOKED: 3,
    LeadStatus.DEPOSIT_PAID: 4,
}


def advance_lead_status(current: str, new: str) -> str:
    """Return `new` unless it would regress a lead below its current rank
    (e.g. a routine reply on an already-booked lead shouldn't make it look
    unbooked in the queue)."""
    if new not in _STATUS_RANK or current not in _STATUS_RANK:
        return new
    return new if _STATUS_RANK[new] >= _STATUS_RANK[current] else current


class UrgencyBand:
    ROUTINE = "routine"
    WARM = "warm"
    HOT = "hot"


class MessageDirection:
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageAuthor:
    ENQUIRER = "enquirer"
    AUTO_ACK = "auto_ack"
    AI_DRAFT = "ai_draft"
    STAFF = "staff"
    AUTO_FOLLOWUP = "auto_followup"


class MessageStatus:
    SENT = "sent"                    # went out (ack, staff reply, follow-up, edited-then-sent)
    PENDING_REVIEW = "pending_review"  # AI draft sitting in the approve/edit queue
    NEEDS_CLINICIAN = "needs_clinician"  # escalated, no AI draft was even attempted
    DISCARDED = "discarded"          # staff rejected the draft without sending


class StaffRole:
    ADMIN = "admin"
    STAFF = "staff"


SUPPORTED_LANGUAGES = ("en", "de", "ar", "ru")
DEFAULT_LANGUAGE = "en"
