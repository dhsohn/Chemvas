import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QEvent, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QBrush,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QKeySequence,
    QNativeGestureEvent,
    QTextBlockFormat,
    QTextCursor,
    QTransform,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QMessageBox,
    QStyle,
    QStyleOptionGraphicsItem,
)

from core.model import Atom, Bond, MoleculeModel
from core.renderer import Renderer
from core.rdkit_adapter import RDKitAdapter
from core.tools import ToolController


class NoteItem(QGraphicsTextItem):
    def __init__(self, canvas) -> None:
        super().__init__()
        self._canvas = canvas
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._last_text = ""

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if self.toPlainText().strip():
            if self.toPlainText() != self._last_text:
                self._last_text = self.toPlainText()
                self._canvas._push_history()
            return
        if self in self._canvas.selected_notes:
            self._canvas.selected_notes.remove(self)
            self._canvas._update_note_selection_box(self)
        scene = self.scene()
        if scene is not None:
            scene.removeItem(self)


class NoSelectLineItem(QGraphicsLineItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectPathItem(QGraphicsPathItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectPolygonItem(QGraphicsPolygonItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectRectItem(QGraphicsRectItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectEllipseItem(QGraphicsEllipseItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectTextItem(QGraphicsTextItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class CanvasView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setScene(QGraphicsScene(self))
        self.scene().selectionChanged.connect(self._update_selection_outline)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#ffffff"))
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
        self.atom_symbol = "C"
        self.bond_items: dict[int, list] = {}
        self.ring_items: list[QGraphicsPolygonItem] = []
        self.active_bond_order = 1
        self.active_bond_style = "single"
        self.snap_angle_step = 30
        self._base_transform = QTransform()
        self._perspective_shear = 0.0
        self._perspective_scale_y = 1.0
        self._selection_rotation_step = 0.0
        self._rotation_group = None
        self.atom_coords_3d: dict[int, tuple[float, float, float]] = {}
        self.atom_plane_normals: dict[int, tuple[float, float, float]] = {}
        self._rotation_base_coords: dict[int, tuple[float, float, float]] = {}
        self._rotation_total_angles: tuple[float, float] | None = None
        self._rotation_plane_normal: tuple[float, float, float] | None = None
        self.rotation_atom_ids: set[int] = set()
        self.rotation_center_3d: tuple[float, float, float] | None = None
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
        self._selection_info_cache = ("", "")
        self._orbital_snap_enabled = False
        self._orbital_snap_step = 15
        self.last_smiles_input: str | None = None
        self.info_item: QGraphicsTextItem | None = None
        self.info_alignment = "left"
        self.info_format = "{name_block} | {formula_block} | {mw_block}"
        self.info_auto_enabled = False
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
        self.hover_items: list = []
        self.hover_atom_id: int | None = None
        self.hover_bond_id: int | None = None
        self._hover_preview_style: str | None = None
        self._selection_info_callback = None
        self._rotation_selection_ids = None
        self.selection_outlines: list[QGraphicsRectItem] = []
        self._smiles_insert_active = False
        self._smiles_preview_model: MoleculeModel | None = None
        self._smiles_preview_items: list[QGraphicsItem] = []
        self._smiles_preview_center: QPointF | None = None
        self._smiles_preview_smiles: str | None = None
        self._template_insert_active = False
        self._template_ring_size: int | None = None
        self._template_ring_style: str | None = None
        self._template_preview_items: list[QGraphicsItem] = []
        self._benzene_preview_items: list[QGraphicsItem] = []
        self._history: list[dict] = []
        self._redo_stack: list[dict] = []
        self._history_enabled = True
        self._history_limit = 100
        self.tools = ToolController(self)
        self.tools.set_active("bond")
        self._push_history()

    def keyPressEvent(self, event) -> None:
        focus_item = self.scene().focusItem()
        if isinstance(focus_item, QGraphicsTextItem):
            if focus_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction:
                super().keyPressEvent(event)
                return
        if event.key() == Qt.Key.Key_Escape:
            if self._template_insert_active:
                self._cancel_template_insert()
                event.accept()
                return
            if self._smiles_insert_active:
                self._cancel_smiles_insert()
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redo()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            did_delete = False
            if self.scene().selectedItems():
                self.delete_selected_items()
            elif self.hover_atom_id is not None:
                self.delete_atom(self.hover_atom_id, record=False)
                did_delete = True
            elif self.hover_bond_id is not None:
                bond_id = self.hover_bond_id
                self._clear_hover_highlight()
                if bond_id is not None:
                    self.delete_bond(bond_id, record=False)
                    did_delete = True
            else:
                if self.hover_bond_id is not None and self.hover_atom_id is None:
                    bond = self.model.bonds[self.hover_bond_id]
                    if bond is not None:
                        ring_item = self._ring_for_bond(self.hover_bond_id)
                        if ring_item is not None:
                            self.delete_ring(ring_item, record=False)
                            did_delete = True
            if did_delete:
                self._push_history()
            event.accept()
            return
        super().keyPressEvent(event)

    def delete_selected_items(self) -> None:
        items = self.scene().selectedItems()
        if not items:
            return
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        ring_items: list[QGraphicsPolygonItem] = []
        note_items: list[QGraphicsTextItem] = []
        arrow_items: list[QGraphicsItem] = []
        orbital_items: list[QGraphicsItem] = []
        other_items: list[QGraphicsItem] = []
        for item in items:
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
                if isinstance(item, QGraphicsPolygonItem):
                    ring_items.append(item)
            elif kind == "note":
                if isinstance(item, QGraphicsTextItem):
                    note_items.append(item)
            elif kind in {
                "arrow",
                "equilibrium",
                "resonance",
                "curved_single",
                "curved_double",
                "inhibit",
                "dotted",
            }:
                arrow_items.append(item)
            elif kind == "orbital":
                orbital_items.append(item)
            elif kind in {"handle", "note_box", "note_select"}:
                continue
            else:
                other_items.append(item)

        for bond_id in sorted(bond_ids, reverse=True):
            self.delete_bond(bond_id, record=False)
        for atom_id in atom_ids:
            self.delete_atom(atom_id, record=False)
        for ring_item in ring_items:
            self.delete_ring(ring_item, record=False)
        for item in note_items:
            if item in self.selected_notes:
                self.selected_notes.remove(item)
            self.scene().removeItem(item)
        if orbital_items or arrow_items:
            self.clear_handles()
        for item in orbital_items + arrow_items + other_items:
            self.scene().removeItem(item)
        self._push_history()

    def _snapshot_state(self) -> dict:
        atoms = {
            atom_id: {
                "element": atom.element,
                "x": atom.x,
                "y": atom.y,
                "color": atom.color,
            }
            for atom_id, atom in self.model.atoms.items()
        }
        bonds = []
        for bond in self.model.bonds:
            if bond is None:
                bonds.append(None)
            else:
                bonds.append(
                    {
                        "a": bond.a,
                        "b": bond.b,
                        "order": bond.order,
                        "style": bond.style,
                        "color": bond.color,
                    }
                )
        ring_fills = []
        for ring_item in self.ring_items:
            polygon = ring_item.polygon()
            points = [(point.x(), point.y()) for point in polygon]
            brush = ring_item.brush()
            color = brush.color().name() if brush.style() != Qt.BrushStyle.NoBrush else None
            alpha = brush.color().alphaF() if brush.style() != Qt.BrushStyle.NoBrush else 0.0
            ring_fills.append(
                {
                    "points": points,
                    "atom_ids": ring_item.data(2),
                    "color": color,
                    "alpha": alpha,
                }
            )
        notes = []
        arrows = []
        orbitals = []
        for item in self.scene().items():
            kind = item.data(0)
            if kind == "note" and isinstance(item, QGraphicsTextItem):
                notes.append(
                    {
                        "text": item.toPlainText(),
                        "x": item.pos().x(),
                        "y": item.pos().y(),
                    }
                )
            elif kind in {
                "arrow",
                "equilibrium",
                "resonance",
                "curved_single",
                "curved_double",
                "inhibit",
                "dotted",
            } and isinstance(item, QGraphicsPathItem):
                data = item.data(2) or {}
                start = data.get("start")
                end = data.get("end")
                control = data.get("control")
                double = data.get("double", False)
                arrows.append(
                    {
                        "kind": kind,
                        "start": (start.x(), start.y()) if isinstance(start, QPointF) else None,
                        "end": (end.x(), end.y()) if isinstance(end, QPointF) else None,
                        "control": (control.x(), control.y()) if isinstance(control, QPointF) else None,
                        "double": bool(double),
                    }
                )
            elif kind == "orbital" and isinstance(item, QGraphicsItemGroup):
                data = item.data(1) or {}
                center = data.get("center")
                meta = item.data(2) or {}
                orbitals.append(
                    {
                        "kind": meta.get("kind", "s"),
                        "center": (center.x(), center.y()) if isinstance(center, QPointF) else None,
                        "scale": item.scale(),
                        "rotation": item.rotation(),
                    }
                )
        settings = {
            "bond_length_px": self.renderer.style.bond_length_px,
            "arrow_line_width": self.arrow_line_width,
            "arrow_head_scale": self.arrow_head_scale,
            "orbital_phase_enabled": self.orbital_phase_enabled,
            "text_font_size": self.text_font_size,
            "text_font_weight": self.text_font_weight,
            "text_italic": self.text_italic,
        }
        return {
            "model": {
                "atoms": atoms,
                "bonds": bonds,
                "next_atom_id": self.model.next_atom_id,
            },
            "ring_fills": ring_fills,
            "notes": notes,
            "arrows": arrows,
            "orbitals": orbitals,
            "settings": settings,
            "last_smiles_input": self.last_smiles_input,
        }

    def _restore_state(self, state: dict) -> None:
        self._history_enabled = False
        try:
            self.clear_scene()
            settings = state.get("settings", {})
            bond_length = settings.get("bond_length_px", self.renderer.style.bond_length_px)
            self.renderer.set_bond_length(bond_length)
            self.arrow_line_width = settings.get("arrow_line_width", self.arrow_line_width)
            self.arrow_head_scale = settings.get("arrow_head_scale", self.arrow_head_scale)
            self.orbital_phase_enabled = settings.get("orbital_phase_enabled", self.orbital_phase_enabled)
            self.text_font_size = settings.get("text_font_size", self.text_font_size)
            self.text_font_weight = settings.get("text_font_weight", self.text_font_weight)
            self.text_italic = settings.get("text_italic", self.text_italic)
            self.last_smiles_input = state.get("last_smiles_input")

            model_state = state.get("model", {})
            atoms_state = model_state.get("atoms", {})
            bonds_state = model_state.get("bonds", [])
            model = MoleculeModel()
            model.atoms = {
                int(atom_id): Atom(
                    element=atom_data.get("element", "C"),
                    x=atom_data.get("x", 0.0),
                    y=atom_data.get("y", 0.0),
                    color=atom_data.get("color", "#000000"),
                )
                for atom_id, atom_data in atoms_state.items()
            }
            bonds: list[Bond | None] = []
            for bond_data in bonds_state:
                if bond_data is None:
                    bonds.append(None)
                else:
                    bonds.append(
                        Bond(
                            a=bond_data.get("a", 0),
                            b=bond_data.get("b", 0),
                            order=bond_data.get("order", 1),
                            style=bond_data.get("style", "single"),
                            color=bond_data.get("color", "#000000"),
                        )
                    )
            model.bonds = bonds
            model.next_atom_id = model_state.get("next_atom_id", len(model.atoms))
            self.model = model

            for ring_state in state.get("ring_fills", []):
                points = [QPointF(x, y) for x, y in ring_state.get("points", [])]
                if len(points) < 3:
                    continue
                ring_item = NoSelectPolygonItem(QPolygonF(points))
                color = ring_state.get("color")
                alpha = ring_state.get("alpha", 0.0)
                if color:
                    fill = QColor(color)
                    fill.setAlphaF(alpha)
                    ring_item.setBrush(QBrush(fill))
                else:
                    ring_item.setBrush(self.renderer.ring_fill_brush())
                ring_item.setPen(QPen(Qt.PenStyle.NoPen))
                ring_item.setData(0, "ring")
                ring_item.setData(2, ring_state.get("atom_ids"))
                self._make_selectable(ring_item)
                self.scene().addItem(ring_item)
                self.ring_items.append(ring_item)

            self._render_model()

            for note_state in state.get("notes", []):
                item = self.add_text_note(QPointF(note_state["x"], note_state["y"]), note_state["text"])
                item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

            for arrow_state in state.get("arrows", []):
                start = arrow_state.get("start")
                end = arrow_state.get("end")
                if start is None or end is None:
                    continue
                item = self.add_arrow(QPointF(*start), QPointF(*end), arrow_state.get("kind", "arrow"))
                control = arrow_state.get("control")
                if control and arrow_state.get("kind") in {"curved_single", "curved_double"}:
                    self._update_curved_control(item, QPointF(*control))

            for orbital_state in state.get("orbitals", []):
                center = orbital_state.get("center")
                if center is None:
                    continue
                kind = orbital_state.get("kind", "s")
                items = self._build_orbital_items(QPointF(*center), kind)
                group = self.scene().createItemGroup(items)
                group.setData(0, "orbital")
                group.setData(1, {"center": QPointF(*center), "base_handle_dist": self.renderer.style.bond_length_px * 0.8})
                group.setData(2, {"kind": kind})
                group.setTransformOriginPoint(QPointF(*center))
                group.setScale(orbital_state.get("scale", 1.0))
                group.setRotation(orbital_state.get("rotation", 0.0))
                self._make_selectable(group)

        finally:
            self._history_enabled = True

    def _push_history(self) -> None:
        if not self._history_enabled:
            return
        state = self._snapshot_state()
        self._history.append(state)
        if len(self._history) > self._history_limit:
            self._history.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if len(self._history) < 2:
            return
        self._redo_stack.append(self._history.pop())
        self._restore_state(self._history[-1])

    def redo(self) -> None:
        if not self._redo_stack:
            return
        state = self._redo_stack.pop()
        self._history.append(state)
        self._restore_state(state)

    def set_tool(self, tool_name: str) -> None:
        self.tools.set_active(tool_name)

    def scene_pos_from_event(self, event) -> QPointF:
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        return self.mapToScene(pos)

    def item_at_event(self, event):
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        for item in self.items(pos):
            if item.data(0) == "selection_outline":
                continue
            kind = item.data(0)
            if kind in {"note_box", "note_select"}:
                continue
            return item
        return None

    def bond_id_from_event(self, event) -> int | None:
        if self.hover_bond_id is not None:
            return self.hover_bond_id
        pos = self.scene_pos_from_event(event)
        return self._find_bond_near(pos, self.renderer.style.bond_length_px * 0.35)

    def set_bond_style(self, style: str, order: int) -> None:
        self.active_bond_style = style
        self.active_bond_order = order
        self.tools.set_active("bond")

    def set_arrow_type(self, arrow_type: str) -> None:
        self.active_arrow_type = arrow_type
        self.tools.set_active("arrow")

    def set_orbital_type(self, orbital_type: str) -> None:
        self.active_orbital_type = orbital_type
        self.tools.set_active("orbital")

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

    def set_info_alignment(self, alignment: str) -> None:
        return

    def set_info_format(self, fmt: str) -> None:
        return

    def get_info_format(self) -> str:
        return ""

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

    def set_bond_length(self, length_px: float) -> None:
        old_length = self.renderer.style.bond_length_px
        self.renderer.set_bond_length(length_px)
        if old_length <= 0 or not self.model.atoms:
            return
        scale = length_px / old_length
        if scale == 1.0:
            return
        self._rescale_model(scale)
        self._rebuild_graphics()
        self._push_history()

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

    def flip_horizontal(self) -> None:
        if not self.model.atoms:
            return
        xs = [atom.x for atom in self.model.atoms.values()]
        center_x = sum(xs) / len(xs)
        for atom in self.model.atoms.values():
            atom.x = center_x - (atom.x - center_x)
        for ring_item in self.ring_items:
            polygon = ring_item.polygon()
            flipped = QPolygonF()
            for point in polygon:
                x = center_x - (point.x() - center_x)
                flipped.append(QPointF(x, point.y()))
            ring_item.setPolygon(flipped)
        self._rebuild_graphics()
        self._push_history()

    def flip_vertical(self) -> None:
        if not self.model.atoms:
            return
        ys = [atom.y for atom in self.model.atoms.values()]
        center_y = sum(ys) / len(ys)
        for atom in self.model.atoms.values():
            atom.y = center_y - (atom.y - center_y)
        for ring_item in self.ring_items:
            polygon = ring_item.polygon()
            flipped = QPolygonF()
            for point in polygon:
                y = center_y - (point.y() - center_y)
                flipped.append(QPointF(point.x(), y))
            ring_item.setPolygon(flipped)
        self._rebuild_graphics()
        self._push_history()

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

    def update_info_label(self, force: bool = False) -> None:
        return

    def insert_info_label(self) -> None:
        return

    def _place_info_text(self, text: str, bounds) -> None:
        return

    def _build_info_text_and_bounds(self, model, smiles_hint: str | None, bounds_override=None):
        return "", (0.0, 0.0, 0.0, 0.0)

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
            elif kind == "ring" and hasattr(item, "polygon"):
                polygon = item.polygon()
                for atom_id, atom in self.model.atoms.items():
                    if polygon.containsPoint(QPointF(atom.x, atom.y), Qt.FillRule.WindingFill):
                        atom_ids.add(atom_id)
        return atom_ids, bond_ids

    def _build_submodel(self, atom_ids: set[int], bond_ids: set[int]):
        submodel = MoleculeModel()
        selected_atoms = set(atom_ids)
        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            selected_atoms.add(bond.a)
            selected_atoms.add(bond.b)

        id_map = {}
        for old_id in selected_atoms:
            atom = self.model.atoms.get(old_id)
            if atom is None:
                continue
            new_id = submodel.add_atom(atom.element, atom.x, atom.y)
            id_map[old_id] = new_id

        for bond_id in bond_ids:
            if not (0 <= bond_id < len(self.model.bonds)):
                continue
            bond = self.model.bonds[bond_id]
            if bond is None:
                continue
            if bond.a in id_map and bond.b in id_map:
                submodel.add_bond(id_map[bond.a], id_map[bond.b], bond.order)

        if not bond_ids:
            for bond in self.model.bonds:
                if bond is None:
                    continue
                if bond.a in id_map and bond.b in id_map:
                    submodel.add_bond(id_map[bond.a], id_map[bond.b], bond.order)

        bounds = self._bounds_for_atoms(selected_atoms)
        return submodel, bounds, id_map

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

    def add_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        item = NoteItem(self)
        item.setPlainText(text)
        item._last_text = text
        item.setData(0, "note")
        item.setPos(pos)
        self.scene().addItem(item)
        self._make_selectable(item)
        self._apply_note_style(item)
        return item

    def update_text_note(self, item: QGraphicsTextItem, text: str) -> None:
        item.setPlainText(text)
        self._apply_note_style(item)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        if item not in self.selected_notes:
            self.select_note(item, additive=False)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        item.setFocus(Qt.FocusReason.MouseFocusReason)
        self.scene().setFocusItem(item)
        cursor = item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def apply_text_style_to_selected(self) -> None:
        for item in self.selected_notes:
            self._apply_note_style(item)

    def _apply_note_style(self, item: QGraphicsTextItem) -> None:
        font = QFont(self.text_font_family, self.text_font_size)
        font.setWeight(self.text_font_weight)
        font.setItalic(self.text_italic)
        item.setFont(font)
        item.setDefaultTextColor(self.text_color)
        doc = item.document()
        option = doc.defaultTextOption()
        option.setAlignment(self.text_alignment)
        doc.setDefaultTextOption(option)
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        if hasattr(QTextBlockFormat, "LineHeightType") and hasattr(QTextBlockFormat.LineHeightType, "ProportionalHeight"):
            height_type = QTextBlockFormat.LineHeightType.ProportionalHeight
        else:
            height_type = QTextBlockFormat.LineHeightTypes.ProportionalHeight
            if hasattr(height_type, "value"):
                height_type = height_type.value
        block_format.setLineHeight(int(self.text_line_spacing * 100), height_type)
        cursor.mergeBlockFormat(block_format)
        self._update_note_box(item)
        self._update_note_selection_box(item)

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        if not additive:
            self.clear_note_selection()
        if item not in self.selected_notes:
            self.selected_notes.append(item)
        self._update_note_selection_box(item)

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        if item in self.selected_notes:
            self.selected_notes.remove(item)
        else:
            self.selected_notes.append(item)
        self._update_note_selection_box(item)

    def clear_note_selection(self) -> None:
        for note in list(self.selected_notes):
            self._update_note_selection_box(note)
        self.selected_notes = []

    def _update_note_box(self, item: QGraphicsTextItem) -> None:
        box = item.data(20)
        rect = item.boundingRect().adjusted(-self.note_padding, -self.note_padding, self.note_padding, self.note_padding)
        if not (self.note_box_enabled or self.note_border_enabled):
            if isinstance(box, QGraphicsRectItem):
                box.setVisible(False)
            return
        if not isinstance(box, QGraphicsRectItem):
            box = NoSelectRectItem(item)
            box.setData(0, "note_box")
            box.setZValue(-1)
            item.setData(20, box)
        box.setVisible(True)
        box.setRect(rect)
        if self.note_box_enabled:
            fill = QColor(self.note_box_color)
            fill.setAlphaF(self.note_box_alpha)
            box.setBrush(fill)
        else:
            box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if self.note_border_enabled:
            pen = QPen(self.note_border_color)
            pen.setWidthF(self.note_border_width)
            box.setPen(pen)
        else:
            box.setPen(Qt.PenStyle.NoPen)

    def _update_note_selection_box(self, item: QGraphicsTextItem) -> None:
        sel = item.data(21)
        rect = item.boundingRect().adjusted(-self.note_padding, -self.note_padding, self.note_padding, self.note_padding)
        selected = item in self.selected_notes
        if not selected:
            if isinstance(sel, QGraphicsRectItem):
                sel.setVisible(False)
            return
        if not isinstance(sel, QGraphicsRectItem):
            sel = NoSelectRectItem(item)
            sel.setData(0, "note_select")
            sel.setZValue(1)
            item.setData(21, sel)
        sel.setVisible(True)
        sel.setRect(rect)
        pen = QPen(self._selection_color)
        pen.setWidthF(self._selection_stroke_delta)
        pen.setStyle(Qt.PenStyle.DashLine)
        sel.setPen(pen)
        sel.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def _make_selectable(self, item) -> None:
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    def _update_selection_outline(self) -> None:
        if self._suspend_selection_outline:
            return
        items = self.scene().selectedItems()
        if not items:
            for outline in self.selection_outlines:
                self.scene().removeItem(outline)
            self.selection_outlines = []
            self._emit_selection_info()
            return
        items = [
            item
            for item in items
            if item.data(0) not in {"handle", "note_box", "note_select", "selection_outline"}
        ]
        if not items:
            return
        atom_ids, bond_ids = self._selected_ids()
        for bond_id in bond_ids:
            if 0 <= bond_id < len(self.model.bonds):
                bond = self.model.bonds[bond_id]
                if bond is not None:
                    atom_ids.add(bond.a)
                    atom_ids.add(bond.b)
        rects: list[QRectF] = []
        if atom_ids:
            bonded_atoms: set[int] = set()
            for bond in self.model.bonds:
                if bond is None:
                    continue
                bonded_atoms.add(bond.a)
                bonded_atoms.add(bond.b)
            for component in self._connected_components(atom_ids):
                include_labels = not any(atom_id in bonded_atoms for atom_id in component)
                bounds = self._bounds_for_atoms(component, include_labels=include_labels)
                if bounds is None:
                    continue
                min_x, min_y, max_x, max_y = bounds
                rects.append(QRectF(min_x, min_y, max_x - min_x, max_y - min_y))
        non_atom_items = [
            item
            for item in items
            if item.data(0) not in {"atom", "bond", "ring"}
        ]
        for item in non_atom_items:
            rects.append(item.sceneBoundingRect())

        for outline in self.selection_outlines:
            self.scene().removeItem(outline)
        self.selection_outlines = []

        pad = self.renderer.style.bond_length_px * 0.1
        for rect in rects:
            rect = rect.adjusted(-pad, -pad, pad, pad)
            outline = NoSelectRectItem()
            outline.setData(0, "selection_outline")
            outline.setZValue(20)
            pen = QPen(QColor("#5eb7ff"))
            pen.setWidthF(1.2)
            pen.setStyle(Qt.PenStyle.DashLine)
            outline.setPen(pen)
            outline.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            outline.setRect(rect)
            self.scene().addItem(outline)
            self.selection_outlines.append(outline)
        self._emit_selection_info()

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        if not self.selection_outlines:
            return
        for outline in self.selection_outlines:
            outline.moveBy(dx, dy)

    def suspend_selection_outline(self, suspend: bool) -> None:
        self._suspend_selection_outline = bool(suspend)

    def _connected_components(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        remaining = set(atom_ids)
        components = []
        adjacency: dict[int, set[int]] = {atom_id: set() for atom_id in atom_ids}
        for bond in self.model.bonds:
            if bond is None:
                continue
            if bond.a in atom_ids and bond.b in atom_ids:
                adjacency[bond.a].add(bond.b)
                adjacency[bond.b].add(bond.a)
        while remaining:
            start = remaining.pop()
            stack = [start]
            comp = {start}
            while stack:
                current = stack.pop()
                for neighbor in adjacency.get(current, ()):
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        comp.add(neighbor)
                        stack.append(neighbor)
            components.append(comp)
        return components

    def set_selection_info_callback(self, callback) -> None:
        self._selection_info_callback = callback

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
            atom_ids, bond_ids = self._selected_ids()
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
        for item in self.hover_items:
            try:
                if item.scene() is self.scene():
                    self.scene().removeItem(item)
            except RuntimeError:
                pass
        self.hover_items = []
        self.hover_atom_id = None
        self.hover_bond_id = None
        self._hover_preview_style = None

    def _update_hover_highlight(self, pos: QPointF) -> None:
        if not self.model.atoms:
            if self.tools.active is not None and self.tools.active.name == "bond":
                preview_style = self._bond_preview_signature()
                if preview_style is None:
                    self._clear_hover_highlight()
                    return
                start = QPointF(pos.x(), pos.y())
                bond_len = self.renderer.style.bond_length_px
                end = QPointF(pos.x() + bond_len, pos.y())
                preview_key = f"{preview_style}:{round(start.x(), 1)}:{round(start.y(), 1)}"
                if preview_key == self._hover_preview_style:
                    return
                self._clear_hover_highlight()
                self._hover_preview_style = preview_key
                items = self._build_bond_preview_items(start, end)
                self._add_hover_preview_items(items)
                return
            self._clear_hover_highlight()
            return
        atom_id = self.model.find_atom_near(
            pos.x(),
            pos.y(),
            self.renderer.style.bond_length_px * 0.3,
        )
        if atom_id is not None:
            preview_style = self._bond_preview_signature()
            preview_key = None
            if preview_style is not None:
                atom = self.model.atoms[atom_id]
                end = self._bond_hover_endpoint(QPointF(atom.x, atom.y), pos)
                preview_key = f"{preview_style}:{round(end.x(), 1)}:{round(end.y(), 1)}"
            if atom_id == self.hover_atom_id and preview_key == self._hover_preview_style:
                return
            self._clear_hover_highlight()
            self.hover_atom_id = atom_id
            atom = self.model.atoms[atom_id]

            radius = self.renderer.style.bond_length_px * 0.25
            circle = QGraphicsEllipseItem(
                atom.x - radius,
                atom.y - radius,
                radius * 2.0,
                radius * 2.0,
            )
            pen = QPen(QColor("#9a9a9a"))
            pen.setWidthF(1.0)
            circle.setPen(pen)
            circle.setBrush(QColor(190, 190, 190, 80))
            circle.setZValue(5)
            self.scene().addItem(circle)
            self.hover_items.append(circle)
            if preview_style is not None:
                self._hover_preview_style = preview_key
                self._add_bond_tool_hover_preview(atom_id, pos)
            return
        if self.hover_atom_id is not None:
            self._clear_hover_highlight()

        bond_id = self._find_bond_near(pos, self.renderer.style.bond_length_px * 0.35)
        if bond_id is None:
            if self.hover_bond_id is not None:
                self._clear_hover_highlight()
            return
        preview_style = None
        if self.tools.active is not None and self.tools.active.name == "bond":
            if self.active_bond_style in {"wedge", "hash"}:
                preview_style = self.active_bond_style
        if bond_id == self.hover_bond_id and preview_style == self._hover_preview_style:
            return
        self._clear_hover_highlight()
        self.hover_bond_id = bond_id
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        a = self.model.atoms[bond.a]
        b = self.model.atoms[bond.b]
        mid = QPointF((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
        radius = self.renderer.style.bond_length_px * 0.22
        circle = QGraphicsEllipseItem(
            mid.x() - radius,
            mid.y() - radius,
            radius * 2.0,
            radius * 2.0,
        )
        pen = QPen(QColor("#9a9a9a"))
        pen.setWidthF(1.0)
        circle.setPen(pen)
        circle.setBrush(QColor(190, 190, 190, 80))
        circle.setZValue(4)
        self.scene().addItem(circle)
        self.hover_items.append(circle)
        if preview_style:
            self._add_bond_style_hover_preview(bond)

    def _find_bond_near(self, pos: QPointF, max_dist: float) -> int | None:
        nearest = None
        nearest_dist = max_dist
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            a = self.model.atoms[bond.a]
            b = self.model.atoms[bond.b]
            dist = self._distance_point_to_segment(pos, QPointF(a.x, a.y), QPointF(b.x, b.y))
            if dist <= nearest_dist:
                nearest = bond_id
                nearest_dist = dist
        return nearest

    def _add_bond_style_hover_preview(self, bond) -> None:
        if self.tools.active is None or self.tools.active.name != "bond":
            return
        style = self.active_bond_style
        if style not in {"wedge", "hash"}:
            return
        a = self.model.atoms.get(bond.a)
        b = self.model.atoms.get(bond.b)
        if a is None or b is None:
            return
        self._hover_preview_style = style
        items = self._build_bond_preview_items(
            QPointF(a.x, a.y),
            QPointF(b.x, b.y),
            bond.a,
            bond.b,
        )
        self._add_hover_preview_items(items)

    def _add_bond_tool_hover_preview(self, atom_id: int, pos: QPointF) -> None:
        if self.tools.active is None or self.tools.active.name != "bond":
            return
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        start = QPointF(atom.x, atom.y)
        end = self._bond_hover_endpoint(start, pos)
        items = self._build_bond_preview_items(start, end, atom_id, None)
        self._add_hover_preview_items(items)

    def _build_bond_preview_items(
        self,
        start: QPointF,
        end: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> list:
        style = self.active_bond_style
        if style == "wedge":
            return self._draw_wedge_bond(start.x(), start.y(), end.x(), end.y(), a_id, b_id)
        if style == "hash":
            return self._draw_hash_bond(start.x(), start.y(), end.x(), end.y(), a_id, b_id)
        if self.active_bond_order >= 2:
            return self._draw_parallel_bonds(
                start.x(),
                start.y(),
                end.x(),
                end.y(),
                self.active_bond_order,
                a_id,
                b_id,
            )
        line_item = NoSelectLineItem(start.x(), start.y(), end.x(), end.y())
        line_item.setPen(self.renderer.bond_pen())
        return [line_item]

    def _add_hover_preview_items(self, items: list) -> None:
        if not items:
            return
        preview_color = QColor(120, 120, 120, 140)
        for item in items:
            if hasattr(item, "pen"):
                pen = item.pen()
                pen.setColor(preview_color)
                item.setPen(pen)
            if hasattr(item, "brush") and item.brush().style() != Qt.BrushStyle.NoBrush:
                brush = item.brush()
                brush.setColor(preview_color)
                item.setBrush(brush)
            item.setOpacity(0.55)
            item.setZValue(4.5)
            self.scene().addItem(item)
            self.hover_items.append(item)

    def _bond_hover_endpoint(self, start: QPointF, pos: QPointF) -> QPointF:
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
        item = self._build_arrow_item(start, end, kind)
        item.setData(0, kind)
        data = item.data(2) or {}
        if kind in {"curved_single", "curved_double"}:
            data.update(
                {
                    "start": start,
                    "end": end,
                    "double": kind == "curved_double",
                }
            )
        else:
            data = {"start": start, "end": end, "control": None, "double": False}
        item.setData(2, data)
        self._make_selectable(item)
        self.scene().addItem(item)
        self._push_history()
        return item

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
        ux = dx / length
        uy = dy / length
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
        ux = dx / length
        uy = dy / length
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

    def add_orbital(self, center: QPointF) -> None:
        items = self._build_orbital_items(center, self.active_orbital_type)
        group = self.scene().createItemGroup(items)
        group.setData(0, "orbital")
        group.setData(1, {"center": QPointF(center), "base_handle_dist": self.renderer.style.bond_length_px * 0.8})
        group.setData(2, {"kind": self.active_orbital_type})
        group.setTransformOriginPoint(center)
        self._make_selectable(group)
        self._push_history()

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
        for handle in self._active_handles:
            self.scene().removeItem(handle)
        self._active_handles = []
        self._handle_target = None
        self._clear_selection_highlight()

    def show_orbital_handles(self, item) -> None:
        self.clear_handles()
        self._set_selection_highlight([item])
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", self.renderer.style.bond_length_px * 0.8)
        if not isinstance(center, QPointF):
            rect = item.boundingRect()
            center = rect.center()
        scale_pos = QPointF(center.x() + base_dist, center.y())
        rotate_pos = QPointF(center.x(), center.y() - base_dist)
        self._active_handles = [
            self._create_handle(scale_pos, "orbital_scale", item),
            self._create_handle(rotate_pos, "orbital_rotate", item),
        ]
        self._handle_target = item

    def show_curved_handles(self, item) -> None:
        self.clear_handles()
        self._set_selection_highlight([item])
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        control = data.get("control")
        if isinstance(start, QPointF) and isinstance(end, QPointF):
            if not isinstance(control, QPointF):
                control = self._default_curved_control(start, end)
            mid = self._curved_midpoint(start, control, end)
            self._update_curved_control(item, mid)
            mid = self._curved_midpoint(start, item.data(2).get("control"), end)
        else:
            rect = item.boundingRect()
            mid = rect.center()
        self._active_handles = [self._create_handle(mid, "curved_control", item)]
        self._handle_target = item

    def _create_handle(self, pos: QPointF, handle_type: str, target):
        radius = 5
        handle = QGraphicsEllipseItem(pos.x() - radius, pos.y() - radius, radius * 2, radius * 2)
        handle.setBrush(QColor("#ffffff"))
        handle.setPen(QColor("#333333"))
        handle.setData(0, "handle")
        handle.setData(1, handle_type)
        handle.setData(2, target)
        handle.setZValue(30)
        self.scene().addItem(handle)
        return handle

    def update_handle_drag(self, handle, scene_pos: QPointF) -> None:
        handle_type = handle.data(1)
        target = handle.data(2)
        if target is None:
            return
        if handle_type == "orbital_scale":
            self._update_orbital_scale(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "orbital_rotate":
            self._update_orbital_rotate(target, scene_pos)
            self.show_orbital_handles(target)
        elif handle_type == "curved_control":
            self._update_curved_control(target, scene_pos)
            self.show_curved_handles(target)

    def _update_orbital_scale(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        base_dist = data.get("base_handle_dist", self.renderer.style.bond_length_px * 0.8)
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        dist = math.hypot(pos.x() - center.x(), pos.y() - center.y())
        scale = max(0.2, dist / base_dist)
        item.setScale(scale)

    def _update_orbital_rotate(self, item, pos: QPointF) -> None:
        data = item.data(1) or {}
        center = data.get("center")
        if not isinstance(center, QPointF):
            center = item.boundingRect().center()
        angle = math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))
        if self._orbital_snap_enabled:
            step = self._orbital_snap_step or 15
            angle = round(angle / step) * step
        item.setRotation(angle)

    def _update_curved_control(self, item, pos: QPointF) -> None:
        data = item.data(2) or {}
        start = data.get("start")
        end = data.get("end")
        double = data.get("double", False)
        if not isinstance(start, QPointF) or not isinstance(end, QPointF):
            return
        mid = self._clamp_curved_midpoint(start, end, pos)
        control = self._control_from_midpoint(start, end, mid)
        path = QPainterPath()
        path.moveTo(start)
        path.quadTo(control, end)
        if double:
            self._add_arrow_head(path, control, end, double=False)
            self._add_arrow_head(path, control, start, double=False)
        else:
            self._add_arrow_head(path, control, end, double=False)
        item.setPath(path)
        data["control"] = control
        item.setData(2, data)
        self._update_selection_outline()

    def _default_curved_control(self, start: QPointF, end: QPointF) -> QPointF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        return QPointF(start.x() + dx * 0.5 + nx * length * 0.3, start.y() + dy * 0.5 + ny * length * 0.3)

    def _curved_midpoint(self, start: QPointF, control: QPointF, end: QPointF) -> QPointF:
        return QPointF(
            0.25 * start.x() + 0.5 * control.x() + 0.25 * end.x(),
            0.25 * start.y() + 0.5 * control.y() + 0.25 * end.y(),
        )

    def _control_from_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        return QPointF(
            2.0 * mid.x() - 0.5 * (start.x() + end.x()),
            2.0 * mid.y() - 0.5 * (start.y() + end.y()),
        )

    def _clamp_curved_midpoint(self, start: QPointF, end: QPointF, mid: QPointF) -> QPointF:
        chord_mid = QPointF((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        v = QPointF(mid.x() - chord_mid.x(), mid.y() - chord_mid.y())
        offset = v.x() * nx + v.y() * ny
        if self._curved_snap:
            step = self.renderer.style.bond_length_px * self._curved_snap_step
            offset = round(offset / step) * step
        max_offset = length * 0.8
        offset = max(-max_offset, min(max_offset, offset))
        return QPointF(chord_mid.x() + nx * offset, chord_mid.y() + ny * offset)

    def _set_selection_highlight(self, items: list) -> None:
        self._clear_selection_highlight()
        self._selected_items = items
        for item in items:
            self._apply_selection_style(item, True)

    def _clear_selection_highlight(self) -> None:
        for item in self._selected_items:
            self._apply_selection_style(item, False)
        self._selected_items = []

    def _apply_selection_style(self, item, selected: bool) -> None:
        if isinstance(item, QGraphicsItemGroup):
            for child in item.childItems():
                self._apply_selection_style(child, selected)
            return
        if hasattr(item, "pen"):
            pen = item.pen()
            if selected:
                item.setData(6, pen)
                pen.setColor(self._selection_color)
                pen.setWidthF(pen.widthF() + self._selection_stroke_delta)
                item.setPen(pen)
            else:
                original = item.data(6)
                if isinstance(original, QPen):
                    item.setPen(original)

    def mousePressEvent(self, event) -> None:
        self._touch_interaction()
        if self._template_insert_active and event.button() == Qt.MouseButton.LeftButton:
            self._commit_template_insert(self.scene_pos_from_event(event))
            self._clear_hover_highlight()
            return
        if self._smiles_insert_active and event.button() == Qt.MouseButton.LeftButton:
            self._commit_smiles_insert(self.scene_pos_from_event(event))
            self._clear_hover_highlight()
            return
        if self.tools.active and self.tools.active.on_mouse_press(event):
            self._clear_hover_highlight()
            return
        super().mousePressEvent(event)
        self._clear_hover_highlight()

    def mouseMoveEvent(self, event) -> None:
        self._touch_interaction()
        if self._template_insert_active:
            self._render_template_preview(self.scene_pos_from_event(event))
            return
        if self._smiles_insert_active:
            self._render_smiles_preview(self.scene_pos_from_event(event))
            return
        if event.buttons() == Qt.MouseButton.NoButton:
            self._update_hover_highlight(self.scene_pos_from_event(event))
        if self.tools.active and self.tools.active.on_mouse_move(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._touch_interaction()
        if self.tools.active and self.tools.active.on_mouse_release(event):
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        self._touch_interaction()
        self._reset_view_transform()
        delta = event.pixelDelta()
        if delta.isNull():
            angle = event.angleDelta()
            dx = -int(angle.x() / 2)
            dy = -int(angle.y() / 2)
        else:
            dx = -delta.x()
            dy = -delta.y()
        if dx or dy:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
            event.accept()
            return
        super().wheelEvent(event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.NativeGesture and isinstance(event, QNativeGestureEvent):
            if event.gestureType() in {
                Qt.NativeGestureType.PanNativeGesture,
                Qt.NativeGestureType.ZoomNativeGesture,
                Qt.NativeGestureType.RotateNativeGesture,
                Qt.NativeGestureType.SmartZoomNativeGesture,
            }:
                self._reset_view_transform()
                event.accept()
                return True
        return super().event(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._reset_view_transform()

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

    def apply_perspective_drag(self, dx: float, dy: float) -> None:
        # Deprecated: kept for compatibility if needed by tools.
        pass

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

    def begin_selection_3d_rotation(self) -> bool:
        atom_ids, bond_ids = self._selected_ids()
        self._rotation_selection_ids = (set(atom_ids), set(bond_ids))
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
            return False
        atom_ids = self._expand_connected_atoms(atom_ids)
        center_2d = self._center_for_atoms(atom_ids)
        if center_2d is None:
            return False
        dist_2d = []
        self.atom_coords_3d = {}
        for atom_id in atom_ids:
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            self.atom_coords_3d[atom_id] = (atom.x, atom.y, 0.0)
            dist_2d.append(math.hypot(atom.x - center_2d.x(), atom.y - center_2d.y()))
        if not self.atom_coords_3d:
            return False
        self._rotation_avg_dist = sum(dist_2d) / len(dist_2d) if dist_2d else 0.0

        self._rotation_base_coords = dict(self.atom_coords_3d)
        self._rotation_total_angles = (0.0, 0.0)
        self._rotation_plane_normal = (0.0, 0.0, 1.0)
        self.rotation_atom_ids = set(self.atom_coords_3d.keys())
        self.rotation_center_3d = (center_2d.x(), center_2d.y(), 0.0)
        return True

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        if not self.rotation_atom_ids or self.rotation_center_3d is None:
            return
        cx, cy, cz = self.rotation_center_3d
        if not hasattr(self, "_last_perspective_transform"):
            self._last_perspective_transform = QTransform()
        angle_y = delta_x * 0.01
        angle_x = delta_y * 0.01
        total_x, total_y = self._rotation_total_angles or (0.0, 0.0)
        total_x += angle_x
        total_y += angle_y
        self._rotation_total_angles = (total_x, total_y)
        self._rotation_plane_normal = self._plane_normal_from_angles(total_x, total_y)
        cos_y = math.cos(angle_y)
        sin_y = math.sin(angle_y)
        cos_x = math.cos(angle_x)
        sin_x = math.sin(angle_x)
        f = self.renderer.style.bond_length_px * 6.0
        for atom_id in self.rotation_atom_ids:
            coords = self._rotation_base_coords.get(atom_id)
            if coords is None:
                continue
            x, y, z = coords
            x -= cx
            y -= cy
            z -= cz
            cos_y_total = math.cos(total_y)
            sin_y_total = math.sin(total_y)
            cos_x_total = math.cos(total_x)
            sin_x_total = math.sin(total_x)
            rx = x * cos_y_total + z * sin_y_total
            rz = -x * sin_y_total + z * cos_y_total
            ry = y * cos_x_total - rz * sin_x_total
            rz2 = y * sin_x_total + rz * cos_x_total
            x = rx + cx
            y = ry + cy
            z = rz2 + cz
            self.atom_coords_3d[atom_id] = (x, y, z)

            proj_x = x
            proj_y = y
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                continue
            atom.x = proj_x
            atom.y = proj_y
            label = self.atom_items.get(atom_id)
            if label is not None:
                self._position_label(label, atom.x, atom.y)
            dot = self.atom_dots.get(atom_id)
            if dot is not None:
                dot.setPos(atom.x, atom.y)

        if getattr(self, "_rotation_avg_dist", 0.0) > 0.0:
            dist_sum = 0.0
            count = 0
            for atom_id in self.rotation_atom_ids:
                atom = self.model.atoms.get(atom_id)
                if atom is None:
                    continue
                dist_sum += math.hypot(atom.x - cx, atom.y - cy)
                count += 1
            if count:
                current_avg = dist_sum / count
                if current_avg > 1e-6:
                    factor = self._rotation_avg_dist / current_avg
                    if abs(factor - 1.0) > 1e-3:
                        for atom_id in self.rotation_atom_ids:
                            atom = self.model.atoms.get(atom_id)
                            if atom is None:
                                continue
                            atom.x = cx + (atom.x - cx) * factor
                            atom.y = cy + (atom.y - cy) * factor
                            coords = self.atom_coords_3d.get(atom_id)
                            if coords is not None:
                                x3, y3, z3 = coords
                                self.atom_coords_3d[atom_id] = (
                                    cx + (x3 - cx) * factor,
                                    cy + (y3 - cy) * factor,
                                    z3,
                                )
                            label = self.atom_items.get(atom_id)
                            if label is not None:
                                self._position_label(label, atom.x, atom.y)
                            dot = self.atom_dots.get(atom_id)
                            if dot is not None:
                                dot.setPos(atom.x, atom.y)

        self._last_perspective_transform = QTransform()
        self._last_perspective_transform.translate(cx, cy)
        self._last_perspective_transform.rotate(total_y * 30.0)
        self._last_perspective_transform.rotate(total_x * 30.0)
        self._last_perspective_transform.translate(-cx, -cy)
        self._redraw_bonds_for_atoms(self.rotation_atom_ids)
        self._rotate_ring_fills_3d(self.rotation_atom_ids, self.rotation_center_3d, angle_x, angle_y, f)
        self._update_selection_outline()

    def end_selection_3d_rotation(self) -> None:
        selection_ids = self._rotation_selection_ids
        rotated_atoms = set(self.rotation_atom_ids)
        plane_normal = self._rotation_plane_normal
        self.rotation_atom_ids = set()
        self.rotation_center_3d = None
        self._rotation_base_coords = {}
        self._rotation_total_angles = None
        self._rotation_selection_ids = None
        self._rotation_plane_normal = None
        if plane_normal is not None:
            for atom_id in rotated_atoms:
                self.atom_plane_normals[atom_id] = plane_normal
        self._push_history()
        if selection_ids is not None:
            self._restore_selection_from_ids(*selection_ids)
        self._emit_selection_info()

    def _redraw_bonds_for_atoms(self, atom_ids: set[int]) -> None:
        bond_ids = set()
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if bond.a in atom_ids or bond.b in atom_ids:
                bond_ids.add(bond_id)
        for bond_id in bond_ids:
            self._redraw_bond(bond_id)

    def bond_sets_for_atoms(self, atom_ids: set[int]) -> tuple[set[int], set[int]]:
        internal: set[int] = set()
        boundary: set[int] = set()
        if not atom_ids:
            return internal, boundary
        for bond_id, bond in enumerate(self.model.bonds):
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
        if self._rotation_group is not None:
            return False
        items = self.scene().selectedItems()
        if not items:
            return False
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
        center = self._center_for_atoms(atom_ids)
        if center is None:
            return False
        self._rotation_group = self.scene().createItemGroup(items)
        self._rotation_group.setTransformOriginPoint(center)
        return True

    def update_rotation_preview(self, angle_degrees: float) -> None:
        if self._rotation_group is None:
            return
        self._rotation_group.setRotation(angle_degrees)

    def commit_selection_rotation(self) -> None:
        if self._rotation_group is None:
            return
        angle = self._rotation_group.rotation()
        self._rotation_group.setRotation(0.0)
        self.scene().destroyItemGroup(self._rotation_group)
        self._rotation_group = None
        if angle:
            self.rotate_selection(angle)

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

    def _update_view_transform(self) -> None:
        transform = QTransform(self._base_transform)
        if self._perspective_shear or self._perspective_scale_y != 1.0:
            transform.shear(self._perspective_shear, 0.0)
            transform.scale(1.0, self._perspective_scale_y)
        self.setTransform(transform)

    def add_bond_from_points(self, start, end) -> None:
        if start == end:
            return
        self.last_smiles_input = None
        snap_tol = self.renderer.style.bond_length_px * 0.1
        start_id = self.model.find_atom_near(start.x(), start.y(), snap_tol)
        if start_id is None:
            start_id = self.model.add_atom("C", start.x(), start.y())
        end_id = self.model.find_atom_near(end.x(), end.y(), snap_tol)
        if end_id is None:
            end_id = self.model.add_atom("C", end.x(), end.y())
        if start_id == end_id:
            return
        self.model.add_bond(start_id, end_id, self.active_bond_order)
        bond_id = len(self.model.bonds) - 1
        self.model.bonds[bond_id].style = self.active_bond_style
        self._add_bond_graphics(bond_id)
        self.update_info_label()
        self._push_history()

    def _benzene_ring_points(
        self,
        center: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        radius = self.renderer.style.bond_length_px
        if attach_atom_id is None and attach_bond_id is None:
            for ring_item in self.ring_items:
                polygon = ring_item.polygon()
                if polygon.containsPoint(center, Qt.FillRule.WindingFill):
                    return None

        points: list[QPointF] = []
        merge: list[tuple[int, float, float]] = []

        if attach_bond_id is not None and 0 <= attach_bond_id < len(self.model.bonds):
            bond = self.model.bonds[attach_bond_id]
            if bond is not None:
                a = self.model.atoms.get(bond.a)
                b = self.model.atoms.get(bond.b)
                if a is not None and b is not None:
                    ax, ay = a.x, a.y
                    bx, by = b.x, b.y
                    mid = QPointF((ax + bx) / 2.0, (ay + by) / 2.0)
                    dx = bx - ax
                    dy = by - ay
                    length = math.hypot(dx, dy) or radius
                    nx = -dy / length
                    ny = dx / length
                    apothem = length * math.sqrt(3) / 2.0
                    center1 = QPointF(mid.x() + nx * apothem, mid.y() + ny * apothem)
                    center2 = QPointF(mid.x() - nx * apothem, mid.y() - ny * apothem)
                    use_center = center1
                    ring_polygon = None
                    for ring_item in self.ring_items:
                        ring_atom_ids = ring_item.data(2)
                        if not isinstance(ring_atom_ids, list):
                            continue
                        if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                            ring_polygon = ring_item.polygon()
                            break
                    if ring_polygon is not None:
                        c1_in = ring_polygon.containsPoint(center1, Qt.FillRule.WindingFill)
                        c2_in = ring_polygon.containsPoint(center2, Qt.FillRule.WindingFill)
                        if c1_in and not c2_in:
                            use_center = center2
                        elif c2_in and not c1_in:
                            use_center = center1
                        elif c1_in and c2_in:
                            return None
                    else:
                        if (center2 - center).manhattanLength() < (center1 - center).manhattanLength():
                            use_center = center2
                    center = use_center
                    theta_mid = math.atan2(mid.y() - center.y(), mid.x() - center.x())
                    theta0 = theta_mid + math.radians(30)
                    for i in range(6):
                        angle = theta0 + math.radians(60 * i)
                        x = center.x() + radius * math.cos(angle)
                        y = center.y() + radius * math.sin(angle)
                        points.append(QPointF(x, y))
                    merge = [(bond.a, ax, ay), (bond.b, bx, by)]

        if not points and attach_atom_id is not None and attach_atom_id in self.model.atoms:
            atom = self.model.atoms[attach_atom_id]
            ax, ay = atom.x, atom.y
            direction = QPointF(0.0, -1.0)
            vectors = []
            for bond in self.model.bonds:
                if bond is None:
                    continue
                if bond.a != attach_atom_id and bond.b != attach_atom_id:
                    continue
                other_id = bond.b if bond.a == attach_atom_id else bond.a
                other = self.model.atoms.get(other_id)
                if other is None:
                    continue
                vx = other.x - ax
                vy = other.y - ay
                vlen = math.hypot(vx, vy)
                if vlen > 0:
                    vectors.append((vx / vlen, vy / vlen))
            if vectors:
                sx = sum(v[0] for v in vectors)
                sy = sum(v[1] for v in vectors)
                if math.hypot(sx, sy) > 1e-6:
                    direction = QPointF(-sx, -sy)
                else:
                    direction = QPointF(-vectors[0][1], vectors[0][0])
            dlen = math.hypot(direction.x(), direction.y()) or 1.0
            center = QPointF(ax + (direction.x() / dlen) * radius, ay + (direction.y() / dlen) * radius)
            theta0 = math.atan2(ay - center.y(), ax - center.x())
            for i in range(6):
                angle = theta0 + math.radians(60 * i)
                x = center.x() + radius * math.cos(angle)
                y = center.y() + radius * math.sin(angle)
                points.append(QPointF(x, y))
            merge = [(attach_atom_id, ax, ay)]

        if not points:
            for i in range(6):
                angle = math.radians(60 * i - 30)
                x = center.x() + radius * math.cos(angle)
                y = center.y() + radius * math.sin(angle)
                points.append(QPointF(x, y))

        return points, merge

    def add_benzene_ring(self, center: QPointF, attach_atom_id: int | None = None, attach_bond_id: int | None = None) -> None:
        self.last_smiles_input = None
        result = self._benzene_ring_points(center, attach_atom_id, attach_bond_id)
        if result is None:
            return
        points, merge = result

        atom_ids: list[int] = []
        for point in points:
            atom_ids.append(self._add_atom_with_merge(point, "C", merge))

        bonds_start = len(self.model.bonds)
        for i in range(6):
            a_id = atom_ids[i]
            b_id = atom_ids[(i + 1) % 6]
            if self._bond_exists(a_id, b_id):
                continue
            order = 2 if i % 2 == 0 else 1
            self.model.add_bond(a_id, b_id, order)

        polygon = QPolygonF(points)
        ring_item = NoSelectPolygonItem(polygon)
        ring_item.setBrush(self.renderer.ring_fill_brush())
        ring_item.setPen(QPen(Qt.PenStyle.NoPen))
        ring_item.setData(0, "ring")
        ring_item.setData(2, list(atom_ids))
        self._make_selectable(ring_item)
        self.scene().addItem(ring_item)
        self.ring_items.append(ring_item)

        for bond_id in range(bonds_start, len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        self.update_info_label()
        self._push_history()

    def _bond_exists(self, a_id: int, b_id: int) -> bool:
        for bond in self.model.bonds:
            if bond is None:
                continue
            if (bond.a == a_id and bond.b == b_id) or (bond.a == b_id and bond.b == a_id):
                return True
        return False

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
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        points = self._cyclohexane_chair_points(center)

        atom_ids = []
        for point in points:
            atom_ids.append(self.model.add_atom("C", point.x(), point.y()))

        for i in range(6):
            self.model.add_bond(atom_ids[i], atom_ids[(i + 1) % 6])

        for i in range(6):
            bond_id = len(self.model.bonds) - 6 + i
            self._add_bond_graphics(bond_id)
        self.update_info_label()
        self._push_history()

    def add_cyclohexane_boat(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        points = self._cyclohexane_boat_points(center)

        atom_ids = []
        for point in points:
            atom_ids.append(self.model.add_atom("C", point.x(), point.y()))

        for i in range(6):
            self.model.add_bond(atom_ids[i], atom_ids[(i + 1) % 6])

        for i in range(6):
            bond_id = len(self.model.bonds) - 6 + i
            self._add_bond_graphics(bond_id)
        self.update_info_label()
        self._push_history()

    def add_cyclopropane(self) -> None:
        self.last_smiles_input = None
        self._add_regular_ring_template(3)
        self.update_info_label()
        self._push_history()

    def add_cyclobutane(self) -> None:
        self.last_smiles_input = None
        self._add_regular_ring_template(4)
        self.update_info_label()
        self._push_history()

    def add_cyclopentane(self) -> None:
        self.last_smiles_input = None
        self._add_regular_ring_template(5)
        self.update_info_label()
        self._push_history()

    def begin_ring_template_insert(self, ring_size: int, style: str = "regular") -> None:
        if ring_size < 3:
            return
        if style not in {"regular", "benzene", "chair", "boat"}:
            return
        if self._smiles_insert_active:
            self._cancel_smiles_insert()
        self._clear_benzene_preview()
        self._template_insert_active = True
        self._template_ring_size = ring_size
        self._template_ring_style = style
        self._render_template_preview(self.mapToScene(self.viewport().rect().center()))

    def add_naphthalene(self) -> None:
        self.last_smiles_input = None
        self._add_fused_benzenes(2)
        self.update_info_label()
        self._push_history()

    def add_anthracene(self) -> None:
        self.last_smiles_input = None
        self._add_fused_benzenes(3, mode="linear")
        self.update_info_label()
        self._push_history()

    def add_phenanthrene(self) -> None:
        self.last_smiles_input = None
        self._add_fused_benzenes(3, mode="angled")
        self.update_info_label()
        self._push_history()

    def add_pyridine(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(6, ["C", "C", "C", "C", "C", "N"])
        self.update_info_label()
        self._push_history()

    def add_pyrimidine(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(6, ["N", "C", "N", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_imidazole(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(5, ["C", "N", "C", "N", "C"])
        self.update_info_label()
        self._push_history()

    def add_pyrrole(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(5, ["N", "C", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_furan(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_thiophene(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(5, ["S", "C", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_indole(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        merge = []
        self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
        five_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.1, center.y() + self.renderer.style.bond_length_px * 0.6)
        elements = ["N", "C", "C", "C", "C"]
        self._add_ring_from_points(self._ring_points(five_center, 5), elements=elements, merge=merge)
        self.update_info_label()
        self._push_history()

    def add_quinoline(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        merge = []
        self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
        other_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.5, center.y())
        elements = ["N", "C", "C", "C", "C", "C"]
        self._add_ring_from_points(self._ring_points(other_center, 6), elements=elements, merge=merge)
        self.update_info_label()
        self._push_history()

    def add_isoquinoline(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        merge = []
        self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
        other_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.5, center.y())
        elements = ["C", "C", "C", "C", "N", "C"]
        self._add_ring_from_points(self._ring_points(other_center, 6), elements=elements, merge=merge)
        self.update_info_label()
        self._push_history()

    def add_benzimidazole(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        merge = []
        self._add_ring_from_points(self._ring_points(center, 6), merge=merge)
        five_center = QPointF(center.x() + self.renderer.style.bond_length_px * 1.1, center.y() + self.renderer.style.bond_length_px * 0.6)
        elements = ["N", "C", "N", "C", "C"]
        self._add_ring_from_points(self._ring_points(five_center, 5), elements=elements, merge=merge)
        self.update_info_label()
        self._push_history()

    def add_phenyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        atom_ids = self._add_ring_from_points(self._ring_points(center, 6))
        attach = QPointF(center.x() - self.renderer.style.bond_length_px * 2.0, center.y())
        attach_id = self.model.add_atom("C", attach.x(), attach.y())
        self.model.add_bond(atom_ids[0], attach_id)
        self._add_bond_graphics(len(self.model.bonds) - 1)
        self.update_info_label()
        self._push_history()

    def add_benzyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        atom_ids = self._add_ring_from_points(self._ring_points(center, 6))
        start = QPointF(center.x() - self.renderer.style.bond_length_px * 2.0, center.y())
        mid = QPointF(start.x() - self.renderer.style.bond_length_px, start.y())
        chain_ids = self._add_linear_chain([start, mid], ["C", "C"], [1])
        self.model.add_bond(atom_ids[0], chain_ids[0])
        self._add_bond_graphics(len(self.model.bonds) - 1)
        self.update_info_label()
        self._push_history()

    def add_vinyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        p1 = QPointF(center.x() - self.renderer.style.bond_length_px, center.y())
        p2 = QPointF(center.x(), center.y())
        self._add_linear_chain([p1, p2], ["C", "C"], [2])
        self.update_info_label()
        self._push_history()

    def add_allyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        points = [QPointF(center.x() - step, center.y()), QPointF(center.x(), center.y()), QPointF(center.x() + step, center.y())]
        self._add_linear_chain(points, ["C", "C", "C"], [2, 1])
        self.update_info_label()
        self._push_history()

    def add_carboxyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        c = QPointF(center.x(), center.y())
        o1 = QPointF(center.x() + step, center.y() - step * 0.6)
        o2 = QPointF(center.x() + step, center.y() + step * 0.6)
        self._add_linear_chain([c, o1], ["C", "O"], [2])
        self._add_linear_chain([c, o2], ["C", "O"], [1])
        self.update_info_label()
        self._push_history()

    def add_nitro(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        n = QPointF(center.x(), center.y())
        o1 = QPointF(center.x() + step, center.y() - step * 0.6)
        o2 = QPointF(center.x() + step, center.y() + step * 0.6)
        self._add_linear_chain([n, o1], ["N", "O"], [2])
        self._add_linear_chain([n, o2], ["N", "O"], [2])
        self.update_info_label()
        self._push_history()

    def add_sulfonyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        s = QPointF(center.x(), center.y())
        o1 = QPointF(center.x() + step, center.y() - step * 0.7)
        o2 = QPointF(center.x() + step, center.y() + step * 0.7)
        self._add_linear_chain([s, o1], ["S", "O"], [2])
        self._add_linear_chain([s, o2], ["S", "O"], [2])
        self.update_info_label()
        self._push_history()

    def add_carbonyl(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        c = QPointF(center.x(), center.y())
        o = QPointF(center.x() + step, center.y())
        self._add_linear_chain([c, o], ["C", "O"], [2])
        self.update_info_label()
        self._push_history()

    def add_tbu(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        c = QPointF(center.x(), center.y())
        branches = [
            QPointF(center.x() + step, center.y()),
            QPointF(center.x() - step, center.y()),
            QPointF(center.x(), center.y() - step),
        ]
        for b in branches:
            self._add_linear_chain([c, b], ["C", "C"], [1])
        self.update_info_label()
        self._push_history()

    def add_ipr(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        c = QPointF(center.x(), center.y())
        b1 = QPointF(center.x() + step, center.y())
        b2 = QPointF(center.x(), center.y() - step)
        self._add_linear_chain([c, b1], ["C", "C"], [1])
        self._add_linear_chain([c, b2], ["C", "C"], [1])
        self.update_info_label()
        self._push_history()

    def add_me(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        p = QPointF(center.x(), center.y())
        self._add_linear_chain([p], ["C"], [])
        self.update_info_label()
        self._push_history()

    def add_et(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px
        p1 = QPointF(center.x() - step / 2, center.y())
        p2 = QPointF(center.x() + step / 2, center.y())
        self._add_linear_chain([p1, p2], ["C", "C"], [1])
        self.update_info_label()
        self._push_history()

    def add_pyranose(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(6, ["O", "C", "C", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_furanose(self) -> None:
        self.last_smiles_input = None
        self._add_hetero_ring_template(5, ["O", "C", "C", "C", "C"])
        self.update_info_label()
        self._push_history()

    def add_peptide_2(self) -> None:
        self.last_smiles_input = None
        center = self.mapToScene(self.viewport().rect().center())
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
        bonds = [1, 1, 1, 1, 1]
        chain_ids = self._add_linear_chain(points, elements, bonds)
        carbonyl_1 = chain_ids[1]
        carbonyl_2 = chain_ids[4]
        o1 = QPointF(points[1].x(), points[1].y() - step * 0.8)
        o2 = QPointF(points[4].x(), points[4].y() - step * 0.8)
        o1_id = self.model.add_atom("O", o1.x(), o1.y())
        o2_id = self.model.add_atom("O", o2.x(), o2.y())
        self.model.add_bond(carbonyl_1, o1_id, 2)
        self.model.add_bond(carbonyl_2, o2_id, 2)
        self._add_bond_graphics(len(self.model.bonds) - 2)
        self._add_bond_graphics(len(self.model.bonds) - 1)
        self.add_or_update_atom_label(o1_id, "O", record=False)
        self.add_or_update_atom_label(o2_id, "O", record=False)
        self.update_info_label()
        self._push_history()

    def add_crown_12_4(self) -> None:
        self.last_smiles_input = None
        self._add_crown_ether(12, 4)
        self.update_info_label()
        self._push_history()

    def add_crown_15_5(self) -> None:
        self.last_smiles_input = None
        self._add_crown_ether(15, 5)
        self.update_info_label()
        self._push_history()

    def add_crown_18_6(self) -> None:
        self.last_smiles_input = None
        self._add_crown_ether(18, 6)
        self.update_info_label()
        self._push_history()

    def _add_regular_ring_template(self, n: int) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        radius = self._regular_ring_radius(n)
        self._add_ring_from_points(self._ring_points(center, n, radius=radius))

    def _add_hetero_ring_template(self, n: int, elements: list[str]) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        radius = self._regular_ring_radius(n)
        self._add_ring_from_points(self._ring_points(center, n, radius=radius), elements=elements)

    def _add_fused_benzenes(self, count: int, mode: str = "linear") -> None:
        center = self.mapToScene(self.viewport().rect().center())
        step = self.renderer.style.bond_length_px * 1.5
        merge = []
        centers = []
        if count == 2:
            centers = [QPointF(center.x() - step / 2, center.y()), QPointF(center.x() + step / 2, center.y())]
        elif mode == "angled":
            centers = [
                QPointF(center.x() - step, center.y()),
                QPointF(center.x(), center.y()),
                QPointF(center.x() + step * 0.6, center.y() + step * 0.6),
            ]
        else:
            centers = [QPointF(center.x() - step, center.y()), QPointF(center.x(), center.y()), QPointF(center.x() + step, center.y())]
        for ring_center in centers:
            self._add_ring_from_points(self._ring_points(ring_center, 6), merge=merge)

    def _add_crown_ether(self, atoms: int, oxygens: int) -> None:
        center = self.mapToScene(self.viewport().rect().center())
        points = self._ring_points(center, atoms, radius=self.renderer.style.bond_length_px * 1.4)
        elements = ["C"] * atoms
        step = atoms // oxygens
        for i in range(0, atoms, step):
            elements[i] = "O"
        self._add_ring_from_points(points, elements=elements)

    def _cyclohexane_chair_points(self, center: QPointF) -> list[QPointF]:
        step = self.renderer.style.bond_length_px
        # Angles tuned to match cyclohexane.png chair reference.
        angle_steep = math.radians(-68.0)
        angle_shallow = math.radians(-25.0)
        v1 = QPointF(math.cos(angle_steep), math.sin(angle_steep))
        v2 = QPointF(math.cos(angle_shallow), math.sin(angle_shallow))

        points = [
            QPointF(0.0, 0.0),
            QPointF(v1.x(), v1.y()),
            QPointF(v1.x() + 1.0, v1.y()),
            QPointF(v1.x() + 1.0 + v2.x(), v1.y() + v2.y()),
            QPointF(1.0 + v2.x(), v2.y()),
            QPointF(v2.x(), v2.y()),
        ]
        min_x = min(point.x() for point in points)
        max_x = max(point.x() for point in points)
        min_y = min(point.y() for point in points)
        max_y = max(point.y() for point in points)
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        shifted = [
            QPointF(
                center.x() + (point.x() - cx) * step,
                center.y() + (point.y() - cy) * step,
            )
            for point in points
        ]
        return self._scale_points_to_bond_length(shifted, center, step)

    def _cyclohexane_boat_points(self, center: QPointF) -> list[QPointF]:
        step = self.renderer.style.bond_length_px
        height = step * 1.0
        bow = height * 0.2
        belly = height * 1.3
        points = [
            QPointF(center.x() - 1.5 * step, center.y() - bow),
            QPointF(center.x() - 0.5 * step, center.y() - height),
            QPointF(center.x() + 0.5 * step, center.y() - height),
            QPointF(center.x() + 1.5 * step, center.y() - bow),
            QPointF(center.x() + 0.5 * step, center.y() + belly),
            QPointF(center.x() - 0.5 * step, center.y() + belly),
        ]
        return self._scale_points_to_bond_length(points, center, step)

    @staticmethod
    def _scale_points_to_bond_length(
        points: list[QPointF],
        center: QPointF,
        bond_length: float,
    ) -> list[QPointF]:
        if len(points) < 2:
            return points
        dx = points[1].x() - points[0].x()
        dy = points[1].y() - points[0].y()
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            return points
        scale = bond_length / dist
        if abs(scale - 1.0) < 1e-6:
            return points
        scaled = []
        for point in points:
            scaled.append(
                QPointF(
                    center.x() + (point.x() - center.x()) * scale,
                    center.y() + (point.y() - center.y()) * scale,
                )
            )
        return scaled

    def _ring_points(self, center: QPointF, n: int, radius: float | None = None):
        radius = radius or self.renderer.style.bond_length_px
        points = []
        for i in range(n):
            angle = math.radians(360 / n * i - 90)
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            points.append(QPointF(x, y))
        return points

    def _regular_ring_radius(self, n: int, bond_length: float | None = None) -> float:
        bond_length = bond_length if bond_length is not None else self.renderer.style.bond_length_px
        if n < 3:
            return bond_length
        denom = 2.0 * math.sin(math.pi / n)
        if denom <= 1e-6:
            return bond_length
        return bond_length / denom

    def _template_points_for_bond(
        self,
        points_local: list[QPointF],
        bond_id: int,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        if len(points_local) < 2 or not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        a = self.model.atoms.get(bond.a)
        b = self.model.atoms.get(bond.b)
        if a is None or b is None:
            return None
        ax, ay = a.x, a.y
        bx, by = b.x, b.y
        p0 = points_local[0]
        p1 = points_local[1]
        local_dx = p1.x() - p0.x()
        local_dy = p1.y() - p0.y()
        local_len = math.hypot(local_dx, local_dy)
        if local_len <= 1e-6:
            return None
        target_dx = bx - ax
        target_dy = by - ay
        target_len = math.hypot(target_dx, target_dy)
        if target_len <= 1e-6:
            return None
        scale = target_len / local_len
        angle_local = math.atan2(local_dy, local_dx)
        angle_target = math.atan2(target_dy, target_dx)
        angle = angle_target - angle_local
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        ux = local_dx / local_len
        uy = local_dy / local_len
        vx = -uy
        vy = ux

        def transform(mirror: bool) -> list[QPointF]:
            pts = []
            for point in points_local:
                dx = point.x() - p0.x()
                dy = point.y() - p0.y()
                du = dx * ux + dy * uy
                dv = dx * vx + dy * vy
                if mirror:
                    dv = -dv
                px = (ux * du + vx * dv) * scale
                py = (uy * du + vy * dv) * scale
                rx = px * cos_a - py * sin_a
                ry = px * sin_a + py * cos_a
                pts.append(QPointF(ax + rx, ay + ry))
            return pts

        def center_of(points: list[QPointF]) -> QPointF:
            cx = sum(p.x() for p in points) / len(points)
            cy = sum(p.y() for p in points) / len(points)
            return QPointF(cx, cy)

        points_a = transform(False)
        points_b = transform(True)
        center_a = center_of(points_a)
        center_b = center_of(points_b)

        ring_polygon = None
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                ring_polygon = ring_item.polygon()
                break
        if ring_polygon is not None:
            a_in = ring_polygon.containsPoint(center_a, Qt.FillRule.WindingFill)
            b_in = ring_polygon.containsPoint(center_b, Qt.FillRule.WindingFill)
            if a_in and not b_in:
                return points_b, [(bond.a, ax, ay), (bond.b, bx, by)]
            if b_in and not a_in:
                return points_a, [(bond.a, ax, ay), (bond.b, bx, by)]
            if a_in and b_in:
                return None
        if center_hint is not None:
            da = (center_a - center_hint).manhattanLength()
            db = (center_b - center_hint).manhattanLength()
            if db < da:
                return points_b, [(bond.a, ax, ay), (bond.b, bx, by)]
        return points_a, [(bond.a, ax, ay), (bond.b, bx, by)]

    def _regular_ring_points_for_bond(
        self,
        n: int,
        bond_id: int,
        center_hint: QPointF | None = None,
    ) -> tuple[list[QPointF], list[tuple[int, float, float]]] | None:
        if n < 3 or not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        a = self.model.atoms.get(bond.a)
        b = self.model.atoms.get(bond.b)
        if a is None or b is None:
            return None
        ax, ay = a.x, a.y
        bx, by = b.x, b.y
        dx = bx - ax
        dy = by - ay
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return None
        radius = length / (2.0 * math.sin(math.pi / n))
        apothem = length / (2.0 * math.tan(math.pi / n))
        mid = QPointF((ax + bx) / 2.0, (ay + by) / 2.0)
        nx = -dy / length
        ny = dx / length
        center1 = QPointF(mid.x() + nx * apothem, mid.y() + ny * apothem)
        center2 = QPointF(mid.x() - nx * apothem, mid.y() - ny * apothem)
        use_center = center1
        ring_polygon = None
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                ring_polygon = ring_item.polygon()
                break
        if ring_polygon is not None:
            c1_in = ring_polygon.containsPoint(center1, Qt.FillRule.WindingFill)
            c2_in = ring_polygon.containsPoint(center2, Qt.FillRule.WindingFill)
            if c1_in and not c2_in:
                use_center = center2
            elif c2_in and not c1_in:
                use_center = center1
            elif c1_in and c2_in:
                return None
        elif center_hint is not None:
            if (center2 - center_hint).manhattanLength() < (center1 - center_hint).manhattanLength():
                use_center = center2

        theta_a = math.atan2(ay - use_center.y(), ax - use_center.x())
        step = 2.0 * math.pi / n
        p_forward = QPointF(
            use_center.x() + radius * math.cos(theta_a + step),
            use_center.y() + radius * math.sin(theta_a + step),
        )
        p_backward = QPointF(
            use_center.x() + radius * math.cos(theta_a - step),
            use_center.y() + radius * math.sin(theta_a - step),
        )
        dist_forward = math.hypot(p_forward.x() - bx, p_forward.y() - by)
        dist_backward = math.hypot(p_backward.x() - bx, p_backward.y() - by)
        direction = 1.0 if dist_forward <= dist_backward else -1.0

        points = []
        for i in range(n):
            angle = theta_a + direction * step * i
            x = use_center.x() + radius * math.cos(angle)
            y = use_center.y() + radius * math.sin(angle)
            points.append(QPointF(x, y))
        merge = [(bond.a, ax, ay), (bond.b, bx, by)]
        return points, merge

    def _add_ring_from_points(self, points, elements: list[str] | None = None, merge: list | None = None):
        merge = merge or []
        atom_ids = []
        for idx, point in enumerate(points):
            element = elements[idx] if elements else "C"
            atom_id = self._add_atom_with_merge(point, element, merge)
            atom_ids.append(atom_id)
        bonds_start = len(self.model.bonds)
        for i in range(len(atom_ids)):
            self.model.add_bond(atom_ids[i], atom_ids[(i + 1) % len(atom_ids)])
        for bond_id in range(bonds_start, len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        for atom_id, element in zip(atom_ids, elements or ["C"] * len(atom_ids)):
            if element != "C":
                atom = self.model.atoms[atom_id]
                self.add_or_update_atom_label(atom_id, atom.element, record=False)
        return atom_ids

    def _add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        tol = self.renderer.style.bond_length_px * 0.2
        for entry in merge:
            atom_id, x, y = entry
            if abs(point.x() - x) < tol and abs(point.y() - y) < tol:
                return atom_id
        atom_id = self.model.add_atom(element, point.x(), point.y())
        merge.append((atom_id, point.x(), point.y()))
        return atom_id

    def _merge_overlapping_atoms(self, atom_id: int) -> None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        tol = max(0.5, self.renderer.style.bond_length_px * 0.05)
        tol_sq = tol * tol
        merge_ids = []
        for other_id, other in self.model.atoms.items():
            if other_id == atom_id:
                continue
            dx = other.x - atom.x
            dy = other.y - atom.y
            if dx * dx + dy * dy <= tol_sq:
                merge_ids.append(other_id)
        if not merge_ids:
            return
        for other_id in merge_ids:
            label = self.atom_items.pop(other_id, None)
            if label is not None:
                self.scene().removeItem(label)
            dot = self.atom_dots.pop(other_id, None)
            if dot is not None:
                self.scene().removeItem(dot)
        for bond in self.model.bonds:
            if bond is None:
                continue
            if bond.a in merge_ids:
                bond.a = atom_id
            if bond.b in merge_ids:
                bond.b = atom_id
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if bond.a == bond.b:
                for item in self.bond_items.get(bond_id, []):
                    self.scene().removeItem(item)
                self.bond_items.pop(bond_id, None)
                self.model.bonds[bond_id] = None
        for other_id in merge_ids:
            self.model.atoms.pop(other_id, None)

    def _add_linear_chain(self, points: list[QPointF], elements: list[str], bonds: list[int]):
        atom_ids = []
        for point, element in zip(points, elements):
            atom_ids.append(self.model.add_atom(element, point.x(), point.y()))
        bonds_start = len(self.model.bonds)
        for i, order in enumerate(bonds):
            self.model.add_bond(atom_ids[i], atom_ids[i + 1], order)
        for bond_id in range(bonds_start, len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        for atom_id, element in zip(atom_ids, elements):
            if element != "C":
                self.add_or_update_atom_label(atom_id, element, record=False)
        return atom_ids

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        clear_smiles: bool = True,
        record: bool = True,
    ) -> None:
        text = text.strip()
        atom = self.model.atoms[atom_id]
        if text:
            atom.element = text
            if clear_smiles:
                self.last_smiles_input = None
        existing_item = self.atom_items.get(atom_id)
        if text.upper() == "C":
            text = ""

        if not text:
            if existing_item is not None:
                self.scene().removeItem(existing_item)
                self.atom_items.pop(atom_id, None)
            if atom.element == "C":
                self._ensure_carbon_dot(atom_id)
            self._redraw_connected_bonds(atom_id)
            if record:
                self._push_history()
            return

        if existing_item is None:
            text_item = NoSelectTextItem()
            self.scene().addItem(text_item)
            self.atom_items[atom_id] = text_item
        else:
            text_item = existing_item

        text_item.setFont(self.renderer.atom_font())
        text_item.setDefaultTextColor(QColor(self.renderer.style.atom_color))
        text_item.setData(0, "atom")
        text_item.setData(1, atom_id)
        self._make_selectable(text_item)
        text_item.setPlainText(text)
        self._position_label(text_item, atom.x, atom.y)
        self._remove_carbon_dot(atom_id)
        self._merge_overlapping_atoms(atom_id)
        self._redraw_connected_bonds(atom_id)
        if record:
            self._push_history()

    def _ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in self.atom_dots:
            return
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        dot = NoSelectEllipseItem(-radius, -radius, radius * 2.0, radius * 2.0)
        dot.setBrush(QColor(self.renderer.style.bond_color))
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
                bond.color = color.name()
                for bond_item in self.bond_items.get(bond_id, []):
                    self._apply_color_to_bond_item(bond_item, color)
                self._push_history()
        elif kind == "atom":
            atom_id = item.data(1)
            if isinstance(item, QGraphicsTextItem):
                item.setDefaultTextColor(color)
            elif isinstance(item, QGraphicsEllipseItem):
                item.setBrush(color)
            if atom_id in self.model.atoms:
                self.model.atoms[atom_id].color = color.name()
                label_item = self.atom_items.get(atom_id)
                if label_item is not None and label_item is not item:
                    label_item.setDefaultTextColor(color)
                dot_item = self.atom_dots.get(atom_id)
                if dot_item is not None and dot_item is not item:
                    dot_item.setBrush(color)
                self._push_history()
        elif kind == "ring":
            fill = QColor(color)
            fill.setAlphaF(self.renderer.style.ring_fill_alpha)
            item.setBrush(fill)
            self._push_history()

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if item is None or not color.isValid():
            return
        if item.data(0) != "ring":
            return
        fill = QColor(color)
        fill.setAlphaF(max(0.0, min(1.0, float(alpha))))
        item.setBrush(fill)
        self._push_history()

    def clear_scene(self) -> None:
        self.scene().clear()
        self.hover_items = []
        self.hover_atom_id = None
        self.hover_bond_id = None
        self.model = MoleculeModel()
        self.atom_coords_3d = {}
        self.atom_plane_normals = {}
        self.atom_items = {}
        self.atom_dots = {}
        self.bond_items = {}
        self.ring_items = []
        self.info_item = None
        self._template_insert_active = False
        self._template_ring_size = None
        self._template_ring_style = None
        self._template_preview_items = []
        self._benzene_preview_items = []

    def load_smiles(self, smiles: str) -> None:
        smiles = smiles.strip()
        if not smiles:
            return
        model = self.rdkit.smiles_to_2d(smiles, scale=self.renderer.style.bond_length_px)
        if model is None:
            message = self.rdkit.last_error or "Failed to render SMILES."
            QMessageBox.warning(self, "SMILES Error", message)
            return
        self.clear_scene()
        self.model = model
        self.last_smiles_input = smiles
        self._render_model()
        self._push_history()

    def begin_smiles_insert(self, smiles: str) -> None:
        if self._template_insert_active:
            self._cancel_template_insert()
        self._clear_benzene_preview()
        smiles = smiles.strip()
        if not smiles:
            return
        model = self.rdkit.smiles_to_2d(smiles, scale=self.renderer.style.bond_length_px)
        if model is None:
            message = self.rdkit.last_error or "Failed to render SMILES."
            QMessageBox.warning(self, "SMILES Error", message)
            return
        self._smiles_insert_active = True
        self._smiles_preview_model = model
        self._smiles_preview_smiles = smiles
        bounds = model.bounds()
        center = QPointF((bounds[0] + bounds[2]) / 2.0, (bounds[1] + bounds[3]) / 2.0)
        self._smiles_preview_center = center
        self._render_smiles_preview(self.mapToScene(self.viewport().rect().center()))

    def _cancel_smiles_insert(self) -> None:
        self._smiles_insert_active = False
        self._smiles_preview_model = None
        self._smiles_preview_smiles = None
        self._smiles_preview_center = None
        self._clear_smiles_preview()

    def _commit_smiles_insert(self, pos: QPointF) -> None:
        if self._smiles_preview_model is None or self._smiles_preview_center is None:
            self._cancel_smiles_insert()
            return
        model = self._smiles_preview_model
        dx = pos.x() - self._smiles_preview_center.x()
        dy = pos.y() - self._smiles_preview_center.y()
        id_map: dict[int, int] = {}
        for atom_id, atom in model.atoms.items():
            new_id = self.model.add_atom(atom.element, atom.x + dx, atom.y + dy)
            self.model.atoms[new_id].color = atom.color
            id_map[atom_id] = new_id
        bonds_start = len(self.model.bonds)
        for bond in model.bonds:
            if bond is None:
                continue
            a_id = id_map.get(bond.a)
            b_id = id_map.get(bond.b)
            if a_id is None or b_id is None:
                continue
            self.model.add_bond(a_id, b_id, bond.order)
            created = self.model.bonds[-1]
            created.style = bond.style
            created.color = bond.color
        for bond_id in range(bonds_start, len(self.model.bonds)):
            self._add_bond_graphics(bond_id)
        for old_id, new_id in id_map.items():
            atom = self.model.atoms[new_id]
            if atom.element == "C":
                self._ensure_carbon_dot(new_id)
            else:
                self.add_or_update_atom_label(new_id, atom.element, clear_smiles=False, record=False)
        self.last_smiles_input = self._smiles_preview_smiles
        self._cancel_smiles_insert()
        self._push_history()

    def _clear_smiles_preview(self) -> None:
        for item in self._smiles_preview_items:
            try:
                if item.scene() is self.scene():
                    self.scene().removeItem(item)
            except RuntimeError:
                pass
        self._smiles_preview_items = []

    def _render_smiles_preview(self, pos: QPointF) -> None:
        if self._smiles_preview_model is None or self._smiles_preview_center is None:
            return
        self._clear_smiles_preview()
        model = self._smiles_preview_model
        dx = pos.x() - self._smiles_preview_center.x()
        dy = pos.y() - self._smiles_preview_center.y()
        preview_color = QColor(120, 120, 120, 140)
        for bond in model.bonds:
            if bond is None:
                continue
            a = model.atoms.get(bond.a)
            b = model.atoms.get(bond.b)
            if a is None or b is None:
                continue
            x1 = a.x + dx
            y1 = a.y + dy
            x2 = b.x + dx
            y2 = b.y + dy
            if bond.order <= 1:
                line = NoSelectLineItem(x1, y1, x2, y2)
                line.setPen(self.renderer.bond_pen())
                items = [line]
            else:
                items = self._draw_parallel_bonds(x1, y1, x2, y2, bond.order)
            for item in items:
                if hasattr(item, "pen"):
                    pen = item.pen()
                    pen.setColor(preview_color)
                    item.setPen(pen)
                item.setOpacity(0.5)
                self.scene().addItem(item)
                self._smiles_preview_items.append(item)
        atom_radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        for atom in model.atoms.values():
            dot = QGraphicsEllipseItem(
                atom.x + dx - atom_radius,
                atom.y + dy - atom_radius,
                atom_radius * 2.0,
                atom_radius * 2.0,
            )
            dot.setBrush(preview_color)
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            dot.setOpacity(0.5)
            self.scene().addItem(dot)
            self._smiles_preview_items.append(dot)

    def _cancel_template_insert(self) -> None:
        self._template_insert_active = False
        self._template_ring_size = None
        self._template_ring_style = None
        self._clear_template_preview()

    def _commit_template_insert(self, pos: QPointF) -> None:
        if not self._template_insert_active or self._template_ring_size is None:
            self._cancel_template_insert()
            return
        ring_size = self._template_ring_size
        ring_style = self._template_ring_style or "regular"
        self.last_smiles_input = None
        bond_id = self._find_bond_near(pos, self.renderer.style.bond_length_px * 0.35)
        if ring_style == "benzene" and ring_size == 6:
            if bond_id is not None:
                self.add_benzene_ring(pos, attach_bond_id=bond_id)
            else:
                self.add_benzene_ring(pos)
            self._cancel_template_insert()
            return
        if ring_style in {"chair", "boat"}:
            local_center = QPointF(0.0, 0.0)
            if ring_style == "chair":
                points_local = self._cyclohexane_chair_points(local_center)
            else:
                points_local = self._cyclohexane_boat_points(local_center)
            if bond_id is not None:
                result = self._template_points_for_bond(points_local, bond_id, pos)
                if result is None:
                    self._cancel_template_insert()
                    return
                points, merge = result
                atom_ids = []
                for point in points:
                    atom_ids.append(self._add_atom_with_merge(point, "C", merge))
                bonds_start = len(self.model.bonds)
                for i in range(len(atom_ids)):
                    a_id = atom_ids[i]
                    b_id = atom_ids[(i + 1) % len(atom_ids)]
                    if self._bond_exists(a_id, b_id):
                        continue
                    self.model.add_bond(a_id, b_id)
                for new_bond_id in range(bonds_start, len(self.model.bonds)):
                    self._add_bond_graphics(new_bond_id)
            else:
                if ring_style == "chair":
                    points = self._cyclohexane_chair_points(pos)
                else:
                    points = self._cyclohexane_boat_points(pos)
                self._add_ring_from_points(points)
            self.update_info_label()
            self._cancel_template_insert()
            self._push_history()
            return
        if bond_id is not None:
            result = self._regular_ring_points_for_bond(ring_size, bond_id, pos)
            if result is None:
                self._cancel_template_insert()
                return
            points, merge = result
            atom_ids = []
            for point in points:
                atom_ids.append(self._add_atom_with_merge(point, "C", merge))
            bonds_start = len(self.model.bonds)
            for i in range(ring_size):
                a_id = atom_ids[i]
                b_id = atom_ids[(i + 1) % ring_size]
                if self._bond_exists(a_id, b_id):
                    continue
                self.model.add_bond(a_id, b_id)
            for new_bond_id in range(bonds_start, len(self.model.bonds)):
                self._add_bond_graphics(new_bond_id)
        else:
            if ring_style == "regular":
                radius = self._regular_ring_radius(ring_size)
                points = self._ring_points(pos, ring_size, radius=radius)
            else:
                points = self._ring_points(pos, ring_size)
            self._add_ring_from_points(points)
        self.update_info_label()
        self._cancel_template_insert()
        self._push_history()

    def _clear_template_preview(self) -> None:
        for item in self._template_preview_items:
            try:
                if item.scene() is self.scene():
                    self.scene().removeItem(item)
            except RuntimeError:
                pass
        self._template_preview_items = []

    def _render_template_preview(self, pos: QPointF) -> None:
        if not self._template_insert_active or self._template_ring_size is None:
            return
        self._clear_template_preview()
        ring_size = self._template_ring_size
        ring_style = self._template_ring_style or "regular"
        points: list[QPointF] | None = None
        bond_id = self._find_bond_near(pos, self.renderer.style.bond_length_px * 0.35)
        if ring_style in {"chair", "boat"}:
            local_center = QPointF(0.0, 0.0)
            if ring_style == "chair":
                points_local = self._cyclohexane_chair_points(local_center)
            else:
                points_local = self._cyclohexane_boat_points(local_center)
            if bond_id is not None:
                result = self._template_points_for_bond(points_local, bond_id, pos)
                if result is None:
                    return
                points = result[0]
            else:
                if ring_style == "chair":
                    points = self._cyclohexane_chair_points(pos)
                else:
                    points = self._cyclohexane_boat_points(pos)
        elif bond_id is not None:
            result = self._regular_ring_points_for_bond(ring_size, bond_id, pos)
            if result is None:
                return
            points = result[0]
        if points is None:
            if ring_style == "regular":
                radius = self._regular_ring_radius(ring_size)
                points = self._ring_points(pos, ring_size, radius=radius)
            else:
                points = self._ring_points(pos, ring_size)
        preview_color = QColor(120, 120, 120, 140)
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            line = NoSelectLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            line.setPen(self.renderer.bond_pen())
            pen = line.pen()
            pen.setColor(preview_color)
            line.setPen(pen)
            line.setOpacity(0.5)
            self.scene().addItem(line)
            self._template_preview_items.append(line)
        atom_radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        for point in points:
            dot = QGraphicsEllipseItem(
                point.x() - atom_radius,
                point.y() - atom_radius,
                atom_radius * 2.0,
                atom_radius * 2.0,
            )
            dot.setBrush(preview_color)
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            dot.setOpacity(0.5)
            self.scene().addItem(dot)
            self._template_preview_items.append(dot)

    def _clear_benzene_preview(self) -> None:
        for item in self._benzene_preview_items:
            try:
                if item.scene() is self.scene():
                    self.scene().removeItem(item)
            except RuntimeError:
                pass
        self._benzene_preview_items = []

    def _render_benzene_preview(
        self,
        pos: QPointF,
        attach_atom_id: int | None = None,
        attach_bond_id: int | None = None,
    ) -> None:
        self._clear_benzene_preview()
        result = self._benzene_ring_points(pos, attach_atom_id, attach_bond_id)
        if result is None:
            return
        points, _ = result
        preview_color = QColor(120, 120, 120, 140)
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            line = NoSelectLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            line.setPen(self.renderer.bond_pen())
            pen = line.pen()
            pen.setColor(preview_color)
            line.setPen(pen)
            line.setOpacity(0.5)
            self.scene().addItem(line)
            self._benzene_preview_items.append(line)
        atom_radius = max(0.6, self.renderer.style.bond_line_width * 0.6)
        for point in points:
            dot = QGraphicsEllipseItem(
                point.x() - atom_radius,
                point.y() - atom_radius,
                atom_radius * 2.0,
                atom_radius * 2.0,
            )
            dot.setBrush(preview_color)
            dot.setPen(QPen(Qt.PenStyle.NoPen))
            dot.setOpacity(0.5)
            self.scene().addItem(dot)
            self._benzene_preview_items.append(dot)

    def _render_model(self) -> None:
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            self._add_bond_graphics(bond_id)

        for atom_id, atom in self.model.atoms.items():
            if atom.element == "C":
                self._ensure_carbon_dot(atom_id)
            else:
                self.add_or_update_atom_label(atom_id, atom.element, clear_smiles=False, record=False)
        self.update_info_label()

    def move_item(self, item, dx: float, dy: float, update_selection: bool = True) -> None:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return
            atom = self.model.atoms.get(atom_id)
            if atom is None:
                return
            atom.x += dx
            atom.y += dy
            item.moveBy(dx, dy)
            for bond_id, bond in enumerate(self.model.bonds):
                if bond is None:
                    continue
                if bond.a == atom_id or bond.b == atom_id:
                    self._redraw_bond(bond_id)
        elif kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return
            bond = self.model.bonds[bond_id]
            if bond is None:
                return
            self._move_atom(bond.a, dx, dy)
            self._move_atom(bond.b, dx, dy)
            self._redraw_connected_bonds(bond.a)
            self._redraw_connected_bonds(bond.b)
        elif kind in {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "orbital",
            "note",
        }:
            item.moveBy(dx, dy)
            if kind == "orbital":
                data = item.data(1) or {}
                center = data.get("center")
                if isinstance(center, QPointF):
                    data["center"] = QPointF(center.x() + dx, center.y() + dy)
                    item.setData(1, data)
            else:
                data = item.data(2) or {}
                start = data.get("start")
                end = data.get("end")
                control = data.get("control")
                if isinstance(start, QPointF) and isinstance(end, QPointF):
                    data["start"] = QPointF(start.x() + dx, start.y() + dy)
                    data["end"] = QPointF(end.x() + dx, end.y() + dy)
                if isinstance(control, QPointF):
                    data["control"] = QPointF(control.x() + dx, control.y() + dy)
                item.setData(2, data)
        if update_selection:
            self._update_selection_outline()

    def move_atoms(
        self,
        atom_ids: set[int],
        dx: float,
        dy: float,
        bond_ids: set[int] | None = None,
        redraw_bond_ids: set[int] | None = None,
        update_selection: bool = True,
    ) -> None:
        if not atom_ids:
            return
        for atom_id in atom_ids:
            self._move_atom(atom_id, dx, dy)
        use_bond_sets = bond_ids is not None or redraw_bond_ids is not None
        if use_bond_sets:
            if bond_ids:
                for bond_id in bond_ids:
                    for item in self.bond_items.get(bond_id, []):
                        item.moveBy(dx, dy)
            if redraw_bond_ids:
                for bond_id in redraw_bond_ids:
                    self.update_bond_geometry(bond_id)
        else:
            self._redraw_bonds_for_atoms(atom_ids)
        self._move_rings_for_atoms(atom_ids, dx, dy)
        if update_selection:
            self._update_selection_outline()

    def _move_rings_for_atoms(self, atom_ids: set[int], dx: float, dy: float) -> None:
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if not any(atom_id in atom_ids for atom_id in ring_atom_ids):
                continue
            polygon = ring_item.polygon()
            shifted = QPolygonF()
            for point in polygon:
                shifted.append(QPointF(point.x() + dx, point.y() + dy))
            ring_item.setPolygon(shifted)

    def _move_atom(self, atom_id: int, dx: float, dy: float) -> None:
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return
        atom.x += dx
        atom.y += dy
        if atom_id in self.atom_coords_3d:
            x, y, z = self.atom_coords_3d[atom_id]
            self.atom_coords_3d[atom_id] = (x + dx, y + dy, z)
        label = self.atom_items.get(atom_id)
        if label is not None:
            label.moveBy(dx, dy)
        dot = self.atom_dots.get(atom_id)
        if dot is not None:
            dot.moveBy(dx, dy)

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
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self._bond_offset_unit_3d(a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self.renderer.style.bond_spacing_px
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]
        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        segments = []
        for offset in offsets:
            ox = nx * offset
            oy = ny * offset
            segments.append((base_x1 + ox, base_y1 + oy, base_x2 + ox, base_y2 + oy))
        return segments

    def _wedge_polygon(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        a_id: int | None = None,
        b_id: int | None = None,
    ) -> QPolygonF:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        x1 = x1 + dx * t0
        y1 = y1 + dy * t0
        x2 = x1 + dx * (t1 - t0)
        y2 = y1 + dy * (t1 - t0)
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        half_width = self.renderer.bold_bond_pen().widthF() / 2.0
        p1 = QPointF(x1, y1)
        p2 = QPointF(x2 + nx * half_width, y2 + ny * half_width)
        p3 = QPointF(x2 - nx * half_width, y2 - ny * half_width)
        return QPolygonF([p1, p2, p3])

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
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        x1 = x1 + dx * t0
        y1 = y1 + dy * t0
        x2 = x1 + dx * (t1 - t0)
        y2 = y1 + dy * (t1 - t0)
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        max_size = self.renderer.bold_bond_pen().widthF()
        max_t = count / (count + 1) if count > 0 else 1.0
        segments = []
        for i in range(count):
            t = (i + 1) / (count + 1)
            cx = x1 + dx * t
            cy = y1 + dy * t
            size = max_size * (t / max_t) if max_t > 0 else max_size
            hx = nx * size / 2.0
            hy = ny * size / 2.0
            segments.append((cx - hx, cy - hy, cx + hx, cy + hy))
        return segments

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
        half_base = base_width / 2.0
        inner_offset = half_base + max(0.0, bold_width - base_width)
        outer_offset = -half_base
        return QPolygonF(
            [
                QPointF(x1 + nx * outer_offset, y1 + ny * outer_offset),
                QPointF(x2 + nx * outer_offset, y2 + ny * outer_offset),
                QPointF(x2 + nx * inner_offset, y2 + ny * inner_offset),
                QPointF(x1 + nx * inner_offset, y1 + ny * inner_offset),
            ]
        )

    def _ring_double_segments(
        self,
        a,
        b,
        center: QPointF,
        a_id: int | None = None,
        b_id: int | None = None,
        center_3d: tuple[float, float, float] | None = None,
    ) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float], tuple[float, float]]:
        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        ux = dx / length
        uy = dy / length
        nx = -dy / length
        ny = dx / length
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self._bond_offset_unit_3d(
                a_id,
                b_id,
                target=center_3d,
            )
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
            if center_3d is None:
                mid_x = (a.x + b.x) / 2.0
                mid_y = (a.y + b.y) / 2.0
                to_cx = center.x() - mid_x
                to_cy = center.y() - mid_y
                if nx * to_cx + ny * to_cy < 0:
                    nx = -nx
                    ny = -ny
        else:
            mid_x = (a.x + b.x) / 2.0
            mid_y = (a.y + b.y) / 2.0
            to_cx = center.x() - mid_x
            to_cy = center.y() - mid_y
            if nx * to_cx + ny * to_cy < 0:
                nx = -nx
                ny = -ny

        spacing = self.renderer.style.bond_spacing_px * 1.1
        t0, t1 = self._trim_line_for_labels(a_id, b_id, a.x, a.y, b.x, b.y)
        base_bx1 = a.x + dx * t0
        base_by1 = a.y + dy * t0
        base_bx2 = a.x + dx * t1
        base_by2 = a.y + dy * t1

        inner_length = math.hypot(base_bx2 - base_bx1, base_by2 - base_by1) or 1.0
        has_label = False
        if a_id is not None and self._label_rect_for_atom(a_id) is not None:
            has_label = True
        if b_id is not None and self._label_rect_for_atom(b_id) is not None:
            has_label = True
        if has_label:
            inner_trim = max(0.6, inner_length * 0.08)
        else:
            inner_trim = max(1.0, inner_length * 0.12)
        inner_x1 = base_bx1 + ux * inner_trim + nx * spacing
        inner_y1 = base_by1 + uy * inner_trim + ny * spacing
        inner_x2 = base_bx2 - ux * inner_trim + nx * spacing
        inner_y2 = base_by2 - uy * inner_trim + ny * spacing
        return (base_bx1, base_by1, base_bx2, base_by2), (inner_x1, inner_y1, inner_x2, inner_y2), (nx, ny)

    def update_bond_geometry(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        items = self.bond_items.get(bond_id, [])
        if not items:
            return
        a = self.model.atoms.get(bond.a)
        b = self.model.atoms.get(bond.b)
        if a is None or b is None:
            return
        if bond.style == "wedge":
            polygon = self._wedge_polygon(a.x, a.y, b.x, b.y, bond.a, bond.b)
            if isinstance(items[0], QGraphicsPolygonItem):
                items[0].setPolygon(polygon)
            return
        if bond.style == "hash":
            count = len(items)
            segments = self._hash_segments(a.x, a.y, b.x, b.y, count, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return

        bold_style = bond.style in {"bold", "bold_in", "bold_out"}
        bold_outward = bond.style == "bold_out"
        if bold_style:
            if bond.order >= 2:
                ring_center = self._ring_center_for_bond(bond) if bond.order == 2 else None
                if bond.order == 2 and ring_center is not None and len(items) >= 2:
                    ring_center_3d = self._ring_center_3d_for_bond(bond)
                    outer_seg, inner_seg, (nx, ny) = self._ring_double_segments(
                        a, b, ring_center, bond.a, bond.b, center_3d=ring_center_3d
                    )
                    use_nx, use_ny = (nx, ny) if not bold_outward else (-nx, -ny)
                    outer_item = items[0]
                    if isinstance(outer_item, QGraphicsPolygonItem):
                        polygon = self._strip_polygon(
                            *outer_seg,
                            use_nx,
                            use_ny,
                            self.renderer.style.bond_line_width,
                            self.renderer.style.bold_bond_width * 1.5,
                        )
                        outer_item.setPolygon(polygon)
                    elif isinstance(outer_item, QGraphicsLineItem):
                        outer_item.setLine(*outer_seg)
                    inner_item = items[1]
                    if isinstance(inner_item, QGraphicsLineItem):
                        inner_item.setLine(*inner_seg)
                    return
                segments = self._parallel_bond_segments(
                    a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b
                )
                if not segments:
                    return
                if isinstance(items[0], QGraphicsPolygonItem):
                    x1, y1, x2, y2 = segments[0]
                    nx, ny = self._line_normal(x1, y1, x2, y2, None)
                    if bold_outward:
                        nx, ny = -nx, -ny
                    polygon = self._strip_polygon(
                        x1,
                        y1,
                        x2,
                        y2,
                        nx,
                        ny,
                        self.renderer.style.bond_line_width,
                        self.renderer.style.bold_bond_width * 1.5,
                    )
                    items[0].setPolygon(polygon)
                elif isinstance(items[0], QGraphicsLineItem):
                    items[0].setLine(*segments[0])
                for item, seg in zip(items[1:], segments[1:]):
                    if isinstance(item, QGraphicsLineItem):
                        item.setLine(*seg)
                return
            t0, t1 = self._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
            bx1 = a.x + (b.x - a.x) * t0
            by1 = a.y + (b.y - a.y) * t0
            bx2 = a.x + (b.x - a.x) * t1
            by2 = a.y + (b.y - a.y) * t1
            ring_center = self._ring_center_for_bond(bond)
            nx, ny = self._line_normal(bx1, by1, bx2, by2, ring_center)
            if bold_outward:
                nx, ny = -nx, -ny
            if isinstance(items[0], QGraphicsPolygonItem):
                polygon = self._strip_polygon(
                    bx1,
                    by1,
                    bx2,
                    by2,
                    nx,
                    ny,
                    self.renderer.style.bond_line_width,
                    self.renderer.style.bold_bond_width * 1.5,
                )
                items[0].setPolygon(polygon)
            elif isinstance(items[0], QGraphicsLineItem):
                items[0].setLine(bx1, by1, bx2, by2)
            return

        if bond.order == 2:
            ring_center = self._ring_center_for_bond(bond)
            if ring_center is not None and len(items) >= 2:
                ring_center_3d = self._ring_center_3d_for_bond(bond)
                outer_seg, inner_seg, _ = self._ring_double_segments(
                    a, b, ring_center, bond.a, bond.b, center_3d=ring_center_3d
                )
                if isinstance(items[0], QGraphicsLineItem):
                    items[0].setLine(*outer_seg)
                if isinstance(items[1], QGraphicsLineItem):
                    items[1].setLine(*inner_seg)
                return
            segments = self._parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return
        if bond.order >= 2:
            segments = self._parallel_bond_segments(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
            for item, seg in zip(items, segments):
                if isinstance(item, QGraphicsLineItem):
                    item.setLine(*seg)
            return

        t0, t1 = self._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
        x1 = a.x + (b.x - a.x) * t0
        y1 = a.y + (b.y - a.y) * t0
        x2 = a.x + (b.x - a.x) * t1
        y2 = a.y + (b.y - a.y) * t1
        if isinstance(items[0], QGraphicsLineItem):
            items[0].setLine(x1, y1, x2, y2)

    def _redraw_connected_bonds(self, atom_id: int) -> None:
        for bond_id, bond in enumerate(self.model.bonds):
            if bond is None:
                continue
            if bond.a == atom_id or bond.b == atom_id:
                self._redraw_bond(bond_id)

    def _redraw_bond(self, bond_id: int) -> None:
        selected = any(item.isSelected() for item in self.bond_items.get(bond_id, []))
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items[bond_id] = []
        self._add_bond_graphics(bond_id)
        if selected:
            for item in self.bond_items.get(bond_id, []):
                item.setSelected(True)

    def delete_atom(self, atom_id: int, record: bool = True) -> None:
        if not isinstance(atom_id, int):
            return
        self.last_smiles_input = None
        label = self.atom_items.pop(atom_id, None)
        if label is not None:
            self.scene().removeItem(label)
        dot = self.atom_dots.pop(atom_id, None)
        if dot is not None:
            self.scene().removeItem(dot)
        bonds_to_remove = [
            i for i, bond in enumerate(self.model.bonds)
            if bond is not None and (bond.a == atom_id or bond.b == atom_id)
        ]
        for bond_id in sorted(bonds_to_remove, reverse=True):
            self.delete_bond(bond_id, record=False)
        self.model.atoms.pop(atom_id, None)
        self.atom_coords_3d.pop(atom_id, None)
        self.atom_plane_normals.pop(atom_id, None)
        if record:
            self._push_history()

    def delete_bond(self, bond_id: int, record: bool = True) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        self.last_smiles_input = None
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items.pop(bond_id, None)
        self.model.bonds[bond_id] = None
        if record:
            self._push_history()

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> None:
        if item in self.ring_items:
            self.ring_items.remove(item)
        self.scene().removeItem(item)
        if record:
            self._push_history()

    def flip_bond_direction(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        if bond.style not in {"wedge", "hash"}:
            return
        bond.a, bond.b = bond.b, bond.a
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items[bond_id] = []
        self._add_bond_graphics(bond_id)

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        bond.style = style
        bond.order = order
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items[bond_id] = []
        self._add_bond_graphics(bond_id)
        self._push_history()

    def cycle_bond_style(self, bond_id: int) -> None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        cycle = ["single", "double", "triple"]
        next_style = cycle[(cycle.index(bond.style) + 1) % len(cycle)] if bond.style in cycle else "single"
        bond.style = next_style
        bond.order = {"single": 1, "double": 2, "triple": 3}[next_style]
        for item in self.bond_items.get(bond_id, []):
            self.scene().removeItem(item)
        self.bond_items[bond_id] = []
        self._add_bond_graphics(bond_id)

    def _add_bond_graphics(self, bond_id: int) -> None:
        bond = self.model.bonds[bond_id]
        if bond is None:
            return
        a = self.model.atoms[bond.a]
        b = self.model.atoms[bond.b]
        items = []
        color = QColor(bond.color or self.renderer.style.bond_color)
        if bond.style == "wedge":
            items = self._draw_wedge_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        elif bond.style == "hash":
            items = self._draw_hash_bond(a.x, a.y, b.x, b.y, bond.a, bond.b)
        elif bond.style in {"bold", "bold_in", "bold_out"}:
            bold_outward = bond.style == "bold_out"
            if bond.order >= 2:
                handled_outer = False
                if bond.order == 2:
                    ring_center = self._ring_center_for_bond(bond)
                    if ring_center is not None:
                        ring_center_3d = self._ring_center_3d_for_bond(bond)
                        outer_style = "bold_outward" if bold_outward else "bold_inward"
                        items = self._draw_ring_double_bond(
                            a,
                            b,
                            ring_center,
                            bond.a,
                            bond.b,
                            outer_style=outer_style,
                            center_3d=ring_center_3d,
                        )
                        handled_outer = True
                    else:
                        items = self._draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
                else:
                    items = self._draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
                if items and not handled_outer:
                    bold_line = items[0]
                    if isinstance(bold_line, QGraphicsLineItem):
                        line = bold_line.line()
                        nx, ny = self._line_normal(line.x1(), line.y1(), line.x2(), line.y2(), None)
                        if bold_outward:
                            nx, ny = -nx, -ny
                        items[0] = self._one_sided_bond_strip(
                            line.x1(),
                            line.y1(),
                            line.x2(),
                            line.y2(),
                            nx,
                            ny,
                            self.renderer.style.bond_line_width,
                            self.renderer.style.bold_bond_width * 1.5,
                        )
            else:
                t0, t1 = self._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
                ring_center = self._ring_center_for_bond(bond)
                bx1 = a.x + (b.x - a.x) * t0
                by1 = a.y + (b.y - a.y) * t0
                bx2 = a.x + (b.x - a.x) * t1
                by2 = a.y + (b.y - a.y) * t1
                nx, ny = self._line_normal(bx1, by1, bx2, by2, ring_center)
                if bold_outward:
                    nx, ny = -nx, -ny
                line_item = self._one_sided_bond_strip(
                    bx1,
                    by1,
                    bx2,
                    by2,
                    nx,
                    ny,
                    self.renderer.style.bond_line_width,
                    self.renderer.style.bold_bond_width * 1.5,
                )
                items = [line_item]
        elif bond.order == 2:
            ring_center = self._ring_center_for_bond(bond)
            if ring_center is not None:
                ring_center_3d = self._ring_center_3d_for_bond(bond)
                items = self._draw_ring_double_bond(
                    a,
                    b,
                    ring_center,
                    bond.a,
                    bond.b,
                    center_3d=ring_center_3d,
                )
            else:
                items = self._draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        elif bond.order >= 2:
            items = self._draw_parallel_bonds(a.x, a.y, b.x, b.y, bond.order, bond.a, bond.b)
        else:
            t0, t1 = self._trim_line_for_labels(bond.a, bond.b, a.x, a.y, b.x, b.y)
            line_item = NoSelectLineItem(a.x + (b.x - a.x) * t0, a.y + (b.y - a.y) * t0, a.x + (b.x - a.x) * t1, a.y + (b.y - a.y) * t1)
            line_item.setPen(self.renderer.bond_pen())
            items = [line_item]

        for item in items:
            item.setData(0, "bond")
            item.setData(1, bond_id)
            self._make_selectable(item)
            self._apply_color_to_bond_item(item, color)
            self.scene().addItem(item)
        self.bond_items[bond_id] = items
    def _ring_center_for_bond(self, bond) -> QPointF | None:
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                xs = []
                ys = []
                for atom_id in ring_atom_ids:
                    atom = self.model.atoms.get(atom_id)
                    if atom is None:
                        continue
                    xs.append(atom.x)
                    ys.append(atom.y)
                if xs and ys:
                    return QPointF(sum(xs) / len(xs), sum(ys) / len(ys))
        return None

    def _ring_center_3d_for_bond(self, bond) -> tuple[float, float, float] | None:
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                coords = []
                for atom_id in ring_atom_ids:
                    coord = self.atom_coords_3d.get(atom_id)
                    if coord is not None:
                        coords.append(coord)
                if len(coords) < 3:
                    return None
                sum_x = sum(c[0] for c in coords)
                sum_y = sum(c[1] for c in coords)
                sum_z = sum(c[2] for c in coords)
                count = len(coords)
                return (sum_x / count, sum_y / count, sum_z / count)
        return None

    def _ring_for_bond(self, bond_id: int) -> QGraphicsPolygonItem | None:
        if not (0 <= bond_id < len(self.model.bonds)):
            return None
        bond = self.model.bonds[bond_id]
        if bond is None:
            return None
        for ring_item in self.ring_items:
            ring_atom_ids = ring_item.data(2)
            if not isinstance(ring_atom_ids, list):
                continue
            if bond.a in ring_atom_ids and bond.b in ring_atom_ids:
                return ring_item
        return None

    def _label_rect_for_atom(self, atom_id: int) -> QRectF | None:
        item = self.atom_items.get(atom_id)
        if item is None:
            return None
        rect = item.sceneBoundingRect()
        pad = max(0.05, self.renderer.style.bond_line_width * 0.05)
        return rect.adjusted(-pad, -pad, pad, pad)

    def _label_cut_radius_for_atom(self, atom_id: int) -> float | None:
        item = self.atom_items.get(atom_id)
        if item is None:
            return None
        rect = item.sceneBoundingRect()
        atom = self.model.atoms.get(atom_id)
        if atom is None:
            return None
        corners = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
        ]
        max_dist = 0.0
        for corner in corners:
            max_dist = max(max_dist, math.hypot(corner.x() - atom.x, corner.y() - atom.y))
        pad = max(0.02, self.renderer.style.bond_line_width * 0.03)
        return (max_dist + pad) * 0.6

    def _line_rect_clip_t(self, p1: QPointF, p2: QPointF, rect: QRectF) -> tuple[float, float] | None:
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        p = [-dx, dx, -dy, dy]
        q = [
            p1.x() - rect.left(),
            rect.right() - p1.x(),
            p1.y() - rect.top(),
            rect.bottom() - p1.y(),
        ]
        u1 = 0.0
        u2 = 1.0
        for pi, qi in zip(p, q):
            if abs(pi) < 1e-9:
                if qi < 0:
                    return None
                continue
            t = qi / pi
            if pi < 0:
                u1 = max(u1, t)
            else:
                u2 = min(u2, t)
            if u1 > u2:
                return None
        return u1, u2

    def _segment_intersection_t(self, p1: QPointF, p2: QPointF, q1: QPointF, q2: QPointF) -> float | None:
        r = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
        s = QPointF(q2.x() - q1.x(), q2.y() - q1.y())
        denom = r.x() * s.y() - r.y() * s.x()
        if abs(denom) < 1e-8:
            return None
        q_p = QPointF(q1.x() - p1.x(), q1.y() - p1.y())
        t = (q_p.x() * s.y() - q_p.y() * s.x()) / denom
        u = (q_p.x() * r.y() - q_p.y() * r.x()) / denom
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return t
        return None

    def _line_rect_intersections(self, p1: QPointF, p2: QPointF, rect: QRectF) -> list[float]:
        tl = rect.topLeft()
        tr = rect.topRight()
        br = rect.bottomRight()
        bl = rect.bottomLeft()
        edges = [(tl, tr), (tr, br), (br, bl), (bl, tl)]
        hits = []
        for a, b in edges:
            t = self._segment_intersection_t(p1, p2, a, b)
            if t is not None:
                hits.append(t)
        return hits

    def _trim_line_for_labels(
        self,
        a_id: int | None,
        b_id: int | None,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> tuple[float, float]:
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            return 0.0, 1.0
        t0 = 0.0
        t1 = 1.0
        p1 = QPointF(x1, y1)
        p2 = QPointF(x2, y2)
        hit_start = False
        hit_end = False
        for atom_id, is_start in ((a_id, True), (b_id, False)):
            if atom_id is None:
                continue
            radius = self._label_cut_radius_for_atom(atom_id)
            if radius is None:
                continue
            t_hit = min(1.0, radius / length)
            if is_start:
                t0 = max(t0, t_hit)
                hit_start = True
            else:
                t1 = min(t1, 1.0 - t_hit)
                hit_end = True
        if hit_start or hit_end:
            gap_t = (self.renderer.style.bond_line_width * 0.02) / length
            if hit_start:
                t0 = min(1.0, t0 + gap_t)
            if hit_end:
                t1 = max(0.0, t1 - gap_t)
        min_span = 0.02
        if t1 - t0 < min_span:
            if hit_start and not hit_end:
                t0 = max(0.0, t1 - min_span)
            elif hit_end and not hit_start:
                t1 = min(1.0, t0 + min_span)
            else:
                mid = (t0 + t1) / 2.0
                t0 = max(0.0, mid - min_span / 2.0)
                t1 = min(1.0, mid + min_span / 2.0)
        return t0, t1


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
        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        ux = dx / length
        uy = dy / length
        nx = -dy / length
        ny = dx / length
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self._bond_offset_unit_3d(
                a_id,
                b_id,
                target=center_3d,
            )
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
            if center_3d is None:
                mid_x = (a.x + b.x) / 2.0
                mid_y = (a.y + b.y) / 2.0
                to_cx = center.x() - mid_x
                to_cy = center.y() - mid_y
                if nx * to_cx + ny * to_cy < 0:
                    nx = -nx
                    ny = -ny
        else:
            mid_x = (a.x + b.x) / 2.0
            mid_y = (a.y + b.y) / 2.0
            to_cx = center.x() - mid_x
            to_cy = center.y() - mid_y
            if nx * to_cx + ny * to_cy < 0:
                nx = -nx
                ny = -ny

        spacing = self.renderer.style.bond_spacing_px * 1.1
        trim = max(1.5, length * 0.12)
        inner_x1 = a.x + ux * trim + nx * spacing
        inner_y1 = a.y + uy * trim + ny * spacing
        inner_x2 = b.x - ux * trim + nx * spacing
        inner_y2 = b.y - uy * trim + ny * spacing

        t0, t1 = self._trim_line_for_labels(a_id, b_id, a.x, a.y, b.x, b.y)
        base_bx1 = a.x + dx * t0
        base_by1 = a.y + dy * t0
        base_bx2 = a.x + dx * t1
        base_by2 = a.y + dy * t1
        if outer_style in {"bold_inward", "bold_outward"}:
            use_nx, use_ny = (nx, ny) if outer_style == "bold_inward" else (-nx, -ny)
            outer_item = self._one_sided_bond_strip(
                base_bx1,
                base_by1,
                base_bx2,
                base_by2,
                use_nx,
                use_ny,
                self.renderer.style.bond_line_width,
                self.renderer.style.bold_bond_width * 1.5,
            )
        else:
            outer_item = NoSelectLineItem(base_bx1, base_by1, base_bx2, base_by2)
            outer_item.setPen(self.renderer.bond_pen())
        inner_length = math.hypot(base_bx2 - base_bx1, base_by2 - base_by1) or 1.0
        has_label = False
        if a_id is not None and self._label_rect_for_atom(a_id) is not None:
            has_label = True
        if b_id is not None and self._label_rect_for_atom(b_id) is not None:
            has_label = True
        if has_label:
            inner_trim = max(0.6, inner_length * 0.08)
        else:
            inner_trim = max(1.0, inner_length * 0.12)
        inner_x1 = base_bx1 + ux * inner_trim + nx * spacing
        inner_y1 = base_by1 + uy * inner_trim + ny * spacing
        inner_x2 = base_bx2 - ux * inner_trim + nx * spacing
        inner_y2 = base_by2 - uy * inner_trim + ny * spacing
        inner_line = NoSelectLineItem(inner_x1, inner_y1, inner_x2, inner_y2)
        inner_line.setPen(self.renderer.bond_pen())
        return [outer_item, inner_line]

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
        if bold_width <= base_width + 1e-6:
            line_item = NoSelectLineItem(x1, y1, x2, y2)
            line_item.setPen(self.renderer.bond_pen())
            return line_item
        half_base = base_width / 2.0
        inner_offset = half_base + max(0.0, bold_width - base_width)
        outer_offset = -half_base
        polygon = QPolygonF(
            [
                QPointF(x1 + nx * outer_offset, y1 + ny * outer_offset),
                QPointF(x2 + nx * outer_offset, y2 + ny * outer_offset),
                QPointF(x2 + nx * inner_offset, y2 + ny * inner_offset),
                QPointF(x1 + nx * inner_offset, y1 + ny * inner_offset),
            ]
        )
        item = NoSelectPolygonItem(polygon)
        item.setPen(QPen(Qt.PenStyle.NoPen))
        item.setBrush(QBrush(QColor(self.renderer.style.bond_color)))
        return item

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

    @staticmethod
    def _plane_normal_from_angles(angle_x: float, angle_y: float) -> tuple[float, float, float]:
        sin_y = math.sin(angle_y)
        cos_y = math.cos(angle_y)
        sin_x = math.sin(angle_x)
        cos_x = math.cos(angle_x)
        nx = sin_y
        ny = -cos_y * sin_x
        nz = cos_y * cos_x
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        return nx / length, ny / length, nz / length

    def _plane_normal_for_atoms(self, a_id: int, b_id: int) -> tuple[float, float, float] | None:
        if a_id in self.rotation_atom_ids and b_id in self.rotation_atom_ids:
            if self._rotation_plane_normal is not None:
                return self._rotation_plane_normal
        normal_a = self.atom_plane_normals.get(a_id)
        normal_b = self.atom_plane_normals.get(b_id)
        if normal_a is None or normal_b is None:
            return None
        dot = normal_a[0] * normal_b[0] + normal_a[1] * normal_b[1] + normal_a[2] * normal_b[2]
        if dot < 0.0:
            normal_b = (-normal_b[0], -normal_b[1], -normal_b[2])
            dot = -dot
        if dot < 0.95:
            return None
        nx = normal_a[0] + normal_b[0]
        ny = normal_a[1] + normal_b[1]
        nz = normal_a[2] + normal_b[2]
        length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        return nx / length, ny / length, nz / length

    def _bond_offset_unit_3d(
        self,
        a_id: int,
        b_id: int,
        target: tuple[float, float, float] | None = None,
    ) -> tuple[float, float, float] | None:
        coords_a = self.atom_coords_3d.get(a_id)
        coords_b = self.atom_coords_3d.get(b_id)
        if coords_a is None or coords_b is None:
            return None
        plane_normal = self._plane_normal_for_atoms(a_id, b_id)
        if plane_normal is None:
            return None
        vx = coords_b[0] - coords_a[0]
        vy = coords_b[1] - coords_a[1]
        vz = coords_b[2] - coords_a[2]
        vlen = math.sqrt(vx * vx + vy * vy + vz * vz)
        if vlen < 1e-6:
            return None
        vx /= vlen
        vy /= vlen
        vz /= vlen
        ox = plane_normal[1] * vz - plane_normal[2] * vy
        oy = plane_normal[2] * vx - plane_normal[0] * vz
        oz = plane_normal[0] * vy - plane_normal[1] * vx
        olen = math.sqrt(ox * ox + oy * oy + oz * oz)
        if olen < 1e-6:
            return None
        ox /= olen
        oy /= olen
        oz /= olen
        if target is not None:
            mx = (coords_a[0] + coords_b[0]) * 0.5
            my = (coords_a[1] + coords_b[1]) * 0.5
            mz = (coords_a[2] + coords_b[2]) * 0.5
            tx = target[0] - mx
            ty = target[1] - my
            tz = target[2] - mz
            if ox * tx + oy * ty + oz * tz < 0.0:
                ox = -ox
                oy = -oy
                oz = -oz
        return ox, oy, oz

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
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        offset_unit = None
        if a_id is not None and b_id is not None:
            offset_unit = self._bond_offset_unit_3d(a_id, b_id)
        if offset_unit is not None:
            nx, ny = offset_unit[0], offset_unit[1]
        else:
            nx = -dy / length
            ny = dx / length
        spacing = self.renderer.style.bond_spacing_px
        offsets = []
        if count == 2:
            offsets = [-spacing / 2, spacing / 2]
        elif count == 3:
            offsets = [-spacing, 0.0, spacing]
        else:
            offsets = [0.0]

        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        base_x1 = x1 + dx * t0
        base_y1 = y1 + dy * t0
        base_x2 = x1 + dx * t1
        base_y2 = y1 + dy * t1
        items = []
        for offset in offsets:
            ox = nx * offset
            oy = ny * offset
            line_item = NoSelectLineItem(base_x1 + ox, base_y1 + oy, base_x2 + ox, base_y2 + oy)
            line_item.setPen(self.renderer.bond_pen())
            items.append(line_item)
        return items

    def _draw_wedge_bond(self, x1: float, y1: float, x2: float, y2: float, a_id: int | None = None, b_id: int | None = None):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        x1 = x1 + dx * t0
        y1 = y1 + dy * t0
        x2 = x1 + dx * (t1 - t0)
        y2 = y1 + dy * (t1 - t0)
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        half_width = self.renderer.bold_bond_pen().widthF() / 2.0
        p1 = QPointF(x1, y1)
        p2 = QPointF(x2 + nx * half_width, y2 + ny * half_width)
        p3 = QPointF(x2 - nx * half_width, y2 - ny * half_width)
        polygon = QPolygonF([p1, p2, p3])
        wedge_item = NoSelectPolygonItem(polygon)
        wedge_item.setPen(self.renderer.bond_pen())
        wedge_item.setBrush(QColor(self.renderer.style.bond_color))
        return [wedge_item]

    def _draw_hash_bond(self, x1: float, y1: float, x2: float, y2: float, a_id: int | None = None, b_id: int | None = None):
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        t0, t1 = self._trim_line_for_labels(a_id, b_id, x1, y1, x2, y2)
        x1 = x1 + dx * t0
        y1 = y1 + dy * t0
        x2 = x1 + dx * (t1 - t0)
        y2 = y1 + dy * (t1 - t0)
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) or 1.0
        nx = -dy / length
        ny = dx / length
        count = max(3, int(length / self.renderer.style.hash_spacing_px))
        max_size = self.renderer.bold_bond_pen().widthF()
        max_t = count / (count + 1)
        items = []
        for i in range(count):
            t = (i + 1) / (count + 1)
            cx = x1 + dx * t
            cy = y1 + dy * t
            size = max_size * (t / max_t) if max_t > 0 else max_size
            hx = nx * size / 2.0
            hy = ny * size / 2.0
            line_item = NoSelectLineItem(cx - hx, cy - hy, cx + hx, cy + hy)
            line_item.setPen(self.renderer.bond_pen())
            items.append(line_item)
        return items

    def _apply_color_to_bond_item(self, item, color: QColor) -> None:
        if hasattr(item, "setPen"):
            pen = item.pen()
            pen.setColor(color)
            item.setPen(pen)
        if hasattr(item, "setBrush") and item.brush().style() != Qt.BrushStyle.NoBrush:
            item.setBrush(color)
