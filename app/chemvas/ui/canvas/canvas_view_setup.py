from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from chemvas.core.rdkit_adapter import RDKitAdapter
from chemvas.domain.document import MoleculeModel
from chemvas.ui.canvas.canvas_callback_state import callback_state_for
from chemvas.ui.canvas.canvas_runtime_state import attach_canvas_runtime_state
from chemvas.ui.canvas.canvas_services import (
    attach_canvas_services,
    build_canvas_services,
)
from chemvas.ui.canvas.sheet_setup_access import apply_sheet_scene_rect_for
from chemvas.ui.canvas.sheet_setup_logic import (
    DEFAULT_SHEET_ORIENTATION,
    DEFAULT_SHEET_SIZE,
)
from chemvas.ui.canvas.sheet_setup_state import set_sheet_setup_state_for
from chemvas.ui.scene.scene_rendering import build_scene_render_context


def initialize_canvas_view(canvas, *, renderer) -> None:
    canvas.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    canvas.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    canvas.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    canvas.setScene(QGraphicsScene(canvas))
    canvas.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    canvas.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
    canvas.setBackgroundBrush(QColor("#e7e7e4"))
    canvas.model = MoleculeModel()
    canvas.renderer = renderer
    canvas.rdkit = RDKitAdapter()
    # The runtime container owns the sheet state, so it has to exist before the
    # setup writes one; otherwise the write lands on the bare canvas and the
    # container builds a second, never-read copy beside it.
    runtime_state = attach_canvas_runtime_state(canvas)
    set_sheet_setup_state_for(canvas, DEFAULT_SHEET_SIZE, DEFAULT_SHEET_ORIENTATION)
    apply_sheet_scene_rect_for(canvas)
    canvas.setMouseTracking(True)
    canvas.viewport().setMouseTracking(True)
    canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    canvas.render_context = build_scene_render_context(
        scene_provider=canvas.scene,
        model_provider=lambda: canvas.model,
        renderer=renderer,
        state=runtime_state,
    )
    canvas.bond_renderer = canvas.render_context.bonds
    runtime_state.tool_settings_state.arrow_line_width = (
        canvas.renderer.style.bond_line_width
    )
    services = build_canvas_services(
        canvas,
        graph_state=runtime_state.graph_state,
        insert_state=runtime_state.insert_state,
        history_service=runtime_state.history_service,
    )
    attach_canvas_services(canvas, services)
    callbacks = callback_state_for(canvas)
    callbacks.scene_selection_group = services.selection.expand_selection_to_groups
    callbacks.scene_selection_outline = services.selection.update_selection_outline
    canvas.scene().selectionChanged.connect(canvas.handle_scene_selection_group_changed)
    canvas.scene().selectionChanged.connect(
        canvas.handle_scene_selection_outline_changed
    )
    services.tool_controller.set_active("bond")


__all__ = ["initialize_canvas_view"]
