"""Native CDXML saves do not depend on edit history or reopen path.

Each case reaches the same document through ordinary editing and checks that
the saved native XML, reopened on its own, still shows that document.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import xml.etree.ElementTree as ET
from copy import deepcopy
from itertools import permutations

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document
from chemvas.ui.export.cdxml_native_text import write_native_caption
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from tests.canvas_factory import build_canvas_view

CC = b"""<CDXML LabelFont="3" LabelSize="10" CaptionFont="3"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 200 200"><fragment id="2"><n id="3" p="50 50"/><n id="4" p="70 50"/><b id="5" B="3" E="4"/></fragment></page></CDXML>"""


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    view.resize(700, 500)
    view.show()
    app.processEvents()
    yield view
    view.services.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _session(canvas):
    return canvas.services.canvas_document_session_service


def _save(state) -> bytes:
    return update_native_document(state, note_writer=write_native_caption)


def _topology(raw: bytes) -> set[frozenset[tuple[str, str]]]:
    """Each fragment as its set of bonded (element, position) pairs."""
    root = ET.fromstring(raw)
    result = set()
    for fragment in root.iter("fragment"):
        nodes = {
            n.get("id"): (n.get("Element", "6"), n.get("p")) for n in fragment.iter("n")
        }
        result.add(
            frozenset(
                frozenset((nodes[b.get("B")], nodes[b.get("E")]))
                for b in fragment.iter("b")
            )
        )
    return result


# 1. Delete -> Undo reorders the atom dict; the save must not depend on it.


def test_delete_undo_of_new_chain_atom_still_saves(canvas):
    session = _session(canvas)
    session.apply_state(parse_cdxml_document(CC).state)
    atoms = canvas.services.canvas_atom_mutation_service
    first = atoms.add_atom("N", 50, -20)
    second = atoms.add_atom("N", 70, -40)
    add_bond_for(canvas, 1, first)
    add_bond_for(canvas, first, second)
    canvas.services.structure_build_service.render_model()
    before = session.snapshot_state()
    saved_before = _save(before)
    order = list(before["model"]["atoms"])

    canvas.services.scene_delete_controller.delete_atom(first)
    canvas.services.history_service.undo()
    after = session.snapshot_state()

    assert list(after["model"]["atoms"]) != order
    assert after["model"] == before["model"]
    saved_after = _save(after)
    assert _topology(saved_after) == _topology(saved_before)
    assert len(ET.fromstring(saved_after).findall(".//fragment")) == 1


def _with_new_atoms(order: tuple[int, ...]) -> dict:
    state = parse_cdxml_document(CC).state
    model = state["model"]
    new_atoms = {
        2: {"element": "N", "x": 0, "y": -20, "color": "#000000"},
        3: {"element": "N", "x": 20, "y": -40, "color": "#000000"},
        4: {"element": "O", "x": 40, "y": -60, "color": "#000000"},
        # Separate new structure, bonded to nothing native.
        5: {"element": "S", "x": 100, "y": 100, "color": "#000000"},
        6: {"element": "S", "x": 120, "y": 100, "color": "#000000"},
    }
    for key in order:
        model["atoms"][key] = {**new_atoms[key], "explicit_label": False}
    template = deepcopy(model["bonds"][0])
    for a, b in ((0, 2), (2, 3), (3, 4), (5, 6)):
        model["bonds"].append({**template, "a": a, "b": b})
    return state


def test_new_atom_fragments_do_not_depend_on_insertion_order():
    reference = None
    for order in permutations((2, 3, 4, 5, 6)):
        raw = _save(_with_new_atoms(order))
        root = ET.fromstring(raw)
        assert len(root.findall(".//fragment")) == 2
        if reference is None:
            reference = _topology(raw)
        assert _topology(raw) == reference


def test_bridging_two_native_fragments_is_still_refused():
    source = CC.replace(
        b"</fragment>",
        b'</fragment><fragment id="6"><n id="7" p="150 50"/></fragment>',
    )
    state = parse_cdxml_document(source).state
    model = state["model"]
    model["atoms"][3] = {
        "element": "N",
        "x": 50,
        "y": -20,
        "color": "#000000",
        "explicit_label": False,
    }
    template = deepcopy(model["bonds"][0])
    model["bonds"] += [{**template, "a": 1, "b": 3}, {**template, "a": 3, "b": 2}]
    with pytest.raises(ValueError, match="two native fragments"):
        _save(state)


