"""Native caption and atom colors share fgcolor-aware palette allocation."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtGui import QFont, QTextDocument
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_palette import allocate_native_color_index
from chemvas.ui.export.cdxml_document_writer import serialize_cdxml_document

pytestmark = pytest.mark.usefixtures("qt_application")

# Document foreground is palette index 2 (red). Absolute black must not be
# written as color 0, or the importer remaps it through fgcolor.
NATIVE = b"""<?xml version="1.0" encoding="UTF-8"?>
<CDXML fgcolor="2" bgcolor="3" LabelFont="3" LabelSize="10" CaptionFont="3" CaptionSize="10" BondLength="20">
<fonttable><font id="3" name="Arial" charset="utf-8"/></fonttable>
<colortable>
  <color r="1" g="0" b="0"/>
  <color r="1" g="1" b="1"/>
  <color r="0" g="0" b="0"/>
</colortable>
<page id="1" BoundingBox="0 0 400 300" bgcolor="3">
  <fragment id="2">
    <n id="3" p="50 60" Element="6" color="2"/>
    <n id="4" p="70 60" Element="8" color="2"><t p="70 60"><s font="3" size="10" face="96" color="2">O</s></t></n>
    <b id="5" B="3" E="4" Order="1" Display="Solid" color="2"/>
  </fragment>
  <t id="6" p="50 100" BoundingBox="50 90 140 112">
    <s font="3" size="10" face="0" color="2">Caption</s>
  </t>
</page>
</CDXML>
"""

RICH = (
    '<p style="margin-top:0;margin-bottom:0">'
    '<span style="font-family:Arial;font-size:10pt;color:#000000">Black</span>'
    '<span style="font-family:Arial;font-size:10pt;color:#ffffff">White</span>'
    '<span style="font-family:Arial;font-size:10pt;color:#00aa55">Green</span>'
    '<span style="font-family:Arial;font-size:10pt;color:#000000">Again</span>'
    "</p>"
)

EXPECTED_RICH_CHARS = [
    (character, color)
    for text, color in (
        ("Black", "#000000"),
        ("White", "#ffffff"),
        ("Green", "#00aa55"),
        ("Again", "#000000"),
    )
    for character in text
]
EXPECTED_GREEN_CHARS = [(character, "#00aa55") for character in "Green"]


def _strip_snapshot(raw: bytes) -> bytes:
    marker = b"\n<!-- ChemvasDocument:"
    assert marker in raw
    return raw[: raw.index(marker)]


def _atom_color(state, key: int | str = 0) -> str:
    atoms = state["model"]["atoms"]
    return atoms[key]["color"] if key in atoms else atoms[str(key)]["color"]


def _native_with_fgcolor(fgcolor: str | None) -> bytes:
    if fgcolor is None:
        return NATIVE.replace(b' fgcolor="2"', b"")
    return NATIVE.replace(b'fgcolor="2"', f'fgcolor="{fgcolor}"'.encode())


def _edited_state(fgcolor: str | None = "2"):
    state = parse_cdxml_document(
        _native_with_fgcolor(fgcolor), preserve_source=True
    ).state
    assert state["notes"][0]["text"] == "Caption"
    state["notes"][0]["text"] = "BlackWhiteGreenAgain"
    state["notes"][0]["html"] = RICH
    atoms = state["model"]["atoms"]
    atom = atoms[0] if 0 in atoms else atoms["0"]
    atom["color"] = "#000000"
    state["model"]["bonds"][0]["color"] = "#00aa55"
    return state


def _document_char_colors(html: str) -> list[tuple[str, str]]:
    """Inspect exact stored HTML; do not rewrite font-family for the reader."""
    document = QTextDocument()
    document.setHtml(html)
    return _char_colors_from_document(document)


def _char_colors_from_document(document: QTextDocument) -> list[tuple[str, str]]:
    observed: list[tuple[str, str]] = []
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                color = fragment.charFormat().foreground().color().name().lower()
                for character in fragment.text():
                    if character in {"\n", "\u2029"}:
                        continue
                    observed.append((character, color))
            iterator += 1
        block = block.next()
    return observed


def _canvas_note_char_colors(canvas) -> list[tuple[str, str]]:
    notes = list(canvas.runtime_state.note_items())
    assert notes
    return _char_colors_from_document(notes[0].document())


def _assert_projected_rich_colors(state) -> None:
    assert (
        _document_char_colors(state["notes"][0].get("html", "")) == EXPECTED_RICH_CHARS
    )
    assert _atom_color(state) == "#000000"
    assert state["model"]["bonds"][0]["color"] == "#00aa55"


def _serialize_edited(fgcolor: str | None) -> bytes:
    state = _edited_state(fgcolor)
    with offscreen_canvas(state, command="test-native-palette-text") as (
        canvas,
        service,
    ):
        saved = serialize_cdxml_document(canvas, service.snapshot_state())
        again = serialize_cdxml_document(canvas, service.snapshot_state())
    assert again == saved
    assert saved.count(b"<!-- ChemvasDocument:") == 1
    return saved


def _caption_native(family: str) -> bytes:
    # Font names travel as CDXML attribute text; XML escaping is separate from
    # the CSS/HTML quoting the importer must apply when projecting captions.
    # colortable index 2 is red (fgcolor); index 5 is absolute green.
    escaped = family.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<CDXML fgcolor="2" bgcolor="3" LabelFont="3" LabelSize="10" CaptionFont="3" CaptionSize="10" BondLength="20">
<fonttable><font id="3" name="{escaped}" charset="utf-8"/></fonttable>
<colortable>
  <color r="1" g="0" b="0"/>
  <color r="1" g="1" b="1"/>
  <color r="0" g="0" b="0"/>
  <color r="0" g="0.6666667" b="0.3333333"/>
</colortable>
<page id="1" BoundingBox="0 0 400 300" bgcolor="3">
  <t id="6" p="50 100" BoundingBox="50 90 140 112">
    <s font="3" size="10" face="0" color="5">Green</s>
  </t>
</page>
</CDXML>
""".encode()


