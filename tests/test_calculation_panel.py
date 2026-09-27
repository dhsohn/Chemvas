from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QEnterEvent, QTransform
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsSimpleTextItem,
    QLabel,
    QPushButton,
    QToolButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
from chemvas.ui.dialogs.calculation_plan_actions import (
    open_calculation_panel_for_window,
)
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.calculation_plan_support import _document_state, _plan

if TYPE_CHECKING:
    from collections.abc import Iterator

    from chemvas.ui.window.main_window_like import MainWindowLike


@pytest.fixture(scope="module")
def app() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def window(app: QApplication) -> Iterator[MainWindowLike]:
    window = build_main_window()
    state = _document_state()
    for atom in state["model"]["atoms"].values():
        atom["x"] *= 40
        atom["y"] *= 40
    state["calculation_plan"] = _plan()
    active_canvas_for_window(
        window
    ).services.canvas_document_session_service.apply_state(state)
    window.resize(1200, 850)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window, 5000)
    open_calculation_panel_for_window(window)
    app.processEvents()
    yield window
    window.ui_references.calculation_panel.shutdown()
    window.close_after_confirmation()
    app.processEvents()


def _hover_mapping(canvas, mapping, point: QPoint, expected: int | None) -> None:
    # Native mouse moves may arrive after QTest.mouseMove returns. Move away
    # first so a cursor left at this position by an earlier test still moves.
    QTest.mouseMove(canvas.viewport(), QPoint(1, 1))
    QTest.qWait(20)
    QTest.mouseMove(canvas.viewport(), point)
    deadline = time.monotonic() + 2.0
    while mapping._hovered != expected and time.monotonic() < deadline:
        QTest.qWait(10)
    assert mapping._hovered == expected


def test_panel_reuses_main_canvas_without_opening_a_dialog(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    assert window.dockWidgetArea(panel) == Qt.DockWidgetArea.RightDockWidgetArea
    assert not panel.isFloating()
    editor = panel.editor
    assert not editor.isWindow()
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    canvas.services.tool_mode_controller.set_tool("bond")
    canvas.centerOn(100, 0)
    editor.tabs.setCurrentIndex(1)
    editor._clear_active_mappings()
    editor.mapping_mode.setChecked(True)
    QApplication.processEvents()
    for atom_id in (0, 2):
        atom = editor._model.atoms[atom_id]
        point = canvas.mapFromScene(QPointF(atom.x, atom.y))
        assert canvas.viewport().rect().contains(point)
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    shared_atom = editor._model.atoms[4]
    shared_position = canvas.mapFromScene(QPointF(shared_atom.x, shared_atom.y))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=shared_position)
    QTest.mouseDClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=shared_position)
    assert editor._mapping_by_reactant[4] == 4
    assert editor._mapping_by_reactant[0] == 2
    assert session.snapshot_state() == before
    point = canvas.mapFromScene(
        QPointF(editor._model.atoms[0].x, editor._model.atoms[0].y)
    )
    _hover_mapping(canvas, panel.mapping, point, 0)
    labels = [
        item
        for item in canvas.scene().items()
        if isinstance(item, QGraphicsSimpleTextItem)
        and item.data(0) == "calculation_atom_id_label"
    ]
    pair = {item.data(1): item for item in labels if item.data(1) in {0, 2}}
    assert pair[0].text() == "R 1"
    assert pair[2].text() == "P 1"
    assert pair[0].brush().color() == pair[2].brush().color()
    QTest.keyClick(canvas.viewport(), Qt.Key.Key_Escape)
    assert not editor.mapping_mode.isChecked()
    assert not [
        item
        for item in canvas.scene().items()
        if item.data(0) == "calculation_atom_id_label"
    ]
    assert session.snapshot_state() == before
    # The original drawing tool works again as soon as mapping mode exits.
    assert canvas.services.tool_controller.active.name == "bond"
    point = canvas.mapFromScene(QPointF(220, 60))
    end = canvas.mapFromScene(QPointF(260, 100))
    assert canvas.viewport().rect().contains(point)
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    assert session.snapshot_state() != before
    assert not editor.isEnabled()
    assert panel._stale


