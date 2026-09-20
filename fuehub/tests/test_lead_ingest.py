from app.channels.base import InboundMessage, InboundPhoto
from app.constants import LeadStatus, MessageStatus
from app.services.lead_service import ingest_inbound


def test_new_lead_gets_instant_ack_and_ai_draft(app, clinic):
    inbound = InboundMessage(
        channel="whatsapp", external_id="+15551234567", body="How much for 3000 grafts?", contact_name="Jane"
    )
    lead = ingest_inbound(clinic=clinic, inbound=inbound)

    assert lead.status == LeadStatus.AWAITING_REVIEW
    assert lead.language == "en"

    messages = lead.messages.order_by("created_at").all()
    assert [m.author_type for m in messages] == ["enquirer", "auto_ack", "ai_draft"]
    assert messages[1].status == MessageStatus.SENT  # ack sends immediately, no review needed
    assert "thank you" in messages[1].body.lower()
    assert messages[2].status == MessageStatus.PENDING_REVIEW  # AI draft waits for approval


def test_clinical_question_is_escalated_not_ai_drafted(app, clinic):
    inbound = InboundMessage(
        channel="email", external_id="patient@example.com", body="Am I a good candidate? I have diabetes."
    )
    lead = ingest_inbound(clinic=clinic, inbound=inbound)

    assert lead.requires_clinical_review is True
    last_message = lead.messages.order_by("created_at").all()[-1]
    assert last_message.status == MessageStatus.NEEDS_CLINICIAN
    assert last_message.body == ""
    assert last_message.ai_generated is False


def test_second_message_from_same_contact_dedupes_to_one_lead(app, clinic):
    first = ingest_inbound(clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1555", body="Hi"))
    second = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="+1555", body="Following up")
    )
    assert first.id == second.id
    # msg1 in, ack, draft1, msg2 in, draft2 -- no second ack, first contact only
    assert second.messages.count() == 5
    assert sum(1 for m in second.messages if m.author_type == "auto_ack") == 1


def test_photos_flag_clinical_review_without_blocking_the_faq_reply(app, clinic):
    inbound = InboundMessage(
        channel="whatsapp",
        external_id="+1555999",
        body="How much for FUE?",
        photos=[InboundPhoto(data=b"fake-image-bytes", content_type="image/jpeg", filename="photo.jpg")],
    )
    lead = ingest_inbound(clinic=clinic, inbound=inbound)

    assert lead.has_photos is True
    assert lead.requires_clinical_review is True
    assert lead.attachments.count() == 1

    # a photo alone isn't a clinical keyword match -- the FAQ question next
    # to it still gets an AI draft, it just also gets flagged for review.
    draft = [m for m in lead.messages if m.author_type == "ai_draft"][0]
    assert draft.status == MessageStatus.PENDING_REVIEW
    assert "personally review" in draft.body.lower()


def test_different_channels_never_collide_on_the_same_lead(app, clinic):
    whatsapp_lead = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="whatsapp", external_id="12345", body="Hi")
    )
    instagram_lead = ingest_inbound(
        clinic=clinic, inbound=InboundMessage(channel="instagram", external_id="12345", body="Hi")
    )
    assert whatsapp_lead.id != instagram_lead.id
