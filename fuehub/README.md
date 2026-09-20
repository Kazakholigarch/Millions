# FueHub Front Desk

A live, always-on front desk for a hair transplant clinic. Every inbound
enquiry -- website contact form, email, WhatsApp, Instagram DM -- lands in
one `Lead` record instead of four separate inboxes, gets an instant
acknowledgment in the enquirer's own language, and a draft FAQ reply
grounded in the clinic's own facts waits in an approve/edit queue for
staff. Clinical questions and photos are routed to a human, never
auto-answered. A capped follow-up sequence (day 2, day 6) recovers leads
that go quiet. A staff dashboard shows response time, the funnel, and how
many bookings the follow-up sequence recovered.

Built first for one clinic (seeded as "FueHub Hair Clinic"), with the data
model already scoped by `clinic_id` throughout so a second clinic is a new
row, not a rewrite.

## Quickstart

```bash
cd fuehub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python seed.py     # demo clinic + staff login + sample leads across every channel/language
python run.py       # http://localhost:5001
```

Log in with the credentials `seed.py` prints (`admin@fuehub.example` /
`changeme123`).

Run the tests: `pytest` (from the `fuehub/` directory).

## What's real vs. simulated by default

Nothing here requires an API key to run -- every external integration has
a safe, credential-free default, and switches to the real thing the moment
you configure it (see `.env.example`):

| Piece | Default | Real, when configured |
|---|---|---|
| AI drafting/translation | `FakeAIClient` -- deterministic, offline, template-based, grounded in the clinic's `knowledge_base` | `FUEHUB_AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` -> real Claude drafting |
| WhatsApp sending | Logged, not sent | `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN`/`TWILIO_WHATSAPP_FROM` -> real Twilio WhatsApp API |
| Instagram DM sending | Logged, not sent | `META_PAGE_ACCESS_TOKEN` -> real Meta Graph API |
| Outbound email | Logged, not sent | `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM` -> real SMTP |
| Calendar | A real internal `AvailabilitySlot` table, managed by staff on the Availability page | not Google/Outlook Calendar -- see below |

Webhook **receiving** is real regardless of send credentials: `/webhooks/<clinic_slug>/{website,email,whatsapp,instagram}`
parse the actual payload shapes those providers send (Twilio form-encoded,
Meta's Messaging webhook JSON, a Mailgun/SendGrid-style inbound-parse
JSON), including Twilio's request-signature check and Meta's
subscription handshake + `X-Hub-Signature-256` check when the matching
secrets are set.

**Calendar** is an internal slot table, not a Google/Outlook sync --
staff add slots on the Availability page (or `booking_service.create_slots`).
The booking flow (`list_upcoming_slots` / `book_slot`) only depends on that
table, so wiring in a real calendar provider later means implementing the
same two functions against that API; nothing else changes.

## How an enquiry flows through the system

1. A webhook (or the website form route) receives a message and normalizes
   it into a common `InboundMessage` shape (`app/channels/base.py`).
2. `lead_service.ingest_inbound` dedupes by `(clinic, channel, external_id)`,
   creates or updates the `Lead`, stores any photos as `Attachment`s, and
   detects language (Unicode script + marker words first, `langdetect` as a
   fallback for longer Latin-script text -- reliable even on very short
   messages like "Fiyat?").
3. **First contact only:** an instant, pre-translated acknowledgment sends
   immediately in the enquirer's language (`app/ai/templates.py` --
   currently English/German/Arabic/Russian; add a language by adding one
   dict entry).
4. The message is scored for urgency (`app/scoring/urgency.py`: budget
   mentioned, a specific date, urgency language, photos, graft/cost
   interest) so hot leads sort to the top of the queue.
5. `app/ai/escalation.py` checks the message against a clinical-keyword
   list (medical history, medication, candidacy, health conditions...) in
   all four languages. A match routes straight to a "needs clinician" queue
   item with **no** AI draft. Otherwise, `app/ai/draft.py` redacts PII
   (`app/ai/redact.py`) and asks the configured AI client for a reply --
   restricted to cost ranges, FUE vs. DHI, package contents, stay length,
   and the free consultation (with real open slots offered when relevant).
   Either way, a photo sets `Lead.requires_clinical_review` so a human
   looks at it -- the AI is instructed never to comment on a photo's
   clinical content, only to acknowledge it.
6. Every draft (and every clinician-flagged item) waits in the queue at
   `/` until a staff member approves, edits, or discards it. Nothing sends
   itself.
7. If a lead goes quiet after staff replies, `followup_service` (run on a
   background scheduler tick) sends one nudge at day 2 and a second at day
   6, then stops for good -- the "quiet" clock is anchored to the
   enquirer's last message so it doesn't reset if staff sends more than
   one nudge.
8. The Analytics page reads straight off monotonic milestone timestamps on
   `Lead` (`first_response_at`, `consultation_booked_at`,
   `deposit_paid_at`) -- not the mutable `status` field -- so funnel counts
   never move backwards.

## Data minimization & access control

- `Lead` stores only what's needed to run the conversation: contact info,
  channel, language, first message, photo references, timestamps, status.
  No marketing profile, no history-of-every-field-change audit trail on
  the lead itself.
- Webhook handlers normalize into `InboundMessage` and never persist the
  provider's raw payload -- only the fields the app actually uses.
- Before any message content reaches the AI client, `app/ai/redact.py`
  strips emails, phone numbers, URLs, @handles, and self-introduced names,
  and the service layer never passes `contact_name`/`phone`/`email` into
  the AI prompt in the first place -- the drafting prompt doesn't need to
  know who's asking to answer "how much for 3000 grafts?".
- Photos are never sent to the AI at all; they're stored under
  `instance/uploads/<clinic>/<lead>/` and served only through a
  login-gated, clinic-scoped route.
- The dashboard is entirely behind `flask-login`, every query is scoped to
  `current_user.clinic_id` (so one clinic's staff can never reach another
  clinic's data even by guessing an id), every POST is CSRF-checked, and
  every approve/edit/send/book/deposit action is written to `AuditLog`
  with the staff member who did it.

## Multi-clinic extension point

Every table is scoped by `clinic_id`. Clinic-specific content -- the FAQ
knowledge base (prices, technique descriptions, package contents, stay
length, consultation details, each translated per language), supported
languages, timezone, and per-channel credentials -- lives on the `Clinic`
row, not in code. Onboarding a second clinic is: insert a `Clinic` row,
fill in its `knowledge_base` and `channel_config`, create its first
`StaffUser`. No application code changes.

## Known simplifications (by design, for an MVP)

- `db.create_all()` on startup, not Alembic migrations -- fine until the
  schema needs to evolve under live data.
- The scheduler (`APScheduler`, in-process) runs the follow-up tick
  in-process with the web server -- a real production deployment would
  split that into its own worker process.
- The offline "fake" AI provider quotes whatever's in `knowledge_base`
  verbatim; if a clinic customizes a free-text field without adding all
  four language variants, the fake provider will phrase the *sentence*
  around it in the target language but the *fact itself* stays in
  whichever language it was entered in. The real Claude provider
  translates on the fly and doesn't have this limitation.
- Media URLs from WhatsApp webhooks need Twilio Basic Auth to fetch, which
  `get_media_download_headers` adds automatically once Twilio credentials
  are configured (Instagram's attachment URLs are pre-signed and need no
  extra header). Either way, if the download fails for any reason -- no
  credentials, no network access -- the attachment falls back to storing
  the reference URL, so the signal ("they sent a photo") is never lost
  even when the bytes can't be pulled down.
