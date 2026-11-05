"""Working-document saves retain native artwork with unambiguous paint order."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import replace

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.domain.document import Atom, Bond
from chemvas.domain.document.cdxml_source import append_unbound_note
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.document_files import read_document
from chemvas.ui.scene.scene_decoration_access import add_mark_for
from tests.test_cdxml_export import _simple_state

pytestmark = pytest.mark.usefixtures("qt_application")

SOURCE = b"""<CDXML LabelFont="3" LabelSize="10" CaptionFont="3" CaptionSize="10" BondLength="40" LineWidth="1"><fonttable><font id="3" name="Arial"/></fonttable><colortable><color r="0.95" g="0.84" b="0.84"/></colortable><page id="1" BoundingBox="0 0 240 160"><graphic id="2" Z="1" GraphicType="Rectangle" RectangleType="RoundEdge Filled" BoundingBox="45 40 120 80" color="2"/><graphic id="3" Z="1" GraphicType="Rectangle" RectangleType="RoundEdge Filled" BoundingBox="140 40 200 80" color="2"/><fragment id="4"><n id="5" Z="2" p="60 60"/><n id="6" Z="2" p="100 60" Element="8" NumHydrogens="0"><t id="7" Z="2" p="100 60"><s font="3" size="10" face="96">O</s></t></n><b id="8" Z="2" B="5" E="6"/></fragment><t id="9" Z="2" p="150 62"><s font="3" size="10">step</s></t></page></CDXML>"""
Z_TAGS = {"n", "b", "t", "graphic", "arrow", "curve", "embeddedobject"}


def _native(raw):
    return raw.split(b"\n<!-- ChemvasDocument:")[0]


def _unique_z(root):
    values = [int(e.attrib["Z"]) for e in root.iter() if e.tag in Z_TAGS]
    assert len(set(values)) == len(values)
    assert all(0 < z <= 32767 for z in values)
    assert not any("Z" in e.attrib for e in root.iter() if e.tag not in Z_TAGS)


def _without_z(raw):
    root = ET.fromstring(raw)
    for e in root.iter():
        e.attrib.pop("Z", None)
    return ET.canonicalize(ET.tostring(root, encoding="unicode"))


def _render(canvas):
    image = QImage(480, 320, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        canvas.scene().render(
            painter, QRectF(0, 0, 480, 320), QRectF(-120, -80, 240, 160)
        )
    finally:
        painter.end()
    return image


CARBONS = b"""<CDXML CaptionFont="3" CaptionSize="10" LineWidth="1"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 240 160"><fragment id="2"><n id="3" p="60 60" Z="1"/><n id="4" p="100 60" Z="2"/><b id="5" B="3" E="4" Z="3"/></fragment></page></CDXML>"""
CROSSING = b"""<CDXML LineWidth="4"><colortable><color r="1" g="0" b="0"/><color r="0" g="0" b="1"/></colortable><page id="1" BoundingBox="0 0 240 160"><fragment id="2"><n id="3" p="60 40" Z="1"/><n id="4" p="100 80" Z="1"/><n id="5" p="60 80" Z="1"/><n id="6" p="100 40" Z="1"/><b id="7" B="3" E="4" Z="1" color="2"/><b id="8" B="5" E="6" Z="1" color="3"/></fragment></page></CDXML>"""


def test_invisible_carbon_hit_targets_do_not_block_caption_save(tmp_path):
    state = parse_cdxml_document(CARBONS).state
    append_unbound_note(state, dict(text="distant", html="", x=60, y=40))
    with offscreen_canvas(state, command="carbon-hit-targets") as (canvas, service):
        before = _render(canvas)
        dots = canvas.runtime_state.atom_graphics_state.atom_dots
        bond = canvas.runtime_state.bond_graphics_state.bond_items[0][0]
        assert len(dots) == 2
        assert all(
            d.sceneBoundingRect().intersects(bond.sceneBoundingRect())
            for d in dots.values()
        )
        assert all(d.export_scene_bounding_rect().isEmpty() for d in dots.values())
        path = tmp_path / "carbons.cdxml"
        service.save_to_file(str(path))
        root = ET.fromstring(path.read_bytes())
        _unique_z(root)
        assert [n.get("id") for n in root.iter("n")] == ["3", "4"]
        assert len(list(root.iter("b"))) == 1
        service.apply_state(read_document(path).state)
        assert _render(canvas) == before


