"""Native ring-fill opacity retains source precision across GUI workflows."""

import math
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QToolButton

from chemvas.bootstrap.main_window import build_main_window
from chemvas.core.document_io import read_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_window_access import snapshot_canvas_state_for
from chemvas.ui.history_commands import UpdateSceneItemCommand
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_item_access import apply_scene_item_state
from chemvas.ui.scene_item_restore import create_ring_item_from_state
from chemvas.ui.scene_item_state_serialization import ring_state_dict
from tests.canvas_factory import build_canvas_view


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def canvas(app):
    view = build_canvas_view()
    yield view
    view.services.document.canvas_scene_reset_service.clear_scene()
    view.close()
    app.processEvents()


def _load(canvas, alpha):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {
                    "id": index,
                    "element": "C",
                    "x": 20 * math.cos(index * math.pi / 3),
                    "y": 20 * math.sin(index * math.pi / 3),
                }
                for index in range(6)
            ],
            "bonds": [{"a": i, "b": (i + 1) % 6, "order": 1} for i in range(6)],
            "ring_fills": [
                {"atom_ids": list(range(6)), "color": "#ffcc00", "alpha": alpha}
            ],
        }
    )
    state = apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": "a" * 64,
            "operations": [{"op": "move_atom", "atom_id": 0, "x": 21.0, "y": 0.0}],
        },
        source_sha256="a" * 64,
        document_version=CANVAS_FILE_VERSION,
    ).state
    canvas.services.document.canvas_document_session_service.apply_state(state)
    return state


@pytest.mark.parametrize("alpha", [0.0, 1.0, 0.25, 0.3, 0.5, 1e-8, 1 - 1e-8])
def test_ring_alpha_survives_compose_patch_gui_save_reopen(canvas, tmp_path, alpha):
    state = _load(canvas, alpha)
    session = canvas.services.document.canvas_document_session_service
    assert state["ring_fills"][0]["alpha"] == alpha
    assert snapshot_canvas_state_for(canvas)["ring_fills"][0]["alpha"] == alpha
    for number in range(2):
        output = tmp_path / f"reopened-{number}.chemvas"
        assert session.save_to_file(str(output)) == []
        saved = read_document(output).state
        assert saved["ring_fills"][0]["alpha"] == alpha
        session.apply_state(saved)
        assert snapshot_canvas_state_for(canvas)["ring_fills"][0]["alpha"] == alpha


@pytest.mark.parametrize("action", ["fill", "clear", "structure_color"])
def test_ring_color_history_restores_exact_source_alpha_without_stale_replay(
    canvas, action
):
    _load(canvas, 0.3)
    ring = ring_items_for(canvas)[0]
    before = snapshot_canvas_state_for(canvas)
    service = canvas.services.scene_operations.canvas_color_mutation_service
    if action == "structure_color":
        service.apply_color_to_items([ring], QColor("#cc3344"))
    else:
        service.apply_ring_fill_color_to_items(
            [ring], QColor("#cc3344"), alpha=0.0 if action == "clear" else 0.25
        )
    after = snapshot_canvas_state_for(canvas)
    assert after != before
    assert (
        after["ring_fills"][0]["alpha"]
        == {"fill": 1.0, "clear": 0.0, "structure_color": 0.3}[action]
    )
    for _ in range(2):
        canvas.services.history_service.undo()
        assert snapshot_canvas_state_for(canvas) == before
        canvas.services.history_service.redo()
        assert snapshot_canvas_state_for(canvas) == after


@pytest.mark.parametrize("publication", ["raise", "false"])
def test_ring_fill_failed_publication_preserves_precise_alpha_and_redo(
    canvas, publication
):
    _load(canvas, 0.3)
    ring = ring_items_for(canvas)[0]
    history = canvas.services.history_service
    add_arrow_for(canvas, QPointF(100, 100), QPointF(150, 100), "line")
    history.undo()
    assert history.can_redo()
    before = snapshot_canvas_state_for(canvas)
    stacks = history.capture_stack_snapshot()
    behavior = (
        {"side_effect": RuntimeError("publish failed")}
        if publication == "raise"
        else {"return_value": False}
    )
    with mock.patch.object(history, "push", **behavior), pytest.raises(RuntimeError):
        canvas.services.scene_operations.canvas_color_mutation_service.apply_ring_fill_color_to_items(
            [ring], QColor("#cc3344")
        )
    assert snapshot_canvas_state_for(canvas) == before
    assert before["ring_fills"][0]["alpha"] == 0.3
    history.verify_stack_snapshot(stacks)


