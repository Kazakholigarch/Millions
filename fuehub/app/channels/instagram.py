from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request

from app.channels.base import ChannelAdapter, InboundMessage, InboundPhoto


def parse_meta_webhook(payload: dict) -> list[InboundMessage]:
    """Meta's Instagram Messaging webhook batches events:
    {"object": "instagram", "entry": [{"messaging": [{"sender": {"id": ...},
    "message": {"text": ..., "attachments": [...]}}]}]}. One webhook call
    can carry several conversations' worth of events, hence a list return.
    """
    messages: list[InboundMessage] = []
    for entry in payload.get("entry", []) or []:
        for event in entry.get("messaging", []) or []:
            message = event.get("message") or {}
            if message.get("is_echo"):
                continue  # our own outbound message, echoed back by Meta
            sender_id = (event.get("sender") or {}).get("id")
            if not sender_id:
                continue

            photos = []
            for att in message.get("attachments", []) or []:
                if att.get("type") == "image":
                    url = (att.get("payload") or {}).get("url")
                    if url:
                        photos.append(InboundPhoto(url=url, content_type="image"))

            messages.append(
                InboundMessage(
                    channel="instagram",
                    external_id=sender_id,
                    body=(message.get("text") or "").strip(),
                    contact_handle=sender_id,
                    photos=photos,
                    provider_message_id=message.get("mid"),
                )
            )
    return messages


def verify_meta_signature(app_secret: str, raw_body: bytes, signature_header: str) -> bool:
    """Meta signs webhook POST bodies with header X-Hub-Signature-256:
    'sha256=<hmac>'."""
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.split("=", 1)[1])


class MetaInstagramAdapter(ChannelAdapter):
    channel_name = "instagram"

    def __init__(self, page_access_token: str):
        self._token = page_access_token

    def send_text(self, *, to: str, body: str) -> None:
        if not to:
            return
        url = f"https://graph.facebook.com/v19.0/me/messages?access_token={self._token}"
        payload = json.dumps({"recipient": {"id": to}, "message": {"text": body}}).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        request.add_header("Content-Type", "application/json")
        urllib.request.urlopen(request, timeout=10)
