from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QGraphicsSimpleTextItem

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.dialogs.calculation_plan_actions import (
    open_calculation_panel_for_window,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.calculation_plan_support import _document_state, _plan

if TYPE_CHECKING:
    from collections.abc import Iterator

    from chemvas.ui.window.main_window_like import MainWindowLike


@pytest.fixture
def window() -> Iterator[MainWindowLike]:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
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
    open_calculation_panel_for_window(window)
    app.processEvents()
    yield window
    window.ui_references.calculation_panel.shutdown()
    window.close_after_confirmation()
    app.processEvents()


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
    QTest.mouseMove(canvas.viewport(), point)
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
        {
            "handoff": {"status": "ready"},
            "payload": {"data": {"endpoint_geometry": {"sides": {}}}},
        },
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
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(atom.x, atom.y)))
    labels = [
        item
        for item in panel.mapping.highlighter._label_items
        if isinstance(item, QGraphicsSimpleTextItem)
    ]
    assert len(labels) == 2
    assert {item.data(1) for item in labels} == {0, 2}
    assert "reactant #0" in editor.suggestion_status.text()
    assert "product #2" in editor.suggestion_status.text()
    QTest.mouseMove(
        canvas.viewport(), canvas.mapFromScene(QPointF(atom.x, atom.y + 100))
    )
    assert not panel.mapping.highlighter._label_items
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(atom.x, atom.y)))
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