def test_rebuilt_crossing_bonds_keep_pixels_and_z_after_snapshot_reopen(tmp_path):
    state = parse_cdxml_document(CROSSING).state
    with offscreen_canvas(state, command="crossing-save-reopen") as (canvas, service):
        assert _render(canvas).pixelColor(160, 120).name() == "#0000ff"
        canvas.render_context.bonds.redraw_bond(0)
        before = _render(canvas)
        assert before.pixelColor(160, 120).name() == "#ff0000"
        original_model = service.snapshot_state()["model"]
        original_source = deepcopy(service.snapshot_state()["cdxml_source"])
        path = tmp_path / "crossing.cdxml"
        service.save_to_file(str(path))
        first = path.read_bytes()
        retained = read_document(path).state["cdxml_source"]
        assert _without_z(retained["xml"]) == _without_z(original_source["xml"])
        assert {k: v for k, v in retained.items() if k != "xml"} == {
            k: v
            for k, v in json.loads(json.dumps(original_source)).items()
            if k != "xml"
        }
        assert service.snapshot_state()["cdxml_source"] == original_source
        root = ET.fromstring(first)
        assert int(root.find('.//b[@id="8"]').get("Z")) < int(
            root.find('.//b[@id="7"]').get("Z")
        )
        service.apply_state(read_document(path).state)
        reopened = _render(canvas)
        service.save_to_file(str(path))
        second = ET.fromstring(path.read_bytes())
        assert reopened == before
        assert int(second.find('.//b[@id="8"]').get("Z")) < int(
            second.find('.//b[@id="7"]').get("Z")
        )
        assert service.snapshot_state()["model"] == original_model
        assert _native(path.read_bytes()) == _native(first)
        service.apply_state(parse_cdxml_document(_native(first)).state)
        assert _render(canvas) == before


@pytest.mark.parametrize("resolved_source", [False, True])
def test_unbound_mark_overlapping_fill_keeps_native_order_on_repeated_save(
    tmp_path, resolved_source
):
    root = ET.fromstring(CROSSING)
    root.find("page").append(
        ET.fromstring(
            '<graphic id="9" Z="1" GraphicType="Rectangle" RectangleType="Filled" '
            'BoundingBox="160.000 40.0 200.00 80.000" color="2"/>'
        )
    )
    if resolved_source:
        for z, element in enumerate((e for e in root.iter() if e.tag in Z_TAGS), 1):
            element.set("Z", str(z))
    state = parse_cdxml_document(ET.tostring(root)).state
    with offscreen_canvas(state, command="unbound-mark-fill") as (canvas, service):
        if not resolved_source:
            canvas.render_context.bonds.redraw_bond(0)
        mark = add_mark_for(canvas, QPointF(60, -20), kind="plus")
        mark.setSelected(False)
        fill = canvas.runtime_state.image_items()[0]
        ranks = {item: n for n, item in enumerate(canvas.scene().items())}
        assert ranks[mark] > ranks[fill]
        assert mark.sceneBoundingRect().intersects(fill.sceneBoundingRect())
        before = _render(canvas)
        assert before.pixelColor(360, 120).name() == "#ff0000"
        assert before.pixelColor(160, 120).name() == (
            "#0000ff" if resolved_source else "#ff0000"
        )
        original = deepcopy(service.snapshot_state())
        path = tmp_path / "mark-fill.cdxml"
        saves = []
        for _ in range(2):
            current = deepcopy(service.snapshot_state())
            service.save_to_file(str(path))
            assert service.snapshot_state() == current
            saved = _native(path.read_bytes())
            saves.append(saved)
            native = ET.fromstring(saved)
            _unique_z(native)
            assert int(native.find('.//graphic[@SymbolType="Plus"]').get("Z")) < int(
                native.find('.//graphic[@id="9"]').get("Z")
            )
            # Only the new mark and Z may differ from the original native XML.
            native.find("page").remove(native.find('.//graphic[@SymbolType="Plus"]'))
            assert _without_z(ET.tostring(native)) == _without_z(
                original["cdxml_source"]["xml"]
            )
            reopened = read_document(path).state
            assert reopened["model"] == json.loads(json.dumps(original["model"]))
            assert reopened["marks"] == original["marks"]
            retained = reopened["cdxml_source"]
            assert retained["items"]["marks"] == [None]
            assert {k: v for k, v in retained.items() if k != "xml"} == {
                k: v
                for k, v in json.loads(json.dumps(original["cdxml_source"])).items()
                if k != "xml"
            }
            assert _without_z(retained["xml"]) == _without_z(
                original["cdxml_source"]["xml"]
            )
            service.apply_state(reopened)
            assert _render(canvas) == before
            service.apply_state(parse_cdxml_document(saved).state)
            assert _render(canvas) == before
            service.apply_state(reopened)
            assert service.snapshot_state()["model"] == original["model"]
        assert saves[1] == saves[0]


