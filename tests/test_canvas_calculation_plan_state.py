from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_view import CanvasView
from tests.test_calculation_plan import _document_state, _plan


def test_calculation_plan_survives_canvas_apply_snapshot_and_old_document_clear() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    service = canvas_services_for(canvas).document.canvas_document_session_service
    state = _document_state()
    state["calculation_plan"] = _plan()

    service.apply_state(state)
    snapshot = service.snapshot_state()

    assert snapshot["calculation_plan"] == _plan()

    legacy_state = _document_state()
    service.apply_state(legacy_state)

    assert "calculation_plan" not in service.snapshot_state()
    canvas.deleteLater()


def test_snapshot_omits_stale_plan_with_a_user_visible_warning() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    service = canvas_services_for(canvas).document.canvas_document_session_service
    state = _document_state()
    stale_plan = _plan()
    stale_plan["states"][0]["members"][0]["component_atom_ids"] = [0]  # type: ignore[index]
    # Apply bypasses the file trust boundary just as an in-memory graph edit can
    # make a previously valid plan stale after it has been loaded.
    state["calculation_plan"] = stale_plan
    service.apply_state(state)

    snapshot, warnings = service.snapshot_state_with_warnings()

    assert "calculation_plan" not in snapshot
    assert any("calculation plan was not saved" in warning for warning in warnings)
    canvas.deleteLater()
