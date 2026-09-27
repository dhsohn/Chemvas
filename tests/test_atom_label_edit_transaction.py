"""A forward atom-label edit is one document transaction, restored on failure."""

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest

from chemvas.core.model_commands import AddAtomsCommand
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


def _click_text_tool(canvas, app, symbol: str) -> None:
    tools = canvas.services.tool_mode_controller
    tools.set_tool("text")
    tools.set_atom_symbol(symbol)
    point = canvas.mapFromScene(QPointF(60, 40))
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
