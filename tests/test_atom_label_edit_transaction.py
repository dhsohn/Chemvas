"""A forward atom-label edit is one document transaction, restored on failure."""

import xml.etree.ElementTree as ET

import pytest
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QFontMetricsF, QKeyEvent, QTextBlockFormat
from PyQt6.QtTest import QTest

from chemvas.core.model_commands import AddAtomsCommand
from chemvas.features.cdxml_document import parse_cdxml_document, read_cdxml_document
from chemvas.ui.canvas.graphics_items import AtomLabelItem
from chemvas.ui.canvas.input_view_access import set_zoom_for
from chemvas.ui.molecule.native_atom_labels import NativeAtomLabelItem
from chemvas.ui.molecule.structure_mutation_access import add_bond_for
from tests.native_canvas_support import app as app
from tests.native_canvas_support import canvas as canvas


def _document(canvas):
    return canvas.services.canvas_document_session_service.snapshot_state()


def _scene(canvas):
    return tuple(canvas.scene().items()), tuple(canvas.scene().selectedItems())


def _fail(*_args, **_kwargs):
    raise RuntimeError("synthetic label edit failure")


def _bonded_carbon_under_oxygen(canvas) -> int:
    """A bonded carbon with an oxygen close enough for a new label to merge."""
    atoms = canvas.services.canvas_atom_mutation_service
    carbon = atoms.add_atom("C", 0.0, 0.0)
    neighbor = atoms.add_atom("C", 40.0, 0.0)
    canvas.bond_renderer.add_bond_graphics(add_bond_for(canvas, carbon, neighbor))
    atoms.add_atom("O", 0.1, -0.3)
    canvas.services.history_service.clear()
    return carbon


@pytest.mark.parametrize(
    "failing_step", ["merged label relayout", "bond redraw", "history push"]
)
def test_failed_label_hotkey_restores_document_scene_and_history(
    canvas, monkeypatch, failing_step
):
    carbon = _bonded_carbon_under_oxygen(canvas)
    labels = canvas.services.atom_label_service
    history = canvas.services.history_service
    target, name = {
        "merged label relayout": (labels, "relayout_atom_label"),
        "bond redraw": (labels.move_controller, "redraw_connected_bonds"),
        "history push": (history, "push"),
    }[failing_step]
    before = _document(canvas)
    scene_before = _scene(canvas)
    stacks = history.capture_stack_snapshot()
    key = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_N, Qt.KeyboardModifier.NoModifier, "n"
    )
    shortcuts = canvas.services.chemdraw_shortcut_service

    with monkeypatch.context() as patch:
        patch.setattr(target, name, _fail)
        with pytest.raises(RuntimeError, match="synthetic label edit failure"):
            shortcuts.handle_atom_hotkey(key, carbon)

    assert _document(canvas) == before
    assert _scene(canvas) == scene_before
    history.verify_stack_snapshot(stacks)
    assert shortcuts.handle_atom_hotkey(key, carbon)
    assert canvas.model.atoms[carbon].element == "N"
    assert len(canvas.model.atoms) == 2
    history.undo()
    assert _document(canvas) == before


def _click_text_tool(
    canvas, app, symbol: str, scene_point: QPointF | None = None
) -> None:
    tools = canvas.services.tool_mode_controller
    tools.set_tool("text")
    tools.set_atom_symbol(symbol)
    point = canvas.mapFromScene(scene_point or QPointF(60, 40))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    app.processEvents()


def test_text_tool_records_a_new_labelled_atom_as_one_undoable_edit(canvas, app):
    history = canvas.services.history_service
    before = _document(canvas)
    before_next_atom_id = canvas.model.next_atom_id

    _click_text_tool(canvas, app, "Cl")

    (atom_id,) = canvas.model.atoms
    assert canvas.model.atoms[atom_id].element == "Cl"
    (command,) = history.state.history
    assert isinstance(command, AddAtomsCommand)
    assert command.atom_states[atom_id]["element"] == "Cl"
    assert command.before_next_atom_id == before_next_atom_id
    assert command.after_next_atom_id == canvas.model.next_atom_id
    after = _document(canvas)
    history.undo()
    assert _document(canvas) == before
    history.redo()
    assert _document(canvas) == after


@pytest.mark.parametrize("failing_step", ["label draw", "history push"])
def test_failed_text_tool_atom_creation_restores_document_and_history(
    canvas, app, monkeypatch, failing_step
):
    history = canvas.services.history_service
    target, name = {
        "label draw": (canvas.services.atom_label_service.drawing, "draw_atom"),
        "history push": (history, "push"),
    }[failing_step]
    errors: list[str] = []
    canvas.runtime_state.callback_state.error = errors.append
    before = _document(canvas)
    scene_before = _scene(canvas)
    stacks = history.capture_stack_snapshot()

    with monkeypatch.context() as patch:
        patch.setattr(target, name, _fail)
        _click_text_tool(canvas, app, "N")

    assert errors
    assert _document(canvas) == before
    assert _scene(canvas) == scene_before
    history.verify_stack_snapshot(stacks)
    _click_text_tool(canvas, app, "N")
    assert [atom.element for atom in canvas.model.atoms.values()] == ["N"]
    history.undo()
    assert _document(canvas) == before


