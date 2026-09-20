from app.ai.faq import compose_faq_reply, detect_topics
from app.models.clinic import _default_knowledge_base


class _DummyClinic:
    def __init__(self):
        self.knowledge_base = _default_knowledge_base()
        self.name = "Test Clinic"
        self.timezone = "Europe/Istanbul"


def test_detects_cost_topic():
    assert "cost" in detect_topics("How much does it cost?")


def test_detects_multiple_topics_at_once():
    topics = detect_topics("What's included in the package and how many days do I stay?")
    assert "package" in topics
    assert "stay" in topics


def test_reply_is_localized_not_just_wrapped_in_english_facts():
    clinic = _DummyClinic()
    reply = compose_faq_reply(language="de", clinic=clinic, topics={"technique"}, has_photos=False)
    assert "Danke" in reply
    # the FUE/DHI descriptions themselves must be the German variant, not English
    assert "Follikel werden" in reply
    assert "individual follicles are removed" not in reply


def test_reply_falls_back_to_english_for_unfilled_language():
    clinic = _DummyClinic()
    clinic.knowledge_base["typical_stay_days"] = {"en": "3-4 days"}  # no "fr" -- unsupported anyway
    reply = compose_faq_reply(language="fr", clinic=clinic, topics={"stay"}, has_photos=False)
    assert "3-4 days" in reply


def test_no_topic_detected_asks_a_clarifying_question():
    clinic = _DummyClinic()
    reply = compose_faq_reply(language="en", clinic=clinic, topics=set(), has_photos=False)
    assert "?" in reply


def test_photo_note_is_appended_and_never_evaluates_the_photo():
    clinic = _DummyClinic()
    reply = compose_faq_reply(language="en", clinic=clinic, topics=set(), has_photos=True)
    assert "photo" in reply.lower()
    assert "specialist will personally review" in reply.lower()
