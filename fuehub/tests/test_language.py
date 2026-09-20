from app.ai.language import detect_language


def test_detects_arabic_by_script():
    assert detect_language("مرحباً، كم تكلفة زراعة الشعر؟") == "ar"


def test_detects_russian_by_script():
    assert detect_language("Здравствуйте, сколько стоит пересадка волос?") == "ru"


def test_detects_german_via_umlaut():
    assert detect_language("Wie viel kostet eine Haartransplantation für 3000 Grafts?") == "de"


def test_detects_german_via_markers_without_umlaut():
    assert detect_language("Ich habe eine Frage zu den Kosten") == "de"


def test_defaults_to_english_for_english_text():
    assert detect_language("Hi, how much does a hair transplant cost?") == "en"


def test_empty_or_missing_text_defaults():
    assert detect_language("") == "en"
    assert detect_language(None) == "en"  # type: ignore[arg-type]


def test_short_ambiguous_text_falls_back_rather_than_guessing():
    # Too short for the statistical detector to be trusted, no script/marker
    # hits -- should fall back to the default rather than a wild guess.
    assert detect_language("Hi") == "en"
