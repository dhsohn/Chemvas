import math
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QBrush,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QNativeGestureEvent,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QInputDialog,
)

from core.history import (
    AddBondCommand,
    ChangeAtomLabelCommand,
    DeleteBondCommand,
    HistoryCommand,
    AddAtomsCommand,
    AddSceneItemsCommand,
    CompositeCommand,
    DeleteAtomsCommand,
    SetAtomPositionsCommand,
    SetRingPolygonsCommand,
    UpdateBondLengthCommand,
    UpdateAtomColorCommand,
    UpdateSceneItemCommand,
    UpdateBondCommand,
)
from core.document_io import read_document, write_document
from core.document_state import deserialize_model_state
from core.model import Atom, Bond, MoleculeModel
from core.renderer import Renderer
from core.rdkit_adapter import RDKitAdapter
from core.template_geometry import (
    cyclohexane_boat_points,
    cyclohexane_chair_points,
    regular_ring_radius,
    ring_points,
    scale_points_to_bond_length,
)
from core.tools import ToolController
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
from ui.scene_decoration_service import SceneDecorationService
from ui.canvas_handle_controller import CanvasHandleController
from ui.curved_arrow_path_service import CurvedArrowPathService, curved_arrow_path_service_for
from ui.handle_mutation_service import HandleMutationService
from ui.handle_overlay_service import HandleOverlayService, handle_overlay_service_for
from ui.canvas_input_controller import CanvasInputController
from ui.canvas_move_controller import CanvasMoveController
from ui.canvas_note_controller import CanvasNoteController
from ui.canvas_pointer_controller import CanvasPointerController
from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    snapshot_canvas_document_state,
)
from ui.canvas_geometry_controller import CanvasGeometryController
from ui.graphics_items import (
    AtomLabelItem,
    AtomDotItem,
    NoSelectLineItem,
    NoSelectPathItem,
    NoSelectPolygonItem,
)
from ui.hover_scene_renderer import (
    add_hover_preview_items as add_hover_preview_items_helper,
    build_atom_hover_indicator as build_atom_hover_indicator_helper,
    build_bond_hover_indicator as build_bond_hover_indicator_helper,
    clear_hover_items as clear_hover_items_helper,
)
from ui.hover_interaction_service import HoverInteractionService
from ui.hover_scene_service import HoverSceneService
from ui.insert_mode_logic import (
    InsertSessionState,
    clear_insert_session,
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
from ui.structure_insert_service import StructureInsertService


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
    controller = getattr(canvas, "_input_controller", None)
    if isinstance(controller, CanvasInputController) and controller.canvas is canvas:
        return controller
    return CanvasInputController(canvas)


def _pointer_controller_for(canvas) -> CanvasPointerController:
    controller = getattr(canvas, "_pointer_controller", None)
    if isinstance(controller, CanvasPointerController) and controller.canvas is canvas:
        return controller
    return CanvasPointerController(canvas)


def _handle_controller_for(canvas) -> CanvasHandleController:
    controller = getattr(canvas, "_handle_controller", None)
    if isinstance(controller, CanvasHandleController) and controller.canvas is canvas:
        return controller
    return CanvasHandleController(canvas)


def _selection_controller_for(canvas) -> SelectionController:
    controller = getattr(canvas, "_selection_controller", None)
    if isinstance(controller, SelectionController) and controller.canvas is canvas:
        return controller
    return SelectionController(canvas)


def _note_controller_for(canvas) -> CanvasNoteController:
    controller = getattr(canvas, "_note_controller", None)
    if isinstance(controller, CanvasNoteController) and controller.canvas is canvas:
        return controller
    return CanvasNoteController(canvas)


def _move_controller_for(canvas) -> CanvasMoveController:
    controller = getattr(canvas, "_move_controller", None)
    if isinstance(controller, CanvasMoveController) and controller.canvas is canvas:
        return controller
    return CanvasMoveController(canvas)


def _geometry_controller_for(canvas) -> CanvasGeometryController:
    controller = getattr(canvas, "_geometry_controller", None)
    if isinstance(controller, CanvasGeometryController) and controller.canvas is canvas:
        return controller
    return CanvasGeometryController(canvas)


def _rotation_preview_controller_for(canvas) -> CanvasRotationPreviewController:
    controller = getattr(canvas, "_rotation_preview_controller", None)
    if isinstance(controller, CanvasRotationPreviewController) and controller.canvas is canvas:
        return controller
    return CanvasRotationPreviewController(canvas)


class CanvasView(QGraphicsView):
    FILE_FORMAT_VERSION = 1
    CLIPBOARD_SELECTION_MIME = "application/x-lightdraw-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setScene(QGraphicsScene(self))
        self.scene().selectionChanged.connect(self._update_selection_outline)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#fdf9f3"))
        self.setSceneRect(QRectF(-2000.0, -2000.0, 4000.0, 4000.0))
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
        self._atom_neighbors: dict[int, set[int]] = {}
        self._atom_bond_ids: dict[int, set[int]] = {}
        self._graph_version = 0
        self._selection_component_cache_signature: tuple[frozenset[int], int] | None = None
        self._selection_component_cache: list[set[int]] = []
        self._rotation_axis_cache: dict[tuple[frozenset[int], frozenset[int], int], tuple[int, set[int]] | None] = {}
        self._rotation_axis_cache_version = self._graph_version
        self._bond_cycle_cache: dict[int, tuple[int, bool]] = {}
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
        self._rotation_base_coords: dict[int, tuple[float, float, float]] = {}
        self._rotation_axis_bond_id: int | None = None
        self._rotation_axis_atoms: tuple[int, int] | None = None
        self._rotation_total_angle = 0.0
        self._rotation_mode: str | None = None
        self._rotation_free_angle_x = 0.0
        self._rotation_free_angle_y = 0.0
        self._rotation_depth_factor = 1.0
        self._rotation_base_bond_length: float | None = None
        self.rotation_atom_ids: set[int] = set()
        self.rotation_center_3d: tuple[float, float, float] | None = None
        self._projection_center_3d: tuple[float, float, float] | None = None
        self._projection_anchor_2d: tuple[float, float] | None = None
        self._rotation_start_projection_center_3d: tuple[float, float, float] | None = None
        self._rotation_start_projection_anchor_2d: tuple[float, float] | None = None
        self._rotation_start_positions: dict[int, tuple[float, float]] = {}
        self._rotation_start_coords_3d: dict[int, tuple[float, float, float]] = {}
        self._rotation_coord_atom_ids: set[int] = set()
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
        self._selection_color = QColor("#1f5eff")
        self._selection_stroke_delta = 0.6
        self._suspend_selection_outline = False
        self._selection_signature = None
        self._selection_pending_signature = None
        self._selection_controller = SelectionController(self)
        self._scene_item_controller = SceneItemController(self)
        self._scene_ops_controller = SceneOpsController(self)
        self._insert_controller = InsertController(self)
        self._input_controller = CanvasInputController(self)
        self._handle_controller = CanvasHandleController(self)
        self._handle_overlay_service = HandleOverlayService(self)
        self._handle_mutation_service = HandleMutationService(self)
        self._curved_arrow_path_service = CurvedArrowPathService(self)
        self._selection_highlight_styler = SelectionHighlightStyler(self)
        self._move_controller = CanvasMoveController(self)
        self._note_controller = CanvasNoteController(self)
        self._pointer_controller = CanvasPointerController(self)
        self._geometry_controller = CanvasGeometryController(self)
        self._rotation_preview_controller = CanvasRotationPreviewController(self)
        self._atom_label_service = AtomLabelService(self)
        self._hover_interaction_service = HoverInteractionService(self)
        self._hover_scene_service = HoverSceneService(self)
        self._mark_hover_preview_service = MarkHoverPreviewService(self)
        self._bond_hover_preview_service = BondHoverPreviewService(self)
        self._structure_build_service = StructureBuildService(self)
        self._benzene_preview_service = BenzenePreviewService(self)
        self._scene_decoration_service = SceneDecorationService(self)
        self._structure_insert_service = StructureInsertService(self)
        self._selection_rotation_controller = SelectionRotationController(self)
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
        self._marks_by_atom: dict[int, list[QGraphicsItem]] = {}
        self.hover_items: list = []
        self.hover_atom_id: int | None = None
        self.hover_bond_id: int | None = None
        self._hover_preview_style: str | None = None
        self._selection_info_callback = None
        self._tool_change_callback = None
        self._rotation_selection_ids = None
        self.selection_outlines: list[QGraphicsItem] = []
        self._smiles_insert_active = False
        self._smiles_preview_model: MoleculeModel | None = None
        self._smiles_preview_items: list[QGraphicsItem] = []
        self._smiles_preview_bond_items: dict[int, list[QGraphicsItem]] = {}
        self._smiles_preview_atom_items: dict[int, QGraphicsEllipseItem] = {}
        self._smiles_preview_center: QPointF | None = None
        self._smiles_preview_smiles: str | None = None
        self._template_insert_active = False
        self._template_ring_size: int | None = None
        self._template_ring_style: str | None = None
        self._template_preview_items: list[QGraphicsItem] = []
        self._template_preview_lines: list[QGraphicsLineItem] = []
        self._template_preview_dots: list[QGraphicsEllipseItem] = []
        self._benzene_preview_items: list[QGraphicsItem] = []
        self._history: list[HistoryCommand] = []
        self._redo_stack: list[HistoryCommand] = []
        self._history_enabled = True
        self._history_limit = 100
        self._clipboard_selection_payload_json: str | None = None
        self._clipboard_paste_source_json: str | None = None
        self._clipboard_paste_count = 0
        self.tools = ToolController(self)
        self.tools.set_active("bond")

    def keyPressEvent(self, event) -> None:
        _input_controller_for(self).key_press_event(event)

    @staticmethod
    def _shortcut_modifiers(event) -> Qt.KeyboardModifier:
        return CanvasInputController.shortcut_modifiers(event)

    def _handle_chemdraw_shortcut(self, event) -> bool:
        return _input_controller_for(self).handle_chemdraw_shortcut(event)

    def _handle_chemdraw_object_shortcut(self, event) -> bool:
        modifiers = self._shortcut_modifiers(event)
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_H:
                self.flip_horizontal()
                return True
            if event.key() == Qt.Key.Key_V:
                self.flip_vertical()
                return True
        return False

    def _handle_chemdraw_generic_hotkey(self, event) -> bool:
        modifiers = self._shortcut_modifiers(event)
        if modifiers == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_Space:
                self.set_tool("select")
                return True
            if event.key() == Qt.Key.Key_X:
                self.set_bond_style("single", 1)
                return True
            if event.key() == Qt.Key.Key_T:
                self.set_tool("text")
                return True
            if event.key() == Qt.Key.Key_E:
                self.set_tool("arrow")
                return True
            if event.key() == Qt.Key.Key_J:
                self.set_tool("benzene")
                return True
        if modifiers == Qt.KeyboardModifier.ShiftModifier and event.key() == Qt.Key.Key_G:
            self.set_tool("ts_bracket")
            return True
        if modifiers == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_D:
            self.set_tool("perspective")
            return True
        return False

    def _handle_chemdraw_atom_hotkey(self, event, atom_id: int) -> bool:
        if atom_id not in self.model.atoms:
            return False
        modifiers = self._shortcut_modifiers(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.prompt_atom_label(atom_id)
            return True
        text = event.text()
        if not text:
            return False
        if text == "+":
            self.add_mark_for_atom(atom_id, self._atom_point(atom_id), kind="plus")
            return True
        if text == "-":
            self.add_mark_for_atom(atom_id, self._atom_point(atom_id), kind="minus")
            return True
        label_hotkeys = {
            "f": "F",
            "F": "CF3",
            "p": "P",
            "P": "Ph",
            "A": "Ac",
            "h": "H",
            "b": "Br",
            "B": "B",
            "i": "I",
            "r": "R",
            "s": "S",
            "S": "Si",
            "m": "Me",
            "n": "N",
            "w": "N",
            "N": "NO2",
            "c": "C",
            "l": "Cl",
            "C": "Cl",
            "x": "X",
            "o": "O",
            "q": "O",
            "d": "D",
            "e": "Et",
            "E": "CO2Me",
            "Z": "N3",
            "M": "MgBr",
            "L": "Li",
            "O": "OMe",
            "Q": "Fmoc",
            "H": "Cbz",
            "Y": "Boc",
            # LiteDraw does not yet have ChemDraw's full group-sprout engine for these,
            # so keep them available as common abbreviation labels.
            "k": "SO2",
            "K": "t-Bu",
        }
        if text in label_hotkeys:
            self._atom_label_service.add_or_update_atom_label(atom_id, label_hotkeys[text], show_carbon=True)
            return True
        if text in {"0", "1"}:
            self._sprout_bond_from_atom(atom_id, style="single", order=1, cyclic=text == "0")
            return True
        if text == "2":
            self._sprout_acetyl_from_atom(atom_id)
            return True
        if text in {"3", "a"}:
            self._sprout_benzene_from_atom(atom_id)
            return True
        if text == "4":
            self._sprout_bond_from_atom(atom_id, style="wedge", order=1)
            return True
        if text == "5":
            self._sprout_bond_from_atom(atom_id, style="hash", order=1)
            return True
        if text == "6":
            self._sprout_regular_ring_from_atom(atom_id, 6)
            return True
        if text == "7":
            self._sprout_regular_ring_from_atom(atom_id, 5)
            return True
        if text == "8":
            self._sprout_bond_from_atom(atom_id, style="double", order=2)
            return True
        if text == "z":
            self._sprout_bond_from_atom(atom_id, style="triple", order=3)
            return True
        if text == "v":
            self._sprout_regular_ring_from_atom(atom_id, 3)
            return True
        if text == "u":
            self._sprout_regular_ring_from_atom(atom_id, 4)
            return True
        return False

    def _handle_chemdraw_bond_hotkey(self, event, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.model.bonds)) or self.model.bonds[bond_id] is None:
            return False
        modifiers = self._shortcut_modifiers(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if event.key() == Qt.Key.Key_B:
                self.apply_bond_style(bond_id, "bold_in", 2)
                return True
            if event.key() == Qt.Key.Key_H:
                self.apply_bond_style(bond_id, "hash", 1)
                return True
        text = event.text()
        if text == "1":
            self.apply_bond_style(bond_id, "single", 1)
            return True
        if text == "2":
            self.apply_bond_style(bond_id, "double", 2)
            return True
        if text == "3":
            self.apply_bond_style(bond_id, "triple", 3)
            return True
        if text == "b":
            self.apply_bond_style(bond_id, "bold_in", 1)
            return True
        if text == "w":
            self.apply_bond_style(bond_id, "wedge", 1)
            return True
        if text == "h":
            self.apply_bond_style(bond_id, "hash", 1)
            return True
        if text == "a":
            self._fuse_benzene_to_bond(bond_id)
            return True
        if text in {"4", "5", "6", "7", "8"}:
            self._fuse_regular_ring_to_bond(bond_id, int(text))
            return True
        if text in {"9", "0"}:
            self._fuse_chair_to_bond(bond_id, mirrored=text == "0")
            return True
        return False

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
        if getattr(self, "_template_insert_active", False) or getattr(self, "_smiles_insert_active", False):
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
        return snapshot_canvas_document_state(self)

    def snapshot_state(self) -> dict:
        return self._snapshot_state()

    def _restore_state(self, state: dict) -> None:
        self._history_enabled = False
        try:
            self.clear_scene()
            apply_document_settings(self, state)

            self.model = deserialize_model_state(state.get("model", {}))
            self._rebuild_bond_adjacency()
            restore_document_pre_model_items(self, state)

            self._render_model()
            restore_document_post_model_items(self, state)
            self._mark_spatial_index_dirty()
        finally:
            self._history_enabled = True

    def restore_state(self, state: dict) -> None:
        self._restore_state(state)
        self._history = []
        self._redo_stack = []

    def save_to_file(self, path: str) -> None:
        write_document(path, self._snapshot_state(), self.FILE_FORMAT_VERSION)

    def export_xyz(self, path: str) -> None:
        export_model, atom_annotations = self.build_3d_conversion_payload()
        xyz_block = self.rdkit.model_to_xyz_block(export_model, atom_annotations=atom_annotations)
        if xyz_block is None:
            message = self.rdkit.last_error or "Failed to export 3D XYZ."
            raise ValueError(message)
        Path(path).write_text(xyz_block, encoding="utf-8")

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
        document = read_document(path)
        self._restore_state(document.state)
        self._history = []
        self._redo_stack = []

    def _push_command(self, command: HistoryCommand) -> None:
        if not self._history_enabled:
            return
        self._history.append(command)
        if len(self._history) > self._history_limit:
            self._history.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._history:
            return
        command = self._history.pop()
        self._redo_stack.append(command)
        command.undo(self)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        command = self._redo_stack.pop()
        self._history.append(command)
        command.redo(self)

    def set_tool_change_callback(self, callback) -> None:
        self._tool_change_callback = callback

    def _notify_tool_change(self) -> None:
        if self._tool_change_callback is not None:
            self._tool_change_callback()

    def set_tool(self, tool_name: str) -> None:
        self.tools.set_active(tool_name)
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def set_mark_kind(self, kind: str) -> None:
        if kind not in {"plus", "minus", "radical"}:
            return
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
        if not self._history_enabled:
            return
        atom = self.model.atoms.get(atom_id)
        after_element = atom.element if atom is not None else before_element
        after_explicit_label = atom.explicit_label if atom is not None else before_explicit_label
        after_smiles_input = self.last_smiles_input
        commands: list[HistoryCommand] = []
        if (
            before_element != after_element
            or before_explicit_label != after_explicit_label
            or before_smiles_input != after_smiles_input
        ):
            commands.append(
                ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=before_element,
                    after_element=after_element,
                    before_explicit_label=before_explicit_label,
                    after_explicit_label=after_explicit_label,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if merge_ids:
            bond_before_states = merge_info.get("bond_before_states", {})
            deleted_bond_ids = set(merge_info.get("deleted_bond_ids", []))
            for bond_id, before_state in bond_before_states.items():
                if bond_id in deleted_bond_ids:
                    commands.append(
                        DeleteBondCommand(
                            bond_id=bond_id,
                            bond_state=before_state,
                            before_smiles_input=before_smiles_input,
                            after_smiles_input=after_smiles_input,
                        )
                    )
                    continue
                bond = self.model.bonds[bond_id]
                if bond is None:
                    continue
                after_state = self._bond_state_dict(bond)
                if before_state != after_state:
                    commands.append(
                        UpdateBondCommand(
                            bond_id=bond_id,
                            before_state=before_state,
                            after_state=after_state,
                            before_smiles_input=before_smiles_input,
                            after_smiles_input=after_smiles_input,
                        )
                    )
            atom_states = merge_info.get("atom_states", {})
            if atom_states:
                commands.append(
                    DeleteAtomsCommand(
                        atom_states=atom_states,
                        mark_states=[],
                        before_next_atom_id=self.model.next_atom_id,
                        after_next_atom_id=self.model.next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                        remove_marks=False,
                    )
                )
        if not commands:
            return
        if len(commands) == 1:
            self._push_command(commands[0])
            return
        self._push_command(CompositeCommand(commands))

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
        commands: list[HistoryCommand] = []
        after_next_atom_id = self.model.next_atom_id
        if after_next_atom_id > before_next_atom_id:
            atom_states = {
                atom_id: self._atom_state_dict(atom_id)
                for atom_id in range(before_next_atom_id, after_next_atom_id)
                if atom_id in self.model.atoms
            }
            if atom_states:
                commands.append(
                    AddAtomsCommand(
                        atom_states=atom_states,
                        before_next_atom_id=before_next_atom_id,
                        after_next_atom_id=after_next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=self.last_smiles_input,
                    )
                )
        for bond_id in range(before_bond_count, len(self.model.bonds)):
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            bond_state = self._bond_state_dict(bond)
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    previous_bond_count=bond_id,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=self.last_smiles_input,
                )
            )
        if added_scene_items:
            states = [self.scene_item_state(item) for item in added_scene_items if item is not None]
            if states:
                commands.append(AddSceneItemsCommand(item_states=states, items=list(added_scene_items)))
        if not commands:
            return
        if len(commands) == 1:
            self._push_command(commands[0])
            return
        self._push_command(CompositeCommand(commands))

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
        label = self.atom_items.pop(atom_id, None)
        if label is not None:
            self.scene().removeItem(label)
        dot = self.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.scene().removeItem(dot)
        if remove_marks:
            self._remove_marks_for_atom(atom_id)
        self.model.atoms.pop(atom_id, None)
        self.atom_coords_3d.pop(atom_id, None)
        neighbors = self._atom_neighbors.pop(atom_id, None)
        if neighbors:
            for neighbor in neighbors:
                neighbor_set = self._atom_neighbors.get(neighbor)
                if neighbor_set is not None and atom_id in neighbor_set:
                    neighbor_set.remove(atom_id)
            self._graph_version += 1
            self._selection_component_cache_signature = None
        bond_ids = self._atom_bond_ids.pop(atom_id, None)
        if bond_ids:
            for bond_id in list(bond_ids):
                bond = self.model.bonds[bond_id] if 0 <= bond_id < len(self.model.bonds) else None
                if bond is None:
                    continue
                other_id = bond.b if bond.a == atom_id else bond.a
                other_set = self._atom_bond_ids.get(other_id)
                if other_set is not None and bond_id in other_set:
                    other_set.remove(bond_id)
        self._mark_spatial_index_dirty()

    def _restore_atom_from_state(self, atom_id: int, state: dict) -> None:
        if not state:
            return
        atom = Atom(
            element=state.get("element", "C"),
            x=state.get("x", 0.0),
            y=state.get("y", 0.0),
            color=state.get("color", "#000000"),
            explicit_label=bool(state.get("explicit_label", False)),
        )
        self.model.atoms[atom_id] = atom
        self._ensure_atom_neighbors(atom_id)
        self._ensure_atom_bond_ids(atom_id)
        if atom_id >= self.model.next_atom_id:
            self.model.next_atom_id = atom_id + 1
        existing_label = self.atom_items.pop(atom_id, None)
        if existing_label is not None:
            self.scene().removeItem(existing_label)
        existing_dot = self.atom_dots.pop(atom_id, None)
        if existing_dot is not None:
            self.scene().removeItem(existing_dot)
        if atom.element.upper() == "C":
            if atom.explicit_label:
                self._atom_label_service.add_or_update_atom_label(
                    atom_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                    allow_merge=False,
                    show_carbon=True,
                )
            else:
                self._ensure_carbon_dot(atom_id)
        else:
            self._atom_label_service.add_or_update_atom_label(
                atom_id,
                atom.element,
                clear_smiles=False,
                record=False,
                allow_merge=False,
            )
        self.apply_atom_color(atom_id, atom.color)
        self._mark_spatial_index_dirty()

    def apply_atom_color(self, atom_id: int, color: str | QColor) -> None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        if isinstance(color, QColor):
            color_value = color
        else:
            color_value = QColor(color)
        if not color_value.isValid():
            return
        atom.color = color_value.name()
        label_item = self.atom_items.get(atom_id)
        if label_item is not None:
            label_item.setDefaultTextColor(color_value)
        dot_item = self.atom_dots.get(atom_id)
        if dot_item is not None:
            dot_item.setBrush(self._implicit_carbon_dot_brush())

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
            marks = self._marks_by_atom.get(atom_id)
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
        if not self._history_enabled:
            return
        if before_state == after_state and before_smiles_input == after_smiles_input:
            return
        command = UpdateBondCommand(
            bond_id=bond_id,
            before_state=before_state,
            after_state=after_state,
            before_smiles_input=before_smiles_input,
            after_smiles_input=after_smiles_input,
        )
        self._push_command(command)

    def _restore_bond_from_state(self, bond_id: int, bond_state: dict) -> None:
        if not bond_state:
            return
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items.pop(bond_id, None)
        existing_bond = self.model.bonds[bond_id] if bond_id < len(self.model.bonds) else None
        bond = Bond(
            a=bond_state.get("a", 0),
            b=bond_state.get("b", 0),
            order=bond_state.get("order", 1),
            style=bond_state.get("style", "single"),
            color=bond_state.get("color", "#000000"),
        )
        if existing_bond is not None and (existing_bond.a != bond.a or existing_bond.b != bond.b):
            self._remove_bond_index(bond_id, existing_bond.a, existing_bond.b)
            self._remove_bond_neighbors(existing_bond.a, existing_bond.b, skip_bond_id=bond_id)
        if bond_id < len(self.model.bonds):
            self.model.bonds[bond_id] = bond
        else:
            self.model.bonds.extend([None] * (bond_id - len(self.model.bonds)))
            self.model.bonds.append(bond)
        if existing_bond is None or (existing_bond.a != bond.a or existing_bond.b != bond.b):
            self._add_bond_neighbors(bond.a, bond.b)
            self._add_bond_index(bond_id, bond.a, bond.b)
        self._add_bond_graphics(bond_id)
        self._mark_spatial_index_dirty()

    def _remove_bond_by_id(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items.pop(bond_id, None)
        if bond is not None:
            self._remove_bond_index(bond_id, bond.a, bond.b)
            self._remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
        self.model.bonds[bond_id] = None
        self._mark_spatial_index_dirty()

    def _trim_bonds_to_length(self, length: int) -> None:
        if length < 0 or length >= len(self.model.bonds):
            return
        for bond_id in range(length, len(self.model.bonds)):
            bond = self.model.bonds[bond_id]
            if bond is not None:
                self._remove_bond_index(bond_id, bond.a, bond.b)
                self._remove_bond_neighbors(bond.a, bond.b, skip_bond_id=bond_id)
            for item in self.bond_items.get(bond_id, []):
                self.scene().removeItem(item)
            self.bond_items.pop(bond_id, None)
        del self.model.bonds[length:]
        self._mark_spatial_index_dirty()

    def scene_pos_from_event(self, event) -> QPointF:
        if hasattr(event, "position"):
            return self.mapToScene(event.position().toPoint())
        if hasattr(event, "pos"):
            return self.mapToScene(event.pos())
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        return self.mapToScene(pos)

    def item_at_scene_pos(self, pos: QPointF):
        bond_item = None
        ring_item = None
        other_item = None
        for item in self.scene().items(
            pos,
            Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
            QTransform(),
        ):
            if item.data(0) == "selection_outline":
                continue
            kind = item.data(0)
            if kind in {"note_box", "note_select"}:
                continue
            if kind == "atom":
                return item
            if kind == "bond" and bond_item is None:
                bond_item = item
                continue
            if kind == "ring" and ring_item is None:
                ring_item = item
                continue
            if other_item is None:
                other_item = item
        if bond_item is None:
            nearby_bond_id = self._find_bond_near(pos, self._bond_pick_radius())
            if nearby_bond_id is not None:
                nearby_items = self.bond_items.get(nearby_bond_id, [])
                if nearby_items:
                    return nearby_items[0]
        return bond_item or ring_item or other_item

    def item_at_event(self, event):
        return self.item_at_scene_pos(self.scene_pos_from_event(event))

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
        atom_id = self.find_atom_near(pos.x(), pos.y(), self._atom_pick_radius())
        if atom_id is None:
            return None
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return None
        return atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y())

    def _nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        bond_id = self._find_bond_near(pos, self._bond_pick_radius())
        if bond_id is None or not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        atom_a = self.model.atoms.get(bond.a)
        atom_b = self.model.atoms.get(bond.b)
        if atom_a is None or atom_b is None:
            return None
        dist = self._distance_point_to_segment(
            pos,
            QPointF(atom_a.x, atom_a.y),
            QPointF(atom_b.x, atom_b.y),
        )
        return bond_id, dist

    def _structure_hit_from_item(self, item) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
        return _selection_controller_for(self)._structure_hit_from_item(item)

    def _structure_item_for_hit(self, hit: StructureHit):
        return _selection_controller_for(self)._structure_item_for_hit(hit)

    def _atom_item_for_id(self, atom_id: int):
        return self.atom_items.get(atom_id) or self.atom_dots.get(atom_id)

    def _selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        return _selection_controller_for(self)._selection_targets_for_item(item)

    def toggle_item_selection(self, item) -> bool:
        return _selection_controller_for(self).toggle_item_selection(item)

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        return _selection_controller_for(self).preferred_structure_hit_at_scene_pos(pos)

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        return _selection_controller_for(self).preferred_structure_item_at_scene_pos(pos)

    def bond_id_from_event(self, event) -> int | None:
        if self.hover_bond_id is not None:
            return self.hover_bond_id
        pos = self.scene_pos_from_event(event)
        return self._find_bond_near(pos, max(self.renderer.style.bond_length_px * 0.35, self._bond_pick_radius()))

    def _selection_rects_for_snapshot(
        self,
        snapshot: SelectionSnapshot,
    ) -> tuple[SelectionRect, ...]:
        return _selection_controller_for(self)._selection_rects_for_snapshot(snapshot)

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
        return max(8.0, self.renderer.style.bond_length_px)

    def _cell_coords(self, x: float, y: float, cell_size: float) -> tuple[int, int]:
        return int(math.floor(x / cell_size)), int(math.floor(y / cell_size))

    def _ensure_spatial_index(self) -> None:
        cell_size = self._grid_cell_size()
        if not self._spatial_index_dirty and abs(self._spatial_cell_size - cell_size) < 1e-6:
            return
        self._rebuild_spatial_index(cell_size)

    def _rebuild_spatial_index(self, cell_size: float) -> None:
        atom_grid: dict[tuple[int, int], set[int]] = {}
        for atom_id, atom in self.model.atoms.items():
            key = self._cell_coords(atom.x, atom.y, cell_size)
            atom_grid.setdefault(key, set()).add(atom_id)

        bond_grid: dict[tuple[int, int], set[int]] = {}
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            a = self.model.atoms.get(bond.a)
            b = self.model.atoms.get(bond.b)
            if a is None or b is None:
                continue
            min_x = min(a.x, b.x)
            max_x = max(a.x, b.x)
            min_y = min(a.y, b.y)
            max_y = max(a.y, b.y)
            min_ix, min_iy = self._cell_coords(min_x, min_y, cell_size)
            max_ix, max_iy = self._cell_coords(max_x, max_y, cell_size)
            for ix in range(min_ix, max_ix + 1):
                for iy in range(min_iy, max_iy + 1):
                    bond_grid.setdefault((ix, iy), set()).add(bond_id)

        self._atom_grid = atom_grid
        self._bond_grid = bond_grid
        self._spatial_cell_size = cell_size
        self._spatial_index_dirty = False

    def find_atom_near(self, x: float, y: float, max_dist: float) -> int | None:
        if not self.model.atoms:
            return None
        self._ensure_spatial_index()
        cell_size = self._spatial_cell_size or self._grid_cell_size()
        if cell_size <= 0:
            return None
        cell_radius = int(math.ceil(max_dist / cell_size))
        ix, iy = self._cell_coords(x, y, cell_size)
        nearest_id = None
        nearest_dist_sq = max_dist * max_dist
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for atom_id in self._atom_grid.get((cx, cy), ()):
                    atom = self.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    dx = atom.x - x
                    dy = atom.y - y
                    dist_sq = dx * dx + dy * dy
                    if dist_sq <= nearest_dist_sq:
                        nearest_id = atom_id
                        nearest_dist_sq = dist_sq
        return nearest_id

    def add_atom(self, element: str, x: float, y: float) -> int:
        atom_id = self.model.add_atom(element, x, y)
        self._ensure_atom_neighbors(atom_id)
        self._ensure_atom_bond_ids(atom_id)
        if element.upper() == "C":
            self._ensure_carbon_dot(atom_id)
        else:
            self._atom_label_service.add_or_update_atom_label(atom_id, element, clear_smiles=False, record=False)
        self._mark_spatial_index_dirty()
        return atom_id

    def add_bond(self, a: int, b: int, order: int = 1) -> int:
        existing_id = self._bond_id_between(a, b)
        if existing_id is not None:
            return existing_id
        self.model.add_bond(a, b, order)
        self._add_bond_neighbors(a, b)
        self._add_bond_index(len(self.model.bonds) - 1, a, b)
        self._mark_spatial_index_dirty()
        return len(self.model.bonds) - 1

    def set_bond_style(self, style: str, order: int) -> None:
        self.active_bond_style = style
        self.active_bond_order = order
        self.tools.set_active("bond")
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def set_arrow_type(self, arrow_type: str) -> None:
        self.active_arrow_type = arrow_type
        self.tools.set_active("arrow")
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

    def set_orbital_type(self, orbital_type: str) -> None:
        self.active_orbital_type = orbital_type
        self.tools.set_active("orbital")
        self._update_selection_outline()
        self._notify_tool_change()
        self._refresh_hover_from_cursor()

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
        self._push_command(CompositeCommand(commands))

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

    def _selected_items_for_transform(self) -> list[QGraphicsItem]:
        excluded_kinds = {"handle", "note_box", "note_select", "selection_outline"}
        selected = [
            item
            for item in self.scene().selectedItems()
            if item.data(0) not in excluded_kinds
        ]
        if self.selected_notes:
            selected.extend(note for note in self.selected_notes if note.scene() is self.scene())
        items: list[QGraphicsItem] = []
        seen = set()
        for item in selected:
            if item in seen:
                continue
            seen.add(item)
            items.append(item)
        return items

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
        for items in self.bond_items.values():
            for item in items:
                self.scene().removeItem(item)
        self.bond_items = {}

        for label in self.atom_items.values():
            self.scene().removeItem(label)
        self.atom_items = {}
        for dot in self.atom_dots.values():
            self.scene().removeItem(dot)
        self.atom_dots = {}

        self._render_model()

    def _selected_ids(self) -> tuple[set[int], set[int]]:
        atom_ids = set()
        bond_ids = set()
        for item in self.scene().selectedItems():
            kind = item.data(0)
            if kind == "atom":
                atom_id = item.data(1)
                if isinstance(atom_id, int):
                    atom_ids.add(atom_id)
            elif kind == "bond":
                bond_id = item.data(1)
                if isinstance(bond_id, int):
                    bond_ids.add(bond_id)
            elif kind == "ring":
                ring_atom_ids = item.data(2)
                if isinstance(ring_atom_ids, list):
                    for atom_id in ring_atom_ids:
                        if isinstance(atom_id, int) and atom_id in self.model.atoms:
                            atom_ids.add(atom_id)
                elif hasattr(item, "polygon"):
                    polygon = item.polygon()
                    for atom_id, atom in self.model.atoms.items():
                        if polygon.containsPoint(QPointF(atom.x, atom.y), Qt.FillRule.WindingFill):
                            atom_ids.add(atom_id)
        return atom_ids, bond_ids

    def _selected_chemical_ids(self) -> tuple[set[int], set[int]]:
        atom_ids, bond_ids = self._selected_ids()
        if atom_ids or bond_ids:
            return atom_ids, bond_ids
        # Scene-only items such as arrows, notes, and TS brackets should not
        # suppress a real atom-bound annotation selection from the 3D/export path.
        for item in self.scene().selectedItems():
            if item.data(0) != "mark":
                continue
            data = item.data(1) or {}
            atom_id = data.get("atom_id")
            if isinstance(atom_id, int) and atom_id in self.model.atoms:
                atom_ids.add(atom_id)
        return atom_ids, bond_ids

    def _selection_items_for_copy(self) -> list[QGraphicsItem]:
        excluded_kinds = {"handle", "note_select", "selection_outline"}
        selected = [
            item
            for item in self.scene().selectedItems()
            if item.data(0) not in excluded_kinds
        ]
        if self.selected_notes:
            selected.extend(note for note in self.selected_notes if note.scene() is self.scene())
        if not selected:
            return []
        items: list[QGraphicsItem] = []
        seen = set()

        def add_item(item: QGraphicsItem) -> None:
            if item in seen:
                return
            kind = item.data(0)
            if kind in excluded_kinds:
                return
            seen.add(item)
            items.append(item)

        def add_with_children(item: QGraphicsItem) -> None:
            add_item(item)
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
        for atom_id, marks in self._marks_by_atom.items():
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
        atom_ids, bond_ids = self._selected_chemical_ids()
        return build_3d_conversion_payload_state(
            self.model,
            atom_ids,
            bond_ids,
            self._mark_kinds_by_atom(),
            bounds_getter=self._bounds_for_atoms,
        )

    def build_selected_structure_payload(self) -> tuple[MoleculeModel, dict[int, dict[str, int]], tuple[float, float, float, float]]:
        atom_ids, bond_ids = self._selected_chemical_ids()
        if not atom_ids and not bond_ids:
            raise ValueError("Select a molecular structure on the canvas first.")
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
                label = self.atom_items.get(atom_id)
                if label is not None:
                    rect = label.sceneBoundingRect()
                    xs.extend([rect.left(), rect.right()])
                    ys.extend([rect.top(), rect.bottom()])
                dot = self.atom_dots.get(atom_id)
                if dot is not None:
                    rect = dot.sceneBoundingRect()
                    xs.extend([rect.left(), rect.right()])
                    ys.extend([rect.top(), rect.bottom()])
        if not xs:
            return self.model.bounds()
        return min(xs), min(ys), max(xs), max(ys)

    def _new_note_item(self) -> QGraphicsTextItem:
        return NoteItem(self)

    def add_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        item = self._new_note_item()
        item.setPlainText(text)
        item._last_text = text
        item.setData(0, "note")
        item.setPos(pos)
        self.scene().addItem(item)
        self.note_items.append(item)
        self._make_selectable(item)
        self._apply_note_style(item)
        return item

    def add_mark(self, pos: QPointF, kind: str | None = None, atom_id: int | None = None, offset: QPointF | None = None, record: bool = True):
        return self._scene_decoration_service.add_mark(
            pos,
            kind=kind,
            atom_id=atom_id,
            offset=offset,
            record=record,
        )

    def add_mark_for_atom(self, atom_id: int, click_pos: QPointF, kind: str | None = None, record: bool = True):
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return None
        kind = kind or self.mark_kind
        offset = self._mark_offset_from_click(atom_id, click_pos, kind=kind)
        center = QPointF(atom.x + offset.x(), atom.y + offset.y())
        return self.add_mark(center, kind=kind, atom_id=atom_id, offset=offset, record=record)

    def _mark_selection_radius(self) -> float:
        return self._atom_pick_radius()

    def _build_mark_item(self, kind: str):
        selection_radius = self._mark_selection_radius()
        if kind == "radical":
            radius = max(1.2, self.renderer.style.bond_line_width * 0.7)
            hit_padding = max(0.0, selection_radius - radius)
            item = AtomDotItem(-radius, -radius, radius * 2.0, radius * 2.0, hit_padding=hit_padding)
            item.setBrush(QColor(self.renderer.style.atom_color))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            return item
        if kind in {"plus", "minus"}:
            text_item = AtomLabelItem(hit_radius=selection_radius)
            text_item.setFont(self.renderer.atom_font())
            text_item.setDefaultTextColor(QColor(self.renderer.style.atom_color))
            text_item.setPlainText("+" if kind == "plus" else "-")
            return text_item
        return None

    def _mark_offset_from_click(self, atom_id: int, click_pos: QPointF, kind: str | None = None) -> QPointF:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return QPointF(0.0, 0.0)
        dx = click_pos.x() - atom.x
        dy = click_pos.y() - atom.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            dx = 1.0
            dy = -1.0
            length = math.hypot(dx, dy)
        direction_x = dx / length
        direction_y = dy / length
        target = self.renderer.style.bond_length_px * 0.2
        mark_kind = kind or self.mark_kind
        label_target = self._mark_target_distance_for_atom(atom_id, direction_x, direction_y, mark_kind)
        if label_target > target:
            target += (label_target - target) * 0.25
        return QPointF(direction_x * target, direction_y * target)

    def _mark_center(self, item) -> QPointF:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            return QPointF(item.pos().x() + rect.center().x(), item.pos().y() + rect.center().y())
        return item.pos()

    def _set_mark_center(self, item, center: QPointF) -> None:
        if isinstance(item, QGraphicsTextItem):
            rect = item.boundingRect()
            item.setPos(center.x() - rect.center().x(), center.y() - rect.center().y())
        else:
            item.setPos(center)

    def _remove_mark_item(self, item) -> None:
        if item in self.mark_items:
            self.mark_items.remove(item)
        data = item.data(1) or {}
        atom_id = data.get("atom_id")
        if isinstance(atom_id, int):
            marks = self._marks_by_atom.get(atom_id)
            if marks and item in marks:
                marks.remove(item)
            if marks and not marks:
                self._marks_by_atom.pop(atom_id, None)
        self.scene().removeItem(item)

    def _remove_marks_for_atom(self, atom_id: int) -> None:
        marks = self._marks_by_atom.pop(atom_id, [])
        for item in list(marks):
            if item in self.mark_items:
                self.mark_items.remove(item)
            self.scene().removeItem(item)

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
        return _selection_controller_for(self)._selection_line_stroke_path(start, end, width)

    def _selection_path_for_bond_item(self, item, width: float | None = None) -> QPainterPath:
        return _selection_controller_for(self)._selection_path_for_bond_item(item, width=width)

    def _selection_path_for_bond(self, bond_id: int) -> QPainterPath:
        return _selection_controller_for(self)._selection_path_for_bond(bond_id)

    def _selection_path_for_object_item(self, item) -> QPainterPath:
        return _selection_controller_for(self)._selection_path_for_object_item(item)

    def _add_selection_object_overlay(self, item, color: QColor) -> None:
        _selection_controller_for(self)._add_selection_object_overlay(item, color)

    def _add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
        atom_pad: float,
    ) -> None:
        _selection_controller_for(self)._add_selection_component_overlay(atom_ids, bond_ids, color, atom_pad)

    def _selection_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        return _selection_controller_for(self)._selection_center_for_atoms(atom_ids)

    def _selection_center_marker_enabled(self) -> bool:
        return _selection_controller_for(self)._selection_center_marker_enabled()

    def _add_selection_center_marker(self, center: QPointF) -> None:
        _selection_controller_for(self)._add_selection_center_marker(center)

    def suspend_selection_outline(self, suspend: bool) -> None:
        self._suspend_selection_outline = bool(suspend)

    def _ensure_atom_neighbors(self, atom_id: int) -> None:
        if atom_id not in self._atom_neighbors:
            self._atom_neighbors[atom_id] = set()

    def _ensure_atom_bond_ids(self, atom_id: int) -> None:
        if atom_id not in self._atom_bond_ids:
            self._atom_bond_ids[atom_id] = set()

    def _add_bond_neighbors(self, a_id: int, b_id: int) -> None:
        self._atom_neighbors.setdefault(a_id, set()).add(b_id)
        self._atom_neighbors.setdefault(b_id, set()).add(a_id)
        self._graph_version += 1

    def _remove_bond_neighbors(self, a_id: int, b_id: int, skip_bond_id: int | None = None) -> None:
        if self._bond_id_between(a_id, b_id, skip_bond_id=skip_bond_id) is not None:
            return
        changed = False
        neighbors_a = self._atom_neighbors.get(a_id)
        if neighbors_a is not None and b_id in neighbors_a:
            neighbors_a.remove(b_id)
            changed = True
        neighbors_b = self._atom_neighbors.get(b_id)
        if neighbors_b is not None and a_id in neighbors_b:
            neighbors_b.remove(a_id)
            changed = True
        if changed:
            self._graph_version += 1

    def _add_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        self._atom_bond_ids.setdefault(a_id, set()).add(bond_id)
        self._atom_bond_ids.setdefault(b_id, set()).add(bond_id)

    def _remove_bond_index(self, bond_id: int, a_id: int, b_id: int) -> None:
        bonds_a = self._atom_bond_ids.get(a_id)
        if bonds_a is not None and bond_id in bonds_a:
            bonds_a.remove(bond_id)
        bonds_b = self._atom_bond_ids.get(b_id)
        if bonds_b is not None and bond_id in bonds_b:
            bonds_b.remove(bond_id)

    def _rebuild_bond_adjacency(self) -> None:
        self._atom_neighbors = {atom_id: set() for atom_id in self.model.atoms}
        self._atom_bond_ids = {atom_id: set() for atom_id in self.model.atoms}
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            self._atom_neighbors.setdefault(bond.a, set()).add(bond.b)
            self._atom_neighbors.setdefault(bond.b, set()).add(bond.a)
            self._atom_bond_ids.setdefault(bond.a, set()).add(bond_id)
            self._atom_bond_ids.setdefault(bond.b, set()).add(bond_id)
        self._graph_version += 1
        self._selection_component_cache_signature = None
        self._selection_component_cache = []

    def _connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        remaining = set(atom_ids)
        components = []
        while remaining:
            start = remaining.pop()
            stack = [start]
            comp = {start}
            while stack:
                current = stack.pop()
                for neighbor in self._atom_neighbors.get(current, ()):
                    if neighbor not in atom_ids:
                        continue
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        comp.add(neighbor)
                        stack.append(neighbor)
            components.append(comp)
        return components

    def _component_without_bond(self, start_atom_id: int, skip_bond_id: int) -> set[int]:
        skip_bond = None
        skip_a = None
        skip_b = None
        has_alt_between = False
        if 0 <= skip_bond_id < len(self.model.bonds):
            skip_bond = self.model.bonds[skip_bond_id]
        if skip_bond is not None:
            skip_a = skip_bond.a
            skip_b = skip_bond.b
            shared = self._atom_bond_ids.get(skip_a, set()) & self._atom_bond_ids.get(skip_b, set())
            has_alt_between = any(bond_id != skip_bond_id for bond_id in shared)
        visited = {start_atom_id}
        stack = [start_atom_id]
        while stack:
            current = stack.pop()
            for neighbor in self._atom_neighbors.get(current, ()):
                if (
                    skip_bond is not None
                    and not has_alt_between
                    and (
                        (current == skip_a and neighbor == skip_b)
                        or (current == skip_b and neighbor == skip_a)
                    )
                ):
                    continue
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)
        return visited

    def _bond_in_cycle(self, bond_id: int) -> bool:
        cached = self._bond_cycle_cache.get(bond_id)
        if cached is not None and cached[0] == self._graph_version:
            return cached[1]
        if not (0 <= bond_id < len(self.model.bonds)):
            self._bond_cycle_cache[bond_id] = (self._graph_version, False)
            return False
        bond = self.model.bonds[bond_id]
        if bond is None:
            self._bond_cycle_cache[bond_id] = (self._graph_version, False)
            return False
        start = bond.a
        target = bond.b
        shared = self._atom_bond_ids.get(start, set()) & self._atom_bond_ids.get(target, set())
        has_alt_between = any(other_id != bond_id for other_id in shared)
        visited = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in self._atom_neighbors.get(current, ()):
                if (
                    not has_alt_between
                    and (
                        (current == start and neighbor == target)
                        or (current == target and neighbor == start)
                    )
                ):
                    continue
                if neighbor in visited:
                    continue
                if neighbor == target:
                    self._bond_cycle_cache[bond_id] = (self._graph_version, True)
                    return True
                visited.add(neighbor)
                stack.append(neighbor)
        self._bond_cycle_cache[bond_id] = (self._graph_version, False)
        return False

    def _bond_is_rotatable(self, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.model.bonds)):
            return False
        bond = self.model.bonds[bond_id]
        if bond is None or bond.order != 1:
            return False
        if self._bond_in_cycle(bond_id):
            return False
        return True

    def _bond_component_atoms(self, bond_id: int) -> set[int] | None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self._component_without_bond(bond.a, bond_id)
        comp_b = self._component_without_bond(bond.b, bond_id)
        return comp_a | comp_b

    def _rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        allow_fallback: bool,
    ) -> set[int] | None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self._component_without_bond(bond.a, bond_id)
        comp_b = self._component_without_bond(bond.b, bond_id)
        effective_selected = set(selected_atom_ids) - {bond.a, bond.b}
        selected_in_a = effective_selected & comp_a
        selected_in_b = effective_selected & comp_b
        if selected_in_a and not selected_in_b:
            return comp_a
        if selected_in_b and not selected_in_a:
            return comp_b
        if not selected_in_a and not selected_in_b:
            a_selected = bond.a in selected_atom_ids
            b_selected = bond.b in selected_atom_ids
            if a_selected ^ b_selected:
                return comp_a if a_selected else comp_b
        if allow_fallback:
            count_a = len(selected_in_a)
            count_b = len(selected_in_b)
            if count_a != count_b:
                return comp_a if count_a > count_b else comp_b
            size_a = max(0, len(comp_a) - 1)
            size_b = max(0, len(comp_b) - 1)
            if size_a != size_b:
                return comp_a if size_a > size_b else comp_b
            return comp_a if len(comp_a) >= len(comp_b) else comp_b
        return None

    def _preferred_rotation_side_for_bond(
        self,
        bond_id: int,
        selected_atom_ids: set[int],
        press_pos: QPointF | None = None,
        allow_fallback: bool = True,
    ) -> set[int] | None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        comp_a = self._component_without_bond(bond.a, bond_id)
        comp_b = self._component_without_bond(bond.b, bond_id)
        component = comp_a | comp_b
        selected_in_component = set(selected_atom_ids) & component
        is_partial_selection = 0 < len(selected_in_component) < len(component)
        effective_selected = selected_in_component - {bond.a, bond.b}
        selected_in_a = effective_selected & comp_a
        selected_in_b = effective_selected & comp_b
        overlap_a = selected_in_component & comp_a
        overlap_b = selected_in_component & comp_b
        atom_a = self.model.atoms.get(bond.a)
        atom_b = self.model.atoms.get(bond.b)
        dist_a = None
        dist_b = None
        if is_partial_selection:
            if selected_in_a and not selected_in_b:
                return comp_a
            if selected_in_b and not selected_in_a:
                return comp_b
            if overlap_a and not overlap_b:
                return comp_a
            if overlap_b and not overlap_a:
                return comp_b
            coverage_a = len(overlap_a) / max(1, len(comp_a))
            coverage_b = len(overlap_b) / max(1, len(comp_b))
            if abs(coverage_a - coverage_b) > 1e-9:
                return comp_a if coverage_a > coverage_b else comp_b
            if len(selected_in_a) != len(selected_in_b):
                return comp_a if len(selected_in_a) > len(selected_in_b) else comp_b
            if len(overlap_a) != len(overlap_b):
                return comp_a if len(overlap_a) > len(overlap_b) else comp_b
        elif not selected_in_a and not selected_in_b:
            a_selected = bond.a in selected_atom_ids
            b_selected = bond.b in selected_atom_ids
            if a_selected ^ b_selected:
                return comp_a if a_selected else comp_b
        if press_pos is not None and atom_a is not None and atom_b is not None:
            dist_a = math.hypot(press_pos.x() - atom_a.x, press_pos.y() - atom_a.y)
            dist_b = math.hypot(press_pos.x() - atom_b.x, press_pos.y() - atom_b.y)
            tol = self.renderer.style.bond_length_px * 0.05
            if abs(dist_a - dist_b) > tol:
                return comp_a if dist_a < dist_b else comp_b
        if not allow_fallback:
            return None
        if is_partial_selection:
            count_a = len(selected_in_a)
            count_b = len(selected_in_b)
            if count_a != count_b:
                return comp_a if count_a > count_b else comp_b
        size_a = max(0, len(comp_a) - 1)
        size_b = max(0, len(comp_b) - 1)
        if size_a != size_b:
            return comp_a if size_a < size_b else comp_b
        if dist_a is not None and dist_b is not None:
            return comp_a if dist_a <= dist_b else comp_b
        return comp_a if bond.a <= bond.b else comp_b

    def _rotatable_axis_from_selection(
        self,
        selected_atom_ids: set[int],
        selected_bond_ids: set[int],
    ) -> tuple[int, set[int]] | None:
        if self._rotation_axis_cache_version != self._graph_version:
            self._rotation_axis_cache.clear()
            self._rotation_axis_cache_version = self._graph_version
        cache_key = (
            frozenset(selected_atom_ids),
            frozenset(selected_bond_ids),
            self._graph_version,
        )
        if cache_key in self._rotation_axis_cache:
            return self._rotation_axis_cache[cache_key]
        def _store(axis: tuple[int, set[int]] | None) -> tuple[int, set[int]] | None:
            self._rotation_axis_cache[cache_key] = axis
            return axis
        explicit_atoms = set(selected_atom_ids)
        bond_atoms: set[int] = set()
        selected_bonds: set[int] = set()
        for bond_id in selected_bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            selected_bonds.add(bond_id)
            bond_atoms.add(bond.a)
            bond_atoms.add(bond.b)
        atoms_for_boundary = explicit_atoms | bond_atoms
        if selected_bonds and len(selected_bonds) == 1:
            bond_id = next(iter(selected_bonds))
            if self._bond_is_rotatable(bond_id):
                rotating = self._preferred_rotation_side_for_bond(
                    bond_id,
                    atoms_for_boundary,
                    allow_fallback=True,
                )
                if rotating is not None:
                    return _store((bond_id, rotating))
        if not explicit_atoms and len(selected_bonds) > 1:
            selected_degree: dict[int, int] = {}
            for bond_id in selected_bonds:
                bond = self.model.bonds[bond_id]
                if bond is None:
                    continue
                selected_degree[bond.a] = selected_degree.get(bond.a, 0) + 1
                selected_degree[bond.b] = selected_degree.get(bond.b, 0) + 1
            has_unselected_bond: dict[int, bool] = {}
            for other_id, other in enumerate(self.model.bonds):
                if other is None or other_id in selected_bonds:
                    continue
                has_unselected_bond[other.a] = True
                has_unselected_bond[other.b] = True
            candidates = []
            for bond_id in selected_bonds:
                bond = self.model.bonds[bond_id]
                if bond is None:
                    continue
                a_leaf = selected_degree.get(bond.a, 0) == 1 and has_unselected_bond.get(bond.a, False)
                b_leaf = selected_degree.get(bond.b, 0) == 1 and has_unselected_bond.get(bond.b, False)
                if a_leaf ^ b_leaf:
                    candidates.append(bond_id)
            if len(candidates) == 1:
                bond_id = candidates[0]
                if self._bond_is_rotatable(bond_id):
                    rotating = self._rotation_side_for_bond(
                        bond_id,
                        bond_atoms,
                        allow_fallback=True,
                    )
                    if rotating is not None:
                        return _store((bond_id, rotating))
                return _store(None)
        if not atoms_for_boundary:
            return _store(None)
        boundary = []
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            a_sel = bond.a in atoms_for_boundary
            b_sel = bond.b in atoms_for_boundary
            if a_sel ^ b_sel:
                boundary.append(bond_id)
        if len(boundary) == 1:
            bond_id = boundary[0]
            if not self._bond_is_rotatable(bond_id):
                return _store(None)
            rotating = self._rotation_side_for_bond(
                bond_id,
                atoms_for_boundary,
                allow_fallback=not explicit_atoms,
            )
            if rotating is not None:
                return _store((bond_id, rotating))
        atoms_for_axis = set(atoms_for_boundary)
        if not atoms_for_axis:
            return _store(None)
        candidates: list[tuple[int, set[int]]] = []
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None or not self._bond_is_rotatable(bond_id):
                continue
            rotating = self._rotation_side_for_bond(
                bond_id,
                atoms_for_axis,
                allow_fallback=False,
            )
            if rotating is None:
                continue
            candidates.append((bond_id, rotating))
        if len(candidates) == 1:
            axis = candidates[0]
        else:
            axis = None
        return _store(axis)

    def set_selection_info_callback(self, callback) -> None:
        self._selection_info_callback = callback

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
        hover_scene_service = getattr(self, "_hover_scene_service", None)
        if hover_scene_service is not None:
            hover_scene_service.clear_hover_highlight()
            return
        self.hover_items = clear_hover_items_helper(self.scene(), self.hover_items)
        self.hover_atom_id = None
        self.hover_bond_id = None
        self._hover_preview_style = None

    def _add_atom_hover_indicator(self, atom_id: int) -> None:
        hover_scene_service = getattr(self, "_hover_scene_service", None)
        if hover_scene_service is not None:
            hover_scene_service.add_atom_hover_indicator(atom_id)
            return
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = self.renderer.style.bond_length_px * 0.25
        circle = build_atom_hover_indicator_helper(QPointF(atom.x, atom.y), radius)
        self.scene().addItem(circle)
        self.hover_items.append(circle)

    def _add_bond_hover_indicator(self, bond_id: int) -> None:
        hover_scene_service = getattr(self, "_hover_scene_service", None)
        if hover_scene_service is not None:
            hover_scene_service.add_bond_hover_indicator(bond_id)
            return
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        a = self.model.atoms.get(bond.a)
        b = self.model.atoms.get(bond.b)
        if a is None or b is None:
            return
        radius = self.renderer.style.bond_length_px * 0.22
        circle = build_bond_hover_indicator_helper(
            QPointF(a.x, a.y),
            QPointF(b.x, b.y),
            radius,
        )
        self.scene().addItem(circle)
        self.hover_items.append(circle)

    def _mark_center_for_pointer(
        self,
        pos: QPointF,
        atom_id: int | None = None,
        kind: str | None = None,
    ) -> QPointF:
        if atom_id is None:
            return QPointF(pos)
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return QPointF(pos)
        offset = self._mark_offset_from_click(atom_id, pos, kind=kind)
        return QPointF(atom.x + offset.x(), atom.y + offset.y())

    def _add_mark_hover_preview(self, pos: QPointF) -> None:
        self._mark_hover_preview_service.add_mark_hover_preview(pos)

    def _update_hover_highlight(self, pos: QPointF) -> None:
        hover_interaction_service = getattr(self, "_hover_interaction_service", None)
        if hover_interaction_service is None:
            hover_interaction_service = HoverInteractionService(self)
        hover_interaction_service.update_hover_highlight(pos)

    def _find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        if not self.model.bonds:
            return None
        self._ensure_spatial_index()
        cell_size = self._spatial_cell_size or self._grid_cell_size()
        if cell_size <= 0:
            return None
        cell_radius = int(math.ceil(max_dist / cell_size))
        ix, iy = self._cell_coords(pos.x(), pos.y(), cell_size)
        nearest = None
        nearest_dist = max_dist
        seen: set[int] = set()
        for cx in range(ix - cell_radius, ix + cell_radius + 1):
            for cy in range(iy - cell_radius, iy + cell_radius + 1):
                for bond_id in self._bond_grid.get((cx, cy), ()):
                    if bond_id in seen:
                        continue
                    seen.add(bond_id)
                    if not (0 <= bond_id < len(self.model.bonds)):
                        continue
                    bond = self.model.bonds[bond_id]
                    if bond is None:
                        continue
                    a = self.model.atoms.get(bond.a)
                    b = self.model.atoms.get(bond.b)
                    if a is None or b is None:
                        continue
                    dist = self._distance_point_to_segment(
                        pos,
                        QPointF(a.x, a.y),
                        QPointF(b.x, b.y),
                    )
                    if dist <= nearest_dist:
                        nearest = bond_id
                        nearest_dist = dist
        return nearest

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
        hover_scene_service = getattr(self, "_hover_scene_service", None)
        if hover_scene_service is not None:
            hover_scene_service.add_hover_preview_items(items)
            return
        if not items:
            return
        self.hover_items.extend(add_hover_preview_items_helper(self.scene(), items))

    def _default_bond_endpoint(self, start: QPointF, start_atom_id: int | None) -> QPointF:
        bond_len = self.renderer.style.bond_length_px
        angle = 0.0
        if start_atom_id is not None:
            atom = self.model.atoms.get(start_atom_id)
            if atom is not None:
                connected = [
                    bond
                    for bond in self.model.bonds
                    if bond is not None and (bond.a == start_atom_id or bond.b == start_atom_id)
                ]
                if connected:
                    vectors = []
                    for bond in connected:
                        other_id = bond.b if bond.a == start_atom_id else bond.a
                        other = self.model.atoms.get(other_id)
                        if other is None:
                            continue
                        dx = other.x - atom.x
                        dy = other.y - atom.y
                        length = math.hypot(dx, dy)
                        if length == 0:
                            continue
                        vectors.append((dx / length, dy / length))
                    if len(vectors) >= 2:
                        sx = sum(v[0] for v in vectors)
                        sy = sum(v[1] for v in vectors)
                        if math.hypot(sx, sy) > 1e-6:
                            angle = math.degrees(math.atan2(-sy, -sx))
                        else:
                            angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 90.0
                    elif vectors:
                        angle = math.degrees(math.atan2(vectors[0][1], vectors[0][0])) - 120.0
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
        abx = b.x() - a.x()
        aby = b.y() - a.y()
        apx = p.x() - a.x()
        apy = p.y() - a.y()
        ab_len_sq = abx * abx + aby * aby
        if ab_len_sq == 0:
            return math.hypot(apx, apy)
        t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_len_sq))
        cx = a.x() + abx * t
        cy = a.y() + aby * t
        return math.hypot(p.x() - cx, p.y() - cy)

    def add_arrow(self, start: QPointF, end: QPointF, kind: str):
        return self._scene_decoration_service.add_arrow(start, end, kind)

    def preview_arrow(self, start: QPointF, end: QPointF, kind: str):
        item = self._build_arrow_item(start, end, kind)
        self.scene().addItem(item)
        return item

    def _build_arrow_item(self, start: QPointF, end: QPointF, kind: str) -> QGraphicsPathItem:
        if kind == "equilibrium":
            return self._build_equilibrium_item(start, end)
        if kind == "resonance":
            return self._build_double_head_arrow(start, end)
        if kind == "curved_single":
            return self._build_curved_arrow(start, end, double=False)
        if kind == "curved_double":
            return self._build_curved_arrow(start, end, double=True)
        if kind == "inhibit":
            return self._build_inhibition_arrow(start, end)
        if kind == "dotted":
            return self._build_dotted_arrow(start, end)
        return self._build_single_head_arrow(start, end)

    def _arrow_pen(self, dotted: bool = False):
        pen = self.renderer.bond_pen()
        pen.setWidthF(self.arrow_line_width)
        if dotted:
            pen.setStyle(Qt.PenStyle.DashLine)
        return pen

    def _build_single_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self._add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def _build_double_head_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self._add_arrow_head(path, start, end, double=False)
        self._add_arrow_head(path, end, start, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def _build_dotted_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self._add_arrow_head(path, start, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen(dotted=True))
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def _build_curved_arrow(self, start: QPointF, end: QPointF, double: bool) -> QGraphicsPathItem:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        control = QPointF(start.x() + dx * 0.5 + nx * length * 0.3, start.y() + dy * 0.5 + ny * length * 0.3)
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self._add_arrow_head(path, control, end, double=False)
            self._add_arrow_head(path, control, start, double=False)
        else:
            self._add_arrow_head(path, control, end, double=False)
        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": control, "double": double})
        return item

    def _build_inhibition_arrow(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        bar = self.renderer.style.bond_length_px * 0.2

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        bar_start = QPointF(end.x() - nx * bar, end.y() - ny * bar)
        bar_end = QPointF(end.x() + nx * bar, end.y() + ny * bar)
        path.moveTo(bar_start)
        path.lineTo(bar_end)
        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def _build_equilibrium_item(self, start: QPointF, end: QPointF) -> QGraphicsPathItem:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        offset = self.renderer.style.bond_spacing_px * 1.5
        start_up = QPointF(start.x() + nx * offset, start.y() + ny * offset)
        end_up = QPointF(end.x() + nx * offset, end.y() + ny * offset)
        start_down = QPointF(start.x() - nx * offset, start.y() - ny * offset)
        end_down = QPointF(end.x() - nx * offset, end.y() - ny * offset)

        path = QPainterPath()
        path.addPath(self._build_single_head_arrow(start_up, end_up).path())
        path.addPath(self._build_single_head_arrow(end_down, start_down).path())

        item = NoSelectPathItem(path)
        item.setPen(self._arrow_pen())
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setData(2, {"start": start, "end": end, "control": None, "double": False})
        return item

    def _add_arrow_head(self, path: QPainterPath, start: QPointF, end: QPointF, double: bool) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = self.renderer.style.bond_length_px * self.arrow_head_scale
        head_angle = math.radians(25)
        offsets = [0.0]
        if double:
            offset_mag = max(1.4, self.arrow_line_width * 1.2)
            offsets = [-offset_mag, offset_mag]
        for offset in offsets:
            dx = math.cos(angle + math.pi / 2) * offset
            dy = math.sin(angle + math.pi / 2) * offset
            tip = QPointF(end.x() + dx, end.y() + dy) if double else end
            left = QPointF(
                tip.x() - head_len * math.cos(angle - head_angle),
                tip.y() - head_len * math.sin(angle - head_angle),
            )
            right = QPointF(
                tip.x() - head_len * math.cos(angle + head_angle),
                tip.y() - head_len * math.sin(angle + head_angle),
            )
            path.moveTo(left)
            path.lineTo(tip)
            path.lineTo(right)

    def _ts_bracket_rect_from_points(self, start: QPointF, end: QPointF) -> QRectF:
        rect = QRectF(start, end).normalized()
        min_width = self.renderer.style.bond_length_px * 1.8
        min_height = self.renderer.style.bond_length_px * 2.4
        if rect.width() < 4.0 and rect.height() < 4.0:
            return QRectF(
                start.x() - min_width / 2.0,
                start.y() - min_height / 2.0,
                min_width,
                min_height,
            )
        center = rect.center()
        width = max(rect.width(), min_width)
        height = max(rect.height(), min_height)
        return QRectF(center.x() - width / 2.0, center.y() - height / 2.0, width, height)

    def _ts_bracket_stroke_width(self) -> float:
        return max(0.8, self.renderer.style.bond_line_width * 0.58)

    def _ts_bracket_path(self, rect: QRectF) -> QPainterPath:
        rect = QRectF(rect).normalized()
        hook = min(rect.width() * 0.18, self.renderer.style.bond_length_px * 0.55)
        hook = max(hook, self.renderer.style.bond_length_px * 0.28)
        bracket_lines = QPainterPath()
        bracket_lines.moveTo(rect.left() + hook, rect.top())
        bracket_lines.lineTo(rect.left(), rect.top())
        bracket_lines.lineTo(rect.left(), rect.bottom())
        bracket_lines.lineTo(rect.left() + hook, rect.bottom())
        bracket_lines.moveTo(rect.right() - hook, rect.top())
        bracket_lines.lineTo(rect.right(), rect.top())
        bracket_lines.lineTo(rect.right(), rect.bottom())
        bracket_lines.lineTo(rect.right() - hook, rect.bottom())

        stroker = QPainterPathStroker()
        stroker.setWidth(self._ts_bracket_stroke_width())
        stroker.setCapStyle(Qt.PenCapStyle.FlatCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        path = stroker.createStroke(bracket_lines)

        font = QFont(self.renderer.style.font_family)
        font.setPixelSize(max(10, round(min(rect.height() * 0.22, self.renderer.style.bond_length_px * 0.95))))
        path.addText(
            rect.right() + hook * 0.18,
            rect.top() + font.pixelSize() * 0.18,
            font,
            "\u2021",
        )
        return path

    def _build_ts_bracket_item(self, rect: QRectF) -> QGraphicsPathItem:
        normalized = QRectF(rect).normalized()
        item = NoSelectPathItem(self._ts_bracket_path(normalized))
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(self.renderer.style.bond_color)))
        item.setData(0, "ts_bracket")
        item.setData(1, {"rect": normalized})
        return item

    def add_ts_bracket_from_points(self, start: QPointF, end: QPointF):
        return self.add_ts_bracket(self._ts_bracket_rect_from_points(start, end))

    def add_ts_bracket(self, rect: QRectF):
        return self._scene_decoration_service.add_ts_bracket(rect)

    def preview_ts_bracket(self, start: QPointF, end: QPointF):
        item = self._build_ts_bracket_item(self._ts_bracket_rect_from_points(start, end))
        preview_color = QColor(120, 120, 120, 140)
        item.setBrush(QBrush(preview_color))
        self.scene().addItem(item)
        return item

    def add_orbital(self, center: QPointF) -> None:
        return self._scene_decoration_service.add_orbital(center)

    def _build_orbital_items(self, center: QPointF, kind: str):
        radius = self.renderer.style.bond_length_px * 0.35
        pen = self.renderer.bond_pen()
        pos_color = QColor(self.renderer.style.orbital_positive_color)
        neg_color = QColor(self.renderer.style.orbital_negative_color)
        pos_color.setAlphaF(self.renderer.style.orbital_alpha)
        neg_color.setAlphaF(self.renderer.style.orbital_alpha)

        def _ellipse_item(cx, cy, rx, ry, fill=None):
            item = QGraphicsEllipseItem(cx - rx, cy - ry, rx * 2, ry * 2)
            item.setPen(pen)
            if fill is not None:
                item.setBrush(fill)
            return item

        items = []
        if kind == "s":
            fill = pos_color if self.orbital_phase_enabled else None
            items.append(_ellipse_item(center.x(), center.y(), radius, radius, fill))
            return items
        if kind == "p":
            fill1 = pos_color if self.orbital_phase_enabled else None
            fill2 = neg_color if self.orbital_phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill2))
            return items
        if kind == "sp":
            fill1 = pos_color if self.orbital_phase_enabled else None
            fill2 = neg_color if self.orbital_phase_enabled else None
            items.append(_ellipse_item(center.x() - radius * 1.2, center.y(), radius * 1.2, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius * 0.6, center.y(), radius * 0.6, radius * 0.4, fill2))
            return items
        if kind == "sp2":
            fill = pos_color if self.orbital_phase_enabled else None
            for angle in [0, 120, 240]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.75, radius * 0.5, fill))
            return items
        if kind == "sp3":
            fill = pos_color if self.orbital_phase_enabled else None
            for angle in [45, 135, 225, 315]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.7, radius * 0.45, fill))
            return items
        if kind == "d":
            fill1 = pos_color if self.orbital_phase_enabled else None
            fill2 = neg_color if self.orbital_phase_enabled else None
            for angle, fill in [(45, fill1), (135, fill2), (225, fill1), (315, fill2)]:
                rad = math.radians(angle)
                cx = center.x() + math.cos(rad) * radius * 1.1
                cy = center.y() + math.sin(rad) * radius * 1.1
                items.append(_ellipse_item(cx, cy, radius * 0.7, radius * 0.45, fill))
            return items
        if kind == "mo_bonding":
            fill = pos_color if self.orbital_phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill))
            return items
        if kind == "mo_antibonding":
            fill1 = pos_color if self.orbital_phase_enabled else None
            fill2 = neg_color if self.orbital_phase_enabled else None
            items.append(_ellipse_item(center.x() - radius, center.y(), radius, radius * 0.7, fill1))
            items.append(_ellipse_item(center.x() + radius, center.y(), radius, radius * 0.7, fill2))
            node = NoSelectLineItem(center.x(), center.y() - radius * 0.8, center.x(), center.y() + radius * 0.8)
            node.setPen(pen)
            items.append(node)
            return items
        return items

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
        return _input_controller_for(self).event(event, native_gesture_event_type=QNativeGestureEvent)

    def _should_override_chemdraw_shortcut(self, event) -> bool:
        return _input_controller_for(self).should_override_chemdraw_shortcut(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
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
        if bond_ids:
            for bond_id in bond_ids:
                if not (0 <= bond_id < len(self.model.bonds)):
                    continue
                bond = self.model.bonds[bond_id]
                if bond is None:
                    continue
                atom_ids.add(bond.a)
                atom_ids.add(bond.b)
        if not atom_ids:
            return
        center = self._center_for_atoms(atom_ids)
        if center is None:
            return
        angle = math.radians(angle_degrees)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            dx = atom.x - center.x()
            dy = atom.y - center.y()
            atom.x = center.x() + dx * cos_a - dy * sin_a
            atom.y = center.y() + dx * sin_a + dy * cos_a
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
        if not self._bond_is_rotatable(axis_hint):
            return None
        component = self._bond_component_atoms(axis_hint)
        if component is None:
            return None
        selected_in_component = rotation_atom_ids & component
        if not selected_in_component:
            return None
        rotating = self._preferred_rotation_side_for_bond(
            axis_hint,
            selected_in_component,
            press_pos=press_pos,
            allow_fallback=True,
        )
        if rotating is None:
            return None
        return axis_hint, rotating

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
        bond_ids = set()
        for atom_id in atom_ids:
            bond_ids.update(self._atom_bond_ids.get(atom_id, ()))
        for bond_id in bond_ids:
            self._redraw_bond(bond_id)

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        internal: set[int] = set()
        boundary: set[int] = set()
        if not atom_ids:
            return internal, boundary
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(self._atom_bond_ids.get(atom_id, ()))
        if not bond_ids:
            for bond_id, bond in enumerate(self.model.bonds):
                if bond is None:
                    continue
                a_in = bond.a in atom_ids
                b_in = bond.b in atom_ids
                if a_in or b_in:
                    bond_ids.add(bond_id)
        for bond_id in bond_ids:
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            a_in = bond.a in atom_ids
            b_in = bond.b in atom_ids
            if a_in and b_in:
                internal.add(bond_id)
            elif a_in or b_in:
                boundary.add(bond_id)
        return internal, boundary

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
        if not atom_ids:
            return set()
        adjacency: dict[int, set[int]] = {}
        for bond in self.model.bonds:
            if bond is None:
                continue
            adjacency.setdefault(bond.a, set()).add(bond.b)
            adjacency.setdefault(bond.b, set()).add(bond.a)
        visited = set(atom_ids)
        stack = list(atom_ids)
        while stack:
            current = stack.pop()
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        return visited

    def _update_ring_fills_for_atoms(self, atom_ids: set[int]) -> None:
        if not atom_ids:
            return
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                continue
            points = []
            for atom_id in ring_atom_ids:
                atom = self.model.atoms.get(atom_id)
                if atom is None:
                    continue
                points.append(QPointF(atom.x, atom.y))
                if len(points) >= 3:
                    ring_item.setPolygon(QPolygonF(points))

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
        if center_3d is None:
            center_3d = self._projection_center_3d
        if center_3d is None:
            return point[0], point[1]
        if anchor_2d is None:
            anchor_2d = self._projection_anchor_2d or (center_3d[0], center_3d[1])
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
        if center_3d is None:
            center_3d = self._projection_center_3d
        if center_3d is None:
            return (point.x(), point.y(), z)
        if anchor_2d is None:
            anchor_2d = self._projection_anchor_2d or (center_3d[0], center_3d[1])
        cx, cy, cz = center_3d
        anchor_x, anchor_y = anchor_2d
        focal = self._perspective_camera_distance()
        dz = max(min(z - cz, focal * 0.7), -focal * 0.8)
        denom = max(focal - dz, focal * 0.2)
        scale = focal / denom
        if abs(scale) <= 1e-9:
            return (point.x(), point.y(), z)
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
        for bond_id in self._atom_bond_ids.get(atom_id, ()):
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
            marks = self._marks_by_atom.get(atom_id)
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
        bond_ids: set[int] = set()
        for atom_id in atom_ids:
            bond_ids.update(self._atom_bond_ids.get(atom_id, ()))
        if not bond_ids:
            for bond_id, bond in enumerate(self.model.bonds):
                if bond is None:
                    continue
                if bond.a in atom_ids and bond.b in atom_ids:
                    bond_ids.add(bond_id)
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

    def _rotation_scale_for_coords(
        self,
        atom_ids: set[int],
        rotated_coords: dict[int, tuple[float, float, float]],
        extra_atom_ids: set[int] | tuple[int, ...] = (),
    ) -> float:
        if not self._rotation_base_bond_length:
            return 1.0
        scale_atom_ids = set(atom_ids)
        scale_atom_ids.update(extra_atom_ids)
        current_coords = dict(self._rotation_base_coords)
        current_coords.update(rotated_coords)
        current_avg = self._average_bond_length_for_atoms(scale_atom_ids, current_coords)
        if not current_avg or current_avg <= 1e-9:
            return 1.0
        scale = self._rotation_base_bond_length / current_avg
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
        cx, cy, cz = center
        cos_y = math.cos(angle_y)
        sin_y = math.sin(angle_y)
        cos_x = math.cos(angle_x)
        sin_x = math.sin(angle_x)
        tol = self.renderer.style.bond_length_px * 0.25
        atom_points = []
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom_points.append(QPointF(atom.x, atom.y))
        if not atom_points:
            return
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                    continue
                points = []
                for atom_id in ring_atom_ids:
                    atom = self.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    points.append(QPointF(atom.x, atom.y))
                if len(points) >= 3:
                    ring_item.setPolygon(QPolygonF(points))
                continue
            polygon = ring_item.polygon()
            matched = False
            for point in polygon:
                for atom_point in atom_points:
                    if math.hypot(point.x() - atom_point.x(), point.y() - atom_point.y()) <= tol:
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                continue
            rotated = QPolygonF()
            for point in polygon:
                x = point.x() - cx
                y = point.y() - cy
                z = 0.0 - cz
                rx = x * cos_y + z * sin_y
                rz = -x * sin_y + z * cos_y
                ry = y * cos_x - rz * sin_x
                rz2 = y * sin_x + rz * cos_x
                x = rx + cx
                y = ry + cy
                z = rz2 + cz
                proj_x = x
                proj_y = y
                rotated.append(QPointF(proj_x, proj_y))
            ring_item.setPolygon(rotated)

    def begin_selection_rotation(self) -> bool:
        return _rotation_preview_controller_for(self).begin_selection_rotation()

    def update_rotation_preview(self, angle_degrees: float) -> None:
        _rotation_preview_controller_for(self).update_rotation_preview(angle_degrees)

    def commit_selection_rotation(self) -> None:
        _rotation_preview_controller_for(self).commit_selection_rotation()

    def _rotate_ring_fills(self, atom_ids: set[int], center: QPointF, angle_rad: float) -> None:
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        tol = self.renderer.style.bond_length_px * 0.25
        atom_points = []
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom_points.append(QPointF(atom.x, atom.y))
        if not atom_points:
            return
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                    continue
                points = []
                for atom_id in ring_atom_ids:
                    atom = self.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    points.append(QPointF(atom.x, atom.y))
                if len(points) >= 3:
                    ring_item.setPolygon(QPolygonF(points))
                continue
            polygon = ring_item.polygon()
            matched = False
            for point in polygon:
                for atom_point in atom_points:
                    if math.hypot(point.x() - atom_point.x(), point.y() - atom_point.y()) <= tol:
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                continue
            rotated = QPolygonF()
            for point in polygon:
                dx = point.x() - center.x()
                dy = point.y() - center.y()
                rx = center.x() + dx * cos_a - dy * sin_a
                ry = center.y() + dx * sin_a + dy * cos_a
                rotated.append(QPointF(rx, ry))
            ring_item.setPolygon(rotated)

    def _center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        xs = []
        ys = []
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            xs.append(atom.x)
            ys.append(atom.y)
        if not xs:
            return None
        return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))

    def _bounding_box_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        xs = []
        ys = []
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            xs.append(atom.x)
            ys.append(atom.y)
        if not xs:
            return None
        return QPointF((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)

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
        polygon = QPolygonF(points)
        ring_item = NoSelectPolygonItem(polygon)
        ring_item.setBrush(self.renderer.ring_fill_brush())
        ring_item.setPen(QPen(Qt.PenStyle.NoPen))
        ring_item.setData(0, "ring")
        ring_item.setData(2, list(atom_ids))
        self._make_selectable(ring_item)
        return ring_item

    def _bond_id_between(self, a_id: int, b_id: int, skip_bond_id: int | None = None) -> int | None:
        if a_id == b_id:
            return None
        bonds_a = self._atom_bond_ids.get(a_id)
        bonds_b = self._atom_bond_ids.get(b_id)
        if bonds_a is None or bonds_b is None:
            for bond_id, bond in enumerate(self.model.bonds):
                if skip_bond_id is not None and bond_id == skip_bond_id:
                    continue
                if bond is None:
                    continue
                if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                    return bond_id
            return None
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
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return bond_id
        return None

    def _bond_exists(self, a_id: int, b_id: int) -> bool:
        return self._bond_id_between(a_id, b_id) is not None

    def _atom_bond_order_sum(self, atom_id: int) -> int:
        total = 0
        for bond in self.model.bonds:
            if bond is None:
                continue
            if bond.a == atom_id or bond.b == atom_id:
                total += max(1, int(bond.order or 1))
        return total


    def add_benzene_template(self) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        self.add_benzene_ring(center)

    def add_cyclohexane_chair(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            points = self._cyclohexane_chair_points(center)
            atom_ids = [self.add_atom("C", point.x(), point.y()) for point in points]
            for i in range(6):
                self.add_bond(atom_ids[i], atom_ids[(i + 1) % 6])
            for i in range(6):
                bond_id = len(self.model.bonds) - 6 + i
                self._add_bond_graphics(bond_id)

        self._structure_build_service.run_recorded_build(_build)

    def add_cyclohexane_boat(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            points = self._cyclohexane_boat_points(center)
            atom_ids = [self.add_atom("C", point.x(), point.y()) for point in points]
            for i in range(6):
                self.add_bond(atom_ids[i], atom_ids[(i + 1) % 6])
            for i in range(6):
                bond_id = len(self.model.bonds) - 6 + i
                self._add_bond_graphics(bond_id)

        self._structure_build_service.run_recorded_build(_build)

    def add_cyclopropane(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_regular_ring_template(3))

    def add_cyclobutane(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_regular_ring_template(4))

    def add_cyclopentane(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_regular_ring_template(5))

    def _insert_session_state(self) -> InsertSessionState:
        return self._insert_controller._insert_session_state()

    def _apply_insert_session_state(self, state: InsertSessionState) -> None:
        self._insert_controller._apply_insert_session_state(state)

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        self._insert_controller.begin_ring_template_insert(ring_size, style)

    def add_naphthalene(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_fused_benzenes(2))

    def add_anthracene(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_fused_benzenes(3, mode="linear"))

    def add_phenanthrene(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_fused_benzenes(3, mode="angled"))

    def add_pyridine(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(6, ["C", "C", "C", "C", "C", "N"])
        )

    def add_pyrimidine(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(6, ["N", "C", "N", "C", "C", "C"])
        )

    def add_imidazole(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(5, ["C", "N", "C", "N", "C"])
        )

    def add_pyrrole(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(5, ["N", "C", "C", "C", "C"])
        )

    def add_furan(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])
        )

    def add_thiophene(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(5, ["S", "C", "C", "C", "C"])
        )

    def add_indole(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            merge = []
            self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
            five_center = QPointF(
                center.x() + self.renderer.style.bond_length_px * 1.1,
                center.y() + self.renderer.style.bond_length_px * 0.6,
            )
            elements = ["N", "C", "C", "C", "C"]
            self._add_ring_from_points(self._ring_points(five_center, 5), elements=elements, merge=merge)

        self._structure_build_service.run_recorded_build(_build)

    def add_quinoline(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            merge = []
            self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
            other_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.5, center.y())
            elements = ["N", "C", "C", "C", "C", "C"]
            self._add_ring_from_points(self._ring_points(other_center, 6), elements=elements, merge=merge)

        self._structure_build_service.run_recorded_build(_build)

    def add_isoquinoline(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            merge = []
            self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
            other_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.5, center.y())
            elements = ["C", "C", "C", "C", "N", "C"]
            self._add_ring_from_points(self._ring_points(other_center, 6), elements=elements, merge=merge)

        self._structure_build_service.run_recorded_build(_build)

    def add_benzimidazole(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            merge = []
            self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
            five_center = QPointF(
                center.x() + self.renderer.style.bond_length_px * 1.1,
                center.y() + self.renderer.style.bond_length_px * 0.6,
            )
            elements = ["N", "C", "N", "C", "C"]
            self._add_ring_from_points(self._ring_points(five_center, 5), elements=elements, merge=merge)

        self._structure_build_service.run_recorded_build(_build)

    def add_phenyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            atom_ids = self._add_ring_from_points(self._ring_points(center, 6))
            attach = QPointF(center.x() - self.renderer.style.bond_length_px * 2.0, center.y())
            attach_id = self.add_atom("C", attach.x(), attach.y())
            self.add_bond(atom_ids[0], attach_id)
            self._add_bond_graphics(len(self.model.bonds) - 1)

        self._structure_build_service.run_recorded_build(_build)

    def add_benzyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            atom_ids = self._add_ring_from_points(self._ring_points(center, 6))
            start = QPointF(center.x() - self.renderer.style.bond_length_px * 2.0, center.y())
            mid = QPointF(start.x() - self.renderer.style.bond_length_px, start.y())
            chain_ids = self._add_linear_chain([start, mid], ["C", "C"], [1])
            self.add_bond(atom_ids[0], chain_ids[0])
            self._add_bond_graphics(len(self.model.bonds) - 1)

        self._structure_build_service.run_recorded_build(_build)

    def add_vinyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            p1 = QPointF(center.x() - self.renderer.style.bond_length_px, center.y())
            p2 = QPointF(center.x(), center.y())
            self._add_linear_chain([p1, p2], ["C", "C"], [2])

        self._structure_build_service.run_recorded_build(_build)

    def add_allyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            points = [
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
            ]
            self._add_linear_chain(points, ["C", "C", "C"], [2, 1])

        self._structure_build_service.run_recorded_build(_build)

    def add_carboxyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            c = QPointF(center.x(), center.y())
            o1 = QPointF(center.x() + step, center.y() - step * 0.6)
            o2 = QPointF(center.x() + step, center.y() + step * 0.6)
            self._add_linear_chain([c, o1], ["C", "O"], [2])
            self._add_linear_chain([c, o2], ["C", "O"], [1])

        self._structure_build_service.run_recorded_build(_build)

    def add_nitro(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            n = QPointF(center.x(), center.y())
            o1 = QPointF(center.x() + step, center.y() - step * 0.6)
            o2 = QPointF(center.x() + step, center.y() + step * 0.6)
            self._add_linear_chain([n, o1], ["N", "O"], [2])
            self._add_linear_chain([n, o2], ["N", "O"], [2])

        self._structure_build_service.run_recorded_build(_build)

    def add_sulfonyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            s = QPointF(center.x(), center.y())
            o1 = QPointF(center.x() + step, center.y() - step * 0.7)
            o2 = QPointF(center.x() + step, center.y() + step * 0.7)
            self._add_linear_chain([s, o1], ["S", "O"], [2])
            self._add_linear_chain([s, o2], ["S", "O"], [2])

        self._structure_build_service.run_recorded_build(_build)

    def add_carbonyl(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            c = QPointF(center.x(), center.y())
            o = QPointF(center.x() + step, center.y())
            self._add_linear_chain([c, o], ["C", "O"], [2])

        self._structure_build_service.run_recorded_build(_build)

    def add_tbu(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            c = QPointF(center.x(), center.y())
            branches = [
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y() - step),
            ]
            for b in branches:
                self._add_linear_chain([c, b], ["C", "C"], [1])

        self._structure_build_service.run_recorded_build(_build)

    def add_ipr(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            c = QPointF(center.x(), center.y())
            b1 = QPointF(center.x() + step, center.y())
            b2 = QPointF(center.x(), center.y() - step)
            self._add_linear_chain([c, b1], ["C", "C"], [1])
            self._add_linear_chain([c, b2], ["C", "C"], [1])

        self._structure_build_service.run_recorded_build(_build)

    def add_me(self) -> None:
        def _build() -> None:
            p = self._structure_build_service.viewport_center()
            self._add_linear_chain([p], ["C"], [])

        self._structure_build_service.run_recorded_build(_build)

    def add_et(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            p1 = QPointF(center.x() - step / 2, center.y())
            p2 = QPointF(center.x() + step / 2, center.y())
            self._add_linear_chain([p1, p2], ["C", "C"], [1])

        self._structure_build_service.run_recorded_build(_build)

    def add_pyranose(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(6, ["O", "C", "C", "C", "C", "C"])
        )

    def add_furanose(self) -> None:
        self._structure_build_service.run_recorded_build(
            lambda: self._add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])
        )

    def add_peptide_2(self) -> None:
        def _build() -> None:
            center = self._structure_build_service.viewport_center()
            step = self.renderer.style.bond_length_px
            points = [
                QPointF(center.x() - step * 2, center.y()),
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step, center.y()),
                QPointF(center.x() + step * 2, center.y()),
                QPointF(center.x() + step * 3, center.y()),
            ]
            elements = ["N", "C", "C", "N", "C", "C"]
            chain_ids = self._add_linear_chain(points, elements, [1, 1, 1, 1, 1])
            carbonyl_1 = chain_ids[1]
            carbonyl_2 = chain_ids[4]
            o1 = QPointF(points[1].x(), points[1].y() - step * 0.8)
            o2 = QPointF(points[4].x(), points[4].y() - step * 0.8)
            o1_id = self.add_atom("O", o1.x(), o1.y())
            o2_id = self.add_atom("O", o2.x(), o2.y())
            self.add_bond(carbonyl_1, o1_id, 2)
            self.add_bond(carbonyl_2, o2_id, 2)
            self._add_bond_graphics(len(self.model.bonds) - 2)
            self._add_bond_graphics(len(self.model.bonds) - 1)
            self._atom_label_service.add_or_update_atom_label(o1_id, "O", record=False)
            self._atom_label_service.add_or_update_atom_label(o2_id, "O", record=False)

        self._structure_build_service.run_recorded_build(_build)

    def add_crown_12_4(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_crown_ether(12, 4))

    def add_crown_15_5(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_crown_ether(15, 5))

    def add_crown_18_6(self) -> None:
        self._structure_build_service.run_recorded_build(lambda: self._add_crown_ether(18, 6))

    def _add_regular_ring_template(self, n: int) -> None:
        self._structure_build_service.add_regular_ring_template(n)

    def _add_hetero_ring_template(self, n: int, elements: list[str]) -> None:
        self._structure_build_service.add_hetero_ring_template(n, elements)

    def _add_fused_benzenes(self, count: int, mode: str = "linear") -> None:
        self._structure_build_service.add_fused_benzenes(count, mode=mode)

    def _add_crown_ether(self, atoms: int, oxygens: int) -> None:
        self._structure_build_service.add_crown_ether(atoms, oxygens)

    def _cyclohexane_chair_points(self, center: QPointF) -> list[QPointF]:
        points = cyclohexane_chair_points(
            (center.x(), center.y()),
            self.renderer.style.bond_length_px,
        )
        return [QPointF(x, y) for x, y in points]

    def _cyclohexane_boat_points(self, center: QPointF) -> list[QPointF]:
        points = cyclohexane_boat_points(
            (center.x(), center.y()),
            self.renderer.style.bond_length_px,
        )
        return [QPointF(x, y) for x, y in points]

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
        return [QPointF(x, y) for x, y in scaled]

    def _ring_points(self, center: QPointF, n: int, radius: float | None = None):
        points = ring_points(
            (center.x(), center.y()),
            n,
            radius or self.renderer.style.bond_length_px,
        )
        return [QPointF(x, y) for x, y in points]

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
        result = compute_template_points_for_bond(
            [(point.x(), point.y()) for point in points_local],
            bond_id,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            center_hint=(center_hint.x(), center_hint.y()) if center_hint is not None else None,
            occupied_polygon=self._ring_polygon_points_for_bond(bond_id),
        )
        if result is None:
            return None
        points, merge = result
        return [QPointF(x, y) for x, y in points], merge

    def _regular_ring_points_for_bond(
        self,
        n: int,
        bond_id: int,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        result = compute_regular_ring_points_for_bond(
            n,
            bond_id,
            atoms=self.model.atoms,
            bonds=self.model.bonds,
            center_hint=(center_hint.x(), center_hint.y()) if center_hint is not None else None,
            occupied_polygon=self._ring_polygon_points_for_bond(bond_id),
        )
        if result is None:
            return None
        points, merge = result
        return [QPointF(x, y) for x, y in points], merge

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
        if atom_id in self.atom_dots:
            return
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        pick_radius = self._atom_pick_radius()
        dot = AtomDotItem(
            -radius,
            -radius,
            radius * 2.0,
            radius * 2.0,
            hit_padding=max(0.0, pick_radius - radius),
        )
        dot.setBrush(self._implicit_carbon_dot_brush())
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setZValue(3)
        dot.setData(0, "atom")
        dot.setData(1, atom_id)
        self._make_selectable(dot)
        dot.setPos(atom.x, atom.y)
        self.scene().addItem(dot)
        self.atom_dots[atom_id] = dot

    def _remove_carbon_dot(self, atom_id: int) -> None:
        dot = self.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.scene().removeItem(dot)

    def _position_label(self, item: QGraphicsTextItem, x: float, y: float) -> None:
        rect = item.boundingRect()
        offset = self.renderer.style.atom_label_offset_px
        item.setPos(x - rect.center().x() + offset, y - rect.center().y() - offset)

    def _restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        replacement_item = self._atom_item_for_id(atom_id)
        if was_selected and replacement_item is not None and replacement_item is not previous_item:
            replacement_item.setSelected(True)
        if refresh_hover:
            self._refresh_hover_from_cursor()

    def apply_color_to_item(self, item, color: QColor) -> None:
        if item is None or not color.isValid():
            return
        try:
            if item.scene() is not self.scene():
                return
        except RuntimeError:
            return
        kind = item.data(0)
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int) and 0 <= bond_id < len(self.model.bonds):
                bond = self.model.bonds[bond_id]
                if bond is None:
                    return
                before_state = self._bond_state_dict(bond)
                bond.color = color.name()
                for bond_item in self.bond_items.get(bond_id, []):
                    self._apply_color_to_bond_item(bond_item, color)
                after_state = self._bond_state_dict(bond)
                if before_state != after_state:
                    command = UpdateBondCommand(
                        bond_id=bond_id,
                        before_state=before_state,
                        after_state=after_state,
                        before_smiles_input=self.last_smiles_input,
                        after_smiles_input=self.last_smiles_input,
                    )
                    self._push_command(command)
        elif kind == "atom":
            atom_id = item.data(1)
            if isinstance(item, QGraphicsTextItem):
                item.setDefaultTextColor(color)
            elif isinstance(item, AtomDotItem):
                item.setBrush(self._implicit_carbon_dot_brush())
            elif isinstance(item, QGraphicsEllipseItem):
                item.setBrush(color)
            if atom_id in self.model.atoms:
                before_color = self.model.atoms[atom_id].color
                self.model.atoms[atom_id].color = color.name()
                label_item = self.atom_items.get(atom_id)
                if label_item is not None and label_item is not item:
                    label_item.setDefaultTextColor(color)
                dot_item = self.atom_dots.get(atom_id)
                if dot_item is not None and dot_item is not item:
                    dot_item.setBrush(self._implicit_carbon_dot_brush())
                after_color = self.model.atoms[atom_id].color
                if before_color != after_color:
                    command = UpdateAtomColorCommand(
                        atom_id=atom_id,
                        before_color=before_color,
                        after_color=after_color,
                    )
                    self._push_command(command)
        elif kind == "ring":
            ring_atom_ids = item.data(2)
            if not isinstance(ring_atom_ids, list):
                return
            atom_ids = {
                atom_id
                for atom_id in ring_atom_ids
                if isinstance(atom_id, int) and atom_id in self.model.atoms
            }
            if not atom_ids:
                return
            bond_ids, _ = self.bond_sets_for_atoms(atom_ids)
            for atom_id in sorted(atom_ids):
                atom_item = self.atom_items.get(atom_id) or self.atom_dots.get(atom_id)
                if atom_item is not None:
                    self.apply_color_to_item(atom_item, color)
            for bond_id in sorted(bond_ids):
                bond_items = self.bond_items.get(bond_id, [])
                if bond_items:
                    self.apply_color_to_item(bond_items[0], color)

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if item is None or not color.isValid():
            return
        if item.data(0) != "ring":
            return
        before_state = self._ring_state_dict(item)
        fill = QColor(color)
        fill.setAlphaF(max(0.0, min(1.0, float(alpha))))
        item.setBrush(fill)
        after_state = self._ring_state_dict(item)
        if before_state != after_state:
            command = UpdateSceneItemCommand(item, before_state, after_state)
            self._push_command(command)

    def clear_scene(self) -> None:
        self.scene().clear()
        self.hover_items = []
        self.hover_atom_id = None
        self.hover_bond_id = None
        self.model = MoleculeModel()
        self._mark_spatial_index_dirty()
        self.atom_coords_3d = {}
        self._projection_center_3d = None
        self._projection_anchor_2d = None
        self._rotation_start_projection_center_3d = None
        self._rotation_start_projection_anchor_2d = None
        self._rotation_axis_bond_id = None
        self._rotation_axis_atoms = None
        self._rotation_total_angle = 0.0
        self._rotation_mode = None
        self._rotation_free_angle_x = 0.0
        self._rotation_free_angle_y = 0.0
        self._rotation_start_positions = {}
        self._rotation_start_coords_3d = {}
        self._rotation_coord_atom_ids = set()
        self.atom_items = {}
        self.atom_dots = {}
        self._atom_neighbors = {}
        self._atom_bond_ids = {}
        self._graph_version = 0
        self._selection_component_cache_signature = None
        self._selection_component_cache = []
        self.bond_items = {}
        self.ring_items = []
        self.note_items = []
        self.mark_items = []
        self.arrow_items = []
        self.ts_bracket_items = []
        self.orbital_items = []
        self._marks_by_atom = {}
        self._smiles_preview_model = None
        self._clear_template_preview()
        self._clear_benzene_preview()
        self._clear_smiles_preview()
        self._apply_insert_session_state(clear_insert_session())

    def load_smiles(self, smiles: str) -> None:
        self._insert_controller.load_smiles(smiles)

    def begin_smiles_insert(self, smiles: str) -> None:
        self._insert_controller.begin_smiles_insert(smiles)

    def _cancel_smiles_insert(self) -> None:
        self._insert_controller._cancel_smiles_insert()

    def _commit_smiles_insert(self, pos: QPointF) -> None:
        self._insert_controller._commit_smiles_insert(pos)

    def _clear_smiles_preview(self) -> None:
        self._insert_controller._clear_smiles_preview()

    def _smiles_preview_snapshot(self):
        return self._insert_controller._smiles_preview_snapshot()

    def _render_smiles_preview(self, pos: QPointF) -> None:
        self._insert_controller._render_smiles_preview(pos)

    def _cancel_template_insert(self) -> None:
        self._insert_controller._cancel_template_insert()

    def _template_insert_request(self, pos: QPointF) -> TemplateInsertRequest | None:
        return self._insert_controller._template_insert_request(pos)

    def _template_point_resolvers(self) -> TemplatePointResolvers:
        return self._insert_controller._template_point_resolvers()

    def _resolve_ring_points_for_template(
        self,
        center: tuple[float, float],
        n: int,
        radius: float | None,
    ) -> list[tuple[float, float]]:
        return self._insert_controller._resolve_ring_points_for_template(center, n, radius)

    def _resolve_regular_ring_points_for_template_bond(
        self,
        n: int,
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._insert_controller._resolve_regular_ring_points_for_template_bond(n, bond_id, center)

    def _resolve_chair_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._insert_controller._resolve_chair_points_for_template(center)

    def _resolve_boat_points_for_template(self, center: tuple[float, float]) -> list[tuple[float, float]]:
        return self._insert_controller._resolve_boat_points_for_template(center)

    def _resolve_template_points_for_template_bond(
        self,
        points_local: list[tuple[float, float]],
        bond_id: int,
        center: tuple[float, float],
    ) -> list[tuple[float, float]] | None:
        return self._insert_controller._resolve_template_points_for_template_bond(points_local, bond_id, center)

    def _template_points_from_pairs(
        self,
        points: list[tuple[float, float]] | None,
    ) -> list[QPointF] | None:
        return InsertController._template_points_from_pairs(points)

    def _bond_merge_seed(self, bond_id: int | None) -> list[tuple[int, float, float]]:
        return self._insert_controller._bond_merge_seed(bond_id)

    def _commit_template_insert(self, pos: QPointF) -> None:
        self._insert_controller._commit_template_insert(pos)

    def _clear_template_preview(self) -> None:
        self._insert_controller._clear_template_preview()

    def _render_template_preview(self, pos: QPointF) -> None:
        self._insert_controller._render_template_preview(pos)

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
        for bond_id in self._atom_bond_ids.get(atom_id, ()):
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
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        if target is None:
            return nx, ny
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        to_tx = target.x() - mid_x
        to_ty = target.y() - mid_y
        if nx * to_tx + ny * to_ty < 0:
            nx = -nx
            ny = -ny
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
        dx = bx - ax
        dy = by - ay
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        nx = -dy / length
        ny = dx / length
        if target is not None:
            mid_x = (ax + bx) * 0.5
            mid_y = (ay + by) * 0.5
            target_x, target_y = self._project_point_3d(target)
            to_tx = target_x - mid_x
            to_ty = target_y - mid_y
            if nx * to_tx + ny * to_ty < 0:
                nx = -nx
                ny = -ny
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
