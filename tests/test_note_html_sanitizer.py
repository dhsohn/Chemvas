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


def test_sanitize_note_html_drops_unsafe_style_values_and_oversized_html() -> None:
    html = '<span style="font-size:expression(alert(1)); color:#abcdef; vertical-align:sub">x</span>'

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    assert "expression" not in sanitized
    assert "font-size" not in sanitized
    assert "color:#abcdef" in sanitized
    assert "vertical-align:sub" in sanitized
    assert sanitize_note_html("<p>" + ("x" * MAX_NOTE_HTML_CHARS)) is None
