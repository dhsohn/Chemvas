from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication, QGraphicsScene
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    import chemvas.ui.calculation_mapping_highlight as highlight_module
    from chemvas.adapters.qt.renderer import Renderer
    from chemvas.ui.calculation_mapping_highlight import (
        CalculationMappingHighlighter,
    )
    from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
    from chemvas.ui.canvas_service_access import canvas_services_for
    from chemvas.ui.canvas_view import CanvasView

from tests.test_calculation_plan import _document_state


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_labels_atoms_with_endpoint_tints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    canvas = SimpleNamespace(scene=lambda: scene)
    centers = {
        1: QPointF(5.0, 5.0),
        2: QPointF(25.0, 5.0),
        3: QPointF(45.0, 5.0),
    }
    monkeypatch.setattr(
        highlight_module,
        "atom_center_point_for",
        lambda _canvas, atom_id: centers.get(atom_id),
    )
    highlighter = CalculationMappingHighlighter(canvas)

    highlighter.show_atom_labels({1, 2}, {2, 3})

    labels = [
        item for item in scene.items() if item.data(0) == "calculation_atom_id_label"
    ]
    assert {item.data(1) for item in labels} == {1, 2, 3}
    color_by_id = {item.data(1): item.brush().color().name() for item in labels}
    # Reactant-set atoms (1, 2) take the reactant tint; 2 stays reactant even
    # though it is also in the product set, and product-only 3 takes the
    # product tint.
    assert color_by_id[1] == "#0072b2"
    assert color_by_id[2] == "#0072b2"
    assert color_by_id[3] == "#d55e00"

    # The id hugs the atom's own anchor, sitting within a few units of the
    # center rather than floating away from the glyph.
    label_3 = next(item for item in labels if item.data(1) == 3)
    assert abs(label_3.pos().x() - centers[3].x()) < 10.0

    highlighter.clear_all()
    assert scene.items() == []


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_grays_out_excluded_atom_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    canvas = SimpleNamespace(scene=lambda: scene)
    centers = {
        1: QPointF(5.0, 5.0),
        2: QPointF(25.0, 5.0),
        3: QPointF(45.0, 5.0),
    }
    monkeypatch.setattr(
        highlight_module,
        "atom_center_point_for",
        lambda _canvas, atom_id: centers.get(atom_id),
    )
    highlighter = CalculationMappingHighlighter(canvas)

    highlighter.show_atom_labels({1}, {2}, {2, 3})

    labels = [
        item for item in scene.items() if item.data(0) == "calculation_atom_id_label"
    ]
    color_by_id = {item.data(1): item.brush().color().name() for item in labels}
    # Only atoms outside both endpoint sets go gray; an excluded id that is
    # also included keeps its endpoint tint.
    assert color_by_id == {1: "#0072b2", 2: "#d55e00", 3: "#9b9b96"}


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_tolerates_missing_scene() -> None:
    highlighter = CalculationMappingHighlighter(SimpleNamespace(scene=lambda: None))

    highlighter.show_atom_labels({1}, {2})
    highlighter.clear_all()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_real_canvas_labels_are_transient_and_preserve_document_selection() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView(renderer=Renderer())
    document_service = canvas_services_for(
        canvas
    ).document.canvas_document_session_service
    document_service.apply_state(_document_state())
    selected = visible_atom_item_for(canvas, 0)
    assert selected is not None
    selected.setSelected(True)
    before = document_service.snapshot_state()
    highlighter = CalculationMappingHighlighter(canvas)

    highlighter.show_atom_labels({0}, {2}, {1})

    labels = [
        item
        for item in canvas.scene().items()
        if item.data(0) == "calculation_atom_id_label"
    ]
    assert {item.data(1) for item in labels} == {0, 1, 2}
    assert selected.isSelected() is True
    assert document_service.snapshot_state() == before

    highlighter.clear_all()

    assert not any(
        item.data(0) == "calculation_atom_id_label" for item in canvas.scene().items()
    )
    assert selected.isSelected() is True
    assert document_service.snapshot_state() == before
    canvas.deleteLater()
