from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.parse
import urllib.request

from app.channels.base import ChannelAdapter, InboundMessage, InboundPhoto


def parse_twilio_webhook(form: dict) -> InboundMessage:
    """Twilio posts WhatsApp messages as application/x-www-form-urlencoded
    with From ("whatsapp:+123..."), Body, ProfileName, NumMedia,
    MediaUrl0..N, MediaContentType0..N."""
    raw_from = form.get("From", "")
    phone = raw_from.replace("whatsapp:", "").strip()
    name = (form.get("ProfileName") or "").strip() or None
    body = (form.get("Body") or "").strip()

    photos = []
    try:
        num_media = int(form.get("NumMedia", "0") or 0)
    except ValueError:
        num_media = 0
    for i in range(num_media):
        url = form.get(f"MediaUrl{i}")
        content_type = form.get(f"MediaContentType{i}") or ""
        if url and content_type.startswith("image"):
            photos.append(InboundPhoto(url=url, content_type=content_type))

    return InboundMessage(
        channel="whatsapp",
        external_id=phone,
        body=body,
        contact_name=name,
        contact_phone=phone,
        photos=photos,
        provider_message_id=form.get("MessageSid"),
    )


def verify_twilio_signature(auth_token: str, url: str, form: dict, signature: str) -> bool:
    """Twilio's request-signing scheme: HMAC-SHA1 over the full request URL
    with sorted-by-key form params appended, base64-encoded.
    https://www.twilio.com/docs/usage/security#validating-requests
    """
    if not auth_token or not signature:
        return False
    data = url
    for key in sorted(form.keys()):
        data += key + form[key]
    computed = base64.b64encode(
        hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    return hmac.compare_digest(computed, signature)


class TwilioWhatsAppAdapter(ChannelAdapter):
    channel_name = "whatsapp"

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    def send_text(self, *, to: str, body: str) -> None:
        if not to:
            return
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        data = urllib.parse.urlencode(
            {"From": f"whatsapp:{self._from_number}", "To": f"whatsapp:{to}", "Body": body}
        ).encode("utf-8")
        credentials = base64.b64encode(f"{self._account_sid}:{self._auth_token}".encode()).decode()
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Authorization", f"Basic {credentials}")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        urllib.request.urlopen(request, timeout=10)
