from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen

from chemvas.features.annotations import (
    atom_label_presentation,
    uses_compact_label_hit_shape,
)
from chemvas.features.graph import connected_atom_unit_vectors
from chemvas.ui.canvas.graphics_items import AtomDotItem, AtomLabelItem
from chemvas.ui.canvas.pick_radius_access import atom_pick_radius
from chemvas.ui.scene.scene_graphics_operations import detach_graphics_item
from chemvas.ui.scene.scene_selectability import make_item_selectable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


class AtomLabelRenderer:
    """Molecular labels and implicit carbon graphics without editor services."""

    def __init__(self, context: SceneRenderContext) -> None:
        self.context = context
        self._relayout_batch_active = False
        self._pending_relayout_atom_ids: set[int] = set()
        self._pending_relayout_bond_ids: set[int] = set()
        self._processed_relayout_bond_ids: set[int] = set()

    def atom_pick_radius(self) -> float:
        return atom_pick_radius(self.context.renderer)

    def draw_atom(self, atom_id: int, *, visible: bool | None = None) -> None:
        """Materialize the current model label, without changing model content."""
        atom = self.context.model.atoms.get(atom_id)
        if atom is None:
            return
        items = self.context.state.atom_graphics_state.atom_items
        existing_item = items.get(atom_id)
        if visible is None:
            visible = bool(atom.element) and (
                atom.element.upper() != "C" or atom.explicit_label
            )
        if not visible:
            if existing_item is not None:
                detach_graphics_item(self.context.scene, existing_item)
                items.pop(atom_id, None)
            if atom.element.upper() == "C":
                self.ensure_carbon_dot(atom_id)
            return
        label_hit_padding = self.context.renderer.style.bond_length_px * 0.12
        label_hit_radius = (
            self.atom_pick_radius()
            if uses_compact_label_hit_shape(atom.element)
            else None
        )
        if existing_item is not None and not isinstance(existing_item, AtomLabelItem):
            detach_graphics_item(self.context.scene, existing_item)
            existing_item = None
            items.pop(atom_id, None)
        if existing_item is None:
            text_item = AtomLabelItem(
                hit_padding=label_hit_padding, hit_radius=label_hit_radius
            )
            self.context.scene.addItem(text_item)
            items[atom_id] = text_item
        else:
            text_item = existing_item
            text_item.set_hit_padding(label_hit_padding)
            text_item.set_hit_radius(label_hit_radius)

        text_item.setFont(self.context.renderer.atom_font())
        text_item.setDefaultTextColor(QColor(atom.color))
        text_item.setData(0, "atom")
        text_item.setData(1, atom_id)
        text_item.setZValue(3)
        make_item_selectable(text_item)
        self.relayout_atom_label(atom_id)
        self.remove_carbon_dot(atom_id)

    def atom_item_for_id(self, atom_id: int):
        return self.context.state.atom_graphics_state.atom_items.get(
            atom_id
        ) or self.context.state.atom_graphics_state.atom_dots.get(atom_id)

    def implicit_carbon_dot_brush(self):
        return QColor(0, 0, 0, 0)

    def ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in self.context.state.atom_graphics_state.atom_dots:
            return
        atom = self.context.model.atoms.get(atom_id)
        if atom is None:
            return
        radius = max(0.6, self.context.renderer.style.bond_line_width * 0.6)
        pick_radius = self.atom_pick_radius()
        dot = AtomDotItem(
            -radius,
            -radius,
            radius * 2.0,
            radius * 2.0,
            hit_padding=max(0.0, pick_radius - radius),
        )
        dot.setBrush(self.implicit_carbon_dot_brush())
        dot.setPen(QPen(Qt.PenStyle.NoPen))
        dot.setZValue(3)
        dot.setData(0, "atom")
        dot.setData(1, atom_id)
        make_item_selectable(dot)
        dot.setPos(atom.x, atom.y)
        self.context.scene.addItem(dot)
        self.context.state.atom_graphics_state.atom_dots[atom_id] = dot

    def remove_carbon_dot(self, atom_id: int) -> None:
        dot = self.context.state.atom_graphics_state.atom_dots.pop(atom_id, None)
        if dot is not None:
            detach_graphics_item(self.context.scene, dot)

    def position_label(self, item, x: float, y: float) -> None:
        offset = self.context.renderer.style.atom_label_offset_px
        center = None
        anchor_center = getattr(item, "anchor_center", None)
        if callable(anchor_center):
            center = anchor_center()
        if center is None:
            center = item.boundingRect().center()
        item.setPos(x - center.x() + offset, y - center.y() - offset)

    @staticmethod
    def _label_presentation_signature(item: AtomLabelItem) -> tuple[object, ...]:
        position = item.pos()
        stack_rect = item._stack_element_rect
        return (
            item.toPlainText(),
            item._raw_text,
            item._layout,
            item._typographic,
            item._anchor_element,
            item._anchor_at_end,
            item._stack,
            (
                None
                if stack_rect is None
                else (
                    stack_rect.x(),
                    stack_rect.y(),
                    stack_rect.width(),
                    stack_rect.height(),
                )
            ),
            (position.x(), position.y()),
        )

    def relayout_atom_label(self, atom_id: int) -> bool:
        """Recompute one label from stored text and current bond geometry.

        The displayed order and anchor are derived presentation state: the
        model keeps exactly what the user typed, while this method can be
        called repeatedly after topology or coordinates change. The return
        value reports whether the visible layout, anchor, or position changed.
        """

        atom = self.context.model.atoms.get(atom_id)
        item = self.context.state.atom_graphics_state.atom_items.get(atom_id)
        if atom is None or not isinstance(item, AtomLabelItem):
            return False
        before = self._label_presentation_signature(item)
        display_text, anchor_element, anchor_at_end, hydrogens_below = (
            atom_label_presentation(self.context.model, atom_id, atom.element)
        )
        item.setPlainText(display_text)
        if hydrogens_below is None:
            item.set_anchor(anchor_element, at_end=anchor_at_end)
        else:
            item.set_stack_anchor(
                anchor_element,
                hydrogens_below=hydrogens_below,
            )
        self.position_label(item, atom.x, atom.y)
        return self._label_presentation_signature(item) != before

    def relayout_atom_labels(
        self,
        atom_ids: Iterable[int],
        *,
        skip_bond_ids: Iterable[int] = (),
    ) -> None:
        """Relayout a batch and refresh each affected incident bond once.

        A bond refresh calls back into this method for its own endpoints. The
        pending sets turn those callbacks into more work for the active batch,
        while the processed set prevents recursion and duplicate refreshes.
        ``skip_bond_ids`` names geometry the caller is already about to update.
        """

        requested_atom_ids = set(atom_ids)
        requested_skip_bond_ids = set(skip_bond_ids)
        self._processed_relayout_bond_ids.update(requested_skip_bond_ids)
        if self._relayout_batch_active:
            # The renderer computes its bond primitive immediately after this
            # callback returns. Relayout these endpoints synchronously so that
            # primitive sees both fresh ends, while deferring any newly
            # affected incident bonds to the owning outer batch.
            changed_atom_ids = self._relayout_atom_ids(requested_atom_ids)
            if changed_atom_ids:
                self._pending_relayout_bond_ids.update(
                    self._incident_bond_ids(changed_atom_ids)
                )
            return
        self._pending_relayout_atom_ids.update(requested_atom_ids)
        self._relayout_batch_active = True
        try:
            while self._pending_relayout_atom_ids or self._pending_relayout_bond_ids:
                pending_atom_ids = sorted(self._pending_relayout_atom_ids)
                self._pending_relayout_atom_ids.clear()
                changed_atom_ids = self._relayout_atom_ids(pending_atom_ids)
                if changed_atom_ids:
                    self._pending_relayout_bond_ids.update(
                        self._incident_bond_ids(changed_atom_ids)
                    )

                pending_bond_ids = sorted(self._pending_relayout_bond_ids)
                self._pending_relayout_bond_ids.clear()
                for bond_id in pending_bond_ids:
                    if bond_id in self._processed_relayout_bond_ids:
                        continue
                    self._processed_relayout_bond_ids.add(bond_id)
                    if not self.context.state.bond_graphics_state.bond_items.get(
                        bond_id
                    ):
                        continue
                    self.context.bonds.update_bond_geometry(bond_id)
        finally:
            self._pending_relayout_atom_ids.clear()
            self._pending_relayout_bond_ids.clear()
            self._processed_relayout_bond_ids.clear()
            self._relayout_batch_active = False

    def _relayout_atom_ids(self, atom_ids: Iterable[int]) -> set[int]:
        return {
            atom_id
            for atom_id in sorted(set(atom_ids))
            if self.relayout_atom_label(atom_id)
        }

    def _incident_bond_ids(self, atom_ids: set[int]) -> set[int]:
        return {
            bond_id
            for bond_id, bond in enumerate(self.context.model.bonds)
            if bond is not None and (bond.a in atom_ids or bond.b in atom_ids)
        }


__all__ = [
    "AtomLabelRenderer",
    "connected_atom_unit_vectors",
    "uses_compact_label_hit_shape",
]
