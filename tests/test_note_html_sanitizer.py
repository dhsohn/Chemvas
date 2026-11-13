from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from chemvas.features.annotations import MAX_NOTE_HTML_CHARS, sanitize_note_html


@pytest.fixture(scope="module")
def qt_application():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _plain_text_after_sanitize_roundtrip(html: str) -> str:
    source = QTextDocument()
    source.setHtml(html)
    expected = source.toPlainText()
    sanitized = sanitize_note_html(source.toHtml())
    assert sanitized is not None
    restored = QTextDocument()
    restored.setHtml(sanitized)
    assert restored.toPlainText() == expected
    assert sanitize_note_html(sanitized) == sanitized
    return expected


def test_sanitize_note_html_preserves_safe_qt_text_styles_and_drops_css_resources() -> (
    None
):
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
    assert "margin-top:0px" in sanitized


def test_sanitize_note_html_drops_unsafe_style_values_and_oversized_html() -> None:
    html = '<span style="font-size:expression(alert(1)); color:#abcdef; vertical-align:sub">x</span>'

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    assert "expression" not in sanitized
    assert "font-size" not in sanitized
    assert "color:#abcdef" in sanitized
    assert "vertical-align:sub" in sanitized
    assert sanitize_note_html("<p>" + ("x" * MAX_NOTE_HTML_CHARS)) is None


def test_sanitize_note_html_keeps_safe_body_subset() -> None:
    html = (
        "<p><b>B</b><strong>S</strong><i>I</i><em>E</em><u>U</u><sub>2</sub><sup>+</sup><br>"
        '<span style="color:#123456; background-color:rgb(10, 20, 30)">S</span></p>'
    )

    sanitized = sanitize_note_html(html)

    assert sanitized == (
        '<p style="white-space:pre-wrap"><b>B</b><strong>S</strong><i>I</i><em>E</em><u>U</u><sub>2</sub><sup>+</sup><br>'
        '<span style="color:#123456; background-color:rgb(10, 20, 30)">S</span></p>'
    )


def test_sanitize_note_html_preserves_legacy_note_formatting_without_document_wrappers() -> (
    None
):
    html = (
        "<html><head>"
        '<meta name="qrichtext" content="1"><title>drop me</title>'
        "<style>p { color: red; }</style>"
        "</head>"
        '<body content="body-content" style="color:#111111">'
        '<div align="CENTER" style="background-color:#ffeeaa; background-image:url(file:///tmp/bg)">'
        '<blockquote style="margin-left:40px; color:rgb(12, 34, 56)">'
        '<p align="RIGHT" class="unused" data-note="x">'
        'Safe <font color="red" face="Courier New" size="4">font</font> '
        "<span style=\"font-family:'Courier New'; font-size:12pt; font-weight:700; "
        "font-style:italic; line-height:125%; text-decoration:underline; color:#abcdef; background-color:lightblue; "
        'vertical-align:super; white-space:pre-wrap">span</span>'
        '</p><ul type="disc"><li value="2">one</li></ul><ol type="A" start="2"><li type="i">two</li></ol>'
        "</blockquote></div></body></html>"
    )

    sanitized = sanitize_note_html(html)

    assert sanitized is not None
    lowered = sanitized.lower()
    assert "<html" not in lowered
    assert "<head" not in lowered
    assert "<body" not in lowered
    assert "<meta" not in lowered
    assert "<style" not in lowered
    assert "content=" not in lowered
    assert "drop me" not in sanitized
    assert "p { color: red; }" not in sanitized
    assert "Safe " in sanitized
    assert '<div align="center" style="background-color:#ffeeaa">' in sanitized
    assert '<blockquote style="margin-left:40px; color:rgb(12, 34, 56)">' in sanitized
    assert '<font color="red" face="Courier New" size="4">font</font>' in sanitized
    assert '<p align="right" style="white-space:pre-wrap">' in sanitized
    assert "font-family:&#x27;Courier New&#x27;" in sanitized
    assert "font-size:12pt" in sanitized
    assert "font-weight:700" in sanitized
    assert "font-style:italic" in sanitized
    assert "line-height:125%" in sanitized
    assert "text-decoration:underline" in sanitized
    assert "color:#abcdef" in sanitized
    assert "background-color:lightblue" in sanitized
    assert "vertical-align:super" in sanitized
    assert (
        '<ul type="disc"><li value="2" style="white-space:pre-wrap">one</li></ul>'
        in sanitized
    )
    assert (
        '<ol type="A" start="2"><li type="i" style="white-space:pre-wrap">two</li></ol>'
        in sanitized
    )
    assert "background-image" not in sanitized
    assert "url(" not in sanitized
    assert sanitized.count("white-space:pre-wrap") == 3
    assert sanitize_note_html(sanitized) == sanitized


