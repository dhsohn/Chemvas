from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QInputDialog

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.features.annotations import (
    attachment_anchor_token,
    attachment_group_at_end,
    hydride_display_text,
    reversed_display_text,
    split_hydride_label,
)
from chemvas.ui.atom_label_access import uses_compact_label_hit_shape_for
from chemvas.ui.atom_label_history_recorder import AtomLabelHistoryRecorder
from chemvas.ui.atom_label_merge_service import AtomLabelMergeService
from chemvas.ui.bond_renderer_access import update_bond_geometry_for
from chemvas.ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    pop_atom_dot_for,
    pop_atom_item_for,
    set_atom_dot_for,
    set_atom_item_for,
    visible_atom_item_for,
)
from chemvas.ui.canvas_bond_graphics_state import bond_items_for_id
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    bonds_for,
    required_atom_for,
)
from chemvas.ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from chemvas.ui.graphics_items import AtomDotItem, AtomLabelItem
from chemvas.ui.pick_radius_access import atom_pick_radius_for
from chemvas.ui.renderer_style_access import (
    atom_color_for,
    atom_font_for,
    atom_label_offset_px_for,
    bond_length_px_for,
    bond_line_width_for,
)
from chemvas.ui.scene_item_access import (
    add_item_to_canvas_scene,
    remove_item_from_canvas_scene,
)
from chemvas.ui.scene_selectability import make_item_selectable
from chemvas.ui.structure_geometry_access import connected_atom_unit_vectors_for

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from chemvas.ui.canvas_view import CanvasView


def _open_direction(vectors: list[tuple[float, float]]) -> tuple[float, float]:
    """Direction toward the open side of an atom, for hydride label placement.

    Opposite the vector sum of the bonds (the same negative-sum rule the bond
    sprout uses at a two-bond vertex). When the bonds cancel out (a straight
    C-NH-C), fall back to the perpendicular of the first bond, flipped so its
    dominant component is positive -- a flat chain stacks its H underneath
    regardless of bond insertion order, like ChemDraw.
    """
    sum_x = sum(dx for dx, _ in vectors)
    sum_y = sum(dy for _, dy in vectors)
    if math.hypot(sum_x, sum_y) > 1e-6:
        return -sum_x, -sum_y
    if vectors:
        perp_x, perp_y = vectors[0][1], -vectors[0][0]
        if (perp_y if abs(perp_y) >= abs(perp_x) else perp_x) < 0.0:
            perp_x, perp_y = -perp_x, -perp_y
        return perp_x, perp_y
    return 1.0, 0.0


