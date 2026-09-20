from __future__ import annotations

import logging

from flask import Blueprint, abort, current_app, request

from app.channels.base import InboundPhoto
from app.channels.email_channel import parse_inbound_email
from app.channels.instagram import parse_meta_webhook, verify_meta_signature
from app.channels.website import parse_form_submission
from app.channels.whatsapp import parse_twilio_webhook, verify_twilio_signature
from app.models import Clinic
from app.services.lead_service import ingest_inbound

logger = logging.getLogger("fuehub.webhooks")

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks/<clinic_slug>")


def _clinic_or_404(clinic_slug: str) -> Clinic:
    clinic = Clinic.query.filter_by(slug=clinic_slug).first()
    if clinic is None:
        abort(404, description="unknown clinic")
    return clinic


@webhooks_bp.route("/website", methods=["POST"])
def website(clinic_slug: str):
    """A direct POST from the clinic's own contact form. Accepts either a
    JSON body or a normal form submission (with optional file uploads for
    photos of the enquirer's hairline/crown)."""
    clinic = _clinic_or_404(clinic_slug)

    form = request.get_json(silent=True) or request.form.to_dict()
    inbound = parse_form_submission(form)

    for file_storage in request.files.getlist("photos"):
        if not file_storage or not file_storage.filename:
            continue
        inbound.photos.append(
            InboundPhoto(
                data=file_storage.read(),
                content_type=file_storage.content_type,
                filename=file_storage.filename,
            )
        )

    if not inbound.body and not inbound.photos:
        abort(400, description="empty submission")

    lead = ingest_inbound(clinic=clinic, inbound=inbound)
    return {"lead_id": lead.id, "status": lead.status}, 201


@webhooks_bp.route("/email", methods=["POST"])
def email(clinic_slug: str):
    """Generic inbound-email-parse webhook (Mailgun/SendGrid-shaped).
    Providers each sign requests their own way; wire in that provider's
    verification here. In the meantime this accepts a shared secret via
    header, configured with EMAIL_WEBHOOK_SECRET."""
    clinic = _clinic_or_404(clinic_slug)
    _require_shared_secret(current_app.config.get("EMAIL_WEBHOOK_SECRET", ""))

    payload = request.get_json(silent=True) or request.form.to_dict()
    inbound = parse_inbound_email(payload)
    if not inbound.external_id:
        abort(400, description="could not determine sender address")

    lead = ingest_inbound(clinic=clinic, inbound=inbound)
    return {"lead_id": lead.id, "status": lead.status}, 201


@webhooks_bp.route("/whatsapp", methods=["POST"])
def whatsapp(clinic_slug: str):
    """Twilio WhatsApp webhook (application/x-www-form-urlencoded)."""
    clinic = _clinic_or_404(clinic_slug)

    auth_token = current_app.config.get("TWILIO_AUTH_TOKEN", "")
    if auth_token:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not verify_twilio_signature(auth_token, request.url, request.form.to_dict(), signature):
            abort(403, description="invalid Twilio signature")

    inbound = parse_twilio_webhook(request.form.to_dict())
    if not inbound.external_id:
        abort(400, description="missing From number")

    ingest_inbound(clinic=clinic, inbound=inbound)
    return ("", 204)


@webhooks_bp.route("/instagram", methods=["GET", "POST"])
def instagram(clinic_slug: str):
    """Meta Instagram Messaging webhook: GET is the subscription handshake,
    POST delivers events (and can batch several)."""
    clinic = _clinic_or_404(clinic_slug)

    if request.method == "GET":
        verify_token = current_app.config.get("META_VERIFY_TOKEN", "")
        if (
            request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == verify_token
        ):
            return request.args.get("hub.challenge", ""), 200
        abort(403, description="invalid verify token")

    app_secret = current_app.config.get("META_APP_SECRET", "")
    if app_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_meta_signature(app_secret, request.get_data(), signature):
            abort(403, description="invalid Meta signature")

    payload = request.get_json(silent=True) or {}
    for inbound in parse_meta_webhook(payload):
        if not inbound.body and not inbound.photos:
            continue
        ingest_inbound(clinic=clinic, inbound=inbound)

    return {"status": "ok"}, 200


def _require_shared_secret(expected: str) -> None:
    if not expected:
        return  # no secret configured -- open endpoint, documented as a pre-launch TODO
    provided = request.headers.get("X-Webhook-Secret", "")
    if provided != expected:
        abort(403, description="invalid webhook secret")
