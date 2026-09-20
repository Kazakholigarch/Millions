from app.constants import UrgencyBand
from app.scoring.urgency import score_lead_text


def test_routine_lead_scores_low():
    result = score_lead_text(combined_inbound_text="Hi, just curious about your clinic.", has_photos=False)
    assert result.band == UrgencyBand.ROUTINE
    assert result.score < 35


def test_hot_lead_with_photos_budget_and_urgency():
    text = "I need this ASAP, my budget is 3000 euros, planning to come next week"
    result = score_lead_text(combined_inbound_text=text, has_photos=True)
    assert result.band == UrgencyBand.HOT
    assert result.score >= 65


def test_photos_alone_bump_score_and_are_explained():
    result = score_lead_text(combined_inbound_text="Here are some photos of my hairline", has_photos=True)
    assert result.score >= 25
    assert any("photo" in reason.lower() for reason in result.reasons)


def test_urgency_language_is_detected_and_explained():
    result = score_lead_text(combined_inbound_text="How soon can I get an appointment?", has_photos=False)
    assert any("urgency" in reason.lower() for reason in result.reasons)


def test_score_is_capped_at_100():
    text = "ASAP urgent budget $5000 next week graft cost FUE DHI how much"
    result = score_lead_text(combined_inbound_text=text, has_photos=True)
    assert result.score <= 100
