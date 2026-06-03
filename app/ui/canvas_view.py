import math
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QNativeGestureEvent,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QInputDialog,
)

from core.history import (
    HistoryCommand,
    CompositeCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
)
from core.model import Bond, MoleculeModel
from core.renderer import Renderer
from core.rdkit_adapter import RDKitAdapter
from core.template_geometry import (
    cyclohexane_boat_points,
    cyclohexane_chair_points,
    regular_ring_radius,
    ring_points,
    scale_points_to_bond_length,
)
from ui.tools import ToolController
from ui.bond_preview_renderer import (
    BondPreviewBuildResolvers,
    BondPreviewConfig,
    BondPreviewUpdateResolvers,
    build_bond_preview_items as build_bond_preview_items_helper,
    update_bond_preview_items as update_bond_preview_items_helper,
)
from ui.bond_hover_preview_service import BondHoverPreviewService
from ui.bond_renderer import BondRenderer
from ui.atom_label_service import AtomLabelService
from ui.benzene_preview_service import BenzenePreviewService
from ui.bond_graphics_logic import refresh_bond_graphics
from ui.canvas_scene_decoration_build_service import (
    CanvasSceneDecorationBuildService,
    canvas_scene_decoration_build_service_for,
)
from ui.scene_decoration_service import SceneDecorationService
from ui.canvas_handle_controller import CanvasHandleController
from ui.curved_arrow_path_service import CurvedArrowPathService, curved_arrow_path_service_for
from ui.handle_mutation_service import HandleMutationService
from ui.handle_overlay_service import HandleOverlayService, handle_overlay_service_for
from ui.canvas_input_controller import CanvasInputController
from ui.canvas_insert_state import CanvasInsertState, insert_state_for
from ui.canvas_move_controller import CanvasMoveController
from ui.canvas_note_controller import CanvasNoteController
from ui.canvas_pointer_controller import CanvasPointerController
from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
from ui.canvas_atom_mutation_service import CanvasAtomMutationService, canvas_atom_mutation_service_for
from ui.canvas_bond_mutation_service import CanvasBondMutationService, canvas_bond_mutation_service_for
from ui.canvas_chemdraw_shortcut_service import (
    CanvasChemdrawShortcutService,
    canvas_chemdraw_shortcut_service_for,
)
from ui.canvas_hit_testing_service import CanvasHitTestingService, canvas_hit_testing_service_for
from ui.canvas_color_mutation_service import CanvasColorMutationService, canvas_color_mutation_service_for
from ui.canvas_document_session_service import CanvasDocumentSessionService
from ui.canvas_geometry_controller import CanvasGeometryController
from ui.canvas_graph_state import CanvasGraphState, graph_state_for
from ui.canvas_graph_service import CanvasGraphService, canvas_graph_service_for
from ui.canvas_history_state import CanvasHistoryState, history_state_for
from ui.canvas_history_service import CanvasHistoryService, history_service_for
from ui.canvas_history_recording_service import CanvasHistoryRecordingService
from ui.canvas_mark_registry import CanvasMarkRegistry, mark_registry_for
from ui.canvas_mark_scene_service import CanvasMarkSceneService, canvas_mark_scene_service_for
from ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService, canvas_ring_fill_scene_service_for
from ui.canvas_rotation_state import CanvasRotationState, rotation_state_for
from ui.canvas_scene_reset_service import CanvasSceneResetService, canvas_scene_reset_service_for
from ui.canvas_services import attach_canvas_services, build_canvas_services
from ui.hover_interaction_service import HoverInteractionService
from ui.hover_scene_service import HoverSceneService
from ui.insert_mode_logic import (
    InsertSessionState,
)
from ui.insert_controller import InsertController
from ui.mark_hover_preview_service import MarkHoverPreviewService
from ui.scene_item_controller import SceneItemController
from ui.selection_rotation_controller import SelectionRotationController
from ui.ring_occupancy_logic import ring_polygon_points_for_bond
from ui.scene_item_state import (
    ARROW_KINDS,
    arrow_state_dict as arrow_state_dict_helper,
    mark_state_dict as mark_state_dict_helper,
    note_state_dict as note_state_dict_helper,
    orbital_state_dict as orbital_state_dict_helper,
    ring_state_dict as ring_state_dict_helper,
    scene_item_state as scene_item_state_helper,
    ts_bracket_rect_from_state as ts_bracket_rect_from_state_helper,
    ts_bracket_state_dict as ts_bracket_state_dict_helper,
)
from ui.scene_ops_controller import SceneOpsController
from ui.selection_controller import SelectionController
from ui.selection_center_logic import bounding_box_center_for_atoms, center_for_atoms
from ui.selection_highlight_styler import (
    SelectionHighlightStyler,
    selection_highlight_styler_for,
)
from ui.selection_hit_logic import (
    SelectionRect,
    SelectionSnapshot,
    StructureHit,
    build_selection_snapshot,
    structure_hit_is_selected,
)
from ui.structure_payload_logic import (
    build_3d_conversion_payload as build_3d_conversion_payload_state,
    build_atom_annotations as build_atom_annotations_state,
    build_structure_payload as build_structure_payload_state,
    build_submodel as build_submodel_state,
    expand_atom_ids_for_structure as expand_atom_ids_for_structure_state,
)
from ui.template_insert_logic import (
    TemplateInsertRequest,
    TemplatePointResolvers,
)
from ui.structure_build_service import StructureBuildService
from ui.structure_geometry_logic import (
    compute_regular_ring_points_for_atom,
    compute_regular_ring_points_for_bond,
    compute_sprout_bond_endpoint,
    compute_template_points_for_bond,
)
from ui.sheet_setup_logic import (
    DEFAULT_SHEET_ORIENTATION,
    DEFAULT_SHEET_SIZE,
    SHEET_MARGIN_PX,
    normalize_sheet_setup,
    sheet_dimensions_px,
)
from ui.structure_insert_service import StructureInsertService
from ui.selection_rotation_logic import rotated_atom_positions, selected_rotation_atom_ids
from ui.state_field import StateField


class NoteItem(QGraphicsTextItem):
    def __init__(self, canvas) -> None:
        super().__init__()
        self._canvas = canvas
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._last_text = ""

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        _note_controller_for(self._canvas).handle_note_focus_out(self)


def _input_controller_for(canvas) -> CanvasInputController:
    return canvas._input_controller


def _pointer_controller_for(canvas) -> CanvasPointerController:
    return canvas._pointer_controller


def _handle_controller_for(canvas) -> CanvasHandleController:
    return canvas._handle_controller


def _selection_controller_for(canvas) -> SelectionController:
    return canvas._selection_controller


def _note_controller_for(canvas) -> CanvasNoteController:
    return canvas._note_controller


def _move_controller_for(canvas) -> CanvasMoveController:
    return canvas._move_controller


def _geometry_controller_for(canvas) -> CanvasGeometryController:
    return canvas._geometry_controller


def _rotation_preview_controller_for(canvas) -> CanvasRotationPreviewController:
    return canvas._rotation_preview_controller


