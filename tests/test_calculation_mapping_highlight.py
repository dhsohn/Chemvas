from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsPathItem,
        QGraphicsRectItem,
        QGraphicsScene,
    )
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
def test_highlighter_distinguishes_mapping_without_changing_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    selected = QGraphicsRectItem(0.0, 0.0, 4.0, 4.0)
    selected.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(selected)
    selected.setSelected(True)
    canvas = SimpleNamespace(scene=lambda: scene)
    rects = {
        10: QRectF(10.0, 20.0, 12.0, 12.0),
        20: QRectF(40.0, 20.0, 12.0, 12.0),
    }
    monkeypatch.setattr(
        highlight_module,
        "selection_indicator_rect_for_atom_for",
        lambda _canvas, atom_id: rects.get(atom_id),
    )
    highlighter = CalculationMappingHighlighter(canvas)

    highlighter.show_mapping(10, 20)

    overlays = [
        item
        for item in scene.items()
        if item.data(0) == "calculation_mapping_highlight"
    ]
    paths = [item for item in overlays if isinstance(item, QGraphicsPathItem)]
    assert len(overlays) == 4
    assert {item.data(1) for item in overlays} == {"R", "P"}
    assert {path.pen().color().name() for path in paths} == {
        "#0072b2",
        "#d55e00",
    }
    assert {path.pen().style() for path in paths} == {
        Qt.PenStyle.SolidLine,
        Qt.PenStyle.DashLine,
    }
    assert scene.selectedItems() == [selected]

    highlighter.clear()

    assert scene.items() == [selected]
    assert selected.isSelected() is True


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_draws_concentric_roles_and_skips_missing_atoms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    canvas = SimpleNamespace(scene=lambda: scene)
    monkeypatch.setattr(
        highlight_module,
        "selection_indicator_rect_for_atom_for",
        lambda _canvas, atom_id: (
            QRectF(10.0, 20.0, 12.0, 12.0) if atom_id == 4 else None
        ),
    )
    highlighter = CalculationMappingHighlighter(canvas)

    highlighter.show_mapping(4, 4)

    paths = [item for item in scene.items() if isinstance(item, QGraphicsPathItem)]
    assert len(paths) == 2
    assert len({path.path().boundingRect().width() for path in paths}) == 2

    highlighter.show_mapping(4, 99)

    assert {
        item.data(1)
        for item in scene.items()
        if item.data(0) == "calculation_mapping_highlight"
    } == {"R"}


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_labels_atoms_and_coexist_with_mapping_marks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    canvas = SimpleNamespace(scene=lambda: scene)
    rects = {
        1: QRectF(0.0, 0.0, 10.0, 10.0),
        2: QRectF(20.0, 0.0, 10.0, 10.0),
        # A wide indicator rect, as a long label like OTs/PPh3 produces.
        3: QRectF(40.0, 0.0, 80.0, 10.0),
    }
    centers = {
        1: QPointF(5.0, 5.0),
        2: QPointF(25.0, 5.0),
        3: QPointF(45.0, 5.0),
    }
    monkeypatch.setattr(
        highlight_module,
        "selection_indicator_rect_for_atom_for",
        lambda _canvas, atom_id: rects.get(atom_id),
    )
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
    # Reactant-included atoms (1, 2) take the reactant tint; 2 stays reactant even
    # though it is also in the product set, and product-only 3 takes the product tint.
    assert color_by_id[1] == "#0072b2"
    assert color_by_id[2] == "#0072b2"
    assert color_by_id[3] == "#d55e00"

    # The id hugs the atom's own anchor (center x 45), not the far right edge of
    # its wide indicator rect (x 120): it sits within a few units of the center.
    label_3 = next(item for item in labels if item.data(1) == 3)
    assert abs(label_3.pos().x() - centers[3].x()) < 10.0

    # A mapping mark is a separate layer: clear() drops only the mark, not labels.
    highlighter.show_mapping(1, 2)
    assert any(
        item.data(0) == "calculation_mapping_highlight" for item in scene.items()
    )
    highlighter.clear()
    assert not any(
        item.data(0) == "calculation_mapping_highlight" for item in scene.items()
    )
    assert any(item.data(0) == "calculation_atom_id_label" for item in scene.items())

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
    # Only atoms outside both endpoints go gray; an excluded id that is also
    # included keeps its endpoint tint.
    assert color_by_id == {1: "#0072b2", 2: "#d55e00", 3: "#9b9b96"}


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_highlighter_tolerates_missing_scene() -> None:
    highlighter = CalculationMappingHighlighter(SimpleNamespace(scene=lambda: None))

    highlighter.show_mapping(1, 2)
    highlighter.show_atom_labels({1}, {2})
    highlighter.clear()
    highlighter.clear_all()


@pytest.mark.skipif(QApplication is None, reason="PyQt6 is required")
def test_real_canvas_highlight_is_transient_and_preserves_document_selection() -> None:
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

    highlighter.show_mapping(0, 2)

    overlays = [
        item
        for item in canvas.scene().items()
        if item.data(0) == "calculation_mapping_highlight"
    ]
    assert len(overlays) == 4
    assert selected.isSelected() is True
    assert document_service.snapshot_state() == before

    highlighter.clear()

    assert not any(
        item.data(0) == "calculation_mapping_highlight"
        for item in canvas.scene().items()
    )
    assert selected.isSelected() is True
    assert document_service.snapshot_state() == before
    canvas.deleteLater()
