from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger("fuehub.channels")


@dataclass
class InboundPhoto:
    """A photo attached to an inbound message. `url` is set for channels
    that hand us a fetchable URL (WhatsApp/Instagram media, or an emailed
    attachment link); `data` is set when the channel handed us bytes
    directly (e.g. a website form upload)."""

    url: str | None = None
    data: bytes | None = None
    content_type: str | None = None
    filename: str | None = None


@dataclass
class InboundMessage:
    """The common shape every channel-specific webhook parser normalizes
    into, before it ever reaches the lead/service layer. This is the one
    place channel differences disappear."""

    channel: str
    external_id: str  # phone number / email address / IG user id / form session token
    body: str
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    contact_handle: str | None = None
    photos: list[InboundPhoto] = field(default_factory=list)
    provider_message_id: str | None = None


class ChannelAdapter(ABC):
    """Sends a reply back out over a channel. Every adapter has a safe,
    credential-free default: log what would have been sent and return.
    Adapters only start actually calling an external API once the matching
    credentials are configured (see app/config.py / .env.example) -- so the
    app is fully runnable and testable with zero API keys, and wiring in a
    real channel later is a config change, not a rewrite.
    """

    channel_name: str = "base"

    @abstractmethod
    def send_text(self, *, to: str, body: str) -> None:
        ...


class LogChannelAdapter(ChannelAdapter):
    channel_name = "log"

    def __init__(self, channel_name: str):
        self.channel_name = channel_name

    def send_text(self, *, to: str, body: str) -> None:
        logger.info("[SIMULATED SEND via %s] to=%s body=%r", self.channel_name, to, body)


def get_adapter(channel: str, *, clinic, config) -> ChannelAdapter:
    """Return the adapter for `channel`, using real credentials when
    configured (app config, optionally overridden per-clinic via
    clinic.channel_config), else the log/no-op adapter."""
    from app.channels.email_channel import EmailAdapter
    from app.channels.instagram import MetaInstagramAdapter
    from app.channels.website import WebsiteAdapter
    from app.channels.whatsapp import TwilioWhatsAppAdapter
    from app.constants import Channel

    clinic_cfg = (clinic.channel_config or {}) if clinic is not None else {}

    if channel == Channel.WHATSAPP:
        cfg = {**_twilio_defaults(config), **clinic_cfg.get("whatsapp", {})}
        if cfg.get("account_sid") and cfg.get("auth_token") and cfg.get("from_number"):
            return TwilioWhatsAppAdapter(**cfg)
        return LogChannelAdapter(Channel.WHATSAPP)

    if channel == Channel.INSTAGRAM:
        cfg = {**_meta_defaults(config), **clinic_cfg.get("instagram", {})}
        if cfg.get("page_access_token"):
            return MetaInstagramAdapter(**cfg)
        return LogChannelAdapter(Channel.INSTAGRAM)

    if channel == Channel.EMAIL:
        cfg = {**_smtp_defaults(config), **clinic_cfg.get("email", {})}
        if cfg.get("host") and cfg.get("from_addr"):
            return EmailAdapter(**cfg)
        return LogChannelAdapter(Channel.EMAIL)

    if channel == Channel.WEBSITE:
        # A contact form has no channel of its own to push a reply into --
        # we fall back to emailing the address the enquirer gave us.
        return WebsiteAdapter(get_adapter(Channel.EMAIL, clinic=clinic, config=config))

    return LogChannelAdapter(channel)


def _twilio_defaults(config) -> dict:
    return {
        "account_sid": getattr(config, "TWILIO_ACCOUNT_SID", ""),
        "auth_token": getattr(config, "TWILIO_AUTH_TOKEN", ""),
        "from_number": getattr(config, "TWILIO_WHATSAPP_FROM", ""),
    }


def _meta_defaults(config) -> dict:
    return {"page_access_token": getattr(config, "META_PAGE_ACCESS_TOKEN", "")}


def get_media_download_headers(channel: str, *, clinic, config) -> dict:
    """Auth headers needed to fetch a channel's media URL, if any. Twilio
    protects WhatsApp media behind Basic Auth with your account
    credentials; Meta's Instagram attachment URLs are pre-signed temporary
    CDN links and need no extra header. Used by lead_service when
    downloading a photo an enquirer sent."""
    from app.constants import Channel

    clinic_cfg = (clinic.channel_config or {}) if clinic is not None else {}

    if channel == Channel.WHATSAPP:
        cfg = {**_twilio_defaults(config), **clinic_cfg.get("whatsapp", {})}
        if cfg.get("account_sid") and cfg.get("auth_token"):
            token = base64.b64encode(f"{cfg['account_sid']}:{cfg['auth_token']}".encode()).decode()
            return {"Authorization": f"Basic {token}"}

    return {}


def resolve_reply_target(lead) -> str:
    """The address/number/id an outbound adapter should send to for this
    lead. A contact form has no channel-native address, so it falls back
    to whatever email the enquirer gave."""
    from app.constants import Channel

    if lead.channel in (Channel.EMAIL, Channel.WEBSITE):
        return lead.contact_email or lead.external_id
    return lead.external_id


def _smtp_defaults(config) -> dict:
    return {
        "host": getattr(config, "SMTP_HOST", ""),
        "port": getattr(config, "SMTP_PORT", 587),
        "user": getattr(config, "SMTP_USER", ""),
        "password": getattr(config, "SMTP_PASSWORD", ""),
        "from_addr": getattr(config, "SMTP_FROM", ""),
    }
