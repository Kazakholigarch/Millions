from __future__ import annotations

import re

"""PII redaction applied to message text before it goes anywhere near the
third-party AI API (see app/ai/draft.py). This is a deliberately narrow,
regex-based pass -- not full NER/anonymization -- because the drafting
prompt never needs contact details in the first place: cost ranges,
FUE vs DHI, package contents, stay length and consultation info don't
require knowing who's asking. The service layer also simply never passes
lead.contact_name/phone/email/handle into the AI prompt at all; this
module only mops up identifiers that show up inline in the free-text
message body itself.
"""

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://\S+")
_HANDLE_RE = re.compile(r"(?<!\w)@[A-Za-z0-9_.]{2,}")
# 8+ digits (allowing separators) with an optional leading +, not immediately
# preceded/followed by another word character -- catches phone numbers in
# most written formats without eating ordinary numbers like "3000 grafts".
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\-.\s()]{6,}\d)(?!\w)")
_NAME_INTRO_RE = re.compile(
    r"(my name is|i am|i'm|ich heiße|ich bin|meine name ist|"
    r"меня зовут|"
    r"اسمي)\s+"
    r"([A-Za-zÀ-ÿЀ-ӿ؀-ۿ]{2,30})",
    re.IGNORECASE,
)


def _looks_like_phone(match: re.Match) -> bool:
    digits = re.sub(r"\D", "", match.group(0))
    return len(digits) >= 7


def redact_pii(text: str) -> str:
    """Return `text` with emails, URLs, @handles, phone-like digit runs and
    self-introduced names replaced by placeholders. Safe to call on empty
    strings."""
    if not text:
        return text

    redacted = _EMAIL_RE.sub("[email]", text)
    redacted = _URL_RE.sub("[link]", redacted)
    redacted = _HANDLE_RE.sub("[handle]", redacted)
    redacted = _PHONE_RE.sub(lambda m: "[phone]" if _looks_like_phone(m) else m.group(0), redacted)
    redacted = _NAME_INTRO_RE.sub(lambda m: f"{m.group(1)} [name]", redacted)
    return redacted
