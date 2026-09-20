from __future__ import annotations

import uuid

from app.channels.base import ChannelAdapter, InboundMessage


def parse_form_submission(form: dict) -> InboundMessage:
    """A direct POST from the clinic's own contact form -- no external
    webhook payload to normalize, just field-name tolerance."""
    name = (form.get("name") or "").strip() or None
    email = (form.get("email") or "").strip() or None
    phone = (form.get("phone") or "").strip() or None
    message = (form.get("message") or "").strip()
    external_id = email or phone or (form.get("session_id") or "").strip() or str(uuid.uuid4())

    return InboundMessage(
        channel="website",
        external_id=external_id,
        body=message,
        contact_name=name,
        contact_phone=phone,
        contact_email=email,
    )


class WebsiteAdapter(ChannelAdapter):
    """A contact form has no channel of its own to push a reply back into,
    so it delegates to the email adapter using whatever address the
    enquirer left."""

    channel_name = "website"

    def __init__(self, email_adapter: ChannelAdapter):
        self._email_adapter = email_adapter

    def send_text(self, *, to: str, body: str) -> None:
        if not to:
            return
        self._email_adapter.send_text(to=to, body=body)