# 2. Showing or hiding a carbon symbol is written to native XML.


def _native_label(raw: bytes, native_id: str) -> str | None:
    node = ET.fromstring(raw).find(f".//n[@id='{native_id}']")
    assert node is not None
    text = node.find("t")
    return None if text is None else "".join(text.itertext())


def test_explicit_carbon_round_trips_through_native_xml(canvas):
    session = _session(canvas)
    session.apply_state(parse_cdxml_document(CC).state)
    canvas.services.atom_label_service.add_or_update_atom_label(
        0, "C", show_carbon=True
    )
    state = session.snapshot_state()
    assert state["model"]["atoms"][0]["explicit_label"] is True
    assert state["model"]["atoms"][0]["element"] == "C"

    raw = _save(state)
    assert _native_label(raw, "3") == "C"
    reopened = parse_cdxml_document(raw).state
    assert reopened["model"]["atoms"][0]["explicit_label"] is True
    assert reopened["model"]["atoms"][0]["element"] == "C"

    # Undo hides it again, and the native text goes with it.
    canvas.services.history_service.undo()
    hidden_state = session.snapshot_state()
    assert hidden_state["model"]["atoms"][0]["explicit_label"] is False
    hidden = _save(hidden_state)
    assert hidden == _save(parse_cdxml_document(CC).state)
    assert _native_label(hidden, "3") is None

    # Hiding a carbon that the source showed removes its native text.
    reopened["model"]["atoms"][0]["explicit_label"] = False
    removed = _save(reopened)
    assert _native_label(removed, "3") is None
    assert (
        parse_cdxml_document(removed).state["model"]["atoms"][0]["explicit_label"]
        is False
    )


def test_showing_carbon_keeps_charge_and_stereo_attributes():
    source = CC.replace(
        b'<n id="3" p="50 50"/>',
        b'<n id="3" p="50 50" Charge="1" AS="R" Isotope="13"/>',
    )
    state = parse_cdxml_document(source).state
    state["model"]["atoms"][0]["explicit_label"] = True
    node = ET.fromstring(_save(state)).find(".//n[@id='3']")
    assert node is not None
    assert (node.get("Charge"), node.get("AS"), node.get("Isotope")) == (
        "1",
        "R",
        "13",
    )
    assert "".join(node.find("t").itertext()) == "C"


# 3. Editing a justified native caption keeps its native anchor.

CAPTION = b"""<CDXML CaptionFont="3"><fonttable><font id="3" name="Arial"/></fonttable><page id="1" BoundingBox="0 0 400 200"><t id="2" p="150 60" Justification="{j}"><s font="3" size="10" face="0">Short</s></t></page></CDXML>"""


def _anchor_x(item, justification: str) -> float:
    item.boundingRect()
    layout = item.document().begin().layout()
    line = layout.lineAt(0)
    x = layout.position().x() + line.naturalTextRect().left()
    if justification == "Center":
        x += line.naturalTextWidth() / 2
    elif justification == "Right":
        x += line.naturalTextWidth()
    return item.mapToScene(QPointF(x, 0)).x()


def _note(canvas):
    items = canvas.runtime_state.scene_items_state.note_items
    assert len(items) == 1
    return next(iter(items.values()))


@pytest.mark.parametrize("justification", ["Left", "Center", "Right"])
def test_caption_edit_keeps_native_anchor_through_undo_save_and_reopen(
    canvas, justification
):
    session = _session(canvas)
    raw = CAPTION.replace(b"{j}", justification.encode())
    session.apply_state(parse_cdxml_document(raw).state)
    item = _note(canvas)
    anchor = _anchor_x(item, justification)

    cursor = QTextCursor(item.document())
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText("A much longer caption than before")
    QApplication.processEvents()
    assert _anchor_x(item, justification) == pytest.approx(anchor)

    item.document().undo()
    assert _anchor_x(item, justification) == pytest.approx(anchor)
    item.document().redo()
    assert _anchor_x(item, justification) == pytest.approx(anchor)

    saved = _save(session.snapshot_state())
    session.apply_state(parse_cdxml_document(saved).state)
    reopened = _note(canvas)
    assert reopened.toPlainText() == "A much longer caption than before"
    assert _anchor_x(reopened, justification) == pytest.approx(anchor)