class CanvasView(QGraphicsView):
    FILE_FORMAT_VERSION = 1
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    _atom_neighbors = StateField("_graph_state", "atom_neighbors")
    _atom_bond_ids = StateField("_graph_state", "atom_bond_ids")
    _graph_version = StateField("_graph_state", "graph_version")
    _selection_component_cache_signature = StateField("_graph_state", "selection_component_cache_signature")
    _selection_component_cache = StateField("_graph_state", "selection_component_cache")
    _rotation_axis_cache = StateField("_graph_state", "rotation_axis_cache")
    _rotation_axis_cache_version = StateField("_graph_state", "rotation_axis_cache_version")
    _bond_cycle_cache = StateField("_graph_state", "bond_cycle_cache")

    _history = StateField("_history_state", "history")
    _redo_stack = StateField("_history_state", "redo_stack")
    _history_enabled = StateField("_history_state", "enabled")
    _history_limit = StateField("_history_state", "limit")
    _history_change_callback = StateField("_history_state", "change_callback")

    _smiles_insert_active = StateField("_insert_state", "smiles_active")
    _smiles_preview_model = StateField("_insert_state", "smiles_preview_model")
    _smiles_preview_items = StateField("_insert_state", "smiles_preview_items")
    _smiles_preview_bond_items = StateField("_insert_state", "smiles_preview_bond_items")
    _smiles_preview_atom_items = StateField("_insert_state", "smiles_preview_atom_items")
    _smiles_preview_center = StateField("_insert_state", "smiles_preview_center")
    _smiles_preview_smiles = StateField("_insert_state", "smiles_preview_smiles")
    _template_insert_active = StateField("_insert_state", "template_active")
    _template_ring_size = StateField("_insert_state", "template_ring_size")
    _template_ring_style = StateField("_insert_state", "template_ring_style")
    _template_preview_items = StateField("_insert_state", "template_preview_items")
    _template_preview_lines = StateField("_insert_state", "template_preview_lines")
    _template_preview_dots = StateField("_insert_state", "template_preview_dots")
    _benzene_preview_items = StateField("_insert_state", "benzene_preview_items")

    _rotation_base_coords = StateField("_rotation_state", "base_coords")
    _rotation_axis_bond_id = StateField("_rotation_state", "axis_bond_id")
    _rotation_axis_atoms = StateField("_rotation_state", "axis_atoms")
    _rotation_total_angle = StateField("_rotation_state", "total_angle")
    _rotation_mode = StateField("_rotation_state", "mode")
    _rotation_free_angle_x = StateField("_rotation_state", "free_angle_x")
    _rotation_free_angle_y = StateField("_rotation_state", "free_angle_y")
    _rotation_base_bond_length = StateField("_rotation_state", "base_bond_length")
    rotation_atom_ids = StateField("_rotation_state", "atom_ids")
    rotation_center_3d = StateField("_rotation_state", "center_3d")
    _projection_center_3d = StateField("_rotation_state", "projection_center_3d")
    _projection_anchor_2d = StateField("_rotation_state", "projection_anchor_2d")
    _rotation_start_projection_center_3d = StateField("_rotation_state", "start_projection_center_3d")
    _rotation_start_projection_anchor_2d = StateField("_rotation_state", "start_projection_anchor_2d")
    _rotation_start_positions = StateField("_rotation_state", "start_positions")
    _rotation_start_coords_3d = StateField("_rotation_state", "start_coords_3d")
    _rotation_coord_atom_ids = StateField("_rotation_state", "coord_atom_ids")
    _rotation_selection_ids = StateField("_rotation_state", "selection_ids")
    _marks_by_atom = StateField("_mark_registry", "by_atom")

    def __init__(self) -> None:
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setScene(QGraphicsScene(self))
        self.scene().selectionChanged.connect(self._update_selection_outline)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#e7e7e4"))
        self.sheet_size = DEFAULT_SHEET_SIZE
        self.sheet_orientation = DEFAULT_SHEET_ORIENTATION
        self._sheet_rect = QRectF()
        self._apply_sheet_scene_rect()
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.model = MoleculeModel()
        self.renderer = Renderer()
        self.rdkit = RDKitAdapter()
        self._last_interaction_time = time.monotonic()
        self._rdkit_warmup_pending = False
        self._rdkit_idle_threshold = 0.4
        self._rdkit_idle_timer = QTimer(self)
        self._rdkit_idle_timer.setInterval(250)
        self._rdkit_idle_timer.timeout.connect(self._maybe_warm_rdkit)
        self._rdkit_idle_timer.start()
        self.atom_items: dict[int, QGraphicsTextItem] = {}
        self.atom_dots: dict[int, QGraphicsEllipseItem] = {}
        self._graph_state = CanvasGraphState()
        self._insert_state = CanvasInsertState()
        self._history_state = CanvasHistoryState()
        self._history_service = CanvasHistoryService(self, self._history_state)
        self._mark_registry = CanvasMarkRegistry()
        self.atom_symbol = "C"
        self.bond_items: dict[int, list] = {}
        self._bond_renderer = BondRenderer(self)
        self._spatial_index_dirty = True
        self._spatial_cell_size = 0.0
        self._atom_grid: dict[tuple[int, int], set[int]] = {}
        self._bond_grid: dict[tuple[int, int], set[int]] = {}
        self.ring_items: list[QGraphicsPolygonItem] = []
        self.active_bond_order = 1
        self.active_bond_style = "single"
        self.snap_angle_step = 30
        self._base_transform = QTransform()
        self._perspective_shear = 0.0
        self._perspective_scale_y = 1.0
        self._rotation_group = None
        self.atom_coords_3d: dict[int, tuple[float, float, float]] = {}
        self._rotation_state = CanvasRotationState()
        self._rotation_depth_factor = 1.0
        self.active_arrow_type = "reaction"
        self.active_orbital_type = "s"
        self.orbital_phase_enabled = False
        self.arrow_line_width = self.renderer.style.bond_line_width
        self.arrow_head_scale = 0.3
        self._active_handles: list[QGraphicsEllipseItem] = []
        self._handle_target = None
        self._selected_items: list = []
        self._curved_snap = False
        self._curved_symmetry = False
        self._curved_snap_step = 0.15
        self._selection_color = QColor("#0d9488")
        self._selection_stroke_delta = 0.6
        self._suspend_selection_outline = False
        self._selection_signature = None
        self._selection_pending_signature = None
        services = build_canvas_services(
            self,
            graph_state=self._graph_state,
            insert_state=self._insert_state,
            history_service=self._history_service,
        )
        attach_canvas_services(self, services)
        self._selection_info_cache = ("", "")
        self._orbital_snap_enabled = False
        self._orbital_snap_step = 15
        self.last_smiles_input: str | None = None
        self.text_font_family = "Arial"
        self.text_font_size = 12
        self.text_font_weight = QFont.Weight.Normal
        self.text_italic = False
        self.text_color = QColor("#222222")
        self.text_alignment = Qt.AlignmentFlag.AlignLeft
        self.text_line_spacing = 1.0
        self.note_box_enabled = False
        self.note_box_color = QColor("#ffffff")
        self.note_box_alpha = 1.0
        self.note_border_enabled = False
        self.note_border_color = QColor("#333333")
        self.note_border_width = 1.0
        self.note_padding = 6.0
        self.selected_notes: list[QGraphicsTextItem] = []
        self.mark_kind = "plus"
        self.note_items: list[QGraphicsTextItem] = []
        self.mark_items: list[QGraphicsItem] = []
        self.arrow_items: list[QGraphicsPathItem] = []
        self.ts_bracket_items: list[QGraphicsPathItem] = []
        self.orbital_items: list[QGraphicsItemGroup] = []
        self._marks_by_atom = {}
        self.hover_items: list = []
        self.hover_atom_id: int | None = None
        self.hover_bond_id: int | None = None
        self._hover_preview_style: str | None = None
        self._selection_info_callback = None
        self._tool_change_callback = None
        self._error_callback = None
        self._rotation_selection_ids = None
        self.selection_outlines: list[QGraphicsItem] = []
        self._clipboard_paste_source_json: str | None = None
        self._clipboard_paste_count = 0
        self.tools.set_active("bond")

    def _apply_sheet_scene_rect(self) -> None:
        width, height = sheet_dimensions_px(self.sheet_size, self.sheet_orientation)
        self._sheet_rect = QRectF(-width / 2.0, -height / 2.0, width, height)
        self.setSceneRect(
            self._sheet_rect.adjusted(
                -SHEET_MARGIN_PX,
                -SHEET_MARGIN_PX,
                SHEET_MARGIN_PX,
                SHEET_MARGIN_PX,
            )
        )

    def sheet_rect(self) -> QRectF:
        return QRectF(self._sheet_rect)

    def set_sheet_setup(self, size_name: str, orientation: str) -> None:
        self.sheet_size, self.sheet_orientation = normalize_sheet_setup(size_name, orientation)
        self._apply_sheet_scene_rect()
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.fillRect(rect, QColor("#e7e7e4"))
        sheet_rect = self.sheet_rect()
        # Layered soft drop shadow so the page reads as paper floating above
        # the workspace rather than blending into it.
        for offset, alpha in ((6.0, 5), (4.0, 9), (2.0, 16)):
            painter.fillRect(
                sheet_rect.adjusted(-offset * 0.4, offset * 0.3, offset, offset + 1.0),
                QColor(0, 0, 0, alpha),
            )
        painter.fillRect(sheet_rect, QColor("#ffffff"))
        pen = QPen(QColor("#dededa"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(sheet_rect)
        painter.restore()

    def keyPressEvent(self, event) -> None:
        _input_controller_for(self).key_press_event(event)

    @staticmethod
    def _shortcut_modifiers(event) -> Qt.KeyboardModifier:
        return CanvasInputController.shortcut_modifiers(event)

    def _handle_chemdraw_shortcut(self, event) -> bool:
        return canvas_chemdraw_shortcut_service_for(self).handle_shortcut(event)

    def _handle_chemdraw_object_shortcut(self, event) -> bool:
        return canvas_chemdraw_shortcut_service_for(self).handle_object_shortcut(event)

    def _handle_chemdraw_generic_hotkey(self, event) -> bool:
        return canvas_chemdraw_shortcut_service_for(self).handle_generic_hotkey(event)

    def _handle_chemdraw_atom_hotkey(self, event, atom_id: int) -> bool:
        return canvas_chemdraw_shortcut_service_for(self).handle_atom_hotkey(event, atom_id)

    def _handle_chemdraw_bond_hotkey(self, event, bond_id: int) -> bool:
        return canvas_chemdraw_shortcut_service_for(self).handle_bond_hotkey(event, bond_id)

    def _atom_has_visible_label(self, atom_id: int) -> bool:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return False
        return atom.element != "C" or atom.explicit_label or atom_id in self.atom_items

    def _atom_point(self, atom_id: int) -> QPointF:
        atom = self.model.atoms[atom_id]
        return QPointF(atom.x, atom.y)

    def _refresh_hover_from_cursor(self) -> None:
        if not hasattr(self, "tools"):
            return
        insert_state = insert_state_for(self)
        if insert_state.template_active or insert_state.smiles_active:
            self._clear_hover_highlight()
            return
        viewport_pos = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(viewport_pos):
            self._update_hover_highlight(self.mapToScene(viewport_pos))
            return
        self._clear_hover_highlight()

    def clear_atom_label(self, atom_id: int) -> None:
        if atom_id not in self.model.atoms:
            return
        self._atom_label_service.add_or_update_atom_label(atom_id, "C", show_carbon=False)

    def prompt_atom_label(self, atom_id: int) -> None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        initial = "" if atom.element == "C" and not atom.explicit_label else atom.element
        text, ok = QInputDialog.getText(
            self,
            "Atom Label",
            "Enter atom symbol:",
            text=initial,
        )
        if not ok:
            return
        text = text.strip()
        if not text:
            self._atom_label_service.add_or_update_atom_label(atom_id, "C", show_carbon=False)
            return
        self._atom_label_service.add_or_update_atom_label(atom_id, text, show_carbon=True)

    def _sprout_bond_endpoint(self, atom_id: int, cyclic: bool = False) -> QPointF | None:
        atom = self.model.atoms.get(atom_id)
        default_endpoint = None
        if atom is not None and not cyclic:
            start = QPointF(atom.x, atom.y)
            endpoint = self._default_bond_endpoint(start, atom_id)
            default_endpoint = (endpoint.x(), endpoint.y())
        point = compute_sprout_bond_endpoint(
            atom_id,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            bond_length=self.renderer.style.bond_length_px,
            cyclic=cyclic,
            default_endpoint=default_endpoint,
        )
        if point is None:
            return None
        return QPointF(point[0], point[1])

    def _sprout_bond_from_atom(self, atom_id: int, style: str, order: int, cyclic: bool = False) -> None:
        self._structure_build_service.sprout_bond_from_atom(
            atom_id,
            style=style,
            order=order,
            cyclic=cyclic,
        )

    def _sprout_benzene_from_atom(self, atom_id: int) -> None:
        self._structure_build_service.sprout_benzene_from_atom(atom_id)

    def _sprout_acetyl_from_atom(self, atom_id: int) -> None:
        self._structure_build_service.sprout_acetyl_from_atom(atom_id)

    def _regular_ring_points_for_atom(
        self,
        n: int,
        attach_atom_id: int,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        result = compute_regular_ring_points_for_atom(
            n,
            attach_atom_id,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            bond_length=self.renderer.style.bond_length_px,
        )
        if result is None:
            return None
        points, merge = result
        return [QPointF(x, y) for x, y in points], merge

    def _sprout_regular_ring_from_atom(self, atom_id: int, n: int) -> None:
        self._structure_build_service.sprout_regular_ring_from_atom(atom_id, n)

    def _fuse_benzene_to_bond(self, bond_id: int) -> None:
        self._structure_build_service.fuse_benzene_to_bond(bond_id)

    def _fuse_regular_ring_to_bond(self, bond_id: int, n: int) -> None:
        self._structure_build_service.fuse_regular_ring_to_bond(bond_id, n)

    def _fuse_chair_to_bond(self, bond_id: int, mirrored: bool = False) -> None:
        self._structure_build_service.fuse_chair_to_bond(bond_id, mirrored=mirrored)

    def delete_selected_items(self) -> bool:
        return self._scene_ops_controller.delete_selected_items()

    def _snapshot_state(self) -> dict:
        return self._canvas_document_session_service.snapshot_state()

    def snapshot_state(self) -> dict:
        return self._snapshot_state()

    def _restore_state(self, state: dict) -> None:
        self._canvas_document_session_service.apply_state(state)

    def restore_state(self, state: dict) -> None:
        self._canvas_document_session_service.restore_state(state)

    def save_to_file(self, path: str) -> None:
        self._canvas_document_session_service.save_to_file(path)

    def export_xyz(self, path: str) -> None:
        export_model, atom_annotations = self.build_3d_conversion_payload()
        xyz_block = self.rdkit.model_to_xyz_block(export_model, atom_annotations=atom_annotations)
        if xyz_block is None:
            message = self.rdkit.last_error or "Failed to export 3D XYZ."
            raise ValueError(message)
        Path(path).write_text(xyz_block, encoding="utf-8")

    def export_xyz_async(self, path: str, *, on_success, on_error) -> None:
        try:
            export_model, atom_annotations = self.build_3d_conversion_payload()
        except Exception as exc:
            on_error(str(exc) or "Failed to export 3D XYZ.")
            return
        if not self.rdkit.is_loaded() and not self.rdkit.preload():
            on_error(self.rdkit.last_error or "RDKit is not available in this environment.")
            return
        from ui.rdkit_async_jobs import export_xyz_in_thread

        export_xyz_in_thread(
            self,
            rdkit_adapter=self.rdkit,
            model=export_model,
            atom_annotations=atom_annotations,
            path=path,
            on_success=on_success,
            on_error=on_error,
        )

    def export_figure(
        self,
        path: str,
        *,
        fmt: str = "svg",
        scope: str = "sheet",
        dpi: int = 300,
        background: str = "transparent",
        sizing: str = "bond",
    ) -> None:
        from ui.export_plan_logic import points_for_mm
        from ui.export_render_service import export_scene

        pad = max(2.0, self.renderer.style.bond_line_width * 2.0)
        items = None
        if scope == "selection":
            items = self._selection_items_for_copy()
            if not items:
                raise ValueError("Select something to export, or choose Whole sheet.")

        unit_scale = 1.0
        target_width_pt = None
        if sizing == "bond":
            style = self.renderer.style
            if style.bond_length_px > 0:
                unit_scale = style.bond_length_pt / style.bond_length_px
        elif sizing == "col1":
            target_width_pt = points_for_mm(84.0)
        elif sizing == "col2":
            target_width_pt = points_for_mm(174.0)
        # sizing == "screen" -> unit_scale stays 1.0 (1 scene px -> 1 pt)

        export_scene(
            self.scene(),
            path,
            fmt=fmt,
            items=items,
            margin=pad,
            dpi=dpi,
            background=background,
            title="Chemvas drawing",
            unit_scale=unit_scale,
            target_width_pt=target_width_pt,
        )

    def insert_structure_model(
        self,
        model: MoleculeModel,
        *,
        center: QPointF | None = None,
        title: str | None = None,
    ) -> tuple[set[int], set[int]]:
        return self._structure_insert_service.insert_structure_model(
            model,
            center=center,
            title=title,
        )

    def load_from_file(self, path: str) -> None:
        self._canvas_document_session_service.load_from_file(path)

    def _push_command(self, command: HistoryCommand) -> None:
        history_service_for(self).push(command)

    def undo(self) -> None:
        history_service_for(self).undo()

    def redo(self) -> None:
        history_service_for(self).redo()

    def set_history_change_callback(self, callback) -> None:
        history_service_for(self).set_change_callback(callback)

    def _notify_history_change(self) -> None:
        history_service_for(self).notify_change()

    def can_undo(self) -> bool:
        return history_service_for(self).can_undo()

    def can_redo(self) -> bool:
        return history_service_for(self).can_redo()

    def set_tool_change_callback(self, callback) -> None:
        self._tool_change_callback = callback

    def _notify_tool_change(self) -> None:
        if self._tool_change_callback is not None:
            self._tool_change_callback()

    def _cancel_pending_insert_modes(self) -> None:
        if self._insert_state.template_active:
            self._cancel_template_insert()
        if self._insert_state.smiles_active:
            self._cancel_smiles_insert()

    def set_tool(self, tool_name: str) -> None:
        self._cancel_pending_insert_modes()
        self.tools.set_active(tool_name)
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def set_mark_kind(self, kind: str) -> None:
        if kind not in {"plus", "minus", "radical"}:
            return
        self._cancel_pending_insert_modes()
        self.mark_kind = kind
        self.tools.set_active("mark")
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def _record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        self._atom_label_service.record_label_change(
            atom_id,
            before_element,
            before_explicit_label,
            before_smiles_input,
            merge_ids,
            merge_info,
        )

    def _bond_state_dict(self, bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def _record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        self._canvas_history_recording_service.record_additions(
            before_next_atom_id,
            before_bond_count,
            before_smiles_input,
            added_scene_items,
        )

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return {}
        explicit = bool(atom.explicit_label)
        if atom.element.upper() == "C" and atom_id in self.atom_items:
            explicit = True
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": explicit,
        }

    def _remove_atom_only(self, atom_id: int, remove_marks: bool = True) -> None:
        canvas_atom_mutation_service_for(self).remove_atom_only(atom_id, remove_marks=remove_marks)

    def _restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        canvas_atom_mutation_service_for(self).restore_atom_from_state(atom_id, state)

    def apply_atom_color(self, atom_id: int, color: str | QColor) -> None:
        canvas_atom_mutation_service_for(self).apply_atom_color(atom_id, color)

    def set_atom_positions(
        self,
        positions: dict[int, tuple[float, float]],
        update_selection: bool = True,
        coords_3d: dict[int, tuple[float, float, float]] | None = None,
    ) -> None:
        if not positions and not coords_3d:
            return
        atom_ids = set()
        for atom_id, (x, y) in positions.items():
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom.x = x
            atom.y = y
            atom_ids.add(atom_id)
            if coords_3d is not None and atom_id in coords_3d:
                self.atom_coords_3d[atom_id] = coords_3d[atom_id]
            elif atom_id in self.atom_coords_3d:
                _, _, z = self.atom_coords_3d[atom_id]
                self.atom_coords_3d[atom_id] = (x, y, z)
            label = self.atom_items.get(atom_id)
            if label is not None:
                self._position_label(label, x, y)
            dot = self.atom_dots.get(atom_id)
            if dot is not None:
                dot.setPos(x, y)
            marks = mark_registry_for(self).get_for_atom(atom_id)
            if marks:
                for mark in list(marks):
                    data = mark.data(1) or {}
                    dx = data.get("dx")
                    dy = data.get("dy")
                    if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                        self._set_mark_center(mark, QPointF(x + dx, y + dy))
                    else:
                        self._set_mark_center(mark, QPointF(x, y))
        if coords_3d is not None:
            for atom_id, coord in coords_3d.items():
                atom = self.model.atoms.get(atom_id)
                if atom is None:
                    continue
                self.atom_coords_3d[atom_id] = coord
                atom_ids.add(atom_id)
        if atom_ids:
            self._redraw_bonds_for_atoms(atom_ids)
            self._update_ring_fills_for_atoms(atom_ids)
        self._mark_spatial_index_dirty()
        if update_selection:
            self._update_selection_outline()

    def set_ring_polygons(
        self,
        ring_items: list[QGraphicsPolygonItem],
        polygons: list[list[tuple[float, float]]],
    ) -> None:
        for ring_item, points in zip(ring_items, polygons):
            if ring_item is None:
                continue
            polygon = QPolygonF([QPointF(x, y) for x, y in points])
            ring_item.setPolygon(polygon)

    def _ring_state_dict(self, ring_item: QGraphicsPolygonItem) -> dict:
        return ring_state_dict_helper(ring_item)

    def _note_state_dict(self, item: QGraphicsTextItem) -> dict:
        return note_state_dict_helper(item)

    def _mark_state_dict(self, item) -> dict:
        return mark_state_dict_helper(item, mark_center_getter=self._mark_center)

    def _arrow_state_dict(self, item) -> dict:
        return arrow_state_dict_helper(item)

    def _ts_bracket_state_dict(self, item) -> dict:
        return ts_bracket_state_dict_helper(item)

    def _ts_bracket_rect_from_state(self, state: dict) -> QRectF | None:
        return ts_bracket_rect_from_state_helper(state)

    def _orbital_state_dict(self, item) -> dict:
        return orbital_state_dict_helper(item)

    def scene_item_state(self, item) -> dict:
        return scene_item_state_helper(item, mark_center_getter=self._mark_center)

    def _restore_ring_from_state(self, ring_state: dict):
        return self._scene_item_controller._restore_ring_from_state(ring_state)

    def _restore_note_from_state(self, note_state: dict):
        return self._scene_item_controller._restore_note_from_state(note_state)

    def _restore_mark_from_state(self, mark_state: dict):
        return self._scene_item_controller._restore_mark_from_state(mark_state)

    def _set_curved_arrow_path(
        self,
        item: QGraphicsPathItem,
        start: QPointF,
        end: QPointF,
        control: QPointF,
        double: bool,
    ) -> None:
        curved_arrow_path_service_for(self).set_curved_arrow_path(item, start, end, control, double)

    def _restore_arrow_from_state(self, arrow_state: dict):
        return self._scene_item_controller._restore_arrow_from_state(arrow_state)

    def _restore_ts_bracket_from_state(self, ts_bracket_state: dict):
        return self._scene_item_controller._restore_ts_bracket_from_state(ts_bracket_state)

    def _restore_orbital_from_state(self, orbital_state: dict):
        return self._scene_item_controller._restore_orbital_from_state(orbital_state)

    def create_scene_item_from_state(self, state: dict):
        return self._scene_item_controller.create_scene_item_from_state(state)

    def attach_scene_item(self, item) -> None:
        self._scene_item_controller.attach_scene_item(item)

    def _bond_ids_for_ring_item(self, item) -> set[int]:
        return self._scene_item_controller._bond_ids_for_ring_item(item)

    def _refresh_bond_geometry_for_ring_item(self, item) -> None:
        self._scene_item_controller._refresh_bond_geometry_for_ring_item(item)

    def restore_scene_item(self, item) -> None:
        self._scene_item_controller.restore_scene_item(item)

    def remove_scene_item(self, item) -> None:
        self._scene_item_controller.remove_scene_item(item)

    def apply_scene_item_state(self, item, state: dict) -> None:
        self._scene_item_controller.apply_scene_item_state(item, state)

    def _record_bond_update(
        self,
        bond_id: int,
        before_state: dict,
        after_state: dict,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> None:
        self._canvas_history_recording_service.record_bond_update(
            bond_id,
            before_state,
            after_state,
            before_smiles_input,
            after_smiles_input,
        )

    def _restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        canvas_bond_mutation_service_for(self).restore_bond_from_state(bond_id, bond_state)

    def _remove_bond_by_id(self, bond_id: int) -> None:
        canvas_bond_mutation_service_for(self).remove_bond_by_id(bond_id)

    def _trim_bonds_to_length(self, length: int) -> None:
        canvas_bond_mutation_service_for(self).trim_bonds_to_length(length)

    def scene_pos_from_event(self, event) -> QPointF:
        return canvas_hit_testing_service_for(self).scene_pos_from_event(event)

    def item_at_scene_pos(self, pos: QPointF):
        return canvas_hit_testing_service_for(self).item_at_scene_pos(pos)

    def item_at_event(self, event):
        return canvas_hit_testing_service_for(self).item_at_event(event)

    @staticmethod
    def _selection_target_item(item) -> bool:
        return item.data(0) not in {"selection_outline", "note_box", "note_select", "handle"}

    def _selected_bond_atom_ids(self, bond_ids: set[int]) -> tuple[tuple[int, int], ...]:
        atom_pairs: list[tuple[int, int]] = []
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            atom_pairs.append((bond.a, bond.b))
        return tuple(atom_pairs)

    def _selection_snapshot(self) -> SelectionSnapshot | None:
        selected = tuple(self.scene().selectedItems())
        if not selected:
            return None
        atom_ids, bond_ids = self._selected_ids()
        return build_selection_snapshot(
            selected_atom_ids=atom_ids,
            selected_bond_ids=bond_ids,
            selected_bond_atom_ids=self._selected_bond_atom_ids(bond_ids),
            selection_items=tuple(item for item in selected if self._selection_target_item(item)),
        )

    def _nearest_atom_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return canvas_hit_testing_service_for(self).nearest_atom_hit(pos)

    def _nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return canvas_hit_testing_service_for(self).nearest_bond_hit(pos)

    def _structure_hit_from_item(self, item) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
        return _selection_controller_for(self).structure_hit_from_item(item)

    def _structure_item_for_hit(self, hit: StructureHit):
        return _selection_controller_for(self).structure_item_for_hit(hit)

    def _atom_item_for_id(self, atom_id: int):
        return self._atom_label_service.atom_item_for_id(atom_id)

    def _selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        return _selection_controller_for(self).selection_targets_for_item(item)

    def toggle_item_selection(self, item) -> bool:
        return _selection_controller_for(self).toggle_item_selection(item)

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        return _selection_controller_for(self).preferred_structure_hit_at_scene_pos(pos)

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        return _selection_controller_for(self).preferred_structure_item_at_scene_pos(pos)

    def bond_id_from_event(self, event) -> int | None:
        return canvas_hit_testing_service_for(self).bond_id_from_event(event)

    def _selection_rects_for_snapshot(
        self,
        snapshot: SelectionSnapshot,
    ) -> tuple[SelectionRect, ...]:
        return _selection_controller_for(self).selection_rects_for_snapshot(snapshot)

    def selection_hit_test(
        self,
        pos: QPointF,
        snapshot: SelectionSnapshot | None = None,
    ) -> bool:
        return _selection_controller_for(self).selection_hit_test(pos, snapshot=snapshot)

    def structure_item_is_selected(
        self,
        item,
        selected_atom_ids: set[int],
        selected_bond_ids: set[int],
    ) -> bool:
        hit, bond_atom_ids, ring_atom_ids = self._structure_hit_from_item(item)
        return structure_hit_is_selected(
            hit,
            selected_atom_ids=selected_atom_ids,
            selected_bond_ids=selected_bond_ids,
            bond_atom_ids=bond_atom_ids,
            ring_atom_ids=ring_atom_ids,
            item_is_selected=bool(item is not None and item.isSelected()),
        )

    def select_structure_for_item(self, item) -> bool:
        return _selection_controller_for(self).select_structure_for_item(item)

    def _mark_spatial_index_dirty(self) -> None:
        self._spatial_index_dirty = True

    def _grid_cell_size(self) -> float:
        return canvas_hit_testing_service_for(self).grid_cell_size()

    def _cell_coords(self, x: float, y: float, cell_size: float) -> tuple[int, int]:
        return canvas_hit_testing_service_for(self).cell_coords(x, y, cell_size)

    def _ensure_spatial_index(self) -> None:
        canvas_hit_testing_service_for(self).ensure_spatial_index()

    def _rebuild_spatial_index(self, cell_size: float) -> None:
        canvas_hit_testing_service_for(self).rebuild_spatial_index(cell_size)

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        return canvas_hit_testing_service_for(self).find_atom_near(x, y, max_dist)

    def add_atom(self, element: str, x: float, y: float) -> int:
        return canvas_atom_mutation_service_for(self).add_atom(element, x, y)

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        return canvas_bond_mutation_service_for(self).add_bond(a, b, order)

    def _activate_tool_variant(self, tool_name: str, **state) -> None:
        for attr_name, value in state.items():
            setattr(self, attr_name, value)
        self.tools.set_active(tool_name)
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def set_bond_style(self, style: str, order: int) -> None:
        self._activate_tool_variant("bond", active_bond_style=style, active_bond_order=order)

    def set_arrow_type(self, arrow_type: str) -> None:
        self._activate_tool_variant("arrow", active_arrow_type=arrow_type)

    def set_orbital_type(self, orbital_type: str) -> None:
        self._activate_tool_variant("orbital", active_orbital_type=orbital_type)

    def set_orbital_phase_enabled(self, enabled: bool) -> None:
        self.orbital_phase_enabled = enabled

    def set_arrow_line_width(self, width: float) -> None:
        self.arrow_line_width = max(0.5, float(width))

    def get_arrow_line_width(self) -> float:
        return self.arrow_line_width

    def set_arrow_head_scale(self, scale: float) -> None:
        self.arrow_head_scale = max(0.1, min(0.8, scale))

    def get_arrow_head_scale(self) -> float:
        return self.arrow_head_scale

    def set_curved_snap(self, enabled: bool) -> None:
        self._curved_snap = bool(enabled)

    def get_curved_snap(self) -> bool:
        return self._curved_snap

    def set_curved_snap_step(self, step: float) -> None:
        self._curved_snap_step = max(0.05, float(step))

    def get_curved_snap_step(self) -> float:
        return self._curved_snap_step

    def set_curved_symmetry(self, enabled: bool) -> None:
        self._curved_symmetry = bool(enabled)

    def get_curved_symmetry(self) -> bool:
        return self._curved_symmetry

    def set_selection_color(self, color: QColor) -> None:
        if color.isValid():
            self._selection_color = color

    def set_selection_stroke_delta(self, delta: float) -> None:
        self._selection_stroke_delta = max(0.1, float(delta))

    def get_selection_stroke_delta(self) -> float:
        return self._selection_stroke_delta

    def set_orbital_snap_enabled(self, enabled: bool) -> None:
        self._orbital_snap_enabled = bool(enabled)

    def get_orbital_snap_enabled(self) -> bool:
        return self._orbital_snap_enabled

    def set_orbital_snap_step(self, step: int) -> None:
        self._orbital_snap_step = max(1, int(step))

    def get_orbital_snap_step(self) -> int:
        return self._orbital_snap_step

    def set_text_font(self, font: QFont) -> None:
        self.text_font_family = font.family()
        self.apply_text_style_to_selected()

    def set_text_size(self, size: int) -> None:
        self.text_font_size = max(6, int(size))
        self.apply_text_style_to_selected()

    def set_text_weight(self, weight: int) -> None:
        self.text_font_weight = max(0, min(99, int(weight)))
        self.apply_text_style_to_selected()

    def get_text_weight(self) -> int:
        return int(self.text_font_weight)

    def set_text_italic(self, enabled: bool) -> None:
        self.text_italic = bool(enabled)
        self.apply_text_style_to_selected()

    def set_text_color(self, color: QColor) -> None:
        if color.isValid():
            self.text_color = color
            self.apply_text_style_to_selected()

    def get_text_font(self) -> QFont:
        return QFont(self.text_font_family, self.text_font_size)

    def get_text_size(self) -> int:
        return self.text_font_size

    def apply_text_preset_acs(self) -> None:
        self.text_font_family = "Arial"
        self.text_font_size = self.renderer.style.font_size_pt
        self.text_font_weight = QFont.Weight.Normal
        self.text_italic = False
        self.text_color = QColor(self.renderer.style.atom_color)
        self.text_alignment = Qt.AlignmentFlag.AlignLeft
        self.text_line_spacing = 1.0
        self.note_box_enabled = False
        self.note_border_enabled = False
        self.apply_text_style_to_selected()

    def apply_text_preset_paper_thin(self) -> None:
        self.text_font_family = "Arial"
        self.text_font_size = max(9, self.renderer.style.font_size_pt - 1)
        self.text_font_weight = QFont.Weight.Normal
        self.text_italic = False
        self.text_color = QColor("#222222")
        self.text_alignment = Qt.AlignmentFlag.AlignLeft
        self.text_line_spacing = 1.05
        self.note_box_enabled = False
        self.note_border_enabled = False
        self.apply_text_style_to_selected()

    def apply_text_preset_paper_bold(self) -> None:
        self.text_font_family = "Arial"
        self.text_font_size = self.renderer.style.font_size_pt + 2
        self.text_font_weight = QFont.Weight.DemiBold
        self.text_italic = False
        self.text_color = QColor("#111111")
        self.text_alignment = Qt.AlignmentFlag.AlignLeft
        self.text_line_spacing = 1.1
        self.note_box_enabled = True
        self.note_box_color = QColor("#ffffff")
        self.note_box_alpha = 1.0
        self.note_border_enabled = True
        self.note_border_color = QColor("#111111")
        self.note_border_width = 1.2
        self.note_padding = 8.0
        self.apply_text_style_to_selected()

    def set_text_alignment(self, alignment: str) -> None:
        mapping = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }
        if alignment in mapping:
            self.text_alignment = mapping[alignment]
            self.apply_text_style_to_selected()

    def set_text_line_spacing(self, spacing: float) -> None:
        self.text_line_spacing = max(0.8, float(spacing))
        self.apply_text_style_to_selected()

    def set_atom_symbol(self, symbol: str) -> None:
        self.atom_symbol = symbol.strip()

    def get_atom_symbol(self) -> str:
        return self.atom_symbol

    def set_note_box_enabled(self, enabled: bool) -> None:
        self.note_box_enabled = bool(enabled)
        self.apply_text_style_to_selected()

    def set_note_box_color(self, color: QColor) -> None:
        if color.isValid():
            self.note_box_color = color
            self.apply_text_style_to_selected()

    def set_note_box_alpha(self, alpha: float) -> None:
        self.note_box_alpha = max(0.0, min(1.0, float(alpha)))
        self.apply_text_style_to_selected()

    def get_note_box_alpha(self) -> float:
        return self.note_box_alpha

    def set_note_border_enabled(self, enabled: bool) -> None:
        self.note_border_enabled = bool(enabled)
        self.apply_text_style_to_selected()

    def set_note_border_color(self, color: QColor) -> None:
        if color.isValid():
            self.note_border_color = color
            self.apply_text_style_to_selected()

    def set_note_border_width(self, width: float) -> None:
        self.note_border_width = max(0.5, float(width))
        self.apply_text_style_to_selected()

    def set_note_padding(self, padding: float) -> None:
        self.note_padding = max(2.0, float(padding))
        self.apply_text_style_to_selected()

    def set_snap_angle_step(self, step: int) -> None:
        self.snap_angle_step = step
        self.tools.set_active("bond")
        self._update_selection_outline()

    def set_bond_length(self, length_px: float) -> None:
        old_length = self.renderer.style.bond_length_px
        before_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in self.model.atoms.items()}
        before_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in self.ring_items
        ]
        self.renderer.set_bond_length(length_px)
        if old_length <= 0 or not self.model.atoms:
            return
        scale = length_px / old_length
        if scale == 1.0:
            return
        self._rescale_model(scale)
        self._rebuild_graphics()
        after_positions = {atom_id: (atom.x, atom.y) for atom_id, atom in self.model.atoms.items()}
        after_ring_polygons = [
            [(point.x(), point.y()) for point in ring_item.polygon()]
            for ring_item in self.ring_items
        ]
        commands: list[HistoryCommand] = [
            UpdateBondLengthCommand(before_length=old_length, after_length=length_px),
            SetAtomPositionsCommand(before_positions=before_positions, after_positions=after_positions),
        ]
        if self.ring_items:
            commands.append(
                SetRingPolygonsCommand(
                    ring_items=list(self.ring_items),
                    before_polygons=before_ring_polygons,
                    after_polygons=after_ring_polygons,
                )
            )
        history_service_for(self).push(CompositeCommand(commands))

    def _rescale_model(self, scale: float) -> None:
        xs = [atom.x for atom in self.model.atoms.values()]
        ys = [atom.y for atom in self.model.atoms.values()]
        center_x = sum(xs) / len(xs)
        center_y = sum(ys) / len(ys)

        for atom in self.model.atoms.values():
            atom.x = center_x + (atom.x - center_x) * scale
            atom.y = center_y + (atom.y - center_y) * scale

        for ring_item in self.ring_items:
            polygon = ring_item.polygon()
            scaled = QPolygonF()
            for point in polygon:
                x = center_x + (point.x() - center_x) * scale
                y = center_y + (point.y() - center_y) * scale
                scaled.append(QPointF(x, y))
            ring_item.setPolygon(scaled)
        self._mark_spatial_index_dirty()

    def _selected_scene_notes(self) -> list[QGraphicsItem]:
        scene = self.scene()
        return [note for note in self.selected_notes if note.scene() is scene]

    @staticmethod
    def _append_unique_scene_item(
        items: list[QGraphicsItem],
        seen: set[QGraphicsItem],
        item: QGraphicsItem,
        *,
        excluded_kinds: set[str],
    ) -> bool:
        if item in seen:
            return False
        if item.data(0) in excluded_kinds:
            return False
        seen.add(item)
        items.append(item)
        return True

    def _selected_scene_items(self, *, excluded_kinds: set[str]) -> list[QGraphicsItem]:
        items: list[QGraphicsItem] = []
        seen: set[QGraphicsItem] = set()
        for item in self.scene().selectedItems():
            CanvasView._append_unique_scene_item(items, seen, item, excluded_kinds=excluded_kinds)
        for note in CanvasView._selected_scene_notes(self):
            CanvasView._append_unique_scene_item(items, seen, note, excluded_kinds=excluded_kinds)
        return items

    def _selected_items_for_transform(self) -> list[QGraphicsItem]:
        excluded_kinds = {"handle", "note_box", "note_select", "selection_outline"}
        return CanvasView._selected_scene_items(self, excluded_kinds=excluded_kinds)

    def _selected_atom_ids_for_transform(self) -> set[int]:
        atom_ids, bond_ids = self._selected_ids()
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            atom_ids.add(bond.a)
            atom_ids.add(bond.b)
        return atom_ids

    @staticmethod
    def _flip_point(point: QPointF, center: QPointF, horizontal: bool) -> QPointF:
        if horizontal:
            return QPointF(center.x() - (point.x() - center.x()), point.y())
        return QPointF(point.x(), center.y() - (point.y() - center.y()))

    @staticmethod
    def _bounds_from_points(points: list[QPointF]) -> QRectF | None:
        if not points:
            return None
        min_x = min(point.x() for point in points)
        max_x = max(point.x() for point in points)
        min_y = min(point.y() for point in points)
        max_y = max(point.y() for point in points)
        return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y))

    def flip_horizontal(self) -> None:
        self._scene_ops_controller.flip_selected_items(horizontal=True)

    def flip_vertical(self) -> None:
        self._scene_ops_controller.flip_selected_items(horizontal=False)

    def _rebuild_graphics(self) -> None:
        scene = self.scene()
        self.bond_items = CanvasView._clear_scene_item_list_map(scene, self.bond_items)
        self.atom_items = CanvasView._clear_scene_item_map(scene, self.atom_items)
        self.atom_dots = CanvasView._clear_scene_item_map(scene, self.atom_dots)
        self._render_model()

    @staticmethod
    def _remove_scene_items(scene: QGraphicsScene, items) -> None:
        for item in items:
            scene.removeItem(item)

    @staticmethod
    def _clear_scene_item_map(scene: QGraphicsScene, item_map: dict) -> dict:
        CanvasView._remove_scene_items(scene, item_map.values())
        return {}

    @staticmethod
    def _clear_scene_item_list_map(scene: QGraphicsScene, item_map: dict) -> dict:
        for items in item_map.values():
            CanvasView._remove_scene_items(scene, items)
        return {}

    def _append_ring_selection_atom_ids(self, atom_ids: set[int], ring_atom_ids) -> None:
        if not isinstance(ring_atom_ids, list):
            return
        for atom_id in ring_atom_ids:
            if isinstance(atom_id, int) and atom_id in self.model.atoms:
                atom_ids.add(atom_id)

    def _append_polygon_selection_atom_ids(self, atom_ids: set[int], polygon) -> None:
        for atom_id, atom in self.model.atoms.items():
            if polygon.containsPoint(QPointF(atom.x, atom.y), Qt.FillRule.WindingFill):
                atom_ids.add(atom_id)

    def _append_selected_item_ids(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        item: QGraphicsItem,
    ) -> None:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                atom_ids.add(atom_id)
            return
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                bond_ids.add(bond_id)
            return
        if kind != "ring":
            return
        ring_atom_ids = item.data(2)
        if isinstance(ring_atom_ids, list):
            CanvasView._append_ring_selection_atom_ids(self, atom_ids, ring_atom_ids)
            return
        if hasattr(item, "polygon"):
            CanvasView._append_polygon_selection_atom_ids(self, atom_ids, item.polygon())

    def _selected_ids(self) -> tuple[set[int], set[int]]:
        atom_ids = set()
        bond_ids = set()
        for item in self.scene().selectedItems():
            CanvasView._append_selected_item_ids(self, atom_ids, bond_ids, item)
        return atom_ids, bond_ids

    def _selected_mark_atom_ids(self) -> set[int]:
        atom_ids: set[int] = set()
        for item in self.scene().selectedItems():
            if item.data(0) != "mark":
                continue
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int) and atom_id in self.model.atoms:
                atom_ids.add(atom_id)
        return atom_ids

    def _selected_chemical_ids(self) -> tuple[set[int], set[int]]:
        atom_ids, bond_ids = self._selected_ids()
        if atom_ids or bond_ids:
            return atom_ids, bond_ids
        # Scene-only items such as arrows, notes, and TS brackets should not
        # suppress a real atom-bound annotation selection from the 3D/export path.
        atom_ids.update(CanvasView._selected_mark_atom_ids(self))
        return atom_ids, bond_ids

    def _selection_items_for_copy(self) -> list[QGraphicsItem]:
        excluded_kinds = {"handle", "note_select", "selection_outline"}
        selected = CanvasView._selected_scene_items(self, excluded_kinds=excluded_kinds)
        if not selected:
            return []
        items: list[QGraphicsItem] = []
        seen: set[QGraphicsItem] = set()

        def add_with_children(item: QGraphicsItem) -> None:
            if not CanvasView._append_unique_scene_item(items, seen, item, excluded_kinds=excluded_kinds):
                return
            for child in item.childItems():
                add_with_children(child)

        for item in selected:
            kind = item.data(0)
            if kind == "bond":
                bond_id = item.data(1)
                if isinstance(bond_id, int):
                    for bond_item in self.bond_items.get(bond_id, []):
                        add_with_children(bond_item)
                    continue
            add_with_children(item)
        return items

    def _selection_payload_for_clipboard(self) -> dict | None:
        return self._scene_ops_controller._selection_payload_for_clipboard()

    @staticmethod
    def _translated_point_value(value, dx: float, dy: float):
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            return (float(value[0]) + dx, float(value[1]) + dy)
        return value

    def _translated_scene_item_state(
        self,
        state: dict,
        *,
        dx: float,
        dy: float,
        atom_id_map: dict[int, int],
    ) -> dict | None:
        if not isinstance(state, dict):
            return None
        translated = dict(state)
        kind = translated.get("kind")
        if kind == "ring":
            ring_atom_ids = translated.get("atom_ids")
            if not isinstance(ring_atom_ids, list) or not ring_atom_ids:
                return None
            mapped_atom_ids: list[int] = []
            for atom_id in ring_atom_ids:
                if not isinstance(atom_id, int) or atom_id not in atom_id_map:
                    return None
                mapped_atom_ids.append(atom_id_map[atom_id])
            points = translated.get("points", [])
            translated_points = []
            for point in points:
                translated_point = self._translated_point_value(point, dx, dy)
                if translated_point is None or translated_point is point:
                    continue
                translated_points.append(translated_point)
            translated["atom_ids"] = mapped_atom_ids
            translated["points"] = translated_points
            return translated
        if kind == "mark":
            atom_id = translated.get("atom_id")
            translated["atom_id"] = atom_id_map.get(atom_id) if isinstance(atom_id, int) else None
            if isinstance(translated.get("x"), (int, float)):
                translated["x"] = float(translated["x"]) + dx
            if isinstance(translated.get("y"), (int, float)):
                translated["y"] = float(translated["y"]) + dy
            return translated
        if kind == "note":
            if isinstance(translated.get("x"), (int, float)):
                translated["x"] = float(translated["x"]) + dx
            if isinstance(translated.get("y"), (int, float)):
                translated["y"] = float(translated["y"]) + dy
            return translated
        if kind in ARROW_KINDS:
            translated["start"] = self._translated_point_value(translated.get("start"), dx, dy)
            translated["end"] = self._translated_point_value(translated.get("end"), dx, dy)
            translated["control"] = self._translated_point_value(translated.get("control"), dx, dy)
            return translated
        if kind == "ts_bracket":
            for key in ("left", "right"):
                if isinstance(translated.get(key), (int, float)):
                    translated[key] = float(translated[key]) + dx
            for key in ("top", "bottom"):
                if isinstance(translated.get(key), (int, float)):
                    translated[key] = float(translated[key]) + dy
            return translated
        if kind == "orbital":
            translated["center"] = self._translated_point_value(translated.get("center"), dx, dy)
            return translated
        return translated

    @staticmethod
    def _clipboard_paste_offset(step: int, bond_length_px: float) -> tuple[float, float]:
        magnitude = max(18.0, bond_length_px * 0.35) * max(1, step)
        return magnitude, magnitude

    def _clipboard_selection_payload(self) -> tuple[dict | None, str | None]:
        return self._scene_ops_controller._clipboard_selection_payload()

    def _select_pasted_content(self, atom_ids: set[int], scene_items: list[QGraphicsItem]) -> None:
        self._scene_ops_controller._select_pasted_content(atom_ids, scene_items)

    @staticmethod
    def _copy_bounds_for_items(items: list[QGraphicsItem]) -> QRectF | None:
        return SceneOpsController._copy_bounds_for_items(items)

    def copy_selection_to_clipboard(self) -> bool:
        return self._scene_ops_controller.copy_selection_to_clipboard()

    def paste_selection_from_clipboard(self) -> bool:
        return self._scene_ops_controller.paste_selection_from_clipboard()

    def _expanded_atom_ids_for_structure(self, atom_ids: set[int], bond_ids: set[int]) -> set[int]:
        return expand_atom_ids_for_structure_state(self.model, atom_ids, bond_ids)

    def _build_submodel(self, atom_ids: set[int], bond_ids: set[int]):
        return build_submodel_state(
            self.model,
            atom_ids,
            bond_ids,
            bounds_getter=self._bounds_for_atoms,
        )

    def _build_atom_annotations(
        self,
        atom_ids: set[int],
        id_map: dict[int, int],
    ) -> dict[int, dict[str, int]]:
        return build_atom_annotations_state(atom_ids, id_map, self._mark_kinds_by_atom())

    def _mark_kinds_by_atom(self) -> dict[int, list[str]]:
        mark_kinds_by_atom: dict[int, list[str]] = {}
        for atom_id, marks in mark_registry_for(self).items():
            kinds: list[str] = []
            for mark in marks:
                data = mark.data(1)
                if not isinstance(data, dict):
                    continue
                kind = data.get("kind")
                if isinstance(kind, str):
                    kinds.append(kind)
            if kinds:
                mark_kinds_by_atom[atom_id] = kinds
        return mark_kinds_by_atom

    def build_3d_conversion_payload(self) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
        atom_ids, bond_ids = self._selected_structure_ids()
        return build_3d_conversion_payload_state(
            self.model,
            atom_ids,
            bond_ids,
            self._mark_kinds_by_atom(),
            bounds_getter=self._bounds_for_atoms,
        )

    def _selected_structure_ids(self, *, require_non_empty: bool = False) -> tuple[set[int], set[int]]:
        atom_ids, bond_ids = self._selected_chemical_ids()
        if require_non_empty and not atom_ids and not bond_ids:
            raise ValueError("Select a molecular structure on the canvas first.")
        return atom_ids, bond_ids

    def build_selected_structure_payload(self) -> tuple[MoleculeModel, dict[int, dict[str, int]], tuple[float, float, float, float]]:
        atom_ids, bond_ids = self._selected_structure_ids(require_non_empty=True)
        return self.build_structure_payload(atom_ids, bond_ids)

    def build_structure_payload(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
    ) -> tuple[MoleculeModel, dict[int, dict[str, int]], tuple[float, float, float, float]]:
        return build_structure_payload_state(
            self.model,
            atom_ids,
            bond_ids,
            self._mark_kinds_by_atom(),
            bounds_getter=self._bounds_for_atoms,
        )

    @staticmethod
    def _extend_bounds_with_item_rect(xs: list[float], ys: list[float], item: QGraphicsItem | None) -> None:
        if item is None:
            return
        rect = item.sceneBoundingRect()
        xs.extend([rect.left(), rect.right()])
        ys.extend([rect.top(), rect.bottom()])

    def _bounds_for_atoms(self, atom_ids: set[int], include_labels: bool = False):
        xs = []
        ys = []
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            xs.append(atom.x)
            ys.append(atom.y)
            if include_labels:
                self._extend_bounds_with_item_rect(xs, ys, self.atom_items.get(atom_id))
                self._extend_bounds_with_item_rect(xs, ys, self.atom_dots.get(atom_id))
        if not xs:
            return self.model.bounds()
        return min(xs), min(ys), max(xs), max(ys)

    def _new_note_item(self) -> QGraphicsTextItem:
        return NoteItem(self)

    def add_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        return _note_controller_for(self).create_text_note(pos, text)

    def add_mark(self, pos: QPointF, kind: str | None = None, atom_id: int | None = None, offset: QPointF | None = None, record: bool = True):
        return self._scene_decoration_service.add_mark(
            pos,
            kind=kind,
            atom_id=atom_id,
            offset=offset,
            record=record,
        )

    def add_mark_for_atom(self, atom_id: int, click_pos: QPointF, kind: str | None = None, record: bool = True):
        return canvas_mark_scene_service_for(self).add_mark_for_atom(
            atom_id,
            click_pos,
            kind=kind,
            record=record,
        )

    def _mark_selection_radius(self) -> float:
        return self._atom_pick_radius()

    def _build_mark_item(self, kind: str):
        return canvas_scene_decoration_build_service_for(self).build_mark_item(kind)

    def _mark_offset_from_click(self, atom_id: int, click_pos: QPointF, kind: str | None = None) -> QPointF:
        return canvas_mark_scene_service_for(self).mark_offset_from_click(atom_id, click_pos, kind=kind)

    def _mark_center(self, item) -> QPointF:
        return canvas_scene_decoration_build_service_for(self).mark_center(item)

    def _set_mark_center(self, item, center: QPointF) -> None:
        canvas_scene_decoration_build_service_for(self).set_mark_center(item, center)

    def _remove_mark_item(self, item) -> None:
        canvas_mark_scene_service_for(self).remove_mark_item(item)

    def _remove_marks_for_atom(self, atom_id: int) -> None:
        canvas_mark_scene_service_for(self).remove_marks_for_atom(atom_id)

    def update_text_note(self, item: QGraphicsTextItem, text: str) -> None:
        _note_controller_for(self).update_text_note(item, text)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        _note_controller_for(self).begin_note_edit(item)

    def apply_text_style_to_selected(self) -> None:
        _note_controller_for(self).apply_text_style_to_selected()

    def _apply_note_style(self, item: QGraphicsTextItem) -> None:
        _note_controller_for(self).apply_note_style(item)

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        _selection_controller_for(self).select_note(item, additive=additive)

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        _selection_controller_for(self).toggle_note_selection(item)

    def clear_note_selection(self) -> None:
        _selection_controller_for(self).clear_note_selection()

    def _update_note_box(self, item: QGraphicsTextItem) -> None:
        _note_controller_for(self).update_note_box(item)

    def _update_note_selection_box(self, item: QGraphicsTextItem) -> None:
        _selection_controller_for(self).update_note_selection_box(item)

    def _make_selectable(self, item) -> None:
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def _update_selection_outline(self) -> None:
        _selection_controller_for(self).update_selection_outline()

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        _selection_controller_for(self).shift_selection_outlines(dx, dy)

    def _atom_pick_radius(self) -> float:
        base_radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        return max(base_radius, self.renderer.style.bond_length_px * 0.32)

    def _bond_pick_radius(self) -> float:
        return self.renderer.style.bond_length_px * 0.528

    @staticmethod
    def _uses_compact_label_hit_shape(text: str) -> bool:
        text = text.strip()
        if len(text) == 1:
            return text.isalpha() and text.upper() == text
        if len(text) == 2:
            return (
                text[0].isalpha()
                and text[0].upper() == text[0]
                and text[1].isalpha()
                and text[1].lower() == text[1]
            )
        return False

    def _selection_indicator_rect_for_atom(self, atom_id: int) -> QRectF | None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return None
        radius = self._atom_pick_radius()
        return QRectF(
            atom.x - radius,
            atom.y - radius,
            radius * 2.0,
            radius * 2.0,
        )

    @staticmethod
    def _implicit_carbon_dot_brush() -> QColor:
        return QColor(0, 0, 0, 0)

    def _selection_bond_overlay_width(self, base_pen: QPen) -> float:
        return max(
            base_pen.widthF() + self.renderer.style.bond_spacing_px * 1.05,
            self._atom_pick_radius() * 0.75,
        )

    def _selection_line_stroke_path(
        self,
        start: QPointF,
        end: QPointF,
        width: float,
    ) -> QPainterPath:
        return _selection_controller_for(self).selection_line_stroke_path(start, end, width)

    def _selection_path_for_bond_item(self, item, width: float | None = None) -> QPainterPath:
        return _selection_controller_for(self).selection_path_for_bond_item(item, width=width)

    def _selection_path_for_bond(self, bond_id: int) -> QPainterPath:
        return _selection_controller_for(self).selection_path_for_bond(bond_id)

    def _selection_path_for_object_item(self, item) -> QPainterPath:
        return _selection_controller_for(self).selection_path_for_object_item(item)

    def _add_selection_object_overlay(self, item, color: QColor) -> None:
        _selection_controller_for(self).add_selection_object_overlay(item, color)

    def _add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
        atom_pad: float,
    ) -> None:
        _selection_controller_for(self).add_selection_component_overlay(atom_ids, bond_ids, color, atom_pad)

    def _selection_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        return _selection_controller_for(self).selection_center_for_atoms(atom_ids)

    def _selection_center_marker_enabled(self) -> bool:
        return _selection_controller_for(self).selection_center_marker_enabled()

    def _add_selection_center_marker(self, center: QPointF) -> None:
        _selection_controller_for(self).add_selection_center_marker(center)

    def suspend_selection_outline(self, suspend: bool) -> None:
        self._suspend_selection_outline = bool(suspend)

    def _ensure_atom_neighbors(self, atom_id: int) -> None:
        canvas_graph_service_for(self).ensure_atom_neighbors(atom_id)

    def _ensure_atom_bond_ids(self, atom_id: int) -> None:
        canvas_graph_service_for(self).ensure_atom_bond_ids(atom_id)

    def _add_bond_neighbors(self, a_id: int, b_id: int) -> None:
        canvas_graph_service_for(self).add_bond_neighbors(a_id, b_id)

    def _remove_bond_neighbors(self, a_id: int, b_id: int, skip_bond_id: int | None = None) -> None:
        canvas_graph_service_for(self).remove_bond_neighbors(a_id, b_id, skip_bond_id=skip_bond_id)

    def _add_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        canvas_graph_service_for(self).add_bond_index(bond_id, a_id, b_id)

    def _remove_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        canvas_graph_service_for(self).remove_bond_index(bond_id, a_id, b_id)

    def _rebuild_bond_adjacency(self) -> None:
        canvas_graph_service_for(self).rebuild_bond_adjacency()

    def _connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        return canvas_graph_service_for(self).connected_components(atom_ids)

    def _component_without_bond(self, start_atom_id: int, skip_bond_id: int) -> set[int]:
        return canvas_graph_service_for(self).component_without_bond(start_atom_id, skip_bond_id)

    def _bond_in_cycle(self, bond_id: int) -> bool:
        return canvas_graph_service_for(self).bond_in_cycle(bond_id)

    def _bond_is_rotatable(self, bond_id: int) -> bool:
        return canvas_graph_service_for(self).bond_is_rotatable(bond_id)

    def _bond_component_atoms(self, bond_id: int) -> set[int] | None:
        return canvas_graph_service_for(self).bond_component_atoms(bond_id)

    def _rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        allow_fallback: bool,
    ) -> set[int] | None:
        return canvas_graph_service_for(self).rotation_side_for_bond(
            bond_id,
            selected_atom_ids,
            allow_fallback,
        )

    def _preferred_rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        press_pos: QPointF | None = None,
        allow_fallback: bool = True,
    ) -> set[int] | None:
        return canvas_graph_service_for(self).preferred_rotation_side_for_bond(
            bond_id,
            selected_atom_ids,
            press_pos=press_pos,
            allow_fallback=allow_fallback,
        )

    def _rotatable_axis_from_selection(
        self,
        selected_atom_ids: set[int],
        selected_bond_ids: set[int],
    ) -> tuple[int, set[int]] | None:
        return canvas_graph_service_for(self).rotatable_axis_from_selection(
            selected_atom_ids,
            selected_bond_ids,
        )

    def set_selection_info_callback(self, callback) -> None:
        self._selection_info_callback = callback

    def set_error_callback(self, callback) -> None:
        self._error_callback = callback

    def notify_error(self, message: str) -> bool:
        """Report a user-facing error. Returns True if a handler consumed it."""
        if self._error_callback is not None:
            self._error_callback(message)
            return True
        return False

    def set_zoom_callback(self, callback) -> None:
        self._zoom_callback = callback

    def _touch_interaction(self) -> None:
        self._last_interaction_time = time.monotonic()

    def _maybe_warm_rdkit(self) -> None:
        if not self._rdkit_warmup_pending:
            return
        if self.rdkit.is_unavailable():
            self._rdkit_warmup_pending = False
            self._selection_pending_signature = None
            return
        if self.rdkit.is_loaded():
            self._rdkit_warmup_pending = False
            self._selection_pending_signature = None
            self._emit_selection_info()
            return
        if time.monotonic() - self._last_interaction_time < self._rdkit_idle_threshold:
            return
        self.rdkit.preload()
        self._rdkit_warmup_pending = False
        self._selection_pending_signature = None
        self._emit_selection_info()

    @staticmethod
    def _selection_signature_for(atom_ids: set[int], bond_ids: set[int]) -> tuple[frozenset[int], frozenset[int]]:
        return frozenset(atom_ids), frozenset(bond_ids)

    def _emit_selection_info(self) -> None:
        if not self._selection_info_callback:
            return
        if self._rotation_selection_ids is not None:
            atom_ids, bond_ids = self._rotation_selection_ids
        else:
            atom_ids, bond_ids = self._selected_chemical_ids()
        if not atom_ids and not bond_ids:
            self._selection_signature = None
            self._selection_pending_signature = None
            self._selection_info_cache = ("", "")
            self._rdkit_warmup_pending = False
            self._selection_info_callback("", "")
            return
        signature = self._selection_signature_for(atom_ids, bond_ids)
        if signature == self._selection_signature:
            formula_text, mw_text = self._selection_info_cache
            self._selection_info_callback(formula_text, mw_text)
            return
        if self.rdkit.is_unavailable():
            self._selection_signature = None
            self._selection_pending_signature = None
            self._selection_info_cache = ("", "")
            self._rdkit_warmup_pending = False
            self._selection_info_callback("", "")
            return
        if not self.rdkit.is_loaded():
            if signature != self._selection_pending_signature:
                self._selection_pending_signature = signature
                self._selection_info_cache = ("", "")
                self._selection_info_callback("", "")
            self._rdkit_warmup_pending = True
            return
        submodel, _, _ = self._build_submodel(atom_ids, bond_ids)
        formula, mw, _ = self.rdkit.compute_props(submodel)
        formula_text = formula or ""
        mw_text = f"{mw:.2f}" if mw is not None else ""
        self._selection_signature = signature
        self._selection_pending_signature = None
        self._selection_info_cache = (formula_text, mw_text)
        self._selection_info_callback(formula_text, mw_text)

    def _clear_hover_highlight(self) -> None:
        self._hover_scene_service.clear_hover_highlight()

    def _add_hover_indicator_item(self, item: QGraphicsItem) -> None:
        self.scene().addItem(item)
        self.hover_items.append(item)

    def _add_atom_hover_indicator(self, atom_id: int) -> None:
        self._hover_scene_service.add_atom_hover_indicator(atom_id)

    def _add_bond_hover_indicator(self, bond_id: int) -> None:
        self._hover_scene_service.add_bond_hover_indicator(bond_id)

    def _mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        kind: str | None = None,
    ) -> QPointF:
        return canvas_mark_scene_service_for(self).mark_center_for_pointer(pos, atom_id, kind=kind)

    def _add_mark_hover_preview(self, pos: QPointF) -> None:
        self._mark_hover_preview_service.add_mark_hover_preview(pos)

    def _update_hover_highlight(self, pos: QPointF) -> None:
        self._hover_interaction_service.update_hover_highlight(pos)

    def _find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        return canvas_hit_testing_service_for(self).find_bond_near(pos, max_dist)

    def _add_bond_style_hover_preview(self, bond) -> None:
        self._bond_hover_preview_service.add_bond_style_hover_preview(bond)

    def _add_bond_tool_hover_preview(self, atom_id: int, pos: QPointF) -> None:
        self._bond_hover_preview_service.add_bond_tool_hover_preview(atom_id, pos)

    def _bond_preview_config(
        self,
        *,
        style: str | None = None,
        order: int | None = None,
    ) -> BondPreviewConfig:
        return BondPreviewConfig(
            style=style or self.active_bond_style,
            order=self.active_bond_order if order is None else order,
            bond_length_px=self.renderer.style.bond_length_px,
            bond_line_width=self.renderer.style.bond_line_width,
            bold_bond_width=self.renderer.style.bold_bond_width,
            hash_spacing_px=self.renderer.style.hash_spacing_px,
        )

    def _bond_preview_build_resolvers(self) -> BondPreviewBuildResolvers:
        return BondPreviewBuildResolvers(
            draw_wedge_bond=self._draw_wedge_bond,
            draw_hash_bond=self._draw_hash_bond,
            draw_dotted_bond=self._draw_dotted_bond,
            draw_parallel_bonds=self._draw_parallel_bonds,
            line_normal=self._line_normal,
            one_sided_bond_strip=self._one_sided_bond_strip,
            bond_pen=self.renderer.bond_pen,
            dotted_bond_pen=self.renderer.dotted_bond_pen,
        )

    def _bond_preview_update_resolvers(self) -> BondPreviewUpdateResolvers:
        return BondPreviewUpdateResolvers(
            wedge_polygon=self._wedge_polygon,
            hash_segments=self._hash_segments,
            dotted_bond_path=self._dotted_bond_path,
            parallel_bond_segments=self._parallel_bond_segments,
            line_normal=self._line_normal,
            strip_polygon=self._strip_polygon,
        )

    def _build_bond_preview_items(
        self,
        start: QPointF,
        end: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list:
        return build_bond_preview_items_helper(
            start,
            end,
            config=self._bond_preview_config(),
            a_id=a_id,
            b_id=b_id,
            resolvers=self._bond_preview_build_resolvers(),
        )

    def update_bond_preview_items(
        self,
        items: list,
        start: QPointF,
        end: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        style: str | None = None,
        order: int | None = None,
    ) -> bool:
        return update_bond_preview_items_helper(
            items,
            start,
            end,
            config=self._bond_preview_config(style=style, order=order),
            a_id=a_id,
            b_id=b_id,
            resolvers=self._bond_preview_update_resolvers(),
        )

    def _add_hover_preview_items(self, items: list) -> None:
        self._hover_scene_service.add_hover_preview_items(items)

    def _connected_atom_unit_vectors(self, atom_id: int) -> list[tuple[float, float]]:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return []
        vectors: list[tuple[float, float]] = []
        for bond in self.model.bonds:
            if bond is None or (bond.a != atom_id and bond.b != atom_id):
                continue
            other_id = bond.b if bond.a == atom_id else bond.a
            other = self.model.atoms.get(other_id)
            if other is None:
                continue
            dx = other.x - atom.x
            dy = other.y - atom.y
            length = math.hypot(dx, dy)
            if length <= 1e-9:
                continue
            vectors.append((dx / length, dy / length))
        return vectors

    @staticmethod
    def _default_bond_angle_for_vectors(vectors: list[tuple[float, float]]) -> float:
        if len(vectors) >= 2:
            sx = sum(dx for dx, _ in vectors)
            sy = sum(dy for _, dy in vectors)
            if math.hypot(sx, sy) > 1e-6:
                return math.degrees(math.atan2(-sy, -sx))
            return math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 90.0
        if vectors:
            return math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 120.0
        return 0.0

    def _default_bond_endpoint(self, start: QPointF, start_atom_id: int | None) -> QPointF:
        bond_len = self.renderer.style.bond_length_px
        angle = 0.0
        if start_atom_id is not None:
            angle = CanvasView._default_bond_angle_for_vectors(
                CanvasView._connected_atom_unit_vectors(self, start_atom_id)
            )
        rad = math.radians(angle)
        return QPointF(start.x() + math.cos(rad) * bond_len, start.y() + math.sin(rad) * bond_len)

    def _bond_hover_endpoint(self, start: QPointF, pos: QPointF, start_atom_id: int | None = None) -> QPointF:
        if start_atom_id is not None:
            return self._default_bond_endpoint(start, start_atom_id)
        dx = pos.x() - start.x()
        dy = pos.y() - start.y()
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            angle = 0.0
        else:
            angle = math.degrees(math.atan2(dy, dx))
        step = self.snap_angle_step or 30
        snap_angle = round(angle / step) * step
        bond_len = self.renderer.style.bond_length_px
        rad = math.radians(snap_angle)
        return QPointF(start.x() + math.cos(rad) * bond_len, start.y() + math.sin(rad) * bond_len)

    def _bond_preview_signature(self) -> str | None:
        if self.tools.active is None or self.tools.active.name != "bond":
            return None
        return f"{self.active_bond_style}:{self.active_bond_order}"

    @staticmethod
    def _distance_point_to_segment(p: QPointF, a: QPointF, b: QPointF) -> float:
        return CanvasHitTestingService.distance_point_to_segment(p, a, b)

    def add_arrow(self, start: QPointF, end: QPointF, kind: str):
        return self._scene_decoration_service.add_arrow(start, end, kind)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        return canvas_scene_decoration_build_service_for(self).preview_arrow(start, end, kind)

    def _build_arrow_item(self, start: QPointF, end: QPointF, kind: str) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_arrow_item(start, end, kind)

    def _build_single_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_single_head_arrow(start, end)

    def _build_double_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_double_head_arrow(start, end)

    def _build_dotted_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_dotted_arrow(start, end)

    def _build_curved_arrow(self, start: QPointF, end: QPointF, double: bool) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_curved_arrow(start, end, double)

    def _build_inhibition_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_inhibition_arrow(start, end)

    def _build_equilibrium_item(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_equilibrium_item(start, end)

    def _add_arrow_head(self, path: QPainterPath, start: QPointF, end: QPointF, double: bool) -> None:
        canvas_scene_decoration_build_service_for(self).add_arrow_head(path, start, end, double)

    def _ts_bracket_rect_from_points(self, start: QPointF, end: QPointF) -> QRectF:
        return canvas_scene_decoration_build_service_for(self).ts_bracket_rect_from_points(start, end)

    def _ts_bracket_stroke_width(self) -> float:
        return canvas_scene_decoration_build_service_for(self).ts_bracket_stroke_width()

    def _ts_bracket_path(self, rect: QRectF) -> QPainterPath:
        return canvas_scene_decoration_build_service_for(self).ts_bracket_path(rect)

    def _build_ts_bracket_item(self, rect: QRectF) -> QGraphicsPathItem:
        return canvas_scene_decoration_build_service_for(self).build_ts_bracket_item(rect)

    def add_ts_bracket_from_points(self, start: QPointF, end: QPointF):
        return self.add_ts_bracket(self._ts_bracket_rect_from_points(start, end))

    def add_ts_bracket(self, rect: QRectF):
        return self._scene_decoration_service.add_ts_bracket(rect)

    def preview_ts_bracket(self, start: QPointF, end: QPointF):
        return canvas_scene_decoration_build_service_for(self).preview_ts_bracket(start, end)

    def add_orbital(self, center: QPointF) -> None:
        return self._scene_decoration_service.add_orbital(center)

    def _build_orbital_items(self, center: QPointF, kind: str):
        return canvas_scene_decoration_build_service_for(self).build_orbital_items(center, kind)

    def clear_handles(self) -> None:
        handle_overlay_service_for(self).clear_handles()

    def show_orbital_handles(self, item) -> None:
        handle_overlay_service_for(self).show_orbital_handles(item)

    def show_curved_handles(self, item) -> None:
        handle_overlay_service_for(self).show_curved_handles(item)

    def _create_handle(self, pos: QPointF, handle_type: str, target):
        return handle_overlay_service_for(self).create_handle(pos, handle_type, target)

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        _handle_controller_for(self).update_handle_drag(handle, scene_pos)

    def _update_orbital_scale(self, item, pos: QPointF) -> None:
        _handle_controller_for(self).update_orbital_scale(item, pos)

    def _update_orbital_rotate(self, item, pos: QPointF) -> None:
        _handle_controller_for(self).update_orbital_rotate(item, pos)

    def _update_curved_control(self, item, pos: QPointF) -> None:
        _handle_controller_for(self).update_curved_control(item, pos)

    def _update_curved_endpoint(self, item, pos: QPointF, endpoint: str) -> None:
        _handle_controller_for(self).update_curved_endpoint(item, pos, endpoint)

    def _default_curved_control(self, start: QPointF, end: QPointF) -> QPointF:
        return _handle_controller_for(self).default_curved_control(start, end)

    def _curved_midpoint(self, start: QPointF, control: QPointF, end: QPointF) -> QPointF:
        return _handle_controller_for(self).curved_midpoint(start, control, end)

    def _control_from_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        return _handle_controller_for(self).control_from_midpoint(start, end, mid)

    def _clamp_curved_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        return _handle_controller_for(self).clamp_curved_midpoint(start, end, mid)

    def _set_selection_highlight(self, items: list) -> None:
        selection_highlight_styler_for(self).set_selection_highlight(items)

    def _clear_selection_highlight(self) -> None:
        selection_highlight_styler_for(self).clear_selection_highlight()

    def _apply_selection_style(self, item, selected: bool) -> None:
        selection_highlight_styler_for(self).apply_selection_style(item, selected)

    def mousePressEvent(self, event) -> None:
        _pointer_controller_for(self).mouse_press_event(
            event,
            base_mouse_press_event=super().mousePressEvent,
        )

    def mouseDoubleClickEvent(self, event) -> None:
        _pointer_controller_for(self).mouse_double_click_event(
            event,
            base_mouse_double_click_event=super().mouseDoubleClickEvent,
        )

    def mouseMoveEvent(self, event) -> None:
        _pointer_controller_for(self).mouse_move_event(
            event,
            base_mouse_move_event=super().mouseMoveEvent,
        )

    def mouseReleaseEvent(self, event) -> None:
        _pointer_controller_for(self).mouse_release_event(
            event,
            base_mouse_release_event=super().mouseReleaseEvent,
        )

    def viewportEvent(self, event) -> bool:
        if "_pointer_controller" not in self.__dict__:
            return super().viewportEvent(event)
        return _pointer_controller_for(self).viewport_event(
            event,
            single_shot=QTimer.singleShot,
            base_viewport_event=super().viewportEvent,
        )

    def wheelEvent(self, event) -> None:
        _pointer_controller_for(self).wheel_event(
            event,
            base_wheel_event=super().wheelEvent,
        )

    def event(self, event) -> bool:
        if "_input_controller" not in self.__dict__:
            return super().event(event)
        return _input_controller_for(self).event(event, native_gesture_event_type=QNativeGestureEvent)

    def _should_override_chemdraw_shortcut(self, event) -> bool:
        return _input_controller_for(self).should_override_chemdraw_shortcut(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        if "_pointer_controller" not in self.__dict__:
            super().scrollContentsBy(dx, dy)
            return
        _pointer_controller_for(self).scroll_contents_by(
            dx,
            dy,
            base_scroll_contents_by=super().scrollContentsBy,
        )

    def _reset_view_transform(self) -> None:
        self._base_transform = QTransform()
        self._perspective_shear = 0.0
        self._perspective_scale_y = 1.0
        self.setTransform(QTransform())

    def rotate_view(self, angle_degrees: float) -> None:
        if angle_degrees:
            transform = QTransform(self._base_transform)
            transform.rotate(angle_degrees)
            self._base_transform = transform
            self._update_view_transform()

    def rotate_selection(self, angle_degrees: float) -> None:
        atom_ids, bond_ids = self._selected_ids()
        atom_ids = selected_rotation_atom_ids(atom_ids, bond_ids, bonds=self.model.bonds)
        if not atom_ids:
            return
        center = self._center_for_atoms(atom_ids)
        if center is None:
            return
        angle = math.radians(angle_degrees)
        for atom_id, (x, y) in rotated_atom_positions(
            atom_ids,
            atoms=self.model.atoms,
            center=center,
            angle_radians=angle,
        ).items():
            atom = self.model.atoms[atom_id]
            atom.x = x
            atom.y = y
            label = self.atom_items.get(atom_id)
            if label is not None:
                self._position_label(label, atom.x, atom.y)
        for atom_id in atom_ids:
            self._redraw_connected_bonds(atom_id)
        self._rotate_ring_fills(atom_ids, center, angle)
        self._update_selection_outline()

    def _axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        press_pos: QPointF | None = None,
    ) -> tuple[int, set[int]] | None:
        return canvas_graph_service_for(self).axis_from_rotation_hint(
            axis_hint,
            rotation_atom_ids,
            press_pos=press_pos,
        )

    def begin_selection_3d_rotation(
        self,
        axis_hint: int | None = None,
        press_pos: QPointF | None = None,
    ) -> bool:
        return self._selection_rotation_controller.begin_selection_3d_rotation(
            axis_hint=axis_hint,
            press_pos=press_pos,
        )

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        self._selection_rotation_controller.update_selection_3d_rotation(delta_x, delta_y)

    def end_selection_3d_rotation(self) -> None:
        self._selection_rotation_controller.end_selection_3d_rotation()

    def _redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        for bond_id in CanvasView._bond_ids_for_atom_ids(self, atom_ids):
            self._redraw_bond(bond_id)

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        return canvas_graph_service_for(self).bond_sets_for_atoms(atom_ids)

    def _restore_selection_from_ids(self, atom_ids: set[int], bond_ids: set[int]) -> None:
        self.scene().clearSelection()
        for atom_id in atom_ids:
            item = self.atom_items.get(atom_id) or self.atom_dots.get(atom_id)
            if item is not None:
                item.setSelected(True)
        for bond_id in bond_ids:
            for item in self.bond_items.get(bond_id, []):
                item.setSelected(True)
        self._update_selection_outline()

    def _expand_connected_atoms(self, atom_ids: set[int]) -> set[int]:
        return canvas_graph_service_for(self).expand_connected_atoms(atom_ids)

    def _update_ring_fills_for_atoms(self, atom_ids: set[int]) -> None:
        canvas_ring_fill_scene_service_for(self).update_ring_fills_for_atoms(atom_ids)

    @staticmethod
    def _normalize_3d(
        dx: float,
        dy: float,
        dz: float,
    ) -> tuple[float, float, float] | None:
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length <= 1e-9:
            return None
        return (dx / length, dy / length, dz / length)

    def _perspective_camera_distance(self) -> float:
        return max(self.renderer.style.bond_length_px * 8.0, 120.0)

    def _project_point_3d(
        self,
        point: tuple[float, float, float],
        center_3d: tuple[float, float, float] | None = None,
        anchor_2d: tuple[float, float] | None = None,
    ) -> tuple[float, float]:
        rotation = rotation_state_for(self)
        if center_3d is None:
            center_3d = rotation.projection_center_3d
        if center_3d is None:
            return point[0], point[1]
        if anchor_2d is None:
            anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
        cx, cy, cz = center_3d
        anchor_x, anchor_y = anchor_2d
        focal = self._perspective_camera_distance()
        dz = max(min(point[2] - cz, focal * 0.7), -focal * 0.8)
        denom = max(focal - dz, focal * 0.2)
        scale = focal / denom
        return (
            anchor_x + (point[0] - cx) * scale,
            anchor_y + (point[1] - cy) * scale,
        )

    def _unproject_scene_point_3d(
        self,
        point: QPointF,
        z: float,
        center_3d: tuple[float, float, float] | None = None,
        anchor_2d: tuple[float, float] | None = None,
    ) -> tuple[float, float, float]:
        rotation = rotation_state_for(self)
        if center_3d is None:
            center_3d = rotation.projection_center_3d
        if center_3d is None:
            return (point.x(), point.y(), z)
        if anchor_2d is None:
            anchor_2d = rotation.projection_anchor_2d or (center_3d[0], center_3d[1])
        cx, cy, cz = center_3d
        anchor_x, anchor_y = anchor_2d
        focal = self._perspective_camera_distance()
        dz = max(min(z - cz, focal * 0.7), -focal * 0.8)
        denom = max(focal - dz, focal * 0.2)
        scale = focal / denom
        return (
            cx + (point.x() - anchor_x) / scale,
            cy + (point.y() - anchor_y) / scale,
            z,
        )

    def _current_atom_coords_3d(self, atom_id: int) -> tuple[float, float, float] | None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return None
        coords = self.atom_coords_3d.get(atom_id)
        if coords is None:
            return (atom.x, atom.y, 0.0)
        proj_x, proj_y = self._project_point_3d(coords)
        tolerance = max(1.0, self.renderer.style.bond_length_px * 0.15)
        if math.hypot(proj_x - atom.x, proj_y - atom.y) > tolerance:
            return (atom.x, atom.y, 0.0)
        return coords

    def _center_for_coords_3d(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> tuple[float, float, float] | None:
        if not atom_ids:
            return None
        points = [coords[atom_id] for atom_id in atom_ids if atom_id in coords]
        if not points:
            return None
        count = len(points)
        return (
            sum(point[0] for point in points) / count,
            sum(point[1] for point in points) / count,
            sum(point[2] for point in points) / count,
        )

    def _atom_in_planar_system(self, atom_id: int) -> bool:
        graph = graph_state_for(self)
        for bond_id in graph.atom_bond_ids.get(atom_id, ()):
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            if bond.order > 1 or self._bond_in_cycle(bond_id):
                return True
        return False

    def _bond_is_planar_fragment_edge(self, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.model.bonds)):
            return False
        bond = self.model.bonds[bond_id]
        if bond is None:
            return False
        if bond.order > 1 or self._bond_in_cycle(bond_id):
            return True
        return self._atom_in_planar_system(bond.a) and self._atom_in_planar_system(bond.b)

    def _planar_fragment_components(self, atom_ids: set[int]) -> list[set[int]]:
        adjacency: dict[int, set[int]] = {}
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if bond.a not in atom_ids or bond.b not in atom_ids:
                continue
            if not self._bond_is_planar_fragment_edge(bond_id):
                continue
            adjacency.setdefault(bond.a, set()).add(bond.b)
            adjacency.setdefault(bond.b, set()).add(bond.a)
        visited: set[int] = set()
        components: list[set[int]] = []
        for atom_id in adjacency:
            if atom_id in visited:
                continue
            component: set[int] = set()
            stack = [atom_id]
            visited.add(atom_id)
            while stack:
                current = stack.pop()
                component.add(current)
                for neighbor in adjacency.get(current, ()):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    stack.append(neighbor)
            if len(component) >= 3:
                components.append(component)
        return components

    def _fragment_plane_normal(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> tuple[float, float, float] | None:
        points = [coords[atom_id] for atom_id in atom_ids if atom_id in coords]
        count = len(points)
        if count < 3:
            return None
        for i in range(count - 2):
            ax, ay, az = points[i]
            for j in range(i + 1, count - 1):
                bx, by, bz = points[j]
                ab = (bx - ax, by - ay, bz - az)
                for k in range(j + 1, count):
                    cx, cy, cz = points[k]
                    ac = (cx - ax, cy - ay, cz - az)
                    normal = self._normalize_3d(
                        ab[1] * ac[2] - ab[2] * ac[1],
                        ab[2] * ac[0] - ab[0] * ac[2],
                        ab[0] * ac[1] - ab[1] * ac[0],
                    )
                    if normal is not None:
                        return normal
        return (0.0, 0.0, 1.0)

    def _flatten_planar_fragments(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]]:
        if not atom_ids:
            return dict(coords)
        flattened = dict(coords)
        for fragment in self._planar_fragment_components(atom_ids):
            normal = self._fragment_plane_normal(fragment, flattened)
            if normal is None:
                continue
            centroid = self._center_for_coords_3d(fragment, flattened)
            if centroid is None:
                continue
            cx, cy, cz = centroid
            nx, ny, nz = normal
            for atom_id in fragment:
                point = flattened.get(atom_id)
                if point is None:
                    continue
                px, py, pz = point
                distance = (px - cx) * nx + (py - cy) * ny + (pz - cz) * nz
                flattened[atom_id] = (
                    px - nx * distance,
                    py - ny * distance,
                    pz - nz * distance,
                )
        return flattened

    def _apply_projected_atom_positions(
        self,
        atom_ids: set[int],
        coords_3d: dict[int, tuple[float, float, float]],
    ) -> None:
        for atom_id in atom_ids:
            point = coords_3d.get(atom_id)
            if point is None:
                continue
            self.atom_coords_3d[atom_id] = point
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            proj_x, proj_y = self._project_point_3d(point)
            atom.x = proj_x
            atom.y = proj_y
            label = self.atom_items.get(atom_id)
            if label is not None:
                self._position_label(label, atom.x, atom.y)
            dot = self.atom_dots.get(atom_id)
            if dot is not None:
                dot.setPos(atom.x, atom.y)
            marks = mark_registry_for(self).get_for_atom(atom_id)
            if marks:
                for mark in list(marks):
                    data = mark.data(1) or {}
                    dx = data.get("dx")
                    dy = data.get("dy")
                    if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
                        self._set_mark_center(mark, QPointF(atom.x + dx, atom.y + dy))
                    else:
                        self._set_mark_center(mark, QPointF(atom.x, atom.y))

    def _average_bond_length_for_atoms(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> float | None:
        if not atom_ids:
            return None
        bond_ids = CanvasView._bond_ids_within_atom_ids(self, atom_ids)
        if not bond_ids:
            return None
        total = 0.0
        count = 0
        for bond_id in bond_ids:
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            if bond.a not in atom_ids or bond.b not in atom_ids:
                continue
            a_coords = coords.get(bond.a)
            b_coords = coords.get(bond.b)
            if a_coords is None or b_coords is None:
                continue
            dx = a_coords[0] - b_coords[0]
            dy = a_coords[1] - b_coords[1]
            dist = math.hypot(dx, dy)
            if dist > 1e-9:
                total += dist
                count += 1
        if count == 0:
            return None
        return total / count

    def _bond_ids_for_atom_ids(self, atom_ids: set[int]) -> set[int]:
        graph = graph_state_for(self)
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(graph.atom_bond_ids.get(atom_id, ()))
        return bond_ids

    def _bond_ids_within_atom_ids(self, atom_ids: set[int]) -> set[int]:
        if not atom_ids:
            return set()
        bond_ids = CanvasView._bond_ids_for_atom_ids(self, atom_ids)
        if not bond_ids:
            # Some test/setup paths do not materialize the adjacency cache.
            return {
                bond_id
                for bond_id, bond in enumerate(self.model.bonds)
                if bond is not None and bond.a in atom_ids and bond.b in atom_ids
            }
        selected_bond_ids: set[int] = set()
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            if bond.a in atom_ids and bond.b in atom_ids:
                selected_bond_ids.add(bond_id)
        return selected_bond_ids

    def _rotation_scale_for_coords(
        self,
        atom_ids: set[int],
        rotated_coords: dict[int, tuple[float, float, float]],
        extra_atom_ids: set[int] | tuple[int, ...] = (),
    ) -> float:
        rotation = rotation_state_for(self)
        if not rotation.base_bond_length:
            return 1.0
        scale_atom_ids = set(atom_ids)
        scale_atom_ids.update(extra_atom_ids)
        current_coords = dict(rotation.base_coords)
        current_coords.update(rotated_coords)
        current_avg = CanvasView._average_bond_length_for_atoms(self, scale_atom_ids, current_coords)
        if not current_avg or current_avg <= 1e-9:
            return 1.0
        scale = rotation.base_bond_length / current_avg
        if not math.isfinite(scale) or scale <= 0.0:
            return 1.0
        return scale

    @staticmethod
    def _rotate_point_around_axis(
        point: tuple[float, float, float],
        axis_start: tuple[float, float, float],
        axis_end: tuple[float, float, float],
        angle: float,
    ) -> tuple[float, float, float]:
        px, py, pz = point
        ax, ay, az = axis_start
        bx, by, bz = axis_end
        vx = bx - ax
        vy = by - ay
        vz = bz - az
        vlen = math.sqrt(vx * vx + vy * vy + vz * vz)
        if vlen < 1e-9:
            return point
        ux = vx / vlen
        uy = vy / vlen
        uz = vz / vlen
        x = px - ax
        y = py - ay
        z = pz - az
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dot = ux * x + uy * y + uz * z
        cross_x = uy * z - uz * y
        cross_y = uz * x - ux * z
        cross_z = ux * y - uy * x
        rx = x * cos_a + cross_x * sin_a + ux * dot * (1.0 - cos_a)
        ry = y * cos_a + cross_y * sin_a + uy * dot * (1.0 - cos_a)
        rz = z * cos_a + cross_z * sin_a + uz * dot * (1.0 - cos_a)
        return rx + ax, ry + ay, rz + az

    def _rotate_ring_fills_3d(
        self,
        atom_ids: set[int],
        center: tuple[float, float, float],
        angle_x: float,
        angle_y: float,
        f: float,
    ) -> None:
        canvas_ring_fill_scene_service_for(self).rotate_ring_fills_3d(atom_ids, center, angle_x, angle_y, f)

    def begin_selection_rotation(self) -> bool:
        return _rotation_preview_controller_for(self).begin_selection_rotation()

    def update_rotation_preview(self, angle_degrees: float) -> None:
        _rotation_preview_controller_for(self).update_rotation_preview(angle_degrees)

    def commit_selection_rotation(self) -> None:
        _rotation_preview_controller_for(self).commit_selection_rotation()

    def _rotate_ring_fills(self, atom_ids: set[int], center: QPointF, angle_rad: float) -> None:
        canvas_ring_fill_scene_service_for(self).rotate_ring_fills(atom_ids, center, angle_rad)

    def _center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        return center_for_atoms(atom_ids, atoms=self.model.atoms)

    def _bounding_box_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        return bounding_box_center_for_atoms(atom_ids, atoms=self.model.atoms)

    def _update_view_transform(self) -> None:
        transform = QTransform(self._base_transform)
        if self._perspective_shear or self._perspective_scale_y != 1.0:
            transform.shear(self._perspective_shear, 0.0)
            transform.scale(1.0, self._perspective_scale_y)
        self.setTransform(transform)

    def add_bond_from_points(self, start, end) -> None:
        self._add_bond_between_points(start, end, self.active_bond_style, self.active_bond_order)

    def _add_bond_between_points(
        self,
        start: QPointF,
        end: QPointF,
        style: str,
        order: int,
    ) -> tuple[int, int] | None:
        return self._structure_build_service.add_bond_between_points(start, end, style, order)

    def _benzene_ring_points(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return self._structure_build_service.benzene_ring_points(
            center,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )

    def add_benzene_ring(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
        before_smiles_input: str | None = None,
    ) -> None:
        self._structure_build_service.add_benzene_ring(
            center,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
            before_smiles_input=before_smiles_input,
        )

    def _create_ring_fill_item(self, points: list[QPointF], atom_ids: list[int]):
        return canvas_ring_fill_scene_service_for(self).create_ring_fill_item(points, atom_ids)

    @staticmethod
    def _bond_matches_atoms(bond: Bond | None, a_id: int, b_id: int) -> bool:
        if bond is None:
            return False
        return (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id)

    @staticmethod
    def _first_matching_bond_id(
        bonds: list[Bond | None],
        a_id: int,
        b_id: int,
        *,
        skip_bond_id: int | None = None,
    ) -> int | None:
        for bond_id, bond in enumerate(bonds):
            if skip_bond_id is not None and bond_id == skip_bond_id:
                continue
            if CanvasView._bond_matches_atoms(bond, a_id, b_id):
                return bond_id
        return None

    def _bond_id_between(self, a_id: int, b_id: int, skip_bond_id: int | None = None) -> int | None:
        if a_id == b_id:
            return None
        graph = graph_state_for(self)
        bonds_a = graph.atom_bond_ids.get(a_id)
        bonds_b = graph.atom_bond_ids.get(b_id)
        if bonds_a is None or bonds_b is None:
            return CanvasView._first_matching_bond_id(
                self.model.bonds,
                a_id,
                b_id,
                skip_bond_id=skip_bond_id,
            )
        if not bonds_a or not bonds_b:
            return None
        shared = bonds_a & bonds_b
        if skip_bond_id is not None and skip_bond_id in shared:
            shared = set(shared)
            shared.discard(skip_bond_id)
        if not shared:
            return None
        for bond_id in sorted(shared):
            bond = self.model.bonds[bond_id]
            if CanvasView._bond_matches_atoms(bond, a_id, b_id):
                return bond_id
        return None

    def _bond_exists(self, a_id: int, b_id: int) -> bool:
        return CanvasView._bond_id_between(self, a_id, b_id) is not None

    def _atom_bond_order_sum(self, atom_id: int) -> int:
        total = 0
        for bond in self.model.bonds:
            if bond is None:
                continue
            if bond.a == atom_id or bond.b == atom_id:
                total += max(1, int(bond.order or 1))
        return total

    def _viewport_scene_center(self) -> QPointF:
        return self.mapToScene(self.viewport().rect().center())

    def _run_recorded_structure_build(self, action) -> None:
        self._structure_build_service.run_recorded_build(action)

    def _run_recorded_regular_ring_template(self, n: int) -> None:
        self._run_recorded_structure_build(lambda: self._add_regular_ring_template(n))

    def _run_recorded_hetero_ring_template(self, n: int, elements: list[str]) -> None:
        self._run_recorded_structure_build(lambda: self._add_hetero_ring_template(n, elements))

    def _run_recorded_fused_benzenes(self, count: int, *, mode: str = "linear") -> None:
        self._run_recorded_structure_build(lambda: self._add_fused_benzenes(count, mode=mode))

    def _run_recorded_crown_ether(self, atoms: int, oxygens: int) -> None:
        self._run_recorded_structure_build(lambda: self._add_crown_ether(atoms, oxygens))

    def add_benzene_template(self) -> None:
        self.add_benzene_ring(self._viewport_scene_center())

    def add_cyclohexane_chair(self) -> None:
        self._structure_build_service.add_cyclohexane_chair()

    def add_cyclohexane_boat(self) -> None:
        self._structure_build_service.add_cyclohexane_boat()

    def add_cyclopropane(self) -> None:
        self._run_recorded_regular_ring_template(3)

    def add_cyclobutane(self) -> None:
        self._run_recorded_regular_ring_template(4)

    def add_cyclopentane(self) -> None:
        self._run_recorded_regular_ring_template(5)

    def _insert_session_state(self) -> InsertSessionState:
        return self._insert_controller.insert_session_state()

    def _apply_insert_session_state(self, state: InsertSessionState) -> None:
        self._insert_controller.apply_insert_session_state(state)

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        self._insert_controller.begin_ring_template_insert(ring_size, style)

    def add_naphthalene(self) -> None:
        self._run_recorded_fused_benzenes(2)

    def add_anthracene(self) -> None:
        self._run_recorded_fused_benzenes(3, mode="linear")

    def add_phenanthrene(self) -> None:
        self._run_recorded_fused_benzenes(3, mode="angled")

    def add_pyridine(self) -> None:
        self._run_recorded_hetero_ring_template(6, ["C", "C", "C", "C", "C", "N"])

    def add_pyrimidine(self) -> None:
        self._run_recorded_hetero_ring_template(6, ["N", "C", "N", "C", "C", "C"])

    def add_imidazole(self) -> None:
        self._run_recorded_hetero_ring_template(5, ["C", "N", "C", "N", "C"])

    def add_pyrrole(self) -> None:
        self._run_recorded_hetero_ring_template(5, ["N", "C", "C", "C", "C"])

    def add_furan(self) -> None:
        self._run_recorded_hetero_ring_template(5, ["O", "C", "C", "C", "C"])

    def add_thiophene(self) -> None:
        self._run_recorded_hetero_ring_template(5, ["S", "C", "C", "C", "C"])

    def add_indole(self) -> None:
        self._structure_build_service.add_indole()

    def add_quinoline(self) -> None:
        self._structure_build_service.add_quinoline()

    def add_isoquinoline(self) -> None:
        self._structure_build_service.add_isoquinoline()

    def add_benzimidazole(self) -> None:
        self._structure_build_service.add_benzimidazole()

    def add_phenyl(self) -> None:
        self._structure_build_service.add_phenyl()

    def add_benzyl(self) -> None:
        self._structure_build_service.add_benzyl()

    def add_vinyl(self) -> None:
        self._structure_build_service.add_vinyl()

    def add_allyl(self) -> None:
        self._structure_build_service.add_allyl()

    def add_carboxyl(self) -> None:
        self._structure_build_service.add_carboxyl()

    def add_nitro(self) -> None:
        self._structure_build_service.add_nitro()

    def add_sulfonyl(self) -> None:
        self._structure_build_service.add_sulfonyl()

    def add_carbonyl(self) -> None:
        self._structure_build_service.add_carbonyl()

    def add_tbu(self) -> None:
        self._structure_build_service.add_tbu()

    def add_ipr(self) -> None:
        self._structure_build_service.add_ipr()

    def add_me(self) -> None:
        self._structure_build_service.add_me()

    def add_et(self) -> None:
        self._structure_build_service.add_et()

    def add_pyranose(self) -> None:
        self._run_recorded_hetero_ring_template(6, ["O", "C", "C", "C", "C", "C"])

    def add_furanose(self) -> None:
        self._run_recorded_hetero_ring_template(5, ["O", "C", "C", "C", "C"])

    def add_peptide_2(self) -> None:
        self._structure_build_service.add_peptide_2()

    def add_crown_12_4(self) -> None:
        self._run_recorded_crown_ether(12, 4)

    def add_crown_15_5(self) -> None:
        self._run_recorded_crown_ether(15, 5)

    def add_crown_18_6(self) -> None:
        self._run_recorded_crown_ether(18, 6)

    def _add_regular_ring_template(self, n: int) -> None:
        self._structure_build_service.add_regular_ring_template(n)

    def _add_hetero_ring_template(self, n: int, elements: list[str]) -> None:
        self._structure_build_service.add_hetero_ring_template(n, elements)

    def _add_fused_benzenes(self, count: int, mode: str = "linear") -> None:
        self._structure_build_service.add_fused_benzenes(count, mode=mode)

    def _add_crown_ether(self, atoms: int, oxygens: int) -> None:
        self._structure_build_service.add_crown_ether(atoms, oxygens)

    @staticmethod
    def _qpoints_from_pairs(points: list[tuple[float, float]]) -> list[QPointF]:
        return [QPointF(x, y) for x, y in points]

    @staticmethod
    def _point_pairs(points: list[QPointF]) -> list[tuple[float, float]]:
        return [(point.x(), point.y()) for point in points]

    @staticmethod
    def _point_pair(point: QPointF | None) -> tuple[float, float] | None:
        if point is None:
            return None
        return point.x(), point.y()

    @staticmethod
    def _template_geometry_result(
        result: tuple[list[tuple[float, float]], list[tuple[int, float, float]]] | None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        if result is None:
            return None
        points, merge = result
        return CanvasView._qpoints_from_pairs(points), merge

    def _cyclohexane_chair_points(self, center: QPointF) -> list[QPointF]:
        points = cyclohexane_chair_points(
            (center.x(), center.y()),
            self.renderer.style.bond_length_px,
        )
        return CanvasView._qpoints_from_pairs(points)

    def _cyclohexane_boat_points(self, center: QPointF) -> list[QPointF]:
        points = cyclohexane_boat_points(
            (center.x(), center.y()),
            self.renderer.style.bond_length_px,
        )
        return CanvasView._qpoints_from_pairs(points)

    @staticmethod
    def _scale_points_to_bond_length(
        points: list[QPointF],
        center: QPointF,
        bond_length: float,
    ) -> list[QPointF]:
        scaled = scale_points_to_bond_length(
            [(point.x(), point.y()) for point in points],
            (center.x(), center.y()),
            bond_length,
        )
        return CanvasView._qpoints_from_pairs(scaled)

    def _ring_points(self, center: QPointF, n: int, radius: float | None = None):
        points = ring_points(
            (center.x(), center.y()),
            n,
            radius or self.renderer.style.bond_length_px,
        )
        return CanvasView._qpoints_from_pairs(points)

    def _regular_ring_radius(self, n: int, bond_length: float | None = None) -> float:
        return regular_ring_radius(
            n,
            bond_length if bond_length is not None else self.renderer.style.bond_length_px,
        )

    def _template_points_for_bond(
        self,
        points_local: list[QPointF],
        bond_id: int,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return CanvasView._compute_bond_template_geometry(
            self,
            compute_template_points_for_bond,
            CanvasView._point_pairs(points_local),
            bond_id,
            center_hint=center_hint,
        )

    def _regular_ring_points_for_bond(
        self,
        n: int,
        bond_id: int,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        return CanvasView._compute_bond_template_geometry(
            self,
            compute_regular_ring_points_for_bond,
            n,
            bond_id,
            center_hint=center_hint,
        )

    def _compute_bond_template_geometry(
        self,
        geometry_fn,
        geometry_input,
        bond_id: int,
        *,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        result = geometry_fn(
            geometry_input,
            bond_id,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            center_hint=CanvasView._point_pair(center_hint),
            occupied_polygon=self._ring_polygon_points_for_bond(bond_id),
        )
        return CanvasView._template_geometry_result(result)

    def _ring_polygon_points_for_bond(self, bond_id: int) -> list[tuple[float, float]] | None:
        return ring_polygon_points_for_bond(
            bond_id,
            bonds=self.model.bonds,
            ring_items=self.ring_items,
        )

    def _add_ring_from_points(self, points, elements: list[str] | None = None, merge: list | None = None):
        return self._structure_build_service.add_ring_from_points(points, elements=elements, merge=merge)

    def _add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        return self._structure_build_service.add_atom_with_merge(point, element, merge)

    def _merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        return self._atom_label_service.merge_overlapping_atoms(atom_id)

    def _add_linear_chain(self, points: list[QPointF], elements: list[str], bonds: list[int]):
        return self._structure_build_service.add_linear_chain(points, elements, bonds)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
    ) -> None:
        self._atom_label_service.add_or_update_atom_label(
            atom_id,
            text,
            clear_smiles=clear_smiles,
            record=record,
            allow_merge=allow_merge,
            show_carbon=show_carbon,
        )

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        self._atom_label_service.ensure_carbon_dot(atom_id)

    def _remove_carbon_dot(self, atom_id: int) -> None:
        self._atom_label_service.remove_carbon_dot(atom_id)

    def _position_label(self, item: QGraphicsTextItem, x: float, y: float) -> None:
        self._atom_label_service.position_label(item, x, y)

    def _restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        self._atom_label_service.restore_atom_item_interaction(
            atom_id,
            previous_item,
            was_selected=was_selected,
            refresh_hover=refresh_hover,
        )

    def apply_color_to_item(self, item, color: QColor) -> None:
        canvas_color_mutation_service_for(self).apply_color_to_item(item, color)

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        canvas_color_mutation_service_for(self).apply_ring_fill_color(item, color, alpha=alpha)

    def clear_scene(self) -> None:
        canvas_scene_reset_service_for(self).clear_scene()

    def load_smiles(self, smiles: str) -> None:
        self._insert_controller.load_smiles(smiles)

    def begin_smiles_insert(self, smiles: str) -> None:
        self._insert_controller.begin_smiles_insert(smiles)

    def _cancel_smiles_insert(self) -> None:
        self._insert_controller.cancel_smiles_insert()

    def _commit_smiles_insert(self, pos: QPointF) -> None:
        self._insert_controller.commit_smiles_insert(pos)

    def _clear_smiles_preview(self) -> None:
        self._insert_controller.clear_smiles_preview()

    def _smiles_preview_snapshot(self):
        return self._insert_controller.smiles_preview_snapshot()

    def _render_smiles_preview(self, pos: QPointF) -> None:
        self._insert_controller.render_smiles_preview(pos)

    def _cancel_template_insert(self) -> None:
        self._insert_controller.cancel_template_insert()

    def _template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return self._insert_controller.template_insert_request(pos)

    def _template_point_resolvers(self) -> TemplatePointResolvers:
        return self._insert_controller.template_point_resolvers()

    def _resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        return self._insert_controller.resolve_ring_points_for_template(center, n, radius)

    def _resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._insert_controller.resolve_regular_ring_points_for_template_bond(n, bond_id, center)

    def _resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._insert_controller.resolve_chair_points_for_template(center)

    def _resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._insert_controller.resolve_boat_points_for_template(center)

    def _resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._insert_controller.resolve_template_points_for_template_bond(points_local, bond_id, center)

    def _template_points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        return None if points is None else CanvasView._qpoints_from_pairs(points)

    def _bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        return self._insert_controller.bond_merge_seed(bond_id)

    def _commit_template_insert(self, pos: QPointF) -> None:
        self._insert_controller.commit_template_insert(pos)

    def _clear_template_preview(self) -> None:
        self._insert_controller.clear_template_preview()

    def _render_template_preview(self, pos: QPointF) -> None:
        self._insert_controller.render_template_preview(pos)

    def _clear_benzene_preview(self) -> None:
        self._benzene_preview_service.clear_preview()

    def _render_benzene_preview(
        self,
        pos: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> None:
        self._benzene_preview_service.render_preview(
            pos,
            attach_atom_id=attach_atom_id,
            attach_bond_id=attach_bond_id,
        )

    def _render_model(self) -> None:
        self._structure_build_service.render_model()

    def move_item(self, item, dx: float, dy: float, update_selection: bool = True) -> None:
        _move_controller_for(self).move_item(item, dx, dy, update_selection=update_selection)

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
    ) -> None:
        _move_controller_for(self).move_atoms(
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
        )

    def _move_rings_for_atoms(self, atom_ids: set[int], _dx: float, _dy: float) -> None:
        _move_controller_for(self).move_rings_for_atoms(atom_ids, _dx, _dy)

    def _move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        _move_controller_for(self).move_atom(atom_id, dx, dy)

    def _parallel_bond_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        return self._bond_renderer.parallel_bond_segments(x1, y1, x2, y2, count, a_id, b_id)

    def _wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        return self._bond_renderer.wedge_polygon(x1, y1, x2, y2, a_id, b_id)

    def _hash_segments(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list[tuple[float, float, float, float]]:
        return self._bond_renderer.hash_segments(x1, y1, x2, y2, count, a_id, b_id)

    def _strip_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ) -> QPolygonF:
        return self._bond_renderer.strip_polygon(x1, y1, x2, y2, nx, ny, base_width, bold_width)

    def _ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float]]:
        return self._bond_renderer.ring_double_segments(a, b, center, a_id, b_id, center_3d)

    def update_bond_geometry(self, bond_id: int) -> None:
        self._bond_renderer.update_bond_geometry(bond_id)

    def _redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        graph = graph_state_for(self)
        for bond_id in graph.atom_bond_ids.get(atom_id, ()):
            if skip_bond_id is not None and bond_id == skip_bond_id:
                continue
            self._redraw_bond(bond_id)

    def _redraw_bond(self, bond_id: int) -> None:
        refresh_bond_graphics(
            bond_id,
            bonds=self.model.bonds,
            bond_items=self.bond_items,
            remove_scene_item=self.scene().removeItem,
            add_bond_graphics=self._add_bond_graphics,
        )

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        return self._scene_ops_controller.delete_atom(atom_id, record=record)

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        return self._scene_ops_controller.delete_bond(bond_id, record=record)

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        return self._scene_ops_controller.delete_ring(item, record=record)

    def flip_bond_direction(self, bond_id: int) -> None:
        self._scene_ops_controller.flip_bond_direction(bond_id)

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        self._scene_ops_controller.apply_bond_style(bond_id, style, order)

    def cycle_bond_style(self, bond_id: int) -> None:
        self._scene_ops_controller.cycle_bond_style(bond_id)

    def _add_bond_graphics(self, bond_id: int) -> None:
        self._bond_renderer.add_bond_graphics(bond_id)

    def _ring_center_for_bond(self, bond) -> QPointF | None:
        return _geometry_controller_for(self).ring_center_for_bond(bond)

    def _ring_center_3d_for_bond(self, bond) -> tuple[float, float, float] | None:
        return _geometry_controller_for(self).ring_center_3d_for_bond(bond)

    def _ring_for_bond(self, bond_id: int) -> QGraphicsPolygonItem | None:
        return _geometry_controller_for(self).ring_for_bond(bond_id)

    def _label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        return _geometry_controller_for(self).label_rect_for_atom(atom_id)

    def _visible_text_rect(self, item: QGraphicsTextItem) -> QRectF:
        return _geometry_controller_for(self).visible_text_rect(item)

    def _visible_label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        return _geometry_controller_for(self).visible_label_rect_for_atom(atom_id)

    def _label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        return _geometry_controller_for(self).label_cut_radius_for_atom(atom_id)

    def _line_rect_clip_t(self, p1: QPointF, p2: QPointF, rect: QRectF) -> tuple[float, float] | None:
        return _geometry_controller_for(self).line_rect_clip_t(p1, p2, rect)

    def _segment_intersection_t(self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF) -> float | None:
        return _geometry_controller_for(self).segment_intersection_t(p1, p2, q1, q2)

    def _ray_rect_exit_distance(self, origin: QPointF, direction: QPointF, rect: QRectF) -> float | None:
        return _geometry_controller_for(self).ray_rect_exit_distance(origin, direction, rect)

    def _mark_clearance_for_kind(self, kind: str) -> float:
        return _geometry_controller_for(self).mark_clearance_for_kind(kind)

    def _mark_target_distance_for_atom(
        self,
        atom_id: int,
        direction_x: float,
        direction_y: float,
        kind: str,
    ) -> float:
        return _geometry_controller_for(self).mark_target_distance_for_atom(atom_id, direction_x, direction_y, kind)

    def _line_rect_intersections(self, p1: QPointF, p2: QPointF, rect: QRectF) -> list[float]:
        return _geometry_controller_for(self).line_rect_intersections(p1, p2, rect)

    def _trim_line_for_labels(
        self,
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[float, float]:
        return _geometry_controller_for(self).trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)


    def _draw_ring_double_bond(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        outer_style: str = "normal",
        center_3d: tuple[float, float, float] | None = None,
    ):
        return self._bond_renderer.draw_ring_double_bond(
            a,
            b,
            center,
            a_id,
            b_id,
            outer_style=outer_style,
            center_3d=center_3d,
        )

    def _one_sided_bond_strip(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        nx: float,
        ny: float,
        base_width: float,
        bold_width: float,
    ):
        return self._bond_renderer.one_sided_bond_strip(x1, y1, x2, y2, nx, ny, base_width, bold_width)

    def _line_normal(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        target: QPointF | None = None,
    ) -> tuple[float, float]:
        nx, ny, _ = CanvasView._line_normal_components(x1, y1, x2, y2)
        if target is None:
            return nx, ny
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        return CanvasView._orient_normal_toward_target(nx, ny, mid_x, mid_y, target.x(), target.y())

    @staticmethod
    def _line_normal_components(
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[float, float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 0.0, 0.0, 0.0
        return -dy / length, dx / length, length

    @staticmethod
    def _orient_normal_toward_target(
        nx: float,
        ny: float,
        mid_x: float,
        mid_y: float,
        target_x: float,
        target_y: float,
    ) -> tuple[float, float]:
        to_tx = target_x - mid_x
        to_ty = target_y - mid_y
        if nx * to_tx + ny * to_ty < 0:
            return -nx, -ny
        return nx, ny

    def _bond_offset_unit_3d(
        self,
        a_id: int,
        b_id: int,
        target: tuple[float, float, float] | None = None,
    ) -> tuple[float, float] | None:
        atom_a = self.model.atoms.get(a_id)
        atom_b = self.model.atoms.get(b_id)
        if atom_a is None or atom_b is None:
            return None
        ax, ay = atom_a.x, atom_a.y
        bx, by = atom_b.x, atom_b.y
        nx, ny, length = CanvasView._line_normal_components(ax, ay, bx, by)
        if length < 1e-9:
            return None
        if target is not None:
            mid_x = (ax + bx) * 0.5
            mid_y = (ay + by) * 0.5
            target_x, target_y = self._project_point_3d(target)
            nx, ny = CanvasView._orient_normal_toward_target(nx, ny, mid_x, mid_y, target_x, target_y)
        return (nx, ny)

    def _draw_parallel_bonds(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        count: int,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self._bond_renderer.draw_parallel_bonds(x1, y1, x2, y2, count, a_id, b_id)

    def _draw_wedge_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self._bond_renderer.draw_wedge_bond(x1, y1, x2, y2, a_id, b_id)

    def _draw_hash_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self._bond_renderer.draw_hash_bond(x1, y1, x2, y2, a_id, b_id)

    def _draw_dotted_bond(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self._bond_renderer.draw_dotted_bond(x1, y1, x2, y2, a_id, b_id)

    def _dotted_bond_path(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ):
        return self._bond_renderer.dotted_bond_path(x1, y1, x2, y2, a_id, b_id)

    def _apply_color_to_bond_item(self, item, color: QColor) -> None:
        if hasattr(item, "setPen"):
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)
        if hasattr(item, "setBrush") and item.brush().style() != Qt.BrushStyle.NoBrush:
            item.setBrush(color)