@pytest.mark.parametrize("label_above", [False, True])
def test_label_hit_padding_is_not_painted_overlap_on_either_side(tmp_path, label_above):
    root = ET.fromstring(CARBONS)
    node = root.find('.//n[@id="4"]')
    node.set("Element", "8")
    node.set("NumHydrogens", "0")
    root.find("page").append(
        ET.fromstring(
            f'<arrow id="10" Z="{4 if label_above else 0}" Tail3D="90 40 0" Head3D="110 40 0" LineWidth="0.5"/>'
        )
    )
    state = parse_cdxml_document(ET.tostring(root)).state
    append_unbound_note(state, dict(text="distant", html="", x=60, y=40))
    with offscreen_canvas(state, command="label-hit-padding") as (canvas, service):
        label = canvas.runtime_state.atom_graphics_state.atom_items[1]
        arrow = canvas.runtime_state.arrow_items()[0]
        ink = label.export_scene_bounding_rect()
        context = canvas.render_context
        context.arrows.set_record(
            arrow,
            replace(
                context.arrows.record(arrow),
                start=(ink.left(), ink.top() - 1),
                end=(ink.right(), ink.top() - 1),
            ),
        )
        if not label_above:
            arrow.setZValue(4)
        assert arrow.sceneBoundingRect().intersects(label.sceneBoundingRect())
        assert not arrow.sceneBoundingRect().intersects(ink)
        path = tmp_path / "label-padding.cdxml"
        service.save_to_file(str(path))
        _unique_z(ET.fromstring(path.read_bytes()))


@pytest.mark.parametrize("rebuild", [False, True])
def test_unbound_crossing_order_must_be_replayable_before_replacement(
    tmp_path, rebuild
):
    root = ET.fromstring(CROSSING)
    bonds = parse_cdxml_document(CROSSING).state["model"]["bonds"]
    fragment = root.find(".//fragment")
    for bond in fragment.findall("b"):
        fragment.remove(bond)
    state = parse_cdxml_document(ET.tostring(root)).state
    state["model"]["bonds"] = bonds
    with offscreen_canvas(state, command="unbound-crossing") as (canvas, service):
        if rebuild:
            canvas.render_context.bonds.redraw_bond(0)
        before = deepcopy(service.snapshot_state())
        image = _render(canvas)
        assert image.pixelColor(160, 120).name() == (
            "#ff0000" if rebuild else "#0000ff"
        )
        path = tmp_path / "existing.cdxml"
        path.write_bytes(b"keep existing destination")
        if rebuild:
            with pytest.raises(
                ValueError, match="snapshot cannot restore this overlapping paint order"
            ):
                service.save_to_file(str(path))
            assert path.read_bytes() == b"keep existing destination"
            assert service.snapshot_state() == before
        else:
            service.save_to_file(str(path))
            service.apply_state(read_document(path).state)
            assert _render(canvas) == image
            assert service.snapshot_state()["model"] == before["model"]


