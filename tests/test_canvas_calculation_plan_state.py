from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.ui.canvas.canvas_view import CanvasView
from tests.calculation_plan_support import _document_state, _plan


def test_calculation_plan_survives_canvas_apply_snapshot_and_old_document_clear() -> (
    None
):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    service = canvas.services.canvas_document_session_service
    state = _document_state()
    state["calculation_plan"] = _plan()

    service.apply_state(state)
    snapshot = service.snapshot_state()

    assert snapshot["calculation_plan"] == _plan()

    legacy_state = _document_state()
    service.apply_state(legacy_state)

    assert "calculation_plan" not in service.snapshot_state()
    canvas.deleteLater()


@pytest.mark.parametrize("kind", ["stale", "invalid"])
def test_snapshot_omits_unsavable_plan_with_a_warning_for_its_cause(
    kind: str,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    service = canvas.services.canvas_document_session_service
    state = _document_state()
    plan = _plan()
    if kind == "stale":
        plan["states"][0]["members"][0]["component_atom_ids"] = [0]  # type: ignore[index]
    else:
        plan["states"][0]["multiplicity"] = 0  # type: ignore[index]
    # Apply skips file validation, so the canvas keeps the plan as given. The
    # stale plan stands for one that a graph edit left behind after a valid load.
    state["calculation_plan"] = plan
    service.apply_state(state)

    snapshot, warnings = service.snapshot_state_with_warnings()

    assert "calculation_plan" not in snapshot
    [warning] = [
        warning for warning in warnings if "calculation plan was not saved" in warning
    ]
    if kind == "stale":
        assert "molecular graph no longer matches" in warning
        assert "Undo the graph edit" in warning
    else:
        assert "State R01 multiplicity must be positive." in warning
        assert "graph" not in warning
        assert "Undo" not in warning
    canvas.deleteLater()