def test_panel_save_is_undoable_and_source_edit_invalidates_check(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    editor._clear_active_mappings()
    editor.accept()
    assert not panel._stale
    assert panel.editor is not editor
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    assert (
        session.snapshot_state()["calculation_plan"]["steps"][0]["atom_correspondence"]
        == []
    )
    panel.editor._check_finished(
        json.dumps(
            {
                "handoff": {"status": "ready"},
                "payload": {"data": {"endpoint_geometry": {"sides": {}}}},
            }
        ).encode(),
        b"source",
        "",
    )
    panel.editor.review_checkbox.setChecked(True)
    assert panel.editor.export_button.isEnabled()
    canvas.services.history_service.undo()
    assert (
        len(
            session.snapshot_state()["calculation_plan"]["steps"][0][
                "atom_correspondence"
            ]
        )
        == 3
    )
    assert panel._stale
    assert panel.editor._checked_artifact is None
    assert not panel.editor.isEnabled()
    panel.reload_drawing()
    assert panel.snapshot_is_current()
    assert panel.editor.isEnabled()


def test_switching_document_or_hiding_panel_exits_mapping(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    panel.editor.mapping_mode.setChecked(True)
    panel.hide()
    assert not panel.editor.mapping_mode.isChecked()
    panel.show()
    panel.editor.mapping_mode.setChecked(True)
    window.services.canvas_document_service.new_canvas(window)
    assert panel._stale
    assert not panel.editor.mapping_mode.isChecked()
    assert not panel.editor.isEnabled()


def test_entering_mapping_clears_note_selection_with_scene_selection(
    window: MainWindowLike,
) -> None:
    from chemvas.ui.selection.selection_queries import selected_scene_notes_for

    panel = window.ui_references.calculation_panel
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    state = session.snapshot_state()
    state["notes"] = [{"text": "caption", "x": 0.0, "y": 200.0}]
    session.apply_state(state)
    panel.reload_drawing()
    note = canvas.runtime_state.note_items()[0]
    assert canvas.services.selection.select_all()
    assert selected_scene_notes_for(canvas)
    assert canvas.scene().selectedItems()
    editor = panel.editor
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    assert not selected_scene_notes_for(canvas)
    assert not canvas.scene().selectedItems()
    box = note.data(21)
    assert box is None or not box.isVisible()
    before = session.snapshot_state()
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert session.snapshot_state() == before
    assert editor.mapping_mode.isChecked()
    assert not panel._stale


def test_tab_moves_keyboard_focus_off_the_canvas_during_mapping(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    for key, modifier in (
        (Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier),
        (Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier),
    ):
        canvas.setFocus()
        assert QApplication.focusWidget() is canvas
        QTest.keyClick(canvas, key, modifier)
        assert QApplication.focusWidget() is not canvas, key
    assert session.snapshot_state() == before
    assert editor.mapping_mode.isChecked()
    assert not panel._stale


def test_mapping_keeps_drawing_gestures_and_hotkeys_off_the_canvas(
    window: MainWindowLike, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6.QtWidgets import QInputDialog, QMenu

    from chemvas.ui.tools import hover as hover_module

    menus: list[list[str]] = []
    monkeypatch.setattr(
        QMenu,
        "exec",
        lambda menu, *_args: menus.append([item.text() for item in menu.actions()]),
    )
    prompts: list[str] = []

    def record_prompt(_parent, title, *_args, **_kwargs):
        prompts.append(title)
        return "", False

    monkeypatch.setattr(QInputDialog, "getText", record_prompt)
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    before = session.snapshot_state()
    canvas.services.tool_mode_controller.set_tool("bond")
    canvas.centerOn(100, 0)
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    QApplication.processEvents()
    oxygen = editor._model.atoms[1]
    point = canvas.mapFromScene(QPointF(oxygen.x, oxygen.y))
    global_point = canvas.viewport().mapToGlobal(point)
    # Drawing hover resolves its target from the global cursor position.
    monkeypatch.setattr(
        hover_module, "QCursor", type("Cursor", (), {"pos": lambda: global_point})
    )
    double_bond = canvas.mapFromScene(QPointF(20, 0))
    for position in (point, double_bond):
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.RightButton, pos=position)
    QApplication.sendEvent(
        canvas.viewport(),
        QEnterEvent(QPointF(point), QPointF(point), QPointF(global_point)),
    )
    QTest.qWait(20)
    hover = canvas.runtime_state.hover_preview_state
    assert menus == []
    assert hover.atom_id is None and hover.bond_id is None
    canvas.setFocus()
    for key in (
        Qt.Key.Key_Plus,
        Qt.Key.Key_1,
        Qt.Key.Key_N,
        Qt.Key.Key_Return,
        Qt.Key.Key_Delete,
        Qt.Key.Key_Space,
        Qt.Key.Key_A,
    ):
        QTest.keyClick(canvas, key)
        assert hover.atom_id is None, key
    assert prompts == []
    assert session.snapshot_state() == before
    assert canvas.services.tool_controller.active.name == "bond"
    assert editor.mapping_mode.isChecked()
    assert not panel._stale
    zoom = canvas.runtime_state.input_view_state.zoom
    QTest.keyClick(canvas, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
    assert canvas.runtime_state.input_view_state.zoom > zoom
    assert editor.mapping_mode.isChecked()
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert not editor.mapping_mode.isChecked()
    assert canvas.services.tool_controller.active.name == "bond"
    canvas.services.hover.update_hover_highlight(QPointF(oxygen.x, oxygen.y))
    assert hover.atom_id == 1


def test_window_minimize_and_dock_float_keep_the_geometry_check(
    window: MainWindowLike, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    cancels: list[bool] = []
    monkeypatch.setattr(editor._checker, "cancel", lambda: cancels.append(True))
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    window.setWindowState(Qt.WindowState.WindowMinimized)
    QApplication.processEvents()
    assert editor.mapping_mode.isChecked()
    window.setWindowState(Qt.WindowState.WindowNoState)
    QApplication.processEvents()
    draft = dict(editor._mapping_by_reactant)
    panel.setFloating(True)
    QApplication.processEvents()
    # Qt re-parents a floating dock with an explicit hide, which leaves canvas
    # mapping as hiding the panel does. The draft stays.
    assert not editor.mapping_mode.isChecked()
    assert editor._mapping_by_reactant == draft
    panel.setFloating(False)
    QApplication.processEvents()
    assert cancels == []
    editor.mapping_mode.setChecked(True)
    panel.hide()
    assert not editor.mapping_mode.isChecked()
    # A running check survives hiding the panel; its result is shown on reopen.
    assert cancels == []


def test_cancelled_window_close_keeps_the_editor_running(
    window: MainWindowLike, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor = window.ui_references.calculation_panel.editor
    shutdowns: list[bool] = []
    monkeypatch.setattr(editor._checker, "shutdown", lambda: shutdowns.append(True))
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    documents = window.services.document_action_service
    monkeypatch.setattr(documents, "confirm_close_window", lambda _window: False)
    window.close()
    assert window.isVisible()
    assert shutdowns == []
    assert editor.mapping_mode.isChecked()
    monkeypatch.setattr(documents, "confirm_close_window", lambda _window: True)
    window.close()
    assert not window.isVisible()
    assert shutdowns == [True]
    assert not editor.mapping_mode.isChecked()


def test_mapping_hover_and_tab_switch_keep_overlays_local(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    canvas = active_canvas_for_window(window)
    before = canvas.services.canvas_document_session_service.snapshot_state()
    editor.tabs.setCurrentIndex(1)
    editor.mapping_mode.setChecked(True)
    assert not panel.mapping.highlighter._label_items
    atom = editor._model.atoms[0]
    canvas.centerOn(atom.x, atom.y)
    _hover_mapping(
        canvas, panel.mapping, canvas.mapFromScene(QPointF(atom.x, atom.y)), 0
    )
    labels = [
        item
        for item in panel.mapping.highlighter._label_items
        if isinstance(item, QGraphicsSimpleTextItem)
    ]
    assert len(labels) == 2
    assert {item.data(1) for item in labels} == {0, 2}
    assert "reactant #0" in editor.suggestion_status.text()
    assert "product #2" in editor.suggestion_status.text()
    _hover_mapping(
        canvas, panel.mapping, canvas.mapFromScene(QPointF(atom.x, atom.y + 100)), None
    )
    assert not panel.mapping.highlighter._label_items
    _hover_mapping(
        canvas, panel.mapping, canvas.mapFromScene(QPointF(atom.x, atom.y)), 0
    )
    assert panel.mapping.highlighter._label_items
    editor.tabs.setCurrentIndex(2)
    assert not editor.mapping_mode.isChecked()
    assert not panel.mapping.highlighter._label_items
    assert canvas.services.canvas_document_session_service.snapshot_state() == before


def test_escape_inside_embedded_editor_preserves_draft(window: MainWindowLike) -> None:
    editor = window.ui_references.calculation_panel.editor
    editor._clear_active_mappings()
    editor.setFocus()
    QTest.keyClick(editor, Qt.Key.Key_Escape)
    assert editor.isVisible()
    assert editor._mapping_by_reactant[0] is None


def test_return_in_editor_fields_keeps_the_draft_unsaved(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    history = canvas.services.history_service
    before = session.snapshot_state()
    stacks = history.capture_stack_snapshot()
    editor.tabs.setCurrentIndex(0)
    editor.reactant_widgets.multiplicity.setValue(3)
    for field in (editor.reactant_widgets.multiplicity, editor.product_widgets.charge):
        field.setFocus()
        QTest.keyClick(field, Qt.Key.Key_Return)
        QTest.keyClick(field, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
    assert panel.editor is editor
    assert editor.reactant_widgets.multiplicity.value() == 3
    assert session.snapshot_state() == before
    history.verify_stack_snapshot(stacks)
    # Nothing is drawn as a default action that Return would trigger.
    assert not [
        button for button in editor.findChildren(QPushButton) if button.isDefault()
    ]
    QTest.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
    states = session.snapshot_state()["calculation_plan"]["states"]
    assert next(item for item in states if item["id"] == "R01")["multiplicity"] == 3


def test_saving_second_pair_keeps_it_selected(window: MainWindowLike) -> None:
    from copy import deepcopy

    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    state = session.snapshot_state()
    second = deepcopy(state["calculation_plan"]["steps"][0])
    second["id"] = "S02"
    state["calculation_plan"]["steps"].append(second)
    session.apply_state(state)
    panel = window.ui_references.calculation_panel
    panel.reload_drawing()
    panel.editor.step_selector.setCurrentIndex(2)
    panel.editor._clear_active_mappings()
    panel.editor.accept()
    assert panel.editor.step_selector.currentData() == "S02"
    assert panel.editor.step_id.text() == "S02"
    steps = session.snapshot_state()["calculation_plan"]["steps"]
    assert len(steps[0]["atom_correspondence"]) == 3
    assert steps[1]["atom_correspondence"] == []


def test_synchronous_worker_failure_unlocks_panel(
    window: MainWindowLike, monkeypatch
) -> None:
    editor = window.ui_references.calculation_panel.editor

    def fail(_state, _step):
        editor._checker.finished.emit(None, b"", "Missing worker executable")

    monkeypatch.setattr(editor._checker, "start", fail)
    editor._start_check()
    assert not editor._checking
    assert editor.check_button.isEnabled()
    assert editor.tabs.isTabEnabled(0)
    assert editor.tabs.isTabEnabled(1)
    assert "Missing worker executable" in editor.check_status.text()


def test_failed_reload_shows_repair_instructions_and_valid_retry_recovers(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    session = active_canvas_for_window(window).services.canvas_document_session_service
    invalid = _document_state()
    invalid["model"]["atoms"][4]["element"] = "OH"
    session.apply_state(invalid)
    before = session.snapshot_state()
    for _ in range(3):
        panel.reload_drawing()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        assert panel.editor is None
        assert panel.mapping is None
        assert not panel.snapshot_is_current()
        page = panel.scroll_area.widget()
        assert page is not None and page.isVisible()
        assert page.objectName() == "calculationLoadError"
        text = " ".join(label.text() for label in page.findChildren(QLabel))
        assert panel.notice.text() == (
            "The drawing needs attention before preparing a pair."
        )
        assert "Could not load the drawing" in text
        assert "atom 4" in text
        assert "hydroxide" in text
        assert "negative charge on O" in text
        assert not panel.findChildren(CalculationStepDialog)
        button = page.findChild(QPushButton)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert active_canvas_for_window(window).hasFocus()
        assert session.snapshot_state() == before
    session.apply_state(_document_state())
    QTest.mouseClick(panel.reload_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert panel.editor is not None and panel.editor.isEnabled()
    assert panel.scroll_area.widget() is panel.editor
    assert panel.snapshot_is_current()


@pytest.mark.parametrize("kind", ["stale", "invalid"])
def test_reload_names_why_the_saved_plan_cannot_load(
    window: MainWindowLike, kind: str
) -> None:
    panel = window.ui_references.calculation_panel
    canvas = active_canvas_for_window(window)
    state = _document_state()
    plan = _plan()
    if kind == "stale":
        plan["states"][0]["members"][0]["component_atom_ids"] = [0]
    else:
        plan["states"][0]["multiplicity"] = 0
    state["calculation_plan"] = plan
    canvas.services.canvas_document_session_service.apply_state(state)

    panel.reload_drawing()

    assert panel.editor is None
    page = panel.scroll_area.widget()
    assert page is not None and page.objectName() == "calculationLoadError"
    text = " ".join(label.text() for label in page.findChildren(QLabel))
    if kind == "stale":
        # The drawing changed under its plan, so the drawing is what to fix.
        assert panel.notice.text() == (
            "The drawing needs attention before preparing a pair."
        )
        assert "Could not load the drawing" in text
        assert "Undo the structure change" in text
    else:
        assert panel.notice.text() == (
            "The saved calculation plan needs attention before preparing a pair."
        )
        assert "Could not load the saved calculation plan" in text
        assert "Could not load the drawing" not in text
        assert "State R01 multiplicity must be positive." in text
        assert "chemvas attach-plan" in text
        assert "Undo" not in text
        assert "structure" not in text
    assert calculation_plan_for(canvas) == plan


@pytest.mark.parametrize("zoom", [0.5, 1.0, 2.0])
def test_hidden_carbon_pick_keeps_screen_tolerance_and_saved_mapping(
    window: MainWindowLike, zoom: float, tmp_path
) -> None:
    from chemvas.core.document_io import read_exact_document, write_document
    from chemvas.domain.document import CANVAS_FILE_VERSION

    canvas = active_canvas_for_window(window)
    panel = window.ui_references.calculation_panel
    editor = panel.editor
    editor.tabs.setCurrentIndex(1)
    editor._clear_active_mappings()
    editor.mapping_mode.setChecked(True)
    canvas.setTransform(QTransform.fromScale(zoom, zoom))
    canvas.centerOn(100, 0)
    QApplication.processEvents()
    for atom_id in (0, 2):
        assert atom_id not in canvas.runtime_state.atom_graphics_state.atom_items
        assert atom_id in canvas.runtime_state.atom_graphics_state.atom_dots
        atom = editor._model.atoms[atom_id]
        point = canvas.mapFromScene(QPointF(atom.x, atom.y)) + QPoint(0, 7)
        _hover_mapping(canvas, panel.mapping, point, atom_id)
        QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
    assert editor._mapping_by_reactant[0] == 2
    editor.accept()
    snapshot = canvas.services.canvas_document_session_service.snapshot_state()
    path = tmp_path / "mapped.chemvas"
    write_document(path, snapshot, CANVAS_FILE_VERSION)
    _, restored = read_exact_document(path)
    assert restored.state["calculation_plan"] == snapshot["calculation_plan"]
    canvas.services.canvas_document_session_service.apply_state(restored.state)
    panel.reload_drawing()
    assert panel.editor._mapping_by_reactant[0] == 2


def test_reaction_mapping_toolbar_tracks_panel_visibility(
    window: MainWindowLike,
) -> None:
    panel = window.ui_references.calculation_panel
    button = window.findChild(QToolButton, "reactionMappingToggleButton")
    assert button is not None and not button.icon().isNull()
    assert button.isChecked()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert not panel.isVisible() and not button.isChecked()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert panel.isVisible() and button.isChecked()
    panel.close()
    assert not button.isChecked()


def test_canvas_selection_stays_owned_by_editor(window: MainWindowLike) -> None:
    editor = window.ui_references.calculation_panel.editor
    initial = editor.canvas_mapping_snapshot()
    assert not editor.pick_canvas_atom(2)
    assert "reactant atom first" in editor.suggestion_status.text()
    assert editor.canvas_mapping_snapshot().selected_reactant is None
    assert not editor.pick_canvas_atom(0)
    assert editor.canvas_mapping_snapshot().selected_reactant == 0
    assert initial.selected_reactant is None
    assert not editor.pick_canvas_atom(3)  # Oxygen cannot replace the carbon pair.
    assert "same element" in editor.suggestion_status.text()
    assert editor.canvas_mapping_snapshot().pairs == initial.pairs
    assert editor.pick_canvas_atom(2)
    assert editor.canvas_mapping_snapshot().selected_reactant is None
    editor.pick_canvas_atom(0)
    editor.clear_canvas_mapping_selection()
    assert editor.canvas_mapping_snapshot().selected_reactant is None
    assert editor.canvas_mapping_snapshot().pairs == initial.pairs


def test_reload_after_source_canvas_is_deleted(window: MainWindowLike) -> None:
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication

    panel = window.ui_references.calculation_panel
    source = active_canvas_for_window(window)
    panel.editor.tabs.setCurrentIndex(1)
    panel.editor.mapping_mode.setChecked(True)
    window.services.canvas_document_service.remove_canvas(window, source)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(source)
    assert panel._stale
    panel.reload_drawing()
    assert panel.canvas is active_canvas_for_window(window)
    assert panel.editor is not None
    assert not panel._stale


def test_unchanged_save_does_not_promise_an_undo_entry(window: MainWindowLike) -> None:
    panel = window.ui_references.calculation_panel
    panel.editor._clear_active_mappings()
    panel.editor.accept()
    assert "Undo restores" in panel.notice.text()
    canvas = active_canvas_for_window(window)
    session = canvas.services.canvas_document_session_service
    saved = session.snapshot_state()
    panel.editor.accept()
    assert "unchanged" in panel.notice.text()
    assert "Undo" not in panel.notice.text()
    assert session.snapshot_state() == saved
    canvas.services.history_service.undo()
    assert (
        len(
            session.snapshot_state()["calculation_plan"]["steps"][0][
                "atom_correspondence"
            ]
        )
        == 3
    )