def test_resolved_snapshot_paint_order_survives_session_recovery(tmp_path, monkeypatch):
    from chemvas.features.session import DocDescriptor
    from chemvas.ui.session import session_snapshot_store
    from chemvas.ui.session.session_snapshot_store import SessionSnapshotStore

    with offscreen_canvas(
        parse_cdxml_document(CROSSING).state, command="crossing-recovery"
    ) as (canvas, service):
        canvas.render_context.bonds.redraw_bond(0)
        before = _render(canvas)
        path = tmp_path / "crossing.cdxml"
        service.save_to_file(str(path))
        service.apply_state(read_document(path).state)
        state = service.snapshot_state()
        root = tmp_path / "sessions"
        writer = SessionSnapshotStore(
            root, session_id="old", pid=424242, process_identity="fixture"
        )
        writer.begin()
        writer.save_documents([DocDescriptor(state, str(path), path.name, True)])
        monkeypatch.setattr(session_snapshot_store, "_pid_alive", lambda pid: False)
        reader = SessionSnapshotStore(
            root, session_id="new", pid=424243, process_identity="fixture2"
        )
        recovered = reader.consume_previous_sessions()
        assert len(recovered.docs) == 1
        assert recovered.docs[0].state["model"] == json.loads(
            json.dumps(state["model"])
        )
        service.apply_state(recovered.docs[0].state)
        assert _render(canvas) == before


def test_reversing_already_resolved_crossing_refuses_before_replacement(tmp_path):
    with offscreen_canvas(
        parse_cdxml_document(CROSSING).state, command="resolved-crossing-conflict"
    ) as (canvas, service):
        canvas.render_context.bonds.redraw_bond(0)
        path = tmp_path / "crossing.cdxml"
        service.save_to_file(str(path))
        original = path.read_bytes()
        service.apply_state(read_document(path).state)
        canvas.render_context.bonds.redraw_bond(1)
        assert _render(canvas).pixelColor(160, 120).name() == "#0000ff"
        before = deepcopy(service.snapshot_state())
        with pytest.raises(
            ValueError, match="snapshot cannot restore this overlapping paint order"
        ):
            service.save_to_file(str(path))
        assert path.read_bytes() == original
        assert service.snapshot_state() == before


def test_invisible_nodes_do_not_make_fragment_painters_interleave(tmp_path):
    root = ET.fromstring(SOURCE)
    root.find("page").append(
        ET.fromstring(
            '<fragment id="10"><n id="11" Z="2" p="80 40"/>'
            '<n id="12" Z="2" p="80 80"/><b id="13" Z="2" B="11" E="12"/></fragment>'
        )
    )
    with offscreen_canvas(
        parse_cdxml_document(ET.tostring(root)).state,
        command="invisible-fragment-nodes",
    ) as (canvas, service):
        before = _render(canvas)
        path = tmp_path / "fragments.cdxml"
        service.save_to_file(str(path))
        native = _native(path.read_bytes())
        _unique_z(ET.fromstring(native))
        assert _without_z(native) == _without_z(ET.tostring(root))
        service.apply_state(parse_cdxml_document(native).state)
        assert _render(canvas) == before


@pytest.mark.parametrize("low,high", [(1, 2), (-4, 0), (40000, 50000)])
def test_save_duplicate_z_pills_preserves_graph_artwork_and_reopen(tmp_path, low, high):
    source = SOURCE.replace(b'Z="1"', f'Z="{low}"'.encode()).replace(
        b'Z="2"', f'Z="{high}"'.encode()
    )
    state = parse_cdxml_document(source).state
    original = state["cdxml_source"]["xml"]
    path = tmp_path / "pills.cdxml"
    with offscreen_canvas(state, command="paint-order") as (canvas, service):
        before = _render(canvas)
        service.save_to_file(str(path))
        raw = path.read_bytes()
        _unique_z(ET.fromstring(raw))
        assert _without_z(raw) == _without_z(original)
        assert b"embeddedobject" not in raw
        assert state["cdxml_source"]["xml"] == original
        service.apply_state(read_document(path).state)
        assert _render(canvas) == before
        service.save_to_file(str(path))
        assert _native(path.read_bytes()) == _native(raw)
        service.apply_state(parse_cdxml_document(_native(raw)).state)
        assert _render(canvas) == before
        service.save_to_file(str(path))
        assert _native(path.read_bytes()) == _native(raw)


