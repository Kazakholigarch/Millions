from app.ai.redact import redact_pii


def test_redacts_email():
    result = redact_pii("Contact me at john.doe@example.com please")
    assert "[email]" in result
    assert "john.doe@example.com" not in result


def test_redacts_phone_number():
    result = redact_pii("Call me at +90 555 123 4567")
    assert "[phone]" in result
    assert "555 123 4567" not in result


def test_redacts_instagram_handle():
    result = redact_pii("find me @johnsmith123 on insta")
    assert "[handle]" in result
    assert "@johnsmith123" not in result


def test_redacts_self_introduced_name():
    result = redact_pii("Hi, my name is John and I want a consultation")
    assert "[name]" in result
    assert "John" not in result


def test_redacts_url():
    result = redact_pii("Here's my profile https://instagram.com/someone")
    assert "[link]" in result
    assert "instagram.com" not in result


def test_leaves_graft_counts_alone():
    # A 4-digit number shouldn't be swept up by the phone-number pattern.
    result = redact_pii("I need about 3000 grafts, maybe 3500")
    assert "3000 grafts" in result
    assert "3500" in result


def test_empty_string_is_safe():
    assert redact_pii("") == ""
