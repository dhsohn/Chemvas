from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPainterPathStroker, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsTextItem,
)

from ui.graphics_items import NoSelectEllipseItem, NoSelectPathItem
from ui.selection_hit_logic import (
    AtomHitCandidate,
    BondHitCandidate,
    SelectionHitRequest,
    SelectionRect,
    StructureHit,
    choose_preferred_structure_hit,
    nearest_ring_atom_id,
    selection_hit_matches,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class SelectionController:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def _atom_item_for_id(self, atom_id: int):
        return self.canvas.atom_items.get(atom_id) or self.canvas.atom_dots.get(atom_id)

    def _nearest_atom_hit(self, pos: QPointF) -> tuple[int, float] | None:
        atom_id = self.canvas.find_atom_near(pos.x(), pos.y(), self.canvas._atom_pick_radius())
        if atom_id is None:
            return None
        atom = self.canvas.model.atoms.get(atom_id)
        if atom is None:
            return None
        return atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y())

    def _nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        bond_id = self.canvas._find_bond_near(pos, self.canvas._bond_pick_radius())
        if bond_id is None or not (0 <= bond_id < len(self.canvas.model.bonds)):
            return None
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return None
        atom_a = self.canvas.model.atoms.get(bond.a)
        atom_b = self.canvas.model.atoms.get(bond.b)
        if atom_a is None or atom_b is None:
            return None
        dist = self.canvas._distance_point_to_segment(
            pos,
            QPointF(atom_a.x, atom_a.y),
            QPointF(atom_b.x, atom_b.y),
        )
        return bond_id, dist

    def _structure_hit_from_item(self, item) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
        if item is None:
            return None, None, None
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if isinstance(atom_id, int):
                return StructureHit(kind="atom", id=atom_id), None, None
            return None, None, None
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int) and 0 <= bond_id < len(self.canvas.model.bonds):
                bond = self.canvas.model.bonds[bond_id]
                if bond is not None:
                    return StructureHit(kind="bond", id=bond_id), (bond.a, bond.b), None
            return None, None, None
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                return StructureHit(kind="ring"), None, ring_atom_ids
            return StructureHit(kind="ring"), None, None
        return StructureHit(kind="other"), None, None

    def _structure_item_for_hit(self, hit: StructureHit):
        if hit.kind == "atom" and isinstance(hit.id, int):
            return self._atom_item_for_id(hit.id)
        if hit.kind == "bond" and isinstance(hit.id, int):
            bond_items = self.canvas.bond_items.get(hit.id, [])
            if bond_items:
                return bond_items[0]
        return None

    def _selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        if item is None:
            return []
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if not isinstance(atom_id, int):
                return []
            atom_item = self._atom_item_for_id(atom_id)
            return [atom_item] if atom_item is not None else []
        if kind == "bond":
            bond_id = item.data(1)
            if not isinstance(bond_id, int):
                return []
            return [bond_item for bond_item in self.canvas.bond_items.get(bond_id, []) if bond_item is not None]
        if kind in {
            "ring",
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "ts_bracket",
            "orbital",
            "mark",
            "note",
        }:
            return [item]
        return []

    def toggle_item_selection(self, item) -> bool:
        targets = self._selection_targets_for_item(item)
        if not targets:
            return False
        should_select = not any(target.isSelected() for target in targets)
        self.canvas.scene().blockSignals(True)
        try:
            for target in targets:
                target.setSelected(should_select)
        finally:
            self.canvas.scene().blockSignals(False)
        self.update_selection_outline()
        return True

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        item = self.canvas.item_at_scene_pos(pos)
        item_hit, _, _ = self._structure_hit_from_item(item)
        if item_hit is not None and item_hit.kind == "atom":
            return item_hit
        atom_hit = self._nearest_atom_hit(pos)
        bond_hit = self._nearest_bond_hit(pos)
        preferred_hit = choose_preferred_structure_hit(
            AtomHitCandidate(
                atom_id=atom_hit[0],
                distance=atom_hit[1],
                has_visible_label=self.canvas._atom_has_visible_label(atom_hit[0]),
            )
            if atom_hit is not None
            else None,
            BondHitCandidate(bond_id=bond_hit[0], distance=bond_hit[1]) if bond_hit is not None else None,
            atom_pick_radius=self.canvas._atom_pick_radius(),
            bond_pick_radius=self.canvas._bond_pick_radius(),
        )
        if preferred_hit is not None:
            preferred_item = self._structure_item_for_hit(preferred_hit)
            if preferred_item is not None:
                return preferred_hit
        if item is not None and item.data(0) == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                nearest_atom_id = nearest_ring_atom_id(
                    [
                        (atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y()))
                        for atom_id in ring_atom_ids
                        for atom in [self.canvas.model.atoms.get(atom_id)]
                        if atom is not None
                    ],
                    max_distance=self.canvas.renderer.style.bond_length_px * 0.4,
                )
                if nearest_atom_id is not None:
                    ring_atom_item = self.canvas.atom_items.get(nearest_atom_id) or self.canvas.atom_dots.get(
                        nearest_atom_id
                    )
                    if ring_atom_item is not None:
                        return StructureHit(kind="atom", id=nearest_atom_id)
            return StructureHit(kind="ring")
        fallback_hit, _, _ = self._structure_hit_from_item(item)
        return fallback_hit

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        hit = self.preferred_structure_hit_at_scene_pos(pos)
        if hit is None:
            return None
        if hit.kind in {"atom", "bond"}:
            return self._structure_item_for_hit(hit)
        return self.canvas.item_at_scene_pos(pos)

    def _selection_rects_for_snapshot(
        self,
        snapshot,
    ) -> tuple[SelectionRect, ...]:
        rects: list[SelectionRect] = []
        object_overlay_kinds = {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
            "ts_bracket",
            "mark",
            "orbital",
        }
        if snapshot.selected_atom_ids:
            for component in self.canvas._connected_components(set(snapshot.selected_atom_ids)):
                bounds = self.canvas._bounds_for_atoms(component)
                if bounds is None:
                    continue
                min_x, min_y, max_x, max_y = bounds
                rects.append(SelectionRect(left=min_x, top=min_y, right=max_x, bottom=max_y))
        for item in snapshot.selection_items:
            if item.data(0) in {"atom", "bond", "ring"}:
                continue
            if item.data(0) in object_overlay_kinds:
                continue
            rect = item.sceneBoundingRect()
            rects.append(
                SelectionRect(
                    left=rect.left(),
                    top=rect.top(),
                    right=rect.right(),
                    bottom=rect.bottom(),
                )
            )
        return tuple(rects)

    def selection_hit_test(self, pos: QPointF, snapshot=None) -> bool:
        if snapshot is None:
            snapshot = self.canvas._selection_snapshot()
        if snapshot is None:
            return False
        outline_hit = False
        for outline in self.canvas.selection_outlines:
            data = outline.data(2) or {}
            if data.get("kind") not in {"component", "object"}:
                continue
            if outline.contains(outline.mapFromScene(pos)):
                outline_hit = True
                break
        item = self.canvas.item_at_scene_pos(pos)
        hit, bond_atom_ids, ring_atom_ids = self._structure_hit_from_item(item)
        return selection_hit_matches(
            SelectionHitRequest(
                point=(pos.x(), pos.y()),
                outline_hit=outline_hit,
                rects=self._selection_rects_for_snapshot(snapshot),
                pad=self.canvas.renderer.style.bond_length_px * 0.1,
                hit=hit,
                selected_atom_ids=snapshot.selected_atom_ids,
                selected_bond_ids=snapshot.selected_bond_ids,
                bond_atom_ids=bond_atom_ids,
                ring_atom_ids=tuple(ring_atom_ids or ()),
                item_is_selected=bool(item is not None and item.isSelected()),
            )
        )

    def update_selection_outline(self) -> None:
        if self.canvas._suspend_selection_outline:
            return
        items = self.canvas.scene().selectedItems()
        if not items:
            for outline in self.canvas.selection_outlines:
                self.canvas.scene().removeItem(outline)
            self.canvas.selection_outlines = []
            self.canvas._emit_selection_info()
            return
        items = [
            item
            for item in items
            if item.data(0) not in {"handle", "note_box", "note_select", "selection_outline"}
        ]
        if not items:
            return
        explicit_atom_ids, bond_ids = self.canvas._selected_ids()
        atom_ids = set(explicit_atom_ids)
        for bond_id in bond_ids:
            if 0 <= bond_id < len(self.canvas.model.bonds):
                bond = self.canvas.model.bonds[bond_id]
                if bond is not None:
                    atom_ids.add(bond.a)
                    atom_ids.add(bond.b)
        object_items = [
            item
            for item in items
            if item.data(0) in {
                "arrow",
                "equilibrium",
                "resonance",
                "curved_single",
                "curved_double",
                "inhibit",
                "dotted",
                "ts_bracket",
                "mark",
                "orbital",
            }
        ]

        for outline in self.canvas.selection_outlines:
            self.canvas.scene().removeItem(outline)
        self.canvas.selection_outlines = []

        atom_pad = self.canvas.renderer.style.bond_length_px * 0.06
        atom_fill = QColor(self.canvas._selection_color)
        atom_fill.setAlpha(45)
        object_fill = QColor(self.canvas._selection_color)
        object_fill.setAlpha(45)
        overlay_bond_ids = {
            bond_id
            for bond_id, bond in enumerate(self.canvas.model.bonds)
            if bond is not None and bond.a in atom_ids and bond.b in atom_ids
        }
        for component in self.canvas._connected_components(atom_ids):
            component_bond_ids = {
                bond_id
                for bond_id in overlay_bond_ids
                if (bond := self.canvas.model.bonds[bond_id]) is not None
                and bond.a in component
                and bond.b in component
            }
            self._add_selection_component_overlay(component, component_bond_ids, atom_fill, atom_pad)

        center = self._selection_center_for_atoms(atom_ids)
        if center is not None and self._selection_center_marker_enabled():
            self._add_selection_center_marker(center)

        for item in object_items:
            self._add_selection_object_overlay(item, object_fill)
        self.canvas._emit_selection_info()

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        if not self.canvas.selection_outlines:
            return
        for outline in self.canvas.selection_outlines:
            outline.moveBy(dx, dy)

    def _selection_line_stroke_path(
        self,
        start: QPointF,
        end: QPointF,
        width: float,
    ) -> QPainterPath:
        bond_path = QPainterPath(start)
        bond_path.lineTo(end)
        stroker = QPainterPathStroker()
        stroker.setWidth(width)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(bond_path)

    def _selection_path_for_bond_item(self, item, width: float | None = None) -> QPainterPath:
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            start = item.mapToScene(QPointF(line.x1(), line.y1()))
            end = item.mapToScene(QPointF(line.x2(), line.y2()))
            stroke_width = width if width is not None else self.canvas._selection_bond_overlay_width(item.pen())
            return self._selection_line_stroke_path(start, end, stroke_width)
        if isinstance(item, QGraphicsPolygonItem):
            bond_path = QPainterPath()
            bond_path.addPolygon(item.mapToScene(item.polygon()))
            return bond_path
        if isinstance(item, QGraphicsPathItem):
            mapped_path = item.sceneTransform().map(item.path())
            if item.pen().style() == Qt.PenStyle.NoPen and item.brush().style() != Qt.BrushStyle.NoBrush:
                return mapped_path
            stroker = QPainterPathStroker()
            stroker.setWidth(width if width is not None else self.canvas._selection_bond_overlay_width(item.pen()))
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return stroker.createStroke(mapped_path)
        return QPainterPath()

    def _selection_path_for_bond(self, bond_id: int) -> QPainterPath:
        if not (0 <= bond_id < len(self.canvas.model.bonds)):
            return QPainterPath()
        bond = self.canvas.model.bonds[bond_id]
        if bond is None:
            return QPainterPath()
        items = self.canvas.bond_items.get(bond_id, [])
        if not items:
            return QPainterPath()
        ring_center = self.canvas._ring_center_for_bond(bond) if bond.order == 2 else None
        if ring_center is not None:
            outer_path = self._selection_path_for_bond_item(items[0])
            if not outer_path.isEmpty():
                return outer_path
        line_items = [item for item in items if isinstance(item, QGraphicsLineItem)]
        if bond.order >= 2 and line_items and len(line_items) == len(items):
            atom_a = self.canvas.model.atoms.get(bond.a)
            atom_b = self.canvas.model.atoms.get(bond.b)
            if atom_a is not None and atom_b is not None:
                t0, t1 = self.canvas._trim_line_for_labels(bond.a, bond.b, atom_a.x, atom_a.y, atom_b.x, atom_b.y)
                base_x1 = atom_a.x + (atom_b.x - atom_a.x) * t0
                base_y1 = atom_a.y + (atom_b.y - atom_a.y) * t0
                base_x2 = atom_a.x + (atom_b.x - atom_a.x) * t1
                base_y2 = atom_a.y + (atom_b.y - atom_a.y) * t1
                dx = base_x2 - base_x1
                dy = base_y2 - base_y1
                length = math.hypot(dx, dy)
                if length > 1e-6:
                    nx = -dy / length
                    ny = dx / length
                    base_mid = QPointF((base_x1 + base_x2) * 0.5, (base_y1 + base_y2) * 0.5)
                    offsets = []
                    widths = []
                    for item in line_items:
                        line = item.line()
                        mid = item.mapToScene(
                            QPointF((line.x1() + line.x2()) * 0.5, (line.y1() + line.y2()) * 0.5)
                        )
                        offsets.append((mid.x() - base_mid.x()) * nx + (mid.y() - base_mid.y()) * ny)
                        widths.append(self.canvas._selection_bond_overlay_width(item.pen()))
                    axis_shift = (min(offsets) + max(offsets)) * 0.5
                    overlay_width = max(widths)
                    return self._selection_line_stroke_path(
                        QPointF(base_x1 + nx * axis_shift, base_y1 + ny * axis_shift),
                        QPointF(base_x2 + nx * axis_shift, base_y2 + ny * axis_shift),
                        overlay_width,
                    )
        bond_path = QPainterPath()
        bond_path.setFillRule(Qt.FillRule.WindingFill)
        for item in items:
            item_path = self._selection_path_for_bond_item(item)
            if not item_path.isEmpty():
                bond_path.addPath(item_path)
        return bond_path

    def _selection_path_for_object_item(self, item) -> QPainterPath:
        kind = item.data(0)
        pad = self.canvas.renderer.style.bond_length_px * 0.12
        if kind == "mark":
            center = self.canvas._mark_center(item)
            radius = self.canvas._mark_selection_radius()
            path = QPainterPath()
            path.addEllipse(center, radius, radius)
            return path
        if kind in {
            "arrow",
            "equilibrium",
            "resonance",
            "curved_single",
            "curved_double",
            "inhibit",
            "dotted",
        } and isinstance(item, QGraphicsPathItem):
            return self._selection_path_for_bond_item(
                item,
                width=max(item.pen().widthF() + pad * 1.5, self.canvas._atom_pick_radius() * 0.7),
            )
        if isinstance(item, QGraphicsTextItem):
            rect = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
            path = QPainterPath()
            path.addRoundedRect(rect, pad * 0.7, pad * 0.7)
            return path
        shape = item.mapToScene(item.shape())
        if shape.isEmpty():
            rect = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
            path = QPainterPath()
            path.addRoundedRect(rect, pad * 0.7, pad * 0.7)
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(pad * 2.0)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        overlay = QPainterPath(shape)
        overlay.addPath(stroker.createStroke(shape))
        simplified = overlay.simplified()
        simplified.setFillRule(Qt.FillRule.WindingFill)
        return simplified

    def _add_selection_object_overlay(self, item, color: QColor) -> None:
        path = self._selection_path_for_object_item(item)
        if path.isEmpty():
            return
        outline = NoSelectPathItem(path)
        outline.setData(0, "selection_outline")
        outline.setData(2, {"kind": "object"})
        outline.setZValue(19)
        outline.setPen(QPen(Qt.PenStyle.NoPen))
        outline.setBrush(QBrush(color))
        self.canvas.scene().addItem(outline)
        self.canvas.selection_outlines.append(outline)

    def _add_selection_component_overlay(
        self,
        atom_ids: set[int],
        bond_ids: set[int],
        color: QColor,
        atom_pad: float,
    ) -> None:
        component_path = QPainterPath()
        component_path.setFillRule(Qt.FillRule.WindingFill)
        for atom_id in atom_ids:
            rect = self.canvas._selection_indicator_rect_for_atom(atom_id)
            if rect is None:
                continue
            component_path.addEllipse(rect.adjusted(-atom_pad, -atom_pad, atom_pad, atom_pad))
        for bond_id in bond_ids:
            bond_path = self._selection_path_for_bond(bond_id)
            if not bond_path.isEmpty():
                component_path.addPath(bond_path)
        if component_path.isEmpty():
            return
        component_path = component_path.simplified()
        component_path.setFillRule(Qt.FillRule.WindingFill)
        outline = NoSelectPathItem(component_path)
        outline.setData(0, "selection_outline")
        outline.setData(2, {"kind": "component", "atom_ids": sorted(atom_ids)})
        outline.setZValue(19)
        outline.setPen(QPen(Qt.PenStyle.NoPen))
        outline.setBrush(QBrush(color))
        self.canvas.scene().addItem(outline)
        self.canvas.selection_outlines.append(outline)

    def _selection_center_for_atoms(self, atom_ids: set[int]) -> QPointF | None:
        if len(atom_ids) < 2:
            return None
        return self.canvas._bounding_box_center_for_atoms(atom_ids)

    def _selection_center_marker_enabled(self) -> bool:
        return self.canvas.tools.active is not None and self.canvas.tools.active.name == "perspective"

    def _add_selection_center_marker(self, center: QPointF) -> None:
        outer_radius = max(3.5, self.canvas.renderer.style.bond_length_px * 0.14)
        inner_radius = max(1.2, self.canvas.renderer.style.bond_length_px * 0.05)
        outer = NoSelectEllipseItem(
            center.x() - outer_radius,
            center.y() - outer_radius,
            outer_radius * 2.0,
            outer_radius * 2.0,
        )
        outer.setData(0, "selection_outline")
        outer.setData(2, {"kind": "center"})
        outer.setZValue(21)
        pen = QPen(QColor("#ff4dc9"))
        pen.setWidthF(1.4)
        outer.setPen(pen)
        outer.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.canvas.scene().addItem(outer)
        self.canvas.selection_outlines.append(outer)

        inner = NoSelectEllipseItem(
            center.x() - inner_radius,
            center.y() - inner_radius,
            inner_radius * 2.0,
            inner_radius * 2.0,
        )
        inner.setData(0, "selection_outline")
        inner.setData(2, {"kind": "center"})
        inner.setZValue(21)
        inner.setPen(QPen(Qt.PenStyle.NoPen))
        inner.setBrush(QBrush(QColor("#ff4dc9")))
        self.canvas.scene().addItem(inner)
        self.canvas.selection_outlines.append(inner)


__all__ = ["SelectionController"]