# A ChemDraw bare phosphorus below its two bonds; the source text is one line.
_NATIVE_P = b"""<CDXML LabelSize="10" LabelFont="3" LabelFace="96" BondLength="20"><fonttable><font id="3" name="Arial"/></fonttable><colortable><color r="1" g="1" b="1"/><color r="0" g="0" b="0"/></colortable><page id="1" BoundingBox="0 0 1200 600"><fragment id="2">
<n id="4717" p="966.47 274.53" Element="15" NumHydrogens="0"><t p="963.13 278.43" BoundingBox="963.13 270.09 969.80 278.43" LabelJustification="Left" LabelAlignment="Below"><s font="3" size="10" color="0">P</s></t></n>
<n id="4718" p="949.15 264.53"/><n id="4719" p="983.79 264.53"/>
<b id="4720" B="4717" E="4718"/><b id="4721" B="4717" E="4719"/>
</fragment></page></CDXML>"""


def _import_native_p(canvas) -> None:
    canvas.services.canvas_document_session_service.apply_state(
        parse_cdxml_document(_NATIVE_P, preserve_source=True).state
    )
    canvas.services.history_service.clear()


def _visible_labels(canvas) -> list[AtomLabelItem]:
    return [
        item
        for item in canvas.scene().items()
        if isinstance(item, AtomLabelItem) and item.isVisible() and item.toPlainText()
    ]


def _assert_native_p(canvas) -> None:
    assert [atom.element for atom in canvas.model.atoms.values()] == ["P", "C", "C"]
    assert len(canvas.model.bonds) == 2
    (label,) = _visible_labels(canvas)
    assert isinstance(label, NativeAtomLabelItem)
    assert label.toPlainText() == "P"
    document = label.document()
    assert document.blockCount() == 1
    block = document.begin()
    assert (
        block.blockFormat().lineHeightType()
        != QTextBlockFormat.LineHeightTypes.FixedHeight.value
    )
    label.boundingRect()
    layout = block.layout()
    line = layout.lineAt(0)
    origin = layout.position() + QPointF(line.x(), line.y() + line.ascent())
    glyph = QFontMetricsF(label.font()).tightBoundingRect("P").translated(origin)
    assert QRectF(QPointF(), document.size()).contains(glyph.adjusted(1, 1, -1, -1))
    atom = canvas.model.atoms[0]
    assert label.y() + origin.y() * label.scale() == pytest.approx(
        atom.y + 278.43 - 274.53
    )


def _assert_saved_native_p(canvas, path) -> None:
    session = canvas.services.canvas_document_session_service
    assert session.save_to_file(str(path)) == []
    root = ET.fromstring(path.read_bytes().split(b"\n<!-- ChemvasDocument:")[0])
    node = root.find('.//n[@id="4717"]')
    assert node is not None
    assert node.get("Element") == "15"
    assert "".join(run.text or "" for run in node.iter("s")) == "P"
    session.apply_state(read_cdxml_document(path).state)
    _assert_native_p(canvas)


def _atom_hotkey(canvas, app, atom_id: int, key: Qt.Key, text: str) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, text)
    assert canvas.services.chemdraw_shortcut_service.handle_atom_hotkey(event, atom_id)
    app.processEvents()


def _assert_plain_o(canvas) -> None:
    # The edit really left P, so restoring P below cannot pass as a no-op.
    assert [atom.element for atom in canvas.model.atoms.values()] == ["O", "C", "C"]
    assert [label.toPlainText() for label in _visible_labels(canvas)] == ["O"]


def test_keyboard_p_on_imported_native_p_keeps_one_line_label(canvas, app, tmp_path):
    _import_native_p(canvas)
    _assert_native_p(canvas)

    _atom_hotkey(canvas, app, 0, Qt.Key.Key_P, "p")
    _assert_native_p(canvas)

    _atom_hotkey(canvas, app, 0, Qt.Key.Key_O, "o")
    _assert_plain_o(canvas)
    _atom_hotkey(canvas, app, 0, Qt.Key.Key_P, "p")

    assert canvas.model.atoms[0].element == "P"
    _assert_native_p(canvas)
    _assert_saved_native_p(canvas, tmp_path / "keyboard-p.cdxml")


def test_atom_tool_p_on_imported_native_p_keeps_one_line_label(canvas, app, tmp_path):
    _import_native_p(canvas)
    atom = canvas.model.atoms[0]
    point = QPointF(atom.x, atom.y)
    set_zoom_for(canvas, 4)
    canvas.centerOn(point)

    _click_text_tool(canvas, app, "P", point)
    _assert_native_p(canvas)

    _click_text_tool(canvas, app, "O", point)
    _assert_plain_o(canvas)
    _click_text_tool(canvas, app, "P", point)

    assert canvas.model.atoms[0].element == "P"
    _assert_native_p(canvas)
    _assert_saved_native_p(canvas, tmp_path / "atom-tool-p.cdxml")


def test_native_p_changed_to_o_undo_redo_restores_native_p(canvas, app):
    _import_native_p(canvas)
    history = canvas.services.history_service
    before = _document(canvas)

    _atom_hotkey(canvas, app, 0, Qt.Key.Key_O, "o")

    assert canvas.model.atoms[0].element == "O"
    assert [label.toPlainText() for label in _visible_labels(canvas)] == ["O"]
    after = _document(canvas)
    history.undo()
    app.processEvents()
    assert _document(canvas) == before
    _assert_native_p(canvas)
    history.redo()
    app.processEvents()
    assert _document(canvas) == after
    assert [label.toPlainText() for label in _visible_labels(canvas)] == ["O"]
    history.undo()
    app.processEvents()
    _assert_native_p(canvas)