def test_whitespace_policy_is_fixed_not_untrusted_css():
    html = '<p style="white-space:nowrap; color:red; white-space:url(file:///x)">  a   b  </p>'
    sanitized = sanitize_note_html(html)
    assert sanitized == '<p style="color:red; white-space:pre-wrap">  a   b  </p>'
    assert sanitize_note_html(sanitized) == sanitized


def test_empty_paragraph_marker_accepts_only_the_qt_empty_value():
    sanitized = sanitize_note_html(
        '<p style="-qt-paragraph-type:empty; -qt-block-indent:7"><br></p>'
        '<p style="-qt-paragraph-type:other; -qt-paragraph-type:url(file:///x)">x</p>'
    )
    assert sanitized == (
        '<p style="-qt-paragraph-type:empty; white-space:pre-wrap"><br></p>'
        '<p style="white-space:pre-wrap">x</p>'
    )
    assert sanitize_note_html(sanitized) == sanitized


@pytest.mark.parametrize("size", ["5.123456789px", "10.499999px", "1000.0px"])
def test_fractional_native_pixel_sizes_survive_repeated_sanitizing(size):
    html = f'<span style="font-size:{size};color:#123456">size</span>'
    sanitized = sanitize_note_html(html)
    assert f"font-size:{size}" in sanitized
    assert sanitize_note_html(sanitized) == sanitized


@pytest.mark.parametrize(
    "size", ["1000.1px", "1001px", "1e9px", "nanpx", "infpx", "-5.123px", "5px url(x)"]
)
def test_native_pixel_size_extension_still_rejects_invalid_values(size):
    html = f'<span style="font-size:{size};color:#123456">size</span>'
    assert sanitize_note_html(html) == '<span style="color:#123456">size</span>'


@pytest.mark.parametrize(
    "html",
    [
        "<h1>A</h1><h1>B</h1>",
        "<pre>A  x</pre><pre>B</pre>",
        "<pre>A  x\nB</pre>",
        "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>",
        '<table><tr><td colspan="2">AB</td></tr><tr><td>C</td><td>D</td></tr></table>',
        '<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>',
        '<h2 style="margin-left:0px">A  y</h2><h2>B</h2>',
    ],
)
def test_sanitize_note_html_roundtrip_matches_qt_plain_text(qt_application, html):
    _plain_text_after_sanitize_roundtrip(html)


def test_sanitize_note_html_strips_hostile_table_attributes():
    html = (
        '<table border="1" cellpadding="3" onclick="x" background="file:///tmp/x">'
        '<tr style="url(file:///x)">'
        '<td background="file:///tmp/x" onclick="x" colspan="2 onmouseover" rowspan="99999">x</td>'
        "</tr></table>"
    )
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "onclick" not in sanitized
    assert "background" not in sanitized
    assert "url(" not in sanitized
    assert "colspan" not in sanitized
    assert "rowspan" not in sanitized
    assert sanitized.startswith("<table")
    assert "<tr>" in sanitized
    assert "<td>" in sanitized