def test_ring_alpha_metadata_never_overrides_a_changed_or_absent_brush(canvas):
    _load(canvas, 0.3)
    ring = ring_items_for(canvas)[0]
    changed = QColor("#ffaa11")
    changed.setAlphaF(0.6)
    ring.setBrush(changed)
    assert (
        snapshot_canvas_state_for(canvas)["ring_fills"][0]["alpha"] == changed.alphaF()
    )
    ring.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    assert snapshot_canvas_state_for(canvas)["ring_fills"][0]["alpha"] == 0.0


def test_subchannel_alpha_history_edit_retains_both_exact_values(canvas):
    _load(canvas, 0.3)
    ring = ring_items_for(canvas)[0]
    before = ring_state_dict(ring)
    after = dict(before, alpha=0.3000000001)
    painted_alpha = ring.brush().color().alphaF()
    apply_scene_item_state(canvas, ring, after)
    # Two distinct document opacities deliberately have identical Qt paint.
    assert ring.brush().color().alphaF() == painted_alpha
    assert ring_state_dict(ring) == after
    history = canvas.services.history_service
    history.push(UpdateSceneItemCommand(ring, before, after))
    history.undo()
    assert ring_state_dict(ring) == before
    history.redo()
    assert ring_state_dict(ring) == after


def test_colorless_ring_retains_existing_no_brush_semantics(app):
    ring = create_ring_item_from_state(
        {"points": [(0, 0), (20, 0), (10, 20)], "color": None, "alpha": 0.3},
        ring_fill_brush_getter=lambda: QBrush(Qt.BrushStyle.NoBrush),
    )
    assert ring_state_dict(ring)["color"] is None
    assert ring_state_dict(ring)["alpha"] == 0.0


def test_precise_ring_alpha_survives_native_clipboard_and_paste_history(canvas):
    _load(canvas, 0.3)
    ring = ring_items_for(canvas)[0]
    ring.setSelected(True)
    clipboard = canvas.services.scene_operations.scene_clipboard_controller
    # Use the native payload boundary without modifying the user's clipboard.
    payload = clipboard.selection_payload_for_clipboard()
    assert payload["rings"][0]["alpha"] == 0.3
    before = snapshot_canvas_state_for(canvas)
    assert clipboard.paste_selection_from_clipboard(
        payload_provider=lambda: (payload, "precise-ring-fill")
    )
    after = snapshot_canvas_state_for(canvas)
    assert len(after["ring_fills"]) == 2
    assert all(state["alpha"] == 0.3 for state in after["ring_fills"])
    canvas.services.history_service.undo()
    assert snapshot_canvas_state_for(canvas) == before
    canvas.services.history_service.redo()
    assert snapshot_canvas_state_for(canvas) == after


def test_real_ring_palette_edit_never_resurrects_loaded_alpha(app):
    window = build_main_window()
    window.show()
    assert QTest.qWaitForWindowExposed(window, 5000)
    canvas = active_canvas_for_window(window)
    try:
        _load(canvas, 0.3)
        ring_items_for(canvas)[0].setSelected(True)
        before = snapshot_canvas_state_for(canvas)
        window.ui_references.tool_actions["ring_fill"].trigger()
        app.processEvents()
        button = next(
            widget
            for widget in window.findChildren(QToolButton)
            if widget.toolTip() == "Ring Fill: Yellow"
        )
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        after = snapshot_canvas_state_for(canvas)
        assert after != before
        assert after["ring_fills"][0]["alpha"] == 1.0
        for _ in range(2):
            canvas.services.history_service.undo()
            assert snapshot_canvas_state_for(canvas) == before
            canvas.services.history_service.redo()
            assert snapshot_canvas_state_for(canvas) == after
    finally:
        services_for_window(window).canvas_document_service.mark_clean(canvas)
        window.close()
        app.processEvents()
