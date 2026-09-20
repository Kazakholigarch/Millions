from __future__ import annotations

import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # fuehub/


class Config:
    SECRET_KEY = os.environ.get("FUEHUB_SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "FUEHUB_DATABASE_URI", f"sqlite:///{BASE_DIR / 'instance' / 'fuehub.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_DIR = BASE_DIR / "instance" / "uploads"
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15MB, generous for a couple of phone photos

    # "fake" is a deterministic, offline, template-based drafter used by
    # default so the app runs with zero external credentials. Set to
    # "anthropic" + ANTHROPIC_API_KEY to draft with a real model.
    AI_PROVIDER = os.environ.get("FUEHUB_AI_PROVIDER", "fake")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

    # WhatsApp (Twilio)
    TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

    # Instagram DM (Meta Graph API)
    META_PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
    META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "fuehub-verify")

    # Outbound email
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    EMAIL_WEBHOOK_SECRET = os.environ.get("EMAIL_WEBHOOK_SECRET", "")

    # Follow-up sequence: nudge at day 2, nudge at day 6, then stop (capped).
    FOLLOWUP_NUDGE_DAYS = (2, 6)
    FOLLOWUP_TICK_SECONDS = int(os.environ.get("FUEHUB_FOLLOWUP_TICK_SECONDS", "3600"))
    SCHEDULER_ENABLED = os.environ.get("FUEHUB_SCHEDULER_ENABLED", "1") == "1"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SCHEDULER_ENABLED = False
    WTF_CSRF_ENABLED = False
    UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="fuehub-test-uploads-"))
    AI_PROVIDER = "fake"
