import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QInputMethodEvent, QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_service_ports import note_controller_for_access
from chemvas.ui.input_view_access import (
    chemdraw_shortcut_text_for,
    should_override_chemdraw_shortcut_for,
)
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.structure_mutation_access import add_atom_for, add_bond_for


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def drawing(app):
    window = build_main_window()
    window.resize(1000, 700)
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowExposed(window, 5000)
    assert QTest.qWaitForWindowActive(window, 5000)
    canvas = active_canvas_for_window(window)
    canvas.services.input.tool_mode_controller.set_tool("select")
    canvas.centerOn(0, 0)
    canvas.setFocus()
    yield window, canvas
    services_for_window(window).canvas_document_service.mark_clean(canvas)
    window.close()
    app.processEvents()


@pytest.fixture
def pointer(monkeypatch):
    def move(canvas, scene_pos):
        local = canvas.mapFromScene(scene_pos)
        global_pos = canvas.viewport().mapToGlobal(local)
        # Wayland need not support pointer warping. Inject the cursor source
        # and a real Qt mouse event, leaving hit testing and key dispatch real.
        monkeypatch.setattr("chemvas.ui.hover.QCursor.pos", lambda: global_pos)
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(local),
            QPointF(global_pos),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(canvas.viewport(), event)

    return move


def _letter_event(letter, *, shift=False, caps=False, event_type=QEvent.Type.KeyPress):
    text = letter.upper() if shift != caps else letter.lower()
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )
    return QKeyEvent(event_type, ord(letter.upper()), modifiers, text)


@pytest.mark.parametrize("caps", [False, True])
@pytest.mark.parametrize("shift", [False, True])
@pytest.mark.parametrize(
    "letter,plain,shifted",
    [
        ("o", "O", "OMe"),
        ("c", "C", "Cl"),
        ("n", "N", "NO2"),
        ("s", "S", "Si"),
        ("h", "H", "Cbz"),
    ],
)
def test_atom_hotkeys_follow_shift_not_caps_lock(
    drawing, pointer, caps, shift, letter, plain, shifted
):
    _window, canvas = drawing
    atom_id = add_atom_for(canvas, "C", 0, 0)
    pointer(canvas, QPointF())
    assert hover_state_for(canvas).atom_id == atom_id
    event = _letter_event(letter, shift=shift, caps=caps)
    assert should_override_chemdraw_shortcut_for(canvas, event)
    QApplication.sendEvent(canvas, event)
    assert canvas.model.atoms[atom_id].element == (shifted if shift else plain)


@pytest.mark.parametrize("caps", [False, True])
@pytest.mark.parametrize("letter", ["a", "z"])
def test_atom_sprouts_are_not_caps_lock_alias_labels(drawing, pointer, caps, letter):
    _window, canvas = drawing
    atom_id = add_atom_for(canvas, "C", 0, 0)
    pointer(canvas, QPointF())
    event = _letter_event(letter, caps=caps)
    assert should_override_chemdraw_shortcut_for(canvas, event)
    QApplication.sendEvent(canvas, event)
    assert canvas.model.atoms[atom_id].element == "C"
    assert sum(atom is not None for atom in canvas.model.atoms) > 1
    if letter == "z":
        assert any(bond is not None and bond.order == 3 for bond in canvas.model.bonds)


@pytest.mark.parametrize("caps", [False, True])
@pytest.mark.parametrize(
    "letter,shift,style,order",
    [
        ("w", False, "wedge", 1),
        ("b", False, "bold_in", 1),
        ("d", False, "dotted", 1),
        ("b", True, "bold_in", 2),
        ("d", True, "dotted_double", 2),
        ("h", True, "hash", 1),
    ],
)
def test_bond_hotkeys_and_override_follow_shift_not_caps_lock(
    drawing, pointer, caps, letter, shift, style, order
):
    _window, canvas = drawing
    a = add_atom_for(canvas, "C", -40, 0)
    b = add_atom_for(canvas, "C", 40, 0)
    bond_id = add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    pointer(canvas, QPointF())
    assert hover_state_for(canvas).bond_id == bond_id
    event = _letter_event(letter, shift=shift, caps=caps)
    assert should_override_chemdraw_shortcut_for(canvas, event)
    QApplication.sendEvent(canvas, event)
    bond = canvas.model.bonds[bond_id]
    assert (bond.style, bond.order) == (style, order)


@pytest.mark.parametrize("caps", [False, True])
def test_caps_lock_bond_fusion_overrides_the_tool_shortcut(drawing, pointer, caps):
    window, canvas = drawing
    a = add_atom_for(canvas, "C", -20, 0)
    b = add_atom_for(canvas, "C", 20, 0)
    bond_id = add_bond_for(canvas, a, b)
    canvas.services.structure.structure_build_service.render_model()
    pointer(canvas, QPointF())
    assert hover_state_for(canvas).bond_id == bond_id
    assert should_override_chemdraw_shortcut_for(canvas, _letter_event("a", caps=caps))
    QApplication.sendEvent(canvas, _letter_event("a", caps=caps))
    assert sum(atom is not None for atom in canvas.model.atoms) == 6
    assert (
        services_for_window(window).context_bar_service.active_tool_name(window)
        == "select"
    )


@pytest.mark.parametrize("text", ["+", "-", "1", "!", "é", "ß", "한", "", "ab"])
@pytest.mark.parametrize("shift", [False, True])
def test_shortcut_case_normalization_preserves_non_ascii_and_symbol_text(text, shift):
    modifiers = (
        Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
    )
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_unknown, modifiers, text)
    assert chemdraw_shortcut_text_for(event) == text


@pytest.mark.parametrize(
    "modifiers", [Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier]
)
def test_modified_uppercase_letters_do_not_relabel_hovered_atoms(
    drawing, pointer, modifiers
):
    _window, canvas = drawing
    atom_id = add_atom_for(canvas, "C", 0, 0)
    pointer(canvas, QPointF())
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_O, modifiers, "O")
    assert not should_override_chemdraw_shortcut_for(canvas, event)
    assert not canvas.services.input.chemdraw_shortcut_service.handle_atom_hotkey(
        event, atom_id
    )
    assert canvas.model.atoms[atom_id].element == "C"


def test_note_editor_keeps_caps_text_and_ime_commit_without_atom_hotkeys(
    drawing, pointer
):
    _window, canvas = drawing
    atom_id = add_atom_for(canvas, "C", 0, 0)
    pointer(canvas, QPointF())
    controller = note_controller_for_access(canvas)
    note = controller.create_text_note(QPointF(-80, 60), "")
    controller.begin_note_edit(note)
    QApplication.sendEvent(canvas, _letter_event("o", caps=True))
    QApplication.sendEvent(canvas, _letter_event("o", shift=True, caps=True))
    event = QInputMethodEvent()
    event.setCommitString("한é")
    QApplication.sendEvent(canvas, event)
    assert note.toPlainText() == "Oo한é"
    assert canvas.model.atoms[atom_id].element == "C"
    controller.finish_note_edit()
