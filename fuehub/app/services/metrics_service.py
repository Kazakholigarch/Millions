from __future__ import annotations

from collections import defaultdict

from app.models import Lead

"""Dashboard analytics: response time by language/channel, the enquiry
funnel, and a recovered-bookings estimate. Deliberately reads straight off
Lead's monotonic milestone timestamps (first_response_at,
consultation_booked_at, deposit_paid_at) rather than the mutable `status`
field, so counts never move backwards just because a booked lead sent
another routine message.
"""


def response_time_breakdown(clinic) -> list[dict]:
    leads = Lead.query.filter_by(clinic_id=clinic.id).filter(Lead.first_response_at.isnot(None)).all()
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for lead in leads:
        minutes = (lead.first_response_at - lead.first_inbound_at).total_seconds() / 60.0
        buckets[(lead.language, lead.channel)].append(minutes)

    rows = []
    for (language, channel), minutes_list in sorted(buckets.items()):
        rows.append(
            {
                "language": language,
                "channel": channel,
                "count": len(minutes_list),
                "avg_minutes": round(sum(minutes_list) / len(minutes_list), 1),
            }
        )
    return rows


def funnel(clinic) -> dict:
    leads = Lead.query.filter_by(clinic_id=clinic.id).all()
    return {
        "enquired": len(leads),
        "responded": sum(1 for lead in leads if lead.first_response_at is not None),
        "consultation_booked": sum(1 for lead in leads if lead.consultation_booked_at is not None),
        "deposit_paid": sum(1 for lead in leads if lead.deposit_paid_at is not None),
    }


def recovered_bookings(clinic) -> dict:
    """Leads that went quiet, were nudged by the automatic follow-up
    sequence, came back on their own, and then booked/paid -- the direct
    revenue case for the whole follow-up feature."""
    nudged_and_replied = Lead.query.filter_by(clinic_id=clinic.id, recovered_by_followup=True).all()
    return {
        "nudged_and_replied": len(nudged_and_replied),
        "recovered_bookings": sum(1 for lead in nudged_and_replied if lead.consultation_booked_at is not None),
        "recovered_deposits": sum(1 for lead in nudged_and_replied if lead.deposit_paid_at is not None),
    }
