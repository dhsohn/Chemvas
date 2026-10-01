"""View > Valence Checking in the browser: the desktop's own warning policy."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from chemvas.bootstrap.web_adapter import (
    BrowserSession,
    document_info,
    drawing_geometry,
    new_document,
)
from chemvas.domain.document import (
    MoleculeModel,
    extract_document_state,
    serialize_model_state_with_warnings,
)

ROOT = Path(__file__).resolve().parents[1]

# Fragment centres, one per native rule: element, formal charge, radical
# electrons, neighbours as (element, bond order[, bond style]) and whether the
# desktop warns. Neighbours always stay within their own limits.
FRAGMENTS = (
    ("C", 0, 0, (("C", 3), ("C", 2)), True),
    ("C", 0, 0, (("C", 2), ("C", 2)), False),
    ("C", 1, 0, (("C", 2), ("C", 2)), True),
    ("N", 0, 0, (("C", 2), ("C", 2)), True),
    ("N", 1, 0, (("C", 2), ("C", 2)), False),
    ("O", 0, 0, (("C", 2), ("C", 1)), True),
    ("O", 1, 0, (("C", 2), ("C", 1)), False),
    ("O", -1, 0, (("C", 2),), True),
    ("B", 0, 0, (("C", 2), ("C", 2)), True),
    ("B", -1, 0, (("C", 2), ("C", 2)), False),
    ("H", 0, 0, (("C", 1), ("C", 1)), True),
    ("F", 0, 0, (("C", 2),), True),
    ("F", -1, 0, (("C", 1),), True),
    ("C", 0, 1, (("C", 3), ("C", 2)), False),
    ("C", 0, 0, (("Ph", 1), ("C", 3), ("C", 2)), False),
    ("C", 0, 0, (("Fe", 1), ("C", 3), ("C", 2)), False),
    ("C", 0, 0, (("C", 3), ("C", 2), ("C", 1, "dotted")), False),
)
STYLES = {1: "single", 2: "double", 3: "triple"}


@pytest.fixture
def desktop_canvas(qt_application):
    from tests.canvas_factory import build_canvas_view

    canvas = build_canvas_view()
    yield canvas
    canvas.services.canvas_scene_reset_service.clear_scene()
    canvas.close()


def charge_marks(atom_id, x, y, charge, radical):
    kinds = ["plus" if charge > 0 else "minus"] * abs(charge) + ["radical"] * radical
    return [
        {
            "kind": kind,
            "text": None,
            "atom_id": atom_id,
            "dx": 8.0,
            "dy": -8.0,
            "x": x + 8.0,
            "y": y - 8.0,
        }
        for kind in kinds
    ]


def document_of(model, marks):
    source = new_document()
    source["state"]["model"] = serialize_model_state_with_warnings(model)[0]
    source["state"]["marks"] = marks
    return source


def fragment_document():
    """Every fragment side by side, with the centres the desktop warns about."""
    model, marks, warned = MoleculeModel(), [], set()
    for index, (element, charge, radical, neighbours, warns) in enumerate(FRAGMENTS):
        x = 60.0 + 80.0 * index
        centre = model.add_atom(element, x, 100.0)
        if charge or radical:
            model.set_atom_annotation(
                centre, {"formal_charge": charge, "radical_electrons": radical}
            )
            marks += charge_marks(centre, x, 100.0, charge, radical)
        if warns:
            warned.add(centre)
        for turn, (neighbour, order, *style) in enumerate(neighbours):
            sign = -1 if turn % 2 else 1
            other = model.add_atom(neighbour, x + 20.0 * sign, 120.0 + 20.0 * turn)
            bond_id = model.add_bond(centre, other, order)
            model.bonds[bond_id] = replace(
                model.bonds[bond_id], style=style[0] if style else STYLES[order]
            )
    return document_of(model, marks), warned


def nitrogen_model():
    """A nitrogen with four single bonds, which the desktop warns about unless N+."""
    model = MoleculeModel()
    centre = model.add_atom("N", 100.0, 100.0)
    for dx, dy in ((20.0, 0.0), (-20.0, 0.0), (0.0, 20.0), (0.0, -20.0)):
        model.add_bond(centre, model.add_atom("C", 100.0 + dx, 100.0 + dy), 1)
    return model, centre


def native_warnings(canvas):
    return sorted(canvas.runtime_state.valence_warnings.warnings_for(canvas.model))


def test_browser_valence_warnings_match_the_desktop_and_change_nothing(desktop_canvas):
    source, warned = fragment_document()
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    # Start from the serialized native state so atom IDs are identical.
    source["state"] = documents.snapshot_state()
    before = deepcopy(source)
    browser = drawing_geometry(extract_document_state(source))["valence_warnings"]
    assert browser == native_warnings(desktop_canvas) == sorted(warned)
    assert source == before


@pytest.mark.parametrize(
    ("stored", "mark", "warned"),
    [(None, False, True), (None, True, True), (1, False, False), (1, True, False)],
)
def test_browser_valence_reads_stored_charges_as_the_desktop_does(
    desktop_canvas, stored, mark, warned
):
    # Restoring a mark shows the stored annotation; it never hydrates one.
    model, centre = nitrogen_model()
    if stored:
        model.set_atom_annotation(centre, {"formal_charge": stored})
    marks = charge_marks(centre, 100.0, 100.0, 1, 0) if mark else []
    source = document_of(model, marks)
    desktop_canvas.services.canvas_document_session_service.apply_state(
        extract_document_state(source)
    )
    browser = drawing_geometry(extract_document_state(source))["valence_warnings"]
    assert browser == native_warnings(desktop_canvas) == ([centre] if warned else [])


def test_browser_valence_warnings_follow_charge_edits_history_and_reopening(
    desktop_canvas,
):
    from tests.test_web_adapter import native_mark_measurements

    model, centre = nitrogen_model()
    source = document_of(model, [])
    documents = desktop_canvas.services.canvas_document_session_service
    documents.apply_state(extract_document_state(source))
    assert native_warnings(desktop_canvas) == [centre]
    desktop_canvas.services.canvas_mark_scene_service.change_charge_for_atom(centre, 1)
    assert native_warnings(desktop_canvas) == []

    model.set_atom_annotation(centre, {"formal_charge": 1})
    charged = document_of(model, charge_marks(centre, 100.0, 100.0, 1, 0))
    font = native_mark_measurements(charged, glyph_ink=True)
    session = BrowserSession()
    session.font = font
    loaded = session.dispatch({"action": "load", "revision": 0, "document": source})
    assert loaded["drawing"]["valence_warnings"] == [centre]
    change = {"kind": "hover_shortcut", "x": 100, "y": 100, "atom_id": 0, "key": "+"}
    edited = session.dispatch({"action": "edit", "revision": 1, "edit": change})
    assert edited["drawing"]["valence_warnings"] == []
    # A rejected edit leaves the accepted drawing and its warnings as they were.
    with pytest.raises((ValueError, KeyError, TypeError)):
        session.dispatch({"action": "edit", "revision": 2, "edit": {"kind": "unknown"}})
    read = session.dispatch({"action": "read"})
    assert (read["revision"], read["drawing"]["valence_warnings"]) == (2, [])
    undone = session.dispatch({"action": "undo", "revision": 2})
    assert undone["drawing"]["valence_warnings"] == [centre]
    redone = session.dispatch({"action": "redo", "revision": 3})
    assert redone["drawing"]["valence_warnings"] == []
    exported = session.dispatch({"action": "export", "revision": 4})["document"]
    assert "valence" not in json.dumps(exported)
    reopened = BrowserSession()
    reopened.font = font
    load = {"action": "load", "revision": 0, "document": exported}
    assert reopened.dispatch(load)["drawing"]["valence_warnings"] == []


@pytest.mark.parametrize("length", [20, 40])
@pytest.mark.parametrize("label", [None, "N", "O", "C", "NH2"])
def test_valence_feedback_sits_on_the_desktop_atom_items(desktop_canvas, length, label):
    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
    from tests.test_web_adapter import native_mark_measurements

    canvas = desktop_canvas
    canvas.renderer.set_bond_length(length)
    canvas.services.structure_build_service.add_bond_between_points(
        QPointF(20, 20), QPointF(20 + length, 20), "single", 1
    )
    if label is not None:
        canvas.services.atom_label_service.add_or_update_atom_label(0, label)
    source = new_document()
    source["state"] = canvas.services.canvas_document_session_service.snapshot_state()
    drawing = document_info(source, font=native_mark_measurements(source))["drawing"]
    script = (
        "import {readFileSync} from 'node:fs';"
        "import {valenceWarningBounds} from './app/chemvas/web/scene.mjs';"
        "const {document, drawing} = JSON.parse(readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify([0, 1].map("
        "id => valenceWarningBounds(document, drawing, id))));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps({"document": source, "drawing": drawing}),
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
    )
    for atom_id, bounds in enumerate(json.loads(result.stdout)):
        native = visible_atom_item_for(canvas, atom_id).sceneBoundingRect().getRect()
        assert bounds == pytest.approx(native, abs=1e-8, rel=0)


def test_browser_valence_warnings_need_no_qt():
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from chemvas.bootstrap.web_adapter import document_info, new_document; "
        "from chemvas.domain.document import MoleculeModel, serialize_model_state_with_warnings; "
        "model = MoleculeModel(); c = model.add_atom('C', 100, 100); "
        "[model.add_bond(c, model.add_atom('C', 60 + 20 * i, 140), 1) for i in range(5)]; "
        "doc = new_document(); doc['state']['model'] = serialize_model_state_with_warnings(model)[0]; "
        "assert document_info(doc)['drawing']['valence_warnings'] == [c]; "
        "assert not any(name.startswith('PyQt6') for name in sys.modules)"
    )
    subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", script, str(ROOT / "app")], check=True
    )