def test_unique_native_order_is_unchanged_even_when_xml_siblings_differ(tmp_path):
    root = ET.fromstring(SOURCE)
    for index, e in enumerate(e for e in root.iter() if e.tag in Z_TAGS):
        e.set("Z", str(300 - index))
    state = parse_cdxml_document(ET.tostring(root)).state
    with offscreen_canvas(state, command="paint-order-control") as (_, service):
        path = tmp_path / "ordered.cdxml"
        service.save_to_file(str(path))
    assert ET.canonicalize(_native(path.read_bytes()).decode()) == ET.canonicalize(
        state["cdxml_source"]["xml"]
    )


def test_overlapping_tied_fills_keep_the_visible_tie_order(tmp_path):
    root = ET.fromstring(SOURCE)
    ET.SubElement(root.find("colortable"), "color", r="0.75", g="0.85", b="1")
    second = root.find('.//graphic[@id="3"]')
    second.set("BoundingBox", "80 40 150 80")
    second.set("color", "3")
    with offscreen_canvas(
        parse_cdxml_document(ET.tostring(root)).state, command="tied-fills"
    ) as (canvas, service):
        before = _render(canvas)
        assert before.pixelColor(180, 140).name() == "#bfd9ff"
        path = tmp_path / "overlap.cdxml"
        service.save_to_file(str(path))
        saved = ET.fromstring(path.read_bytes())
        _unique_z(saved)
        assert int(saved.find('.//graphic[@id="2"]').get("Z")) < int(
            saved.find('.//graphic[@id="3"]').get("Z")
        )
        service.apply_state(parse_cdxml_document(_native(path.read_bytes())).state)
        assert _render(canvas) == before


def test_fresh_native_save_has_unique_z_and_no_flattening(tmp_path):
    state = _simple_state(
        atoms={0: Atom("C", -60, -20), 1: Atom("O", -20, -20)},
        bonds=[Bond(0, 1)],
        shapes=[
            dict(
                kind="shape",
                shape_kind="rect",
                left=-80,
                top=-40,
                right=0,
                bottom=10,
                fill="#eeeeee",
                stroke_style="none",
            )
        ],
    )
    with offscreen_canvas(state, command="fresh-paint-order") as (canvas, service):
        before = _render(canvas)
        path = tmp_path / "fresh.cdxml"
        service.save_to_file(str(path))
        root = ET.fromstring(path.read_bytes())
        _unique_z(root)
        assert root.find(".//embeddedobject") is None
        fill_z = int(root.find(".//graphic").get("Z"))
        assert all(
            fill_z < int(e.get("Z")) for e in root.iter() if e.tag in {"n", "b", "t"}
        )
        service.apply_state(read_document(path).state)
        assert _render(canvas) == before


def test_hidden_nickname_and_superseded_arrow_keep_chemistry_and_references(tmp_path):
    root = ET.fromstring(SOURCE)
    node = root.find('.//n[@id="6"]')
    node.attrib.pop("Element")
    node.attrib.pop("NumHydrogens")
    node.set("NodeType", "Nickname")
    node.find("t/s").text = "OMe"
    node.insert(
        0,
        ET.fromstring(
            '<fragment id="20" ConnectionOrder="23"><n id="21" p="100 60" Element="8" Z="1"/>'
            '<n id="22" p="140 60" Z="1"/><n id="23" p="60 60" NodeType="ExternalConnectionPoint" Z="1"/>'
            '<b id="24" B="21" E="22" Z="1"/><b id="25" B="21" E="23" Z="1"/></fragment>'
        ),
    )
    page = root.find("page")
    page.append(
        ET.fromstring(
            '<graphic id="30" SupersededBy="31" Z="1" GraphicType="Line" BoundingBox="190 120 140 120"/>'
        )
    )
    page.append(
        ET.fromstring(
            '<arrow id="31" Z="2" Tail3D="140 120 0" Head3D="190 120 0" ArrowheadHead="Full"/>'
        )
    )
    page.append(
        ET.fromstring(
            '<scheme id="32"><step id="33" ReactionStepReactants="4" ReactionStepArrows="31"/></scheme>'
        )
    )
    state = parse_cdxml_document(ET.tostring(root)).state
    with offscreen_canvas(state, command="hidden-paint-order") as (canvas, service):
        before = _render(canvas)
        path = tmp_path / "nickname.cdxml"
        service.save_to_file(str(path))
        saved = ET.fromstring(path.read_bytes())
        _unique_z(saved)
        assert _without_z(path.read_bytes()) == _without_z(state["cdxml_source"]["xml"])
        service.apply_state(parse_cdxml_document(_native(path.read_bytes())).state)
        assert _render(canvas) == before
        assert len(canvas.model.atoms) == 2
        assert len(canvas.model.bonds) == 1


