"""Own selection mutations, group reconciliation and rendering updates."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from chemvas.domain.document import VALID_ARROW_KINDS
from chemvas.features.selection import (
    AtomHitCandidate,
    BondHitCandidate,
    SelectionHitRequest,
    SelectionRect,
    StructureHit,
    choose_preferred_structure_hit,
    nearest_ring_atom_id,
    selection_hit_matches,
    structure_hit_is_selected,
)
from chemvas.ui.annotations.projections import group_projections
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_group_state import group_ids_for_members_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.canvas.graphics_items import NoSelectRectItem
from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
from chemvas.ui.scene.scene_group_operations import (
    _group_has_scene_members,
    _is_groupable_standalone_item,
    _structure_items_for_atom_ids,
    group_selection_targets_for,
    notes_only_group_member_notes_for,
)
from chemvas.ui.selection.selection_geometry_access import bounds_for_atoms_for
from chemvas.ui.selection.selection_outline_items import selection_outline_pen
from chemvas.ui.selection.selection_outline_service import (
    OBJECT_OVERLAY_KINDS,
    SelectionOutlineService,
)
from chemvas.ui.selection.selection_queries import (
    TRANSFORM_SELECTION_EXCLUDED_KINDS,
    clear_scene_selection_for,
    scene_selected_items_for,
    selected_atom_ids_for_transform_for,
    selected_mark_atom_ids_for,
    selected_scene_items_for,
    selected_scene_notes_for,
    selection_snapshot_for,
    set_scene_items_selected_for,
)
from chemvas.ui.selection.selection_state import (
    add_selected_note_for,
    remove_selected_note_for,
)
from chemvas.ui.selection.selection_structure_targets import (
    STRUCTURE_OVERLAY_KINDS,
    structure_selection_targets_for_item,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas.canvas_graph_service import CanvasGraphService
    from chemvas.ui.canvas.canvas_hit_testing_service import CanvasHitTestingService
    from chemvas.ui.canvas.canvas_view import CanvasView


class SelectionController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        graph_service: CanvasGraphService,
        hit_testing_service: CanvasHitTestingService,
        active_tool_name_provider: Callable[[], str | None] | None = None,
    ) -> None:
        self.canvas = canvas
        self.graph_service = graph_service
        self.hit_testing_service = hit_testing_service
        self.outline_service = SelectionOutlineService(
            canvas,
            graph_service=graph_service,
            active_tool_name_provider=active_tool_name_provider,
        )

    def clear(self) -> None:
        clear_scene_selection_for(self.canvas)
        self.clear_note_selection()

    def select_single_structure_item(self, item) -> bool:
        targets = self.selection_targets_for_item(item)
        if not targets:
            return False
        self.clear()
        set_scene_items_selected_for(self.canvas, targets, True, block_signals=False)
        return True

    def structure_item_is_selected(
        self, item, selected_atom_ids, selected_bond_ids
    ) -> bool:
        hit, bond_atom_ids, ring_atom_ids = self.structure_hit_from_item(item)
        return structure_hit_is_selected(
            hit,
            selected_atom_ids=selected_atom_ids,
            selected_bond_ids=selected_bond_ids,
            bond_atom_ids=bond_atom_ids,
            ring_atom_ids=ring_atom_ids,
            item_is_selected=bool(item is not None and item.isSelected()),
        )

    def structure_hit_from_item(
        self, item
    ) -> tuple[StructureHit | None, tuple[int, int] | None, list[int] | None]:
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
            if isinstance(bond_id, int):
                bond = self.canvas.model.bond_for_id(bond_id)
                if bond is not None:
                    return StructureHit(kind="bond", id=bond_id), (bond.a, bond.b), None
            return None, None, None
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                return StructureHit(kind="ring"), None, ring_atom_ids
            return StructureHit(kind="ring"), None, None
        return StructureHit(kind="other"), None, None

    def structure_item_for_hit(self, hit: StructureHit):
        if hit.kind == "atom" and isinstance(hit.id, int):
            return self.atom_item_for_id(hit.id)
        if hit.kind == "bond" and isinstance(hit.id, int):
            bond_items = self.canvas.runtime_state.bond_graphics_state.bond_items.get(
                hit.id, []
            )
            if bond_items:
                return bond_items[0]
        return None

    def selection_targets_for_item(self, item) -> list[QGraphicsItem]:
        return structure_selection_targets_for_item(
            self.canvas,
            item,
            atom_item_for_id=self.atom_item_for_id,
        )

    def toggle_item_selection(self, item) -> bool:
        targets = self.selection_targets_for_item(item)
        if not targets:
            return False
        targets = group_selection_targets_for(self.canvas, targets)
        note_targets = [target for target in targets if target.data(0) == "note"]
        scene_targets = [target for target in targets if target.data(0) != "note"]
        # Notes carry their own selection state, so they never contribute to
        # the toggle decision and are routed through the selection owner; their Qt
        # flags are mirrored afterwards since attached notes are Qt-selectable.
        should_select = (
            not any(target.isSelected() for target in scene_targets)
            if scene_targets
            else None
        )
        set_scene_items_selected_for(self.canvas, scene_targets, bool(should_select))
        applied = self.apply_group_note_toggle(note_targets, should_select)
        if note_targets and applied is not None:
            set_scene_items_selected_for(self.canvas, note_targets, applied)
        self.update_selection_outline()
        return True

    def preferred_structure_hit_at_scene_pos(self, pos: QPointF) -> StructureHit | None:
        item = self.item_at_scene_pos(pos)
        item_hit, _, _ = self.structure_hit_from_item(item)
        if item is not None and item.data(0) == "mark":
            return item_hit
        if item_hit is not None and item_hit.kind == "atom":
            return item_hit
        atom_hit = self.nearest_atom_hit(pos)
        bond_hit = self.nearest_bond_hit(pos)
        preferred_hit = choose_preferred_structure_hit(
            AtomHitCandidate(
                atom_id=atom_hit[0],
                distance=atom_hit[1],
            )
            if atom_hit is not None
            else None,
            BondHitCandidate(bond_id=bond_hit[0], distance=bond_hit[1])
            if bond_hit is not None
            else None,
            atom_pick_radius=atom_pick_radius_for(self.canvas),
            bond_pick_radius=self.canvas.renderer.style.bond_length_px * 0.528,
        )
        if preferred_hit is not None:
            preferred_item = self.structure_item_for_hit(preferred_hit)
            if preferred_item is not None:
                return preferred_hit
        if item is not None and item.data(0) == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                nearest_atom_id = nearest_ring_atom_id(
                    [
                        (atom_id, math.hypot(atom.x - pos.x(), atom.y - pos.y()))
                        for atom_id in ring_atom_ids
                        for atom in [self.canvas.model.atom_for_id(atom_id)]
                        if atom is not None
                    ],
                    max_distance=self.canvas.renderer.style.bond_length_px * 0.4,
                )
                if nearest_atom_id is not None:
                    ring_atom_item = visible_atom_item_for(self.canvas, nearest_atom_id)
                    if ring_atom_item is not None:
                        return StructureHit(kind="atom", id=nearest_atom_id)
            return StructureHit(kind="ring")
        fallback_hit, _, _ = self.structure_hit_from_item(item)
        return fallback_hit

    def preferred_structure_item_at_scene_pos(self, pos: QPointF):
        hit = self.preferred_structure_hit_at_scene_pos(pos)
        if hit is None:
            return None
        if hit.kind in {"atom", "bond"}:
            return self.structure_item_for_hit(hit)
        return self.item_at_scene_pos(pos)

    def select_structure_for_item(self, item) -> bool:
        if item is None:
            return False
        kind = item.data(0)
        if kind in STRUCTURE_OVERLAY_KINDS:
            clear_scene_selection_for(self.canvas)
            self.clear_note_selection()
            item.setSelected(True)
            return True
        atom_ids = self._connected_atom_ids_for_item(item)
        if not atom_ids:
            return False
        clear_scene_selection_for(self.canvas)
        self.clear_note_selection()
        for atom_id in atom_ids:
            atom_item = self.atom_item_for_id(atom_id)
            if atom_item is not None:
                atom_item.setSelected(True)
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a not in atom_ids or bond.b not in atom_ids:
                continue
            for (
                bond_item
            ) in self.canvas.runtime_state.bond_graphics_state.bond_items.get(
                bond_id, []
            ):
                bond_item.setSelected(True)
        for ring_item in self.canvas.runtime_state.ring_items():
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list) and all(
                atom_id in atom_ids for atom_id in ring_atom_ids
            ):
                ring_item.setSelected(True)
        self.update_selection_outline()
        return True

    def select_note(self, item: QGraphicsTextItem, additive: bool = False) -> None:
        if not additive:
            self.clear_note_selection()
        changed = item not in self.canvas.runtime_state.selection_state.selected_notes
        add_selected_note_for(self.canvas, item)
        self.update_note_selection_box(item)
        if changed:
            self.expand_note_selection_to_groups(item)
            self._refresh_outline_for_note_change()

    def toggle_note_selection(self, item: QGraphicsTextItem) -> None:
        if item in self.canvas.runtime_state.selection_state.selected_notes:
            remove_selected_note_for(self.canvas, item)
            self._deselect_grouped_note_companions(item)
        else:
            add_selected_note_for(self.canvas, item)
            self.expand_note_selection_to_groups(item)
        self.update_note_selection_box(item)
        self._refresh_outline_for_note_change()

    def clear_note_selection(self) -> None:
        notes = list(self.canvas.runtime_state.selection_state.selected_notes)
        self.canvas.runtime_state.selection_state.selected_notes = []
        for note in notes:
            self.update_note_selection_box(note)
        if notes:
            # Drop the notes' Qt flags with the service selection: mirrored
            # flags (e.g. from a group toggle) would otherwise survive as an
            # invisible Qt selection that delete/copy/drag still acts on.
            set_scene_items_selected_for(self.canvas, notes, False)
        for note in notes:
            # Mixed groups deselect as a unit: without this, clearing the note
            # selection (e.g. NoteTool press on empty canvas) would leave the
            # group's scene members selected and the box spanning notes that a
            # drag no longer moves.
            self.deselect_groups_for_note(note)
        if notes:
            self._refresh_outline_for_note_change()

    def update_note_selection_box(self, item: QGraphicsTextItem) -> None:
        sel = item.data(21)
        padding = self.canvas.runtime_state.text_style_state.note_padding
        rect = item.boundingRect().adjusted(
            -padding,
            -padding,
            padding,
            padding,
        )
        selected = item in self.canvas.runtime_state.selection_state.selected_notes
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
        sel.setPen(
            selection_outline_pen(self.canvas.runtime_state.selection_state.color)
        )
        sel.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def selection_rects_for_snapshot(
        self,
        snapshot,
    ) -> tuple[SelectionRect, ...]:
        rects: list[SelectionRect] = []
        if snapshot.selected_atom_ids:
            for component in self.graph_service.connected_components(
                set(snapshot.selected_atom_ids)
            ):
                bounds = bounds_for_atoms_for(self.canvas, component)
                if bounds is None:
                    continue
                min_x, min_y, max_x, max_y = bounds
                rects.append(
                    SelectionRect(left=min_x, top=min_y, right=max_x, bottom=max_y)
                )
        for item in snapshot.selection_items:
            if item.data(0) in {"atom", "bond", "ring"}:
                continue
            if item.data(0) in OBJECT_OVERLAY_KINDS:
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
            snapshot = selection_snapshot_for(self.canvas)
        if snapshot is None:
            return False
        outline_hit = False
        for outline in self.canvas.runtime_state.selection_state.outlines:
            data = outline.data(2) or {}
            if data.get("kind") not in {"component", "object", "group"}:
                continue
            if data.get("object_kind") in VALID_ARROW_KINDS:
                # Arrow halos scale with the drawing. Picking uses the same
                # screen-space stroke corridor before and after selection.
                continue
            if outline.contains(outline.mapFromScene(pos)):
                outline_hit = True
                break
        item = self.hit_testing_service.item_at_scene_pos(pos)
        hit, bond_atom_ids, ring_atom_ids = self.structure_hit_from_item(item)
        return selection_hit_matches(
            SelectionHitRequest(
                point=(pos.x(), pos.y()),
                outline_hit=outline_hit,
                rects=self.selection_rects_for_snapshot(snapshot),
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
        if self.canvas.runtime_state.selection_state.suspend_outline:
            return
        self.outline_service.update_selection_outline()

    def shift_selection_outlines(self, dx: float, dy: float) -> None:
        self.outline_service.shift_selection_outlines(dx, dy)

    def atom_item_for_id(self, atom_id: int):
        return visible_atom_item_for(self.canvas, atom_id)

    def _connected_atom_ids_for_item(self, item) -> set[int]:
        kind = item.data(0)
        if kind == "atom":
            atom_id = item.data(1)
            if (
                isinstance(atom_id, int)
                and self.canvas.model.atom_for_id(atom_id) is not None
            ):
                return self.graph_service.expand_connected_atoms({atom_id})
            return set()
        if kind == "bond":
            bond_id = item.data(1)
            if isinstance(bond_id, int):
                bond = self.canvas.model.bond_for_id(bond_id)
                if bond is not None:
                    return self.graph_service.expand_connected_atoms({bond.a, bond.b})
            return set()
        if kind == "ring":
            ring_atom_ids = item.data(2)
            if isinstance(ring_atom_ids, list):
                return self.graph_service.expand_connected_atoms(
                    {
                        atom_id
                        for atom_id in ring_atom_ids
                        if self.canvas.model.atom_for_id(atom_id) is not None
                    }
                )
        return set()

    def item_at_scene_pos(self, pos: QPointF):
        return self.hit_testing_service.item_at_scene_pos(pos)

    def nearest_atom_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return self.hit_testing_service.nearest_atom_hit(pos)

    def nearest_bond_hit(self, pos: QPointF) -> tuple[int, float] | None:
        return self.hit_testing_service.nearest_bond_hit(pos)

    def set_note_selected(self, item: QGraphicsTextItem, selected: bool) -> None:
        is_selected = item in self.canvas.runtime_state.selection_state.selected_notes
        if selected == is_selected:
            return
        if selected:
            add_selected_note_for(self.canvas, item)
            self.expand_note_selection_to_groups(item)
        else:
            remove_selected_note_for(self.canvas, item)
            self._deselect_grouped_note_companions(item)
        self.update_note_selection_box(item)
        self._refresh_outline_for_note_change()

    def _deselect_grouped_note_companions(self, item: QGraphicsTextItem) -> None:
        # A notes-only group deselects as a unit, mirroring the select-direction
        # expansion; otherwise Ctrl-clicking one member leaves a partial group
        # that delete/copy/drag would silently act on.
        member_notes = notes_only_group_member_notes_for(self.canvas, item)
        for member in member_notes:
            if (
                member is item
                or member
                not in self.canvas.runtime_state.selection_state.selected_notes
            ):
                continue
            remove_selected_note_for(self.canvas, member)
            self.update_note_selection_box(member)
        if member_notes:
            # Attached notes are Qt-selectable (e.g. via rubber band); clear
            # those flags too so a lingering Qt selection cannot keep a member
            # in drag snapshots after the unit deselected.
            set_scene_items_selected_for(self.canvas, member_notes, False)
        # Mixed groups deselect as a unit too: the group box spans attached
        # members, so leaving the scene members selected would keep a box over
        # a note that a drag no longer moves.
        self.deselect_groups_for_note(item)

    def _refresh_outline_for_note_change(self) -> None:
        # Note selection lives outside QGraphicsScene selection, so it never
        # emits selectionChanged; refresh explicitly or a notes-only group box
        # would linger after the note selection is cleared (e.g. switching to
        # the bond tool).
        self.update_selection_outline()

    def apply_group_note_toggle(
        self,
        notes: list[QGraphicsItem],
        selected: bool | None,
    ) -> bool | None:
        """Select or deselect grouped notes as a unit.

        ``selected`` mirrors the group's structure members; pass ``None`` when the
        group has no selectable scene members so the direction is decided from the
        notes' own current state. Returns the direction that was applied so the
        caller can mirror it onto the notes' Qt selection flags.
        """
        if not notes:
            return None
        if selected is None:
            current = self.canvas.runtime_state.selection_state.selected_notes
            selected = not all(note in current for note in notes)
        for note in notes:
            self.set_note_selected(cast("QGraphicsTextItem", note), selected)
        return selected

    def expand_note_selection_to_groups(self, note) -> None:
        """Expand an explicit explicit note selection to its complete group.

        Keeping this entry point separate from ``expand_selection_to_groups``
        is intentional: a Qt-selected note from a rubber band must not become a
        sticky group anchor, while a direct Note-tool selection is an explicit
        request to select the group as one unit.
        """
        state = self.canvas.runtime_state.group_state
        if state.expanding or not state.groups:
            return
        target_group = next(
            (
                group
                for group in state.groups.values()
                if require_scene_record_id(note) in group.item_ids
            ),
            None,
        )
        if target_group is None:
            return
        members = group_projections(self.canvas, target_group.item_ids)
        member_notes = [member for member in members if member.data(0) == "note"]
        selected_notes = selected_scene_notes_for(self.canvas)
        missing = [
            member
            for member in member_notes
            if not any(member is selected for selected in selected_notes)
        ]
        has_scene_members = _group_has_scene_members(self.canvas, target_group)
        if not missing and not has_scene_members:
            return
        state.expanding = True
        try:
            if has_scene_members:
                atom_ids = target_group.atom_ids & set(self.canvas.model.atoms)
                scene_items = _structure_items_for_atom_ids(self.canvas, atom_ids)
                scene_items.extend(
                    member for member in members if member.data(0) != "note"
                )
                set_scene_items_selected_for(self.canvas, scene_items, True)
            for member in missing:
                self.select_note(member, additive=True)
        finally:
            state.expanding = False

    def deselect_groups_for_note(self, note) -> None:
        """Deselect the whole group when one of its notes is deselected directly.

        Mirrors the scene-side unit rule: without this, deselecting a mixed
        group's note (note focus-out, NoteTool Ctrl-click) leaves the scene
        members selected, so the group box keeps spanning a note that a drag
        would leave behind.
        """
        state = self.canvas.runtime_state.group_state
        if state.expanding or not state.groups:
            return
        target_groups = [
            group
            for group in state.groups.values()
            if require_scene_record_id(note) in group.item_ids
            and _group_has_scene_members(self.canvas, group)
        ]
        if not target_groups:
            return
        state.expanding = True
        try:
            for group in target_groups:
                live_atom_ids = group.atom_ids & set(self.canvas.model.atoms)
                members = group_projections(self.canvas, group.item_ids)
                scene_items = _structure_items_for_atom_ids(self.canvas, live_atom_ids)
                # Notes are included: attach_scene_item makes them Qt-selectable,
                # so a rubber-band-selected note would otherwise keep its Qt
                # selection and keep triggering the group box.
                scene_items.extend(members)
                set_scene_items_selected_for(self.canvas, scene_items, False)
                selected_notes = selected_scene_notes_for(self.canvas)
                for member in members:
                    if member.data(0) != "note" or member is note:
                        continue
                    if any(member is selected for selected in selected_notes):
                        remove_selected_note_for(self.canvas, member)
                        self.update_note_selection_box(member)
        finally:
            state.expanding = False

    def _stale_group_notes(self, state, active_group_ids: set[int]) -> list:
        """Selected note members of groups that are no longer scene-selected.

        Qt's rubber band and clearSelection only touch scene selection, so once an
        expansion selects a group's note, nothing would ever deselect it — and a
        still-selected note would keep re-triggering the group. These notes must be
        dropped so the group deselects as a unit.
        """
        selected_notes = selected_scene_notes_for(self.canvas)
        if not selected_notes:
            return []
        stale: list = []
        for group_id, group in state.groups.items():
            if group_id in active_group_ids:
                continue
            member_notes = [
                note
                for note in selected_notes
                if require_scene_record_id(note) in group.item_ids
            ]
            if not member_notes:
                continue
            # A notes-only group is never scene-triggered; leave its manual
            # note-tool selection alone.
            if not _group_has_scene_members(self.canvas, group):
                continue
            stale.extend(member_notes)
        return stale

    def expand_selection_to_groups(self) -> None:
        state = self.canvas.runtime_state.group_state
        if state.expanding or not state.groups:
            return
        atom_ids = {
            atom_id
            for atom_id in selected_atom_ids_for_transform_for(self.canvas)
            if atom_id in self.canvas.model.atoms
        }
        # Trigger only from Qt scene selection. Explicit note selection must not
        # anchor a group: the rubber band never deselects notes, so a note trigger
        # would make a once-touched group impossible to marquee-deselect.
        trigger_items = [
            item
            for item in scene_selected_items_for(self.canvas)
            if _is_groupable_standalone_item(self.canvas, item)
        ]
        # Selected atom-bound marks stand in for their atoms when matching groups,
        # but stay out of `atom_ids` so the atoms still count as missing and get
        # selected by the expansion below.
        trigger_atom_ids = atom_ids | selected_mark_atom_ids_for(self.canvas)
        group_ids = group_ids_for_members_for(
            self.canvas, trigger_atom_ids, trigger_items
        )
        # Notes-only groups have no shrink path here (the stale-note reconciliation
        # skips them), so a Qt-selected note must not scene-expand them or a
        # marquee that once touched the note could never deselect the group; their
        # unit behaviour lives entirely in the explicit note-selection paths.
        group_ids = {
            group_id
            for group_id in group_ids
            if _group_has_scene_members(self.canvas, state.groups[group_id])
        }
        member_atom_ids: set[int] = set()
        member_items: list = []
        for group_id in group_ids:
            group = state.groups[group_id]
            member_atom_ids.update(group.atom_ids)
            member_items.extend(group_projections(self.canvas, group.item_ids))
        member_atom_ids &= set(self.canvas.model.atoms)
        selected_items = selected_scene_items_for(
            self.canvas, excluded_kinds=TRANSFORM_SELECTION_EXCLUDED_KINDS
        )
        selected_ids = set(map(id, selected_items))
        missing_atoms = member_atom_ids - atom_ids
        missing_items = [item for item in member_items if id(item) not in selected_ids]
        stale_notes = self._stale_group_notes(state, group_ids)
        if not missing_atoms and not missing_items and not stale_notes:
            return
        state.expanding = True
        try:
            scene_items = _structure_items_for_atom_ids(self.canvas, member_atom_ids)
            scene_items.extend(item for item in missing_items if item.data(0) != "note")
            set_scene_items_selected_for(self.canvas, scene_items, True)
            for note in missing_items:
                if note.data(0) == "note":
                    self.select_note(note, additive=True)
            for note in stale_notes:
                self.toggle_note_selection(note)
            self.update_selection_outline()
        finally:
            state.expanding = False
