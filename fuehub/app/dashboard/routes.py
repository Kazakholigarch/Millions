from __future__ import annotations

import datetime as dt
import secrets
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app.constants import SUPPORTED_LANGUAGES, Channel, MessageStatus
from app.extensions import db
from app.models import Attachment, AvailabilitySlot, Lead, Message, StaffUser
from app.services import booking_service, metrics_service, reply_service
from app.timeutil import from_clinic_local, to_clinic_local

dashboard_bp = Blueprint(
    "dashboard", __name__, template_folder="templates", static_folder="static", static_url_path="/dashboard/static"
)


# -- access control -----------------------------------------------------
# Every query below scopes explicitly by current_user.clinic_id so one
# clinic's staff can never read or act on another clinic's leads, even by
# guessing an id -- this is deliberate defense-in-depth on top of the
# login_required gate, and it's what "second clinic slots in later" needs
# to stay true at the data-access layer, not just the schema.

@dashboard_bp.before_request
def _enforce_csrf():
    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            abort(400, description="invalid or missing CSRF token")


@dashboard_bp.app_context_processor
def _inject_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {"csrf_token": session["csrf_token"]}


def _lead_or_404(lead_id: int) -> Lead:
    lead = Lead.query.filter_by(id=lead_id, clinic_id=current_user.clinic_id).first()
    if lead is None:
        abort(404)
    return lead


def _message_or_404(message_id: int) -> Message:
    message = Message.query.filter_by(id=message_id, clinic_id=current_user.clinic_id).first()
    if message is None:
        abort(404)
    return message


@dashboard_bp.app_template_filter("local_time")
def _local_time_filter(value, fmt: str = "%a %Y-%m-%d %H:%M"):
    """Renders a naive-UTC datetime column in the logged-in staff member's
    clinic timezone (see app/timeutil.py -- every DateTime column in this
    app is stored as naive UTC)."""
    if value is None:
        return ""
    timezone = current_user.clinic.timezone if current_user.is_authenticated else "UTC"
    return to_clinic_local(value, timezone).strftime(fmt)


# -- auth -----------------------------------------------------------------

@dashboard_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.queue"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        staff = StaffUser.query.filter(db.func.lower(StaffUser.email) == email).first()
        if staff and staff.is_active_staff and staff.check_password(password):
            login_user(staff)
            return redirect(url_for("dashboard.queue"))
        flash("Invalid email or password.", "error")

    return render_template("login.html")


@dashboard_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("dashboard.login"))


# -- queue ------------------------------------------------------------------

@dashboard_bp.route("/")
@login_required
def queue():
    q = (
        Message.query.join(Lead, Message.lead_id == Lead.id)
        .filter(Message.clinic_id == current_user.clinic_id)
        .filter(Message.status.in_([MessageStatus.PENDING_REVIEW, MessageStatus.NEEDS_CLINICIAN]))
    )
    channel = request.args.get("channel") or None
    language = request.args.get("language") or None
    if channel:
        q = q.filter(Message.channel == channel)
    if language:
        q = q.filter(Message.language == language)

    items = q.order_by(Lead.urgency_score.desc(), Message.created_at.asc()).all()

    return render_template(
        "queue.html",
        items=items,
        channel=channel,
        language=language,
        channels=Channel.ALL,
        languages=SUPPORTED_LANGUAGES,
        MessageStatus=MessageStatus,
    )


@dashboard_bp.route("/queue/<int:message_id>/send", methods=["POST"])
@login_required
def send_from_queue(message_id: int):
    message = _message_or_404(message_id)
    body = request.form.get("body")
    try:
        reply_service.send_reply(message=message, staff=current_user, body=body)
        flash("Reply sent.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.queue"))


@dashboard_bp.route("/queue/<int:message_id>/discard", methods=["POST"])
@login_required
def discard_from_queue(message_id: int):
    message = _message_or_404(message_id)
    try:
        reply_service.discard_reply(message=message, staff=current_user, reason=request.form.get("reason", ""))
        flash("Draft discarded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.queue"))


# -- lead detail --------------------------------------------------------

