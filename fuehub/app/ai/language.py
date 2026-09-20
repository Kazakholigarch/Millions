from __future__ import annotations

import re

from app.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

try:
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0  # deterministic results
    _LANGDETECT_AVAILABLE = True
except ImportError:  # pragma: no cover - langdetect is a declared dependency
    _LANGDETECT_AVAILABLE = False

_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_GERMAN_CHARS_RE = re.compile(r"[äöüßÄÖÜ]")
_GERMAN_MARKERS_RE = re.compile(
    r"\b(ich|und|nicht|haare|haartransplantation|wie ?viel|möchte|kosten|kostet|"
    r"transplantat|brauche|tage|guten tag|hallo|preis)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Best-effort ISO 639-1 code, restricted to the clinic's supported set.

    Unicode script is checked first: it's unambiguous even on very short
    messages ("Fiyat?", "Kac greft?"), where a statistical detector like
    langdetect is unreliable. German is caught next via umlauts/common
    words for the same reason. Only after those do we fall back to
    langdetect, and only for messages long enough for it to be meaningful.
    Anything we don't recognize (or don't have templates for) falls back to
    the clinic's default language rather than guessing.
    """
    if not text or not text.strip():
        return DEFAULT_LANGUAGE

    if _ARABIC_RE.search(text):
        return "ar"
    if _CYRILLIC_RE.search(text):
        return "ru"
    if _GERMAN_CHARS_RE.search(text) or _GERMAN_MARKERS_RE.search(text):
        return "de"

    if _LANGDETECT_AVAILABLE and len(text.strip()) >= 8:
        try:
            code = detect(text)
        except LangDetectException:
            code = None
        if code in SUPPORTED_LANGUAGES:
            return code

    return DEFAULT_LANGUAGE
