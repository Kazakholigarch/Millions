from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage

from app.channels.base import ChannelAdapter, InboundMessage, InboundPhoto

_FROM_HEADER_RE = re.compile(r'(?:"?([^"<]*)"?\s*)?<?([\w.+-]+@[\w-]+\.[\w.-]+)>?')


def parse_inbound_email(payload: dict) -> InboundMessage:
    """Normalizes the field-name conventions used by common inbound-parse
    webhook providers (Mailgun/SendGrid-style: `from`/`sender` +
    `body-plain`/`text`, plus an `attachments` list)."""
    raw_from = payload.get("from") or payload.get("sender") or ""
    name, email = _split_from_header(raw_from)

    body = (payload.get("body-plain") or payload.get("text") or payload.get("body") or "").strip()
    subject = (payload.get("subject") or "").strip()
    if subject and body:
        body = f"{subject}\n\n{body}"
    elif subject:
        body = subject

    photos = []
    for att in payload.get("attachments", []) or []:
        if not isinstance(att, dict):
            continue
        url = att.get("url")
        content_type = att.get("content_type") or ""
        if url and content_type.startswith("image"):
            photos.append(InboundPhoto(url=url, content_type=content_type))

    return InboundMessage(
        channel="email",
        external_id=email or raw_from,
        body=body,
        contact_name=name,
        contact_email=email,
        photos=photos,
    )


def _split_from_header(raw: str) -> tuple[str | None, str | None]:
    match = _FROM_HEADER_RE.search(raw or "")
    if not match:
        return None, None
    name = match.group(1)
    return (name.strip() or None if name else None), match.group(2)


class EmailAdapter(ChannelAdapter):
    channel_name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, from_addr: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_addr = from_addr

    def send_text(self, *, to: str, body: str) -> None:
        if not to:
            return
        message = EmailMessage()
        message["Subject"] = "Re: your hair transplant enquiry"
        message["From"] = self._from_addr
        message["To"] = to
        message.set_content(body)

        with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(message)