class AtomLabelService:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service,
        history_service=None,
        hover_refresh: Callable[[], None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.move_controller = move_controller
        self.graph_service = graph_service
        self._hover_refresh = hover_refresh or (lambda: None)
        self._relayout_batch_active = False
        self._pending_relayout_atom_ids: set[int] = set()
        self._pending_relayout_bond_ids: set[int] = set()
        self._processed_relayout_bond_ids: set[int] = set()
        self._history_recorder = AtomLabelHistoryRecorder(
            canvas,
            history_service=history_service,
        )
        self.merge_service = AtomLabelMergeService(
            canvas,
            graph_service=graph_service,
        )

    def atom_item_for_id(self, atom_id: int):
        return visible_atom_item_for(self.canvas, atom_id)

    def implicit_carbon_dot_brush(self):
        return QColor(0, 0, 0, 0)

    def ensure_carbon_dot(self, atom_id: int) -> None:
        if atom_id in atom_dots_for(self.canvas):
            return
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        radius = max(0.6, bond_line_width_for(self.canvas) * 0.6)
        pick_radius = atom_pick_radius_for(self.canvas)
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
        add_item_to_canvas_scene(self.canvas, dot)
        set_atom_dot_for(self.canvas, atom_id, dot)

    def remove_carbon_dot(self, atom_id: int) -> None:
        dot = pop_atom_dot_for(self.canvas, atom_id)
        if dot is not None:
            remove_item_from_canvas_scene(self.canvas, dot)

    def position_label(self, item, x: float, y: float) -> None:
        offset = atom_label_offset_px_for(self.canvas)
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

        atom = atom_for_id(self.canvas, atom_id)
        item = atom_items_for(self.canvas).get(atom_id)
        if atom is None or not isinstance(item, AtomLabelItem):
            return False
        before = self._label_presentation_signature(item)
        display_text, anchor_element, anchor_at_end, hydrogens_below = (
            self._hydride_layout(atom_id, atom.element)
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
                    if not bond_items_for_id(self.canvas, bond_id):
                        continue
                    update_bond_geometry_for(self.canvas, bond_id)
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
            for bond_id, bond in enumerate(bonds_for(self.canvas))
            if bond is not None and (bond.a in atom_ids or bond.b in atom_ids)
        }

    def _hydride_layout(
        self, atom_id: int, text: str
    ) -> tuple[str, str | None, bool, bool | None]:
        # Element+hydrogen labels ("NH", "OH", "NH2", "CH3") anchor on the element
        # with the hydrogens pointing away from the bonds; other multi-part
        # labels ("CF3", "Ph3P") anchor on the token facing the bonds. Returns
        # (display_text, anchor_element, anchor_at_end, hydrogens_below);
        # hydrogens_below is None for the horizontal layouts and picks the
        # stacked line side otherwise.
        split = split_hydride_label(text)
        if split is None:
            return self._token_anchor_layout(atom_id, text)
        element, h_count = split
        if h_count <= 0:
            return self._token_anchor_layout(atom_id, text)
        atom = atom_for_id(self.canvas, atom_id)
        if atom is not None and atom.explicit_label:
            return text, None, False, None
        # Put the hydrogens on the open side of the atom, quantised to the
        # dominant axis. A vertical open side (both bonds of a vertex rising,
        # or a flat C-NH-C chain) stacks the H on its own line under/over the
        # element, ChemDraw-style, instead of forcing a horizontal layout.
        vectors = connected_atom_unit_vectors_for(self.canvas, atom_id)
        open_x, open_y = _open_direction(vectors)
        if abs(open_y) > abs(open_x):
            hydrogens_below = open_y > 0.0
            v_direction = 1.0 if hydrogens_below else -1.0
            # Mirror of the horizontal guard below: keep full-box clearance when
            # a bond runs almost straight along the hydrogen direction.
            if any(dy * v_direction > 0.95 for _, dy in vectors):
                return text, None, False, None
            return text, element, False, hydrogens_below
        face_left = open_x < 0.0
        # Only when a bond runs almost straight along that horizontal direction
        # (within ~18 degrees) would the hydrogens sit on top of it; keep the
        # label centred with full-box clearance there. Ordinary diagonal
        # ring/chain neighbours -- a regular hexagon N-H has bonds near
        # (+-0.866, 0.5) -- stay anchored.
        h_direction = -1.0 if face_left else 1.0
        if any(dx * h_direction > 0.95 for dx, _ in vectors):
            return text, None, False, None
        display = hydride_display_text(element, h_count, face_left=face_left)
        return display, element, face_left, None

    def _token_anchor_layout(
        self, atom_id: int, text: str
    ) -> tuple[str, str | None, bool, bool | None]:
        # Multi-part labels ("CF3", "Ph3P", "OMe") anchor on their attachment
        # group, so that glyph sits on the atom and bonds trim to it instead of
        # clearing the whole label box. When the attachment group is typed on
        # the side away from the bonds ("CF3" or "OTs" approached from the
        # right), the display text reverses group-wise ("F3C", "TsO"),
        # ChemDraw-style, without touching the stored label. When the
        # attachment end is unknowable, the token facing the bonds anchors
        # as typed. A vertical open side, an unreversible label, or a bond
        # running along the label body keeps the centred full-clearance layout.
        vectors = connected_atom_unit_vectors_for(self.canvas, atom_id)
        if not vectors:
            # With no attachment direction there is no chemical reason to
            # reverse the user's text or select one end as the bond anchor.
            return text, None, False, None
        open_x, open_y = _open_direction(vectors)
        if abs(open_y) > abs(open_x):
            return text, None, False, None
        anchor_at_end = open_x < 0.0
        display = text
        attachment_at_end = self._attachment_at_end(text)
        if attachment_at_end is not None and attachment_at_end != anchor_at_end:
            flipped = reversed_display_text(text)
            if flipped is not None:
                display = flipped
        token = attachment_anchor_token(display, at_end=anchor_at_end)
        if token is None:
            return text, None, False, None
        # Same guard as the horizontal hydride layout: a bond running almost
        # straight along the label body would sit under the text.
        body_direction = -1.0 if anchor_at_end else 1.0
        if any(dx * body_direction > 0.95 for dx, _ in vectors):
            return text, None, False, None
        return display, token, anchor_at_end, None

    @staticmethod
    def _attachment_at_end(text: str) -> bool | None:
        # The alias table is the chemistry authority: its keys are typed
        # attachment-first, so a label matching a key attaches at the start and
        # a label whose group-reversal matches a key ("Ph3P" -> "PPh3", "MeO"
        # -> "OMe") attaches at the end. Unknown labels fall back to the
        # syntactic signals; None means the end is genuinely ambiguous.
        if text in ATOM_ALIAS_DEFINITIONS:
            return False
        flipped = reversed_display_text(text)
        if flipped is not None and flipped in ATOM_ALIAS_DEFINITIONS:
            return True
        return attachment_group_at_end(text)

    def restore_atom_item_interaction(
        self,
        atom_id: int,
        previous_item,
        *,
        was_selected: bool,
        refresh_hover: bool,
    ) -> None:
        replacement_item = self.atom_item_for_id(atom_id)
        if (
            was_selected
            and replacement_item is not None
            and replacement_item is not previous_item
        ):
            replacement_item.setSelected(True)
        if refresh_hover:
            self._hover_refresh()

    def record_label_change(
        self,
        atom_id: int,
        before_element: str,
        before_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        after_element = atom.element if atom is not None else before_element
        after_explicit_label = (
            atom.explicit_label if atom is not None else before_explicit_label
        )
        self._history_recorder.record_label_change(
            atom_id,
            before_element=before_element,
            after_element=after_element,
            before_explicit_label=before_explicit_label,
            after_explicit_label=after_explicit_label,
            before_smiles_input=before_smiles_input,
            merge_ids=merge_ids,
            merge_info=merge_info,
        )

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        return self.merge_service.merge_overlapping_atoms(atom_id)

    def add_or_update_atom_label(
        self,
        atom_id: int,
        text: str,
        clear_smiles: bool = True,
        record: bool = True,
        allow_merge: bool = True,
        show_carbon: bool = False,
        literal_label: bool | None = None,
    ) -> None:
        text = text.strip()
        show_carbon = bool(show_carbon)
        atom = required_atom_for(self.canvas, atom_id)
        before_element = atom.element
        before_explicit_label = atom.explicit_label
        before_smiles_input = last_smiles_input_for(self.canvas)
        previous_atom_item = self.atom_item_for_id(atom_id)
        was_selected = bool(
            previous_atom_item is not None and previous_atom_item.isSelected()
        )
        refresh_hover = hover_state_for(self.canvas).atom_id == atom_id
        if text:
            atom.element = text
            if clear_smiles:
                clear_last_smiles_input_for(self.canvas)
        existing_item = atom_items_for(self.canvas).get(atom_id)
        show_label = bool(text)
        explicit_label = (
            bool(before_explicit_label and text == before_element)
            if literal_label is None
            else bool(literal_label)
        )
        if atom.element.upper() == "C":
            if show_carbon and show_label:
                explicit_label = True
            else:
                show_label = False
        atom.explicit_label = explicit_label
        if not show_label:
            text = ""

        if not text:
            if existing_item is not None:
                remove_item_from_canvas_scene(self.canvas, existing_item)
                pop_atom_item_for(self.canvas, atom_id)
            if atom.element.upper() == "C":
                self.ensure_carbon_dot(atom_id)
            if self.move_controller is not None:
                self.move_controller.redraw_connected_bonds(atom_id)
            self.restore_atom_item_interaction(
                atom_id,
                previous_atom_item,
                was_selected=was_selected,
                refresh_hover=refresh_hover,
            )
            if record:
                self.record_label_change(
                    atom_id,
                    before_element,
                    before_explicit_label,
                    before_smiles_input,
                    [],
                    {},
                )
            return

        label_hit_padding = bond_length_px_for(self.canvas) * 0.12
        label_hit_radius = (
            atom_pick_radius_for(self.canvas)
            if uses_compact_label_hit_shape_for(self.canvas, text)
            else None
        )
        if existing_item is not None and not isinstance(existing_item, AtomLabelItem):
            remove_item_from_canvas_scene(self.canvas, existing_item)
            existing_item = None
            pop_atom_item_for(self.canvas, atom_id)
        if existing_item is None:
            text_item = AtomLabelItem(
                hit_padding=label_hit_padding, hit_radius=label_hit_radius
            )
            add_item_to_canvas_scene(self.canvas, text_item)
            set_atom_item_for(self.canvas, atom_id, text_item)
        else:
            text_item = existing_item
            text_item.set_hit_padding(label_hit_padding)
            text_item.set_hit_radius(label_hit_radius)

        text_item.setFont(atom_font_for(self.canvas))
        text_item.setDefaultTextColor(QColor(atom_color_for(self.canvas)))
        text_item.setData(0, "atom")
        text_item.setData(1, atom_id)
        text_item.setZValue(3)
        make_item_selectable(text_item)
        self.relayout_atom_label(atom_id)
        self.remove_carbon_dot(atom_id)
        merge_ids, merge_info = (
            self.merge_overlapping_atoms(atom_id) if allow_merge else ([], {})
        )
        if merge_ids:
            # Merging can retarget or remove the last incident bond. Re-derive
            # the presentation even when there is no surviving bond for the
            # renderer-driven refresh below to visit.
            self.relayout_atom_label(atom_id)
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id)
        self.restore_atom_item_interaction(
            atom_id,
            previous_atom_item,
            was_selected=was_selected,
            refresh_hover=refresh_hover,
        )
        if record:
            self.record_label_change(
                atom_id,
                before_element,
                before_explicit_label,
                before_smiles_input,
                merge_ids,
                merge_info,
            )

    def prompt_atom_label(self, atom_id: int) -> None:
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            return
        initial = (
            ""
            if atom.element.upper() == "C" and not atom.explicit_label
            else atom.element
        )
        text, ok = QInputDialog.getText(
            self.canvas,
            "Atom Label",
            "Enter atom symbol:",
            text=initial,
        )
        if not ok:
            return
        text = text.strip()
        if not text:
            self.add_or_update_atom_label(atom_id, "C", show_carbon=False)
            return
        self.add_or_update_atom_label(atom_id, text, show_carbon=True)


__all__ = ["AtomLabelService"]
