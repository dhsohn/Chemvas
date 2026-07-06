from __future__ import annotations

from ui.note_html_sanitizer import MAX_NOTE_HTML_CHARS, sanitize_note_html


def test_sanitize_note_html_preserves_safe_qt_text_styles_and_drops_css_resources() -> None:
    html = (
        '<p style="font-size:12pt; vertical-align:super; background-image:url(file:///tmp/x); '
        'color:#123456; -qt-block-indent:0; margin-top:0px">x</p>'
    )

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    assert "font-size:12pt" in sanitized
    assert "vertical-align:super" in sanitized
    assert "color:#123456" in sanitized
    assert "background-image" not in sanitized
    assert "url(" not in sanitized
    assert "file:" not in sanitized
    assert "-qt-block-indent" not in sanitized
    assert "margin-top" not in sanitized


def test_sanitize_note_html_drops_unsafe_style_values_and_oversized_html() -> None:
    html = '<span style="font-size:expression(alert(1)); color:#abcdef; vertical-align:sub">x</span>'

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    assert "expression" not in sanitized
    assert "font-size" not in sanitized
    assert "color:#abcdef" in sanitized
    assert "vertical-align:sub" in sanitized
    assert sanitize_note_html("<p>" + ("x" * MAX_NOTE_HTML_CHARS)) is None


def test_sanitize_note_html_keeps_narrow_body_subset() -> None:
    html = '<p><b>B</b><i>I</i><sub>2</sub><sup>+</sup><br><span style="color:#123456">S</span></p>'

    sanitized = sanitize_note_html(html)

    assert sanitized == (
        '<p><b>B</b><i>I</i><sub>2</sub><sup>+</sup><br>'
        '<span style="color:#123456">S</span></p>'
    )


def test_sanitize_note_html_strips_document_and_legacy_font_markup() -> None:
    html = (
        "<html><head>"
        '<meta name="qrichtext" content="1"><title>drop me</title>'
        "<style>p { color: red; }</style>"
        "</head>"
        '<body content="body-content" style="color:#111111">'
        '<p align="RIGHT" class="unused" data-note="x">'
        'Safe <font color="red" face="Courier New" size="4">font</font> '
        '<span style="font-family:\'Courier New\'; font-size:12pt; font-weight:700; '
        'font-style:italic; line-height:125%; text-decoration:underline; color:#abcdef; '
        'vertical-align:super; white-space:pre-wrap">span</span>'
        "</p></body></html>"
    )

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    lowered = sanitized.lower()
    assert "<html" not in lowered
    assert "<head" not in lowered
    assert "<body" not in lowered
    assert "<meta" not in lowered
    assert "<font" not in lowered
    assert "<style" not in lowered
    assert "content=" not in lowered
    assert "drop me" not in sanitized
    assert "p { color: red; }" not in sanitized
    assert "Safe font" in sanitized
    assert '<p align="right">' in sanitized
    assert "font-family:&#x27;Courier New&#x27;" in sanitized
    assert "font-size:12pt" in sanitized
    assert "font-weight:700" in sanitized
    assert "font-style:italic" in sanitized
    assert "line-height:125%" in sanitized
    assert "text-decoration:underline" in sanitized
    assert "color:#abcdef" in sanitized
    assert "vertical-align:super" in sanitized
    assert "white-space" not in sanitized