@pytest.mark.parametrize(
    ("fgcolor", "caption_colors", "atom_color", "bond_color"),
    [
        (None, ["0", "1", "5", "0"], "0", "5"),
        ("0", ["0", "1", "5", "0"], "0", "5"),
        ("2", ["4", "1", "5", "4"], "4", "5"),
    ],
)
def test_rich_caption_colors_survive_fgcolor_modes(
    fgcolor: str | None,
    caption_colors: list[str],
    atom_color: str,
    bond_color: str,
):
    saved = _serialize_edited(fgcolor)
    with_snapshot = parse_cdxml_document(saved).state
    _assert_projected_rich_colors(with_snapshot)

    native = _strip_snapshot(saved)
    from_native = parse_cdxml_document(native, preserve_source=True).state
    _assert_projected_rich_colors(from_native)
    assert _document_char_colors(
        with_snapshot["notes"][0]["html"]
    ) == _document_char_colors(from_native["notes"][0]["html"])

    root = ET.fromstring(native)
    assert root.get("fgcolor") == fgcolor
    runs = root.find('.//t[@id="6"]').findall("s")
    assert "".join("".join(run.itertext()) for run in runs) == "BlackWhiteGreenAgain"
    assert [run.get("color") for run in runs] == caption_colors
    assert root.find('.//n[@id="3"]').get("color") == atom_color
    assert root.find(".//b").get("color") == bond_color

    if fgcolor == "2":
        assert root.get("bgcolor") == "3"
        assert root.find("page").get("bgcolor") == "3"
        assert [
            (
                round(float(c.get("r")) * 255),
                round(float(c.get("g")) * 255),
                round(float(c.get("b")) * 255),
            )
            for c in root.findall("colortable/color")
        ] == [
            (255, 0, 0),
            (255, 255, 255),
            (0, 0, 0),
            (0, 170, 85),
        ]
        with offscreen_canvas(with_snapshot, command="test-native-palette-rewrite") as (
            canvas,
            service,
        ):
            second = serialize_cdxml_document(canvas, service.snapshot_state())
            assert _canvas_note_char_colors(canvas) == EXPECTED_RICH_CHARS
        assert ET.canonicalize(_strip_snapshot(second).decode()) == ET.canonicalize(
            native.decode()
        )


def test_apple_system_ui_font_default_keeps_caption_colors_on_native_reopen(
    qt_application,
):
    application = QApplication.instance()
    assert application is qt_application
    previous = application.font()
    application.setFont(QFont(".AppleSystemUIFont", 9))
    try:
        saved = _serialize_edited("2")
        native = _strip_snapshot(saved)
        root = ET.fromstring(native)
        fonts = {
            font.get("id"): font.get("name") for font in root.findall("fonttable/font")
        }
        assert ".AppleSystemUIFont" in fonts.values()
        runs = root.find('.//t[@id="6"]').findall("s")
        assert [run.get("color") for run in runs] == ["4", "1", "5", "4"]

        from_native = parse_cdxml_document(native, preserve_source=True).state
        html = from_native["notes"][0]["html"]
        assert "&#x27;.AppleSystemUIFont&#x27;" in html
        assert _document_char_colors(html) == EXPECTED_RICH_CHARS

        with offscreen_canvas(from_native, command="test-native-apple-font-reopen") as (
            canvas,
            _service,
        ):
            assert _canvas_note_char_colors(canvas) == EXPECTED_RICH_CHARS
    finally:
        application.setFont(previous)