@dashboard_bp.route("/leads/<int:lead_id>")
@login_required
def lead_detail(lead_id: int):
    lead = _lead_or_404(lead_id)
    messages = lead.messages.order_by(Message.created_at.asc()).all()
    attachments = lead.attachments.all()
    slots = booking_service.list_upcoming_slots(current_user.clinic, limit=10)
    return render_template("lead_detail.html", lead=lead, messages=messages, attachments=attachments, slots=slots)


@dashboard_bp.route("/leads/<int:lead_id>/reply", methods=["POST"])
@login_required
def manual_reply(lead_id: int):
    lead = _lead_or_404(lead_id)
    try:
        reply_service.send_manual_message(lead=lead, staff=current_user, body=request.form.get("body", ""))
        flash("Reply sent.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.lead_detail", lead_id=lead.id))


@dashboard_bp.route("/leads/<int:lead_id>/book", methods=["POST"])
@login_required
def book_consultation(lead_id: int):
    lead = _lead_or_404(lead_id)
    slot_id = request.form.get("slot_id", type=int)
    slot = AvailabilitySlot.query.filter_by(id=slot_id, clinic_id=current_user.clinic_id).first()
    if slot is None:
        flash("That slot is no longer available.", "error")
        return redirect(url_for("dashboard.lead_detail", lead_id=lead.id))
    try:
        booking_service.book_slot(slot=slot, lead=lead, staff=current_user)
        flash("Consultation booked.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard.lead_detail", lead_id=lead.id))


@dashboard_bp.route("/leads/<int:lead_id>/deposit", methods=["POST"])
@login_required
def mark_deposit(lead_id: int):
    lead = _lead_or_404(lead_id)
    booking_service.mark_deposit_paid(lead=lead, staff=current_user)
    flash("Deposit marked as paid.", "success")
    return redirect(url_for("dashboard.lead_detail", lead_id=lead.id))


@dashboard_bp.route("/leads/<int:lead_id>/attachments/<int:attachment_id>")
@login_required
def attachment_file(lead_id: int, attachment_id: int):
    lead = _lead_or_404(lead_id)
    attachment = Attachment.query.filter_by(id=attachment_id, lead_id=lead.id).first()
    if attachment is None:
        abort(404)
    if attachment.file_path.startswith("external-reference::"):
        return redirect(attachment.file_path.split("::", 1)[1])
    upload_root = Path(current_app.config["UPLOAD_DIR"])
    directory = (upload_root / attachment.file_path).parent
    filename = Path(attachment.file_path).name
    return send_from_directory(directory, filename)


# -- analytics ------------------------------------------------------------

@dashboard_bp.route("/analytics")
@login_required
def analytics():
    clinic = current_user.clinic
    return render_template(
        "analytics.html",
        response_times=metrics_service.response_time_breakdown(clinic),
        funnel=metrics_service.funnel(clinic),
        recovered=metrics_service.recovered_bookings(clinic),
    )


# -- availability -----------------------------------------------------------

@dashboard_bp.route("/availability", methods=["GET", "POST"])
@login_required
def availability():
    clinic = current_user.clinic

    if request.method == "POST":
        if not current_user.is_admin:
            abort(403)
        try:
            # <input type=datetime-local> submits the time the staff member
            # sees on screen, i.e. clinic-local -- convert to naive UTC
            # before storing (every DateTime column in this app is UTC).
            start = from_clinic_local(dt.datetime.fromisoformat(request.form.get("start_time", "")), clinic.timezone)
            end = from_clinic_local(dt.datetime.fromisoformat(request.form.get("end_time", "")), clinic.timezone)
        except ValueError:
            flash("Invalid date/time.", "error")
            return redirect(url_for("dashboard.availability"))
        booking_service.create_slots(clinic, [(start, end, request.form.get("label") or None)])
        flash("Slot added.", "success")
        return redirect(url_for("dashboard.availability"))

    slots = (
        AvailabilitySlot.query.filter_by(clinic_id=clinic.id)
        .order_by(AvailabilitySlot.start_time.asc())
        .all()
    )
    return render_template("availability.html", slots=slots)
