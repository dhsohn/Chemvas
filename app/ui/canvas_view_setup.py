from __future__ import annotations

from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

from ui.canvas_bond_renderer_state import bond_renderer_for
from ui.canvas_callback_state import callback_state_for
from ui.canvas_model_state import model_for
from ui.canvas_rdkit_state import rdkit_adapter_for
from ui.canvas_renderer_state import renderer_for
from ui.canvas_runtime_state import attach_canvas_runtime_state
from ui.canvas_services import attach_canvas_services, build_canvas_services
from ui.renderer_style_access import bond_line_width_for
from ui.scene_group_operations import expand_selection_to_groups_for
from ui.sheet_setup_access import apply_sheet_scene_rect_for
from ui.sheet_setup_logic import DEFAULT_SHEET_ORIENTATION, DEFAULT_SHEET_SIZE
from ui.sheet_setup_state import set_sheet_setup_state_for


def initialize_canvas_view(canvas) -> None:
    canvas.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    canvas.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    canvas.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    canvas.setScene(QGraphicsScene(canvas))
    canvas.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
    canvas.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
    canvas.setBackgroundBrush(QColor("#e7e7e4"))
    set_sheet_setup_state_for(canvas, DEFAULT_SHEET_SIZE, DEFAULT_SHEET_ORIENTATION)
    model_for(canvas)
    renderer_for(canvas)
    rdkit_adapter_for(canvas)
    runtime_state = attach_canvas_runtime_state(canvas)
    apply_sheet_scene_rect_for(canvas)
    canvas.setMouseTracking(True)
    canvas.viewport().setMouseTracking(True)
    canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    bond_renderer_for(canvas)
    runtime_state.tool_settings_state.arrow_line_width = bond_line_width_for(canvas)
    services = build_canvas_services(
        canvas,
        graph_state=runtime_state.graph_state,
        insert_state=runtime_state.insert_state,
        history_service=runtime_state.history_service,
    )
    attach_canvas_services(canvas, services)
    callbacks = callback_state_for(canvas)
    callbacks.scene_selection_group = partial(expand_selection_to_groups_for, canvas)
    callbacks.scene_selection_outline = services.selection_controller.update_selection_outline
    canvas.scene().selectionChanged.connect(canvas.handle_scene_selection_group_changed)
    canvas.scene().selectionChanged.connect(canvas.handle_scene_selection_outline_changed)
    services.tools.set_active("bond")


__all__ = ["initialize_canvas_view"]