@pytest.mark.parametrize(
    ("family", "html_needle"),
    [
        (".AppleSystemUIFont", "&#x27;.AppleSystemUIFont&#x27;"),
        ("Arial", "&#x27;Arial&#x27;"),
        ("Courier New", "&#x27;Courier New&#x27;"),
        ("Foo'Bar", "&#x27;Foo\\&#x27;Bar&#x27;"),
        ("Foo\\Bar", "&#x27;Foo\\\\Bar&#x27;"),
        ("Noto Sans 日本語", "&#x27;Noto Sans 日本語&#x27;"),
        ('Foo"Bar', "&#x27;Foo&quot;Bar&#x27;"),
    ],
)
def test_caption_font_family_css_quoting_retains_run_color(
    family: str, html_needle: str
):
    state = parse_cdxml_document(_caption_native(family), preserve_source=True).state
    html = state["notes"][0]["html"]
    assert html_needle in html
    assert "color: #00aa55" in html
    # Exact stored HTML must keep the authored green; no test-side repairs.
    assert _document_char_colors(html) == EXPECTED_GREEN_CHARS
    with offscreen_canvas(state, command="test-native-font-family-quote") as (
        canvas,
        _service,
    ):
        assert _canvas_note_char_colors(canvas) == EXPECTED_GREEN_CHARS


def test_allocate_native_color_index_uppercase_absent_and_reuse():
    bare = ET.Element("CDXML")
    assert allocate_native_color_index(bare, "#000000") == "0"
    assert allocate_native_color_index(bare, "#FFFFFF") == "1"
    assert bare.find("colortable") is None

    custom = ET.Element("CDXML", fgcolor="2")
    first = allocate_native_color_index(custom, "#00AA55")
    again = allocate_native_color_index(custom, "#00aa55")
    black = allocate_native_color_index(custom, "#000000")
    black_again = allocate_native_color_index(custom, "#000000")
    assert first == again == "2"
    assert black == black_again == "3"
    table = custom.find("colortable")
    assert table is not None
    assert [
        (
            round(float(c.get("r")) * 255),
            round(float(c.get("g")) * 255),
            round(float(c.get("b")) * 255),
        )
        for c in table
    ] == [(0, 170, 85), (0, 0, 0)]

    default_fg = ET.Element("CDXML", fgcolor="0")
    assert allocate_native_color_index(default_fg, "#000000") == "0"
    assert default_fg.find("colortable") is None


def test_allocate_native_color_index_expands_short_hex():
    bare = ET.Element("CDXML")
    assert allocate_native_color_index(bare, "#FFF") == "1"
    assert allocate_native_color_index(bare, "#000") == "0"
    assert bare.find("colortable") is None

    custom = ET.Element("CDXML", fgcolor="2")
    black = allocate_native_color_index(custom, "#000")
    black_again = allocate_native_color_index(custom, "#000000")
    assert black == black_again == "2"
    table = custom.find("colortable")
    assert table is not None
    assert [
        (
            round(float(c.get("r")) * 255),
            round(float(c.get("g")) * 255),
            round(float(c.get("b")) * 255),
        )
        for c in table
    ] == [(0, 0, 0)]

    red_root = ET.Element("CDXML")
    red = allocate_native_color_index(red_root, "#f00")
    red_again = allocate_native_color_index(red_root, "#ff0000")
    assert red == red_again == "2"
    red_table = red_root.find("colortable")
    assert red_table is not None
    assert [
        (
            round(float(c.get("r")) * 255),
            round(float(c.get("g")) * 255),
            round(float(c.get("b")) * 255),
        )
        for c in red_table
    ] == [(255, 0, 0)]

    for invalid in ("red", "#ff00"):
        with pytest.raises(ValueError, match="#rgb or #rrggbb"):
            allocate_native_color_index(ET.Element("CDXML"), invalid)


def test_short_hex_atom_color_survives_native_serialize_and_reopen():
    state = parse_cdxml_document(NATIVE, preserve_source=True).state
    atoms = state["model"]["atoms"]
    atom = atoms[0] if 0 in atoms else atoms["0"]
    atom["color"] = "#f00"
    with offscreen_canvas(state, command="test-native-short-hex-color") as (
        canvas,
        service,
    ):
        saved = serialize_cdxml_document(canvas, service.snapshot_state())
    native = _strip_snapshot(saved)
    root = ET.fromstring(native)
    color_index = root.find('.//n[@id="3"]').get("color")
    assert color_index is not None
    entry = root.find("colortable")[int(color_index) - 2]
    assert (
        round(float(entry.get("r")) * 255),
        round(float(entry.get("g")) * 255),
        round(float(entry.get("b")) * 255),
    ) == (255, 0, 0)
    reopened = parse_cdxml_document(native, preserve_source=True).state
    assert _atom_color(reopened) == "#ff0000"
