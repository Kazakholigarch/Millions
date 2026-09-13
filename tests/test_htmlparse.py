"""Stdlib HTML extraction, including the malformed markup real sites serve."""
from __future__ import annotations

from engine.htmlparse import detect_analytics, parse

BASE = "https://acme.com/"


def test_extracts_head_metadata():
    doc = parse(
        '<html lang="en-GB"><head><meta charset="utf-8">'
        "<title>Acme Plumbing</title>"
        '<meta name="description" content="We fix pipes">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="canonical" href="/home"></head><body></body></html>',
        BASE,
    )
    assert doc.title == "Acme Plumbing"
    assert doc.meta_description == "We fix pipes"
    assert doc.viewport.startswith("width=device-width")
    assert doc.canonical == "https://acme.com/home"  # resolved against the base
    assert doc.lang == "en-GB"
    assert doc.charset == "utf-8"


def test_relative_urls_resolve_against_the_page():
    doc = parse('<body><img src="../img/a.png"><a href="/x">x</a></body>', "https://acme.com/a/b/")
    assert doc.images[0].src == "https://acme.com/a/img/a.png"
    assert doc.links == ["https://acme.com/x"]


def test_javascript_and_data_urls_are_skipped():
    doc = parse('<body><a href="javascript:void(0)">x</a><img src="data:image/png;base64,AA"></body>', BASE)
    assert doc.links == []
    assert doc.images == []


def test_distinguishes_missing_alt_from_empty_alt():
    """alt="" is a deliberate decorative marker; a missing alt is a defect."""
    doc = parse('<body><img src="/a.png"><img src="/b.png" alt=""><img src="/c.png" alt="Hi"></body>', BASE)
    assert doc.images[0].alt is None
    assert doc.images[1].alt == ""
    assert len(doc.images_missing_alt) == 2  # absent and empty both count


def test_render_blocking_is_only_head_scripts_without_async_or_defer():
    doc = parse(
        "<head>"
        '<script src="/blocking.js"></script>'
        '<script src="/async.js" async></script>'
        '<script src="/defer.js" defer></script>'
        '<script src="/mod.js" type="module"></script>'
        '<script type="application/ld+json">{"@type":"Thing"}</script>'
        "<script>var inline = 1;</script>"
        '</head><body><script src="/body.js"></script></body>',
        BASE,
    )
    assert [s.src for s in doc.render_blocking_scripts] == ["https://acme.com/blocking.js"]


def test_json_ld_types_are_collected_including_nested():
    doc = parse(
        '<script type="application/ld+json">'
        '{"@type":"LocalBusiness","department":{"@type":"Store"}}</script>',
        BASE,
    )
    assert set(doc.jsonld_types) == {"LocalBusiness", "Store"}


def test_malformed_json_ld_does_not_raise():
    assert parse('<script type="application/ld+json">{not json</script>', BASE).jsonld_types == []


def test_mixed_content_only_flagged_on_https_pages():
    markup = '<body><img src="http://cdn.example/a.png"></body>'
    assert parse(markup, "https://acme.com/").insecure_resources == ["http://cdn.example/a.png"]
    assert parse(markup, "http://acme.com/").insecure_resources == []


def test_internal_and_external_links_are_separated():
    doc = parse('<body><a href="/a">a</a><a href="https://other.com/b">b</a></body>', BASE)
    assert doc.internal_links == ["https://acme.com/a"]
    assert doc.external_links == ["https://other.com/b"]


def test_forms_and_lead_capture_detection():
    doc = parse(
        '<body><form action="/go" method="post"><input type="email"><textarea></textarea></form>'
        '<form><input type="search"></form></body>',
        BASE,
    )
    assert len(doc.forms) == 2
    assert doc.forms[0].looks_like_lead_capture
    assert not doc.forms[1].looks_like_lead_capture


def test_unclosed_form_is_still_captured():
    """Real sites ship unclosed tags; a dropped form is a false finding."""
    doc = parse('<body><form action="/go"><input type="email"></body>', BASE)
    assert len(doc.forms) == 1


def test_script_and_style_contents_are_not_page_text():
    doc = parse(
        "<body><style>body{color:red}</style><script>var x='hello';</script>"
        "<p>Real visible words here</p></body>",
        BASE,
    )
    assert "color" not in doc.text
    assert "var x" not in doc.text
    assert "Real visible words here" in doc.text


def test_contact_details_extracted_from_text():
    doc = parse("<body><p>Call 555-123-4567 or email hi@acme.com</p></body>", BASE)
    assert doc.emails == ["hi@acme.com"]
    assert doc.phones


def test_analytics_detected_by_src_and_by_inline_code():
    by_src = parse('<head><script src="https://plausible.io/js/script.js"></script></head>', BASE)
    assert "Plausible" in detect_analytics(by_src)

    inline = parse("<head><script>window.dataLayer=[];gtag('js',new Date());</script></head>", BASE)
    assert "Google Analytics / GTM" in detect_analytics(inline)

    assert detect_analytics(parse("<body>nothing</body>", BASE)) == []


def test_self_closing_and_void_tags_are_handled():
    doc = parse('<body><img src="/a.png" alt="a" /><br/><hr/><p>text</p></body>', BASE)
    assert len(doc.images) == 1


def test_garbage_input_does_not_raise():
    for garbage in ("", "<<<>>>", "<html><body><p>unclosed", "\x00\x01binary"):
        assert parse(garbage, BASE) is not None


def test_favicon_detected_from_any_icon_rel():
    for rel in ("icon", "shortcut icon", "apple-touch-icon"):
        assert parse(f'<head><link rel="{rel}" href="/f.ico"></head>', BASE).has_favicon
    assert not parse('<head><link rel="stylesheet" href="/a.css"></head>', BASE).has_favicon