def test_sanitize_note_html_drops_unsafe_heading_and_pre_styles():
    sanitized = sanitize_note_html('<h1 style="url(file:///x); color:red">T</h1>')
    assert sanitized is not None
    assert "url(" not in sanitized
    assert "color:red" in sanitized
    assert "white-space:pre-wrap" in sanitized

    sanitized_pre = sanitize_note_html('<pre style="white-space:normal">  A</pre>')
    assert sanitized_pre == "<pre>  A</pre>"
    assert "white-space" not in sanitized_pre


def _nested_table_html(*, wide: int, extra_rows: int) -> str:
    wide_row = "".join(f"<td>c{c}</td>" for c in range(wide))
    narrow_rows = "".join("<tr><td>x</td></tr>" for _ in range(extra_rows))
    return f"<table><tr>{wide_row}</tr>{narrow_rows}</table>"


def test_sanitize_note_html_keeps_table_at_exact_grid_budget() -> None:
    cols = 100
    rows = 100
    html = (
        "<table>"
        + "".join(
            "<tr>" + "".join("<td>x</td>" for _ in range(cols)) + "</tr>"
            for _ in range(rows)
        )
        + "</table>"
    )
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" in sanitized
    assert sanitized.count("<td>") == cols * rows


def test_sanitize_note_html_keeps_table_below_grid_budget() -> None:
    cols = 100
    rows = 99
    html = (
        "<table>"
        + "".join(
            "<tr>" + "".join("<td>x</td>" for _ in range(cols)) + "</tr>"
            for _ in range(rows)
        )
        + "</table>"
    )
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" in sanitized
    assert sanitized.count("<tr>") == rows


def test_sanitize_note_html_flattens_oversized_ragged_table_but_keeps_text() -> None:
    html = _nested_table_html(wide=101, extra_rows=99)
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "c0" in sanitized
    assert "x" in sanitized
    assert sanitize_note_html(sanitized) == sanitized


def test_sanitize_note_html_flattens_oversized_colspan_grid() -> None:
    html = (
        "<table>"
        + "".join('<tr><td colspan="100">x</td></tr>' for _ in range(101))
        + "</table>"
    )
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "x" in sanitized


def test_sanitize_note_html_nested_tables_aggregate_grid_budget() -> None:
    inner_rows = "".join(
        "<tr>" + "".join("<td>i</td>" for _ in range(100)) + "</tr>" for _ in range(100)
    )
    inner = f"<table>{inner_rows}</table>"
    html = f"<table><tr><td>{inner}</td></tr><tr><td>o</td></tr></table>"
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "i" in sanitized
    assert "o" in sanitized


def test_sanitize_note_html_table_fallback_retains_inline_formatting() -> None:
    html = _nested_table_html(wide=101, extra_rows=99).replace(
        "<td>c0</td>", "<td><b>c0</b></td>", 1
    )
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "<b>c0</b>" in sanitized


def test_sanitize_note_html_flattens_unclosed_oversized_fragment() -> None:
    wide = "".join("<td>x</td>" for _ in range(101))
    narrow = "".join("<tr><td>y</td></tr>" for _ in range(99))
    html = f"<table><tr>{wide}</tr>{narrow}"
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "x" in sanitized
    assert "y" in sanitized


def test_sanitize_note_html_deduplicates_duplicate_span_attrs_on_output() -> None:
    html = '<table><tr><td colspan="2" colspan="9999">x</td></tr></table>'
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert 'colspan="2"' in sanitized
    assert "9999" not in sanitized


def test_sanitize_note_html_rejects_non_ascii_colspan_digits() -> None:
    html = '<table><tr><td colspan="٢">x</td></tr></table>'
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "colspan" not in sanitized
    assert "<table" in sanitized


def test_sanitize_note_html_preserves_rowspan_in_bounded_table() -> None:
    html = '<table><tr><td rowspan="2">A</td><td>B</td></tr><tr><td>C</td></tr></table>'
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert 'rowspan="2"' in sanitized


def test_sanitize_note_html_orphan_table_cells_are_flattened() -> None:
    html = "<td>x</td><table><tr><td>y</td></tr></table>"
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "<table" not in sanitized
    assert "x" in sanitized
    assert "y" in sanitized


