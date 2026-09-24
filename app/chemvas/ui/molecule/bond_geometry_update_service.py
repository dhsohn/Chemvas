from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem, QGraphicsPolygonItem

from chemvas.ui.molecule.bond_geometry_plan_service import (
    BondLinePrimitive,
    BondPathPrimitive,
    BondPolygonPrimitive,
)

if TYPE_CHECKING:
    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class BondGeometryUpdateService:
    def __init__(self, context: SceneRenderContext, *, planner) -> None:
        self.context = context
        self.planner = planner

    @staticmethod
    def _reset_item_origin(item) -> None:
        pos = item.pos()
        if abs(pos.x()) <= 1e-6 and abs(pos.y()) <= 1e-6:
            return
        item.setPos(0.0, 0.0)

    @staticmethod
    def _apply_primitive(item, primitive) -> None:
        if isinstance(primitive, BondLinePrimitive):
            item.setLine(*primitive.segment)
            return
        if isinstance(primitive, BondPathPrimitive):
            item.setPath(primitive.path)
            return
        if isinstance(primitive, BondPolygonPrimitive):
            item.setPolygon(primitive.polygon)
            return
        raise TypeError(f"unsupported bond primitive: {type(primitive).__name__}")

    @staticmethod
    def _validate_topology(items, primitives) -> None:
        if len(items) != len(primitives):
            raise ValueError("bond graphics topology does not match geometry plan")
        expected_item_types = {
            BondLinePrimitive: QGraphicsLineItem,
            BondPathPrimitive: QGraphicsPathItem,
            BondPolygonPrimitive: QGraphicsPolygonItem,
        }
        for item, primitive in zip(items, primitives, strict=True):
            expected_type = expected_item_types.get(type(primitive))
            if expected_type is None or not isinstance(item, expected_type):
                raise TypeError("bond graphics topology does not match geometry plan")

    def topology_is_stale(self, bond_id: int) -> bool:
        """True when a fresh build would not reproduce the current item count.

        Hash-mark counts derive from bond length; the in-place update reuses
        the existing items, so a length change during a gesture freezes the
        count until something rebuilds the bond.
        """
        bond = self.context.bond_for_id(bond_id)
        if bond is None:
            return False
        items = self.context.state.bond_graphics_state.bond_items.get(bond_id)
        if not items:
            return False
        a = self.context.model.atoms.get(bond.a)
        b = self.context.model.atoms.get(bond.b)
        if a is None or b is None:
            return False
        fresh = self.planner.primitives_for_bond(bond, a, b, topology_count=None)
        return len(fresh) != len(items)

    def update_bond_geometry(self, bond_id: int) -> None:
        bond = self.context.bond_for_id(bond_id)
        if bond is None:
            return
        items = self.context.state.bond_graphics_state.bond_items.get(bond_id)
        if not items:
            return
        a = self.context.model.atoms.get(bond.a)
        b = self.context.model.atoms.get(bond.b)
        if a is None or b is None:
            return

        primitives = self.planner.primitives_for_bond(
            bond,
            a,
            b,
            topology_count=len(items),
        )
        self._validate_topology(items, primitives)
        for item, primitive in zip(items, primitives, strict=True):
            self._reset_item_origin(item)
            self._apply_primitive(item, primitive)


__all__ = ["BondGeometryUpdateService"]