def test_added_native_objects_receive_scene_order_on_save(tmp_path):
    state = parse_cdxml_document(SOURCE).state
    append_unbound_note(state, dict(text="new", html="", x=30, y=25))
    state["model"]["atoms"][2] = dict(
        element="C", x=-80, y=20, color="#000000", explicit_label=False
    )
    state["model"]["next_atom_id"] = 3
    state["model"]["bonds"].append(
        dict(a=0, b=2, order=1, style="single", color="#000000")
    )
    state["arrows"].append(dict(kind="arrow", start=[-80, 40], end=[-40, 40]))
    state["cdxml_source"]["items"]["arrows"].append(None)
    with offscreen_canvas(state, command="added-paint-order") as (_, service):
        path = tmp_path / "added.cdxml"
        service.save_to_file(str(path))
        root = ET.fromstring(path.read_bytes())
        _unique_z(root)
        assert len(list(root.iter("n"))) == 3
        assert len(list(root.iter("b"))) == 2
        assert len(list(root.iter("arrow"))) == 1
        reopened = parse_cdxml_document(_native(path.read_bytes())).state
        assert len(reopened["model"]["atoms"]) == 3
        assert len(reopened["model"]["bonds"]) == 2
        assert [n["text"] for n in reopened["notes"]] == ["step", "new"]


@pytest.mark.parametrize(
    "failure,message",
    [
        ("interleave", "interleaves with overlapping artwork"),
        ("fragments", "interleaves with overlapping artwork"),
        ("conflict", "conflicts with overlapping scene artwork"),
        ("missing", "No scene item establishes"),
        ("invalid", "must use integer Z"),
        ("overflow", "Too many drawable objects"),
        ("fallback", "Cannot resolve native fallback"),
    ],
)
def test_ambiguous_or_unrepresentable_order_refuses_without_overwrite(
    tmp_path, monkeypatch, failure, message
):
    root = ET.fromstring(SOURCE)
    if failure == "interleave":
        root.find('.//graphic[@id="2"]').set("Z", "2")
    elif failure == "fragments":
        root.find("page").append(
            ET.fromstring(
                '<fragment id="10"><n id="11" Z="2" p="80 40"/>'
                '<n id="12" Z="2" p="80 80" Element="8" NumHydrogens="0">'
                '<t id="14" Z="2" p="80 80"><s font="3" size="10">O</s></t></n>'
                '<b id="13" Z="2" B="11" E="12"/></fragment>'
            )
        )
    elif failure == "conflict":
        root.find("page").append(
            ET.fromstring('<arrow id="10" Z="0" Tail3D="50 50 0" Head3D="110 50 0"/>')
        )
    elif failure == "invalid":
        root.find('.//t[@id="9"]').set("Z", "1.5")
    elif failure == "fallback":
        root.find("page").append(
            ET.fromstring('<graphic id="10" Z="1" SupersededBy="999"/>')
        )
    state = parse_cdxml_document(ET.tostring(root)).state
    with offscreen_canvas(state, command="refuse-paint-order") as (canvas, service):
        if failure == "conflict":
            # Source order is restored on load. Explicitly reverse this visible
            # arrow/fill pair to exercise the conflict refusal, not insertion order.
            canvas.runtime_state.arrow_items()[0].setZValue(-2)
        if failure == "missing":
            canvas.scene().removeItem(canvas.runtime_state.image_items()[0])
        if failure == "overflow":
            from chemvas.ui.export import cdxml_document_paint_order

            assert cdxml_document_paint_order._Z_MAX == 32767
            monkeypatch.setattr(cdxml_document_paint_order, "_Z_MAX", 6)
        path = tmp_path / "existing.cdxml"
        path.write_bytes(b"keep existing file")
        with pytest.raises(ValueError, match=message):
            service.save_to_file(str(path))
        assert path.read_bytes() == b"keep existing file"