def _assert_flattened(html: str, *texts: str) -> None:
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert not any(f"<{tag}" in sanitized for tag in ("table", "tr", "td", "th"))
    for text in texts:
        assert text in sanitized


def test_orphan_rows_without_table_tag_count_toward_budget() -> None:
    wide = "".join("<td>x</td>" for _ in range(101))
    narrow = "".join("<tr><td>y</td></tr>" for _ in range(99))
    _assert_flattened(f"<tr>{wide}</tr>{narrow}", "x", "y")


def test_implicitly_closed_inner_table_counts_rows_in_outer_table() -> None:
    wide = "".join("<td>x</td>" for _ in range(101))
    narrow = "".join("<tr><td>y</td></tr>" for _ in range(99))
    inner = "<td><table><tr><td>i</td></tr></td></tr>"
    _assert_flattened(f"<table><tr>{wide}{inner}{narrow}</table>", "x", "y", "i")


def test_rowspan_occupancy_widens_later_rows_past_budget() -> None:
    first = "".join('<td rowspan="100">r</td>' for _ in range(100))
    rest = "".join("<tr><td>y</td></tr>" for _ in range(99))
    _assert_flattened(f"<table><tr>{first}</tr>{rest}</table>", "r", "y")


def test_one_slot_over_budget_flattens() -> None:
    row = "<tr>" + "<td>x</td>" * 137 + "</tr>"
    _assert_flattened("<table>" + row * 73 + "</table>", "x")


def test_cell_overlapping_rowspan_uses_qt_column_skip() -> None:
    first = '<tr><td>a</td><td colspan="71" rowspan="71">x</td></tr>'
    rest = '<tr><td colspan="71">b</td><td>c</td></tr>' * 70
    _assert_flattened(f"<table>{first}{rest}</table>", "a", "b", "c")


def _nested_paragraph_ragged_table_html() -> str:
    wide = "".join(f"<td>c{c}</td>" for c in range(101))
    narrow = "".join("<tr><td>x</td></tr>" for _ in range(99))
    return (
        f"<table><tr>{wide}<td><p>"
        f"<table><tr><p>x</p></tr>{narrow}</table>"
        f"</p></td></tr></table>"
    )


def test_nested_paragraph_in_table_markup_flattens_and_keeps_cell_text() -> None:
    _assert_flattened(_nested_paragraph_ragged_table_html(), "c0", "x")


def _fifty_by_hundred_table(*, close: bool = True) -> str:
    body = "".join(
        "<tr>" + "".join("<td>x</td>" for _ in range(100)) + "</tr>" for _ in range(50)
    )
    if close:
        return f"<table>{body}</table>"
    return f"<table>{body}"


@pytest.mark.parametrize("close_second", [True, False])
def test_sibling_tables_at_exact_aggregate_budget_preserve_both(
    close_second: bool,
) -> None:
    html = _fifty_by_hundred_table() + _fifty_by_hundred_table(close=close_second)
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert sanitized.count("<table") == 2
    assert sanitized.count("<td>") == 10_000
    assert "x" in sanitized
    assert sanitize_note_html(sanitized) == sanitized


def test_sibling_table_one_slot_over_aggregate_budget_flattens() -> None:
    half = _fifty_by_hundred_table()
    over = '<table><tr><td colspan="5001">z</td></tr></table>'
    _assert_flattened(half + over, "x", "z")


def test_heading_whitespace_behavior_after_sanitize_roundtrip(qt_application) -> None:
    html = '<h1 style="white-space:pre-wrap">A   b</h1>'
    sanitized = sanitize_note_html(html)
    assert sanitized is not None
    assert "white-space:pre-wrap" in sanitized
    document = QTextDocument()
    document.setHtml(sanitized)
    assert document.toPlainText() == "A   b"
    roundtrip = sanitize_note_html(document.toHtml())
    assert roundtrip is not None
    assert "white-space:pre-wrap" in roundtrip
    restored = QTextDocument()
    restored.setHtml(roundtrip)
    assert restored.toPlainText() == "A   b"
