import datetime as dt

from app.channels.base import InboundMessage
from app.constants import MessageAuthor
from app.extensions import db
from app.services.followup_service import run_followup_tick
from app.services.lead_service import ingest_inbound


def _age_lead(lead, days_since_last_inbound: int) -> None:
    lead.last_inbound_at = dt.datetime.utcnow() - dt.timedelta(days=days_since_last_inbound)
    db.session.commit()


def _new_lead(clinic, external_id="+1"):
    return ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id=external_id, body="Hi"))


def test_no_nudge_before_two_days(app, clinic):
    lead = _new_lead(clinic)
    _age_lead(lead, days_since_last_inbound=1)
    assert run_followup_tick() == 0
    assert lead.follow_up_stage == 0


def test_first_nudge_fires_at_two_days(app, clinic):
    lead = _new_lead(clinic)
    _age_lead(lead, days_since_last_inbound=2)
    assert run_followup_tick() == 1
    assert lead.follow_up_stage == 1
    nudges = [m for m in lead.messages if m.author_type == MessageAuthor.AUTO_FOLLOWUP]
    assert len(nudges) == 1


def test_second_nudge_waits_for_six_days_from_original_silence(app, clinic):
    lead = _new_lead(clinic)
    _age_lead(lead, days_since_last_inbound=2)
    run_followup_tick()
    assert lead.follow_up_stage == 1

    _age_lead(lead, days_since_last_inbound=4)  # still short of day 6
    assert run_followup_tick() == 0
    assert lead.follow_up_stage == 1

    _age_lead(lead, days_since_last_inbound=6)
    assert run_followup_tick() == 1
    assert lead.follow_up_stage == 2


def test_sequence_is_capped_at_two_nudges_ever(app, clinic):
    lead = _new_lead(clinic)
    _age_lead(lead, days_since_last_inbound=2)
    run_followup_tick()
    _age_lead(lead, days_since_last_inbound=6)
    run_followup_tick()
    assert lead.follow_up_stage == 2

    _age_lead(lead, days_since_last_inbound=30)
    assert run_followup_tick() == 0  # capped -- no third nudge no matter how long they stay quiet


def test_unanswered_new_message_is_not_nudged_on_top_of(app, clinic):
    lead = _new_lead(clinic)
    _age_lead(lead, days_since_last_inbound=2)
    # they wrote again more recently than our last outbound -- a draft is
    # presumably sitting in the queue for it, so don't also fire a nudge.
    lead.last_inbound_at = dt.datetime.utcnow()
    db.session.commit()
    assert run_followup_tick() == 0
