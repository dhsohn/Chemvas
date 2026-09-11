from __future__ import annotations

import math
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF

from chemvas.core.history import HistoryCommand, SetAtomPositionsCommand
from chemvas.features.rendering import refresh_bond_graphics
from chemvas.features.selection import rotated_atom_positions, rotation_drag_angle
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.bond_graphics_access import add_bond_graphics_for
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_graph_state import graph_state_for
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import (
    atoms_for,
    bonds_for,
)
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_canvas_access import set_atom_positions_for_history
from chemvas.ui.history_commands import SetSceneGeometryCommand, UpdateSceneItemCommand
from chemvas.ui.history_recording_access import record_bond_update_for
from chemvas.ui.move_access import move_atoms_for, move_item_for
from chemvas.ui.scene_align_logic import align_deltas, distribute_deltas
from chemvas.ui.scene_flip_geometry import (
    bounds_from_points as bounds_from_points_logic,
)
from chemvas.ui.scene_flip_geometry import (
    flip_bounds_for_item,
    flip_center_for_selection,
)
from chemvas.ui.scene_flip_geometry import (
    flip_point as flip_point_logic,
)
from chemvas.ui.scene_flip_grouping import (
    build_flip_atom_position_maps,
    group_items_for_flip_transform,
)
from chemvas.ui.scene_flip_state import flip_scene_item_state
from chemvas.ui.scene_item_access import (
    apply_scene_item_state as apply_scene_item_state_helper,
)
from chemvas.ui.scene_item_access import remove_item_from_canvas_scene
from chemvas.ui.scene_item_state import (
    ARROW_KINDS,
    bond_state_dict,
    scene_item_state_for,
    ts_bracket_rect_from_state,
)
from chemvas.ui.scene_rotation_state import rotate_scene_item_state, rotated_point
from chemvas.ui.scene_signal_blocking import blocked_scene_signals
from chemvas.ui.scene_single_item_mutation_logic import (
    apply_bond_style_with_history,
    cycle_bond_style_with_history,
    flip_bond_direction_with_history,
)
from chemvas.ui.scene_transform_apply_logic import (
    apply_component_flip_transform,
    apply_standalone_flip_transform,
)
from chemvas.ui.selection_collection_access import (
    independent_selection_items,
    selected_atom_ids_for_transform_for,
    selected_items_for_transform_for,
)
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.transactions.document import document_transaction

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.canvas_view import CanvasView


@dataclass(frozen=True, slots=True)
class _AlignObject:
    """One thing Align/Distribute moves as a unit.

    A whole molecule (every atom of a structure that has a selected atom), a
    standalone scene item, or a group carrying both.
    """

    rect: QRectF
    atom_ids: frozenset[int]
    items: tuple[object, ...]


ROTATION_STATE_ITEM_KINDS = ARROW_KINDS | {
    "orbital",
    "mark",
    "note",
    "image",
    "ts_bracket",
    "shape",
}


@dataclass(slots=True)
class RotationDragSession:
    """One rotation-handle drag: what turns, about where, and how far so far.

    Every frame is computed from the positions and states captured at the
    press, so the sweep never accumulates rounding and a return to the
    starting angle restores the document exactly.
    """

    center: QPointF
    press_pos: QPointF
    before_positions: dict[int, tuple[float, float]]
    item_states: tuple[tuple[QGraphicsItem, dict], ...]
    before_coords_3d: dict[int, tuple[float, float, float]]
    angle_degrees: float = 0.0


def _atomic_history_transform(operation):
    @wraps(operation)
    def run(controller, *args, **kwargs):
        with (
            document_transaction(
                controller.canvas,
                history_service=controller.history,
            ),
            blocked_scene_signals(controller.canvas.scene()),
        ):
            return operation(controller, *args, **kwargs)

    return run


class SceneTransformController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.graph = graph_state_for(canvas)
        self.graph_service = graph_service
        self.history = history_service
        self.marks = mark_registry_for(canvas)

    @property
    def _atoms(self):
        return atoms_for(self.canvas)

    @property
    def _bonds(self):
        return bonds_for(self.canvas)

    def _graph_service(self):
        if self.graph_service is None:
            msg = "SceneTransformController requires graph_service"
            raise RuntimeError(msg)
        return self.graph_service

    def _add_bond_graphics(self, bond_id: int) -> None:
        add_bond_graphics_for(self.canvas, bond_id)

    def _set_atom_positions(
        self,
        positions: dict[int, tuple[float, float]],
        *,
        update_selection: bool = True,
        coords_3d: dict[int, tuple[float, float, float]] | None = None,
    ) -> None:
        set_atom_positions_for_history(
            self.canvas,
            positions,
            update_selection=update_selection,
            coords_3d=coords_3d,
        )

    def _atom_coords_3d(self, atom_ids):
        coords = atom_coords_3d_for(self.canvas)
        return {atom_id: coords[atom_id] for atom_id in atom_ids if atom_id in coords}

    def _atom_geometry_command(self, before_positions, before_coords_3d):
        rotation = rotation_state_for(self.canvas)
        return SetAtomPositionsCommand(
            before_positions=before_positions,
            after_positions={
                atom_id: (self._atoms[atom_id].x, self._atoms[atom_id].y)
                for atom_id in before_positions
            },
            before_coords_3d=before_coords_3d,
            after_coords_3d=self._atom_coords_3d(before_positions),
            restore_projection_state=True,
            before_projection_center_3d=rotation.projection_center_3d,
            after_projection_center_3d=rotation.projection_center_3d,
            before_projection_anchor_2d=rotation.projection_anchor_2d,
            after_projection_anchor_2d=rotation.projection_anchor_2d,
            update_selection=False,
        )

    def _translate_geometry(self, atom_ids, items, dx, dy):
        before_positions = {
            atom_id: (self._atoms[atom_id].x, self._atoms[atom_id].y)
            for atom_id in atom_ids
        }
        before_coords = self._atom_coords_3d(atom_ids)
        # Bound marks and ring fills are moved by the atom operation. Record
        # them too, and restore them *after* their atoms in both directions.
        dependent_items = self._atom_bound_marks(atom_ids) + [
            item
            for item in ring_items_for(self.canvas)
            if atom_ids.intersection(item.data(2) or ())
        ]
        before_items = [
            (item, self._scene_item_state(item))
            for item in dict.fromkeys([*dependent_items, *items])
        ]
        if atom_ids:
            bond_ids, boundary_ids = self._graph_service().bond_sets_for_atoms(atom_ids)
            move_atoms_for(
                self.canvas,
                atom_ids,
                dx,
                dy,
                bond_ids=bond_ids,
                redraw_bond_ids=boundary_ids,
                update_selection=False,
                rebuild_stale_bond_topology=True,
            )
        for item in items:
            move_item_for(self.canvas, item, dx, dy, update_selection=False)
        return SetSceneGeometryCommand(
            atom_commands=(
                [self._atom_geometry_command(before_positions, before_coords)]
                if before_positions
                else []
            ),
            item_commands=[
                UpdateSceneItemCommand(item, before, self._scene_item_state(item))
                for item, before in before_items
                if before
            ],
        )

    def _redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(
                atom_id, skip_bond_id=skip_bond_id
            )

    def _bond_state(self, bond) -> dict:
        return bond_state_dict(bond)

    def _scene_item_state(self, item) -> dict:
        return scene_item_state_for(self.canvas, item)

    def _record_bond_update(self, *args) -> None:
        record_bond_update_for(self.canvas, *args)

    def _apply_scene_item_state(self, item, state: dict) -> None:
        apply_scene_item_state_helper(self.canvas, item, state)

    def _flip_bounds_for_item(self, item):
        return flip_bounds_for_item(
            item,
            scene_item_state_getter=self._scene_item_state,
            bounds_from_points=bounds_from_points_logic,
        )

    def _rebuild_bond_graphics(self, bond_id: int, *, redraw_connected: bool) -> None:
        refresh_bond_graphics(
            bond_id,
            bonds=self._bonds,
            bond_items=bond_items_for(self.canvas),
            remove_scene_item=lambda item: remove_item_from_canvas_scene(
                self.canvas, item
            ),
            add_bond_graphics=self._add_bond_graphics,
            redraw_connected=redraw_connected,
            redraw_connected_bonds=self._redraw_connected_bonds,
        )

    def flip_bond_direction(self, bond_id: int) -> None:
        flip_bond_direction_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=last_smiles_input_for(self.canvas),
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self._record_bond_update,
        )

    def apply_bond_style(self, bond_id: int, style: str, order: int) -> None:
        apply_bond_style_with_history(
            bond_id,
            bonds=self._bonds,
            style=style,
            order=order,
            before_smiles_input=last_smiles_input_for(self.canvas),
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self._record_bond_update,
        )

    def cycle_bond_style(self, bond_id: int) -> None:
        cycle_bond_style_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=last_smiles_input_for(self.canvas),
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            rebuild_bond_graphics=self._rebuild_bond_graphics,
            record_bond_update=self._record_bond_update,
        )

    def selected_atom_components_for_transform(
        self, atom_ids: set[int]
    ) -> list[set[int]]:
        if not atom_ids:
            return []
        component_key = (frozenset(atom_ids), self.graph.graph_version)
        if component_key != self.graph.selection_component_cache_signature:
            self.graph.selection_component_cache_signature = component_key
            self.graph.selection_component_cache = (
                self._graph_service().connected_components(atom_ids)
            )
        return [set(component) for component in self.graph.selection_component_cache]

    @_atomic_history_transform
    def flip_selected_items(self, horizontal: bool) -> None:
        items = selected_items_for_transform_for(self.canvas)
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        if not atom_ids and not items:
            return

        atom_commands: list[SetAtomPositionsCommand] = []
        item_commands: list[UpdateSceneItemCommand] = []
        atom_components = self.selected_atom_components_for_transform(atom_ids)
        groups = group_items_for_flip_transform(
            items,
            atom_components=atom_components,
            marks_by_atom=self.marks.by_atom,
        )

        # Like rotation, flip is one transform of the whole selection. Per-object
        # pivots would leave a group's caption/image in place and destroy its layout.
        center = flip_center_for_selection(
            atom_ids,
            items,
            atoms=self._atoms,
            flip_bounds_getter=self._flip_bounds_for_item,
        )
        if center is None:
            return

        def flip_state(item, before_state, center, is_horizontal, transformed):
            return flip_scene_item_state(
                item,
                before_state,
                center=center,
                horizontal=is_horizontal,
                transformed_atom_positions=transformed,
                atoms=self._atoms,
                flip_point=flip_point_logic,
                ts_bracket_rect_from_state=ts_bracket_rect_from_state,
            )

        for component, component_items in zip(
            atom_components, groups.component_items, strict=False
        ):
            position_maps = build_flip_atom_position_maps(
                sorted(component),
                atoms=self._atoms,
                center=center,
                flip_point=lambda point, pivot: flip_point_logic(
                    point, pivot, horizontal
                ),
            )
            before_coords = self._atom_coords_3d(component)
            component_commands = apply_component_flip_transform(
                component_items=component_items,
                scene_item_state_getter=self._scene_item_state,
                position_maps=position_maps,
                center=center,
                horizontal=horizontal,
                flip_state_getter=flip_state,
                set_atom_positions=self._set_atom_positions,
                apply_scene_item_state=self._apply_scene_item_state,
            )
            atom_command = next(
                (
                    command
                    for command in component_commands
                    if isinstance(command, SetAtomPositionsCommand)
                ),
                None,
            )
            if atom_command is not None:
                atom_commands.append(
                    self._atom_geometry_command(
                        atom_command.before_positions, before_coords
                    )
                )
            item_commands.extend(
                command
                for command in component_commands
                if isinstance(command, UpdateSceneItemCommand)
            )

        for item in groups.standalone_items:
            command = apply_standalone_flip_transform(
                item,
                scene_item_state_getter=self._scene_item_state,
                center=center,
                horizontal=horizontal,
                flip_state_getter=flip_state,
                apply_scene_item_state=self._apply_scene_item_state,
            )
            if command is None:
                continue
            item_commands.append(command)

        if not atom_commands and not item_commands:
            return
        refresh_selection_outline_for(self.canvas)
        geometry_command = SetSceneGeometryCommand(atom_commands, item_commands)
        if self.history.push(geometry_command) is False:
            raise RuntimeError("Selection flip history push did not commit")

    @_atomic_history_transform
    def translate_selected_items(self, dx: float, dy: float) -> bool:
        if not dx and not dy:
            return False
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        items = independent_selection_items(
            selected_items_for_transform_for(self.canvas), atom_ids
        )
        if not atom_ids and not items:
            return False
        command = self._translate_geometry(atom_ids, items, dx, dy)
        refresh_selection_outline_for(self.canvas)
        if self.history.push(command) is False:
            raise RuntimeError("Selection translation history push did not commit")
        return True

    def _object_rect(self, atom_ids: set[int], items: list) -> QRectF | None:
        rect: QRectF | None = None
        for atom_id in sorted(atom_ids):
            atom_item = visible_atom_item_for(self.canvas, atom_id)
            if atom_item is not None:
                atom_rect = atom_item.sceneBoundingRect()
            else:
                atom = atoms_for(self.canvas).get(atom_id)
                if atom is None:
                    continue
                atom_rect = QRectF(atom.x, atom.y, 0.0, 0.0)
            rect = atom_rect if rect is None else rect.united(atom_rect)
        for item in items:
            item_rect = item.sceneBoundingRect()
            rect = item_rect if rect is None else rect.united(item_rect)
        return rect

    def _alignment_objects(self) -> list[_AlignObject]:
        selected_atoms = selected_atom_ids_for_transform_for(self.canvas)
        items = independent_selection_items(
            selected_items_for_transform_for(self.canvas), selected_atoms
        )
        # A structure moves whole even when only part of it is selected, so
        # Align never stretches a bond: expand each selected atom to its full
        # molecule rather than to the component of the selected atoms only.
        structures = [
            set(component)
            for component in self._graph_service().connected_components(
                set(atoms_for(self.canvas))
            )
            if component & selected_atoms
        ]
        objects: list[_AlignObject] = []
        claimed_atoms: set[int] = set()
        claimed_items: set[int] = set()
        # A group is one object: its structures and items keep their layout.
        for group in group_state_for(self.canvas).groups.values():
            group_atoms: set[int] = set()
            for structure in structures:
                if structure & group.atom_ids:
                    group_atoms |= structure
            group_items = [item for item in items if item in group.items]
            if not group_atoms and not group_items:
                continue
            rect = self._object_rect(group_atoms, group_items)
            if rect is None:
                continue
            objects.append(
                _AlignObject(rect, frozenset(group_atoms), tuple(group_items))
            )
            claimed_atoms |= group_atoms
            claimed_items |= {id(item) for item in group_items}
        for structure in structures:
            if structure & claimed_atoms:
                continue
            rect = self._object_rect(structure, [])
            if rect is not None:
                objects.append(_AlignObject(rect, frozenset(structure), ()))
        for item in items:
            if id(item) in claimed_items:
                continue
            rect = item.sceneBoundingRect()
            if rect.isValid():
                objects.append(_AlignObject(rect, frozenset(), (item,)))
        return objects

    def _apply_object_deltas(
        self, objects: list[_AlignObject], deltas: list[tuple[float, float]]
    ) -> bool:
        commands: list[SetSceneGeometryCommand] = []
        for target, (dx, dy) in zip(objects, deltas, strict=True):
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                continue
            commands.append(
                self._translate_geometry(
                    set(target.atom_ids), list(target.items), dx, dy
                )
            )
        if not commands:
            return False
        refresh_selection_outline_for(self.canvas)
        command = SetSceneGeometryCommand(
            atom_commands=[
                atom_command
                for entry in commands
                for atom_command in entry.atom_commands
            ],
            item_commands=[
                item_command
                for entry in commands
                for item_command in entry.item_commands
            ],
        )
        if self.history.push(command) is False:
            raise RuntimeError("Selection alignment history push did not commit")
        return True

    @_atomic_history_transform
    def align_selected_items(self, mode: str) -> bool:
        objects = self._alignment_objects()
        if len(objects) < 2:
            return False
        return self._apply_object_deltas(
            objects, align_deltas([target.rect for target in objects], mode)
        )

    @_atomic_history_transform
    def distribute_selected_items(self, axis: str) -> bool:
        objects = self._alignment_objects()
        if len(objects) < 3:
            return False
        return self._apply_object_deltas(
            objects, distribute_deltas([target.rect for target in objects], axis)
        )

    def _atom_bound_marks(self, atom_ids: set[int]) -> list:
        marks: list = []
        seen: set = set()
        for atom_id in atom_ids:
            for mark in self.marks.by_atom.get(atom_id, ()):
                if mark is None or mark in seen:
                    continue
                seen.add(mark)
                marks.append(mark)
        return marks

    @staticmethod
    def _rotation_state_items(items: list) -> list:
        return [item for item in items if item.data(0) in ROTATION_STATE_ITEM_KINDS]

    def _rotation_selection(self) -> tuple[set[int], list, list]:
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        items = self._rotation_state_items(
            independent_selection_items(
                selected_items_for_transform_for(self.canvas), atom_ids
            )
        )
        transform_items = self._atom_bound_marks(atom_ids) + items
        return atom_ids, items, transform_items

    def _rotation_center(self, atom_ids: set[int], items: list):
        return flip_center_for_selection(
            atom_ids,
            items,
            atoms=self._atoms,
            flip_bounds_getter=self._flip_bounds_for_item,
        )

    @_atomic_history_transform
    def rotate_selected_items(self, angle_degrees: float) -> None:
        if not angle_degrees:
            return
        atom_ids, items, transform_items = self._rotation_selection()
        # Marks attached to selected atoms are filtered out of ``items`` (their
        # atom carries them), but a translation-only atom move would leave the
        # mark on the same side of the atom. Rotate them explicitly like flip.
        if not atom_ids and not transform_items:
            return
        center = self._rotation_center(atom_ids, items)
        if center is None:
            return
        before_positions: dict[int, tuple[float, float]] = {}
        before_coords = self._atom_coords_3d(atom_ids)
        for atom_id in atom_ids:
            atom = self._atoms.get(atom_id)
            if atom is None:
                continue
            before_positions[atom_id] = (atom.x, atom.y)
        after_positions = rotated_atom_positions(
            before_positions.keys(),
            atoms=self._atoms,
            center=center,
            angle_radians=math.radians(angle_degrees),
        )
        # Capture item states before moving atoms so atom-bound marks are read
        # at their original positions (set_atom_positions repositions them).
        item_updates: list[tuple[object, dict, dict]] = []
        for item in transform_items:
            before_state = self._scene_item_state(item)
            after_state = rotate_scene_item_state(
                item,
                before_state,
                center=center,
                angle_degrees=angle_degrees,
                transformed_atom_positions=after_positions,
                atoms=self._atoms,
                ts_bracket_rect_from_state=ts_bracket_rect_from_state,
            )
            if not before_state or not after_state or before_state == after_state:
                continue
            item_updates.append((item, before_state, after_state))
        atom_command = None
        if after_positions and before_positions != after_positions:
            self._set_atom_positions(after_positions, update_selection=False)
            atom_command = self._atom_geometry_command(before_positions, before_coords)
        item_commands = []
        for item, before_state, after_state in item_updates:
            self._apply_scene_item_state(item, after_state)
            item_commands.append(
                UpdateSceneItemCommand(item, before_state, after_state)
            )
        if atom_command is None and not item_commands:
            return
        refresh_selection_outline_for(self.canvas)
        if (
            self.history.push(
                SetSceneGeometryCommand(
                    [atom_command] if atom_command else [], item_commands
                )
            )
            is False
        ):
            raise RuntimeError("Selection rotation history push did not commit")

    def begin_rotation_drag(self, press_pos: QPointF) -> RotationDragSession | None:
        """Capture what a rotation-handle drag turns, or ``None`` if nothing."""
        atom_ids, items, transform_items = self._rotation_selection()
        if not atom_ids and not transform_items:
            return None
        center = self._rotation_center(atom_ids, items)
        if center is None:
            return None
        before_positions: dict[int, tuple[float, float]] = {}
        for atom_id in atom_ids:
            atom = self._atoms.get(atom_id)
            if atom is not None:
                before_positions[atom_id] = (atom.x, atom.y)
        # Read item states before any atom moves: an atom-bound mark is
        # repositioned by set_atom_positions, so its state must be the
        # pre-drag one for every frame to rotate from.
        item_states = tuple(
            (item, self._scene_item_state(item)) for item in transform_items
        )
        return RotationDragSession(
            center=QPointF(center),
            press_pos=QPointF(press_pos),
            before_positions=before_positions,
            item_states=item_states,
            before_coords_3d=self._atom_coords_3d(before_positions),
        )

    def update_rotation_drag(
        self,
        session: RotationDragSession,
        pos: QPointF,
        *,
        snap_step: float | None = None,
    ) -> None:
        angle = rotation_drag_angle(
            session.center, session.press_pos, pos, snap_step=snap_step
        )
        if angle == session.angle_degrees:
            return
        session.angle_degrees = angle
        after_positions, item_updates = self._rotation_drag_result(session)
        if after_positions:
            self._set_atom_positions(
                after_positions,
                update_selection=False,
                coords_3d=session.before_coords_3d if angle == 0.0 else None,
            )
        if angle == 0.0:
            # Back at the start: items that turned earlier in this drag return
            # to the state captured at the press.
            item_updates = [
                (item, before_state, before_state)
                for item, before_state in session.item_states
                if before_state
            ]
        for item, _before_state, after_state in item_updates:
            self._apply_scene_item_state(item, after_state)
        refresh_selection_outline_for(self.canvas)

    def rotation_drag_command(
        self, session: RotationDragSession
    ) -> HistoryCommand | None:
        """The one history command for a finished drag; ``None`` if it did not turn."""
        after_positions, item_updates = self._rotation_drag_result(session)
        atom_command = None
        if after_positions and session.before_positions != after_positions:
            atom_command = self._atom_geometry_command(
                dict(session.before_positions), session.before_coords_3d
            )
        item_commands = []
        for item, before_state, after_state in item_updates:
            item_commands.append(
                UpdateSceneItemCommand(item, before_state, after_state)
            )
        if atom_command is None and not item_commands:
            return None
        return SetSceneGeometryCommand(
            [atom_command] if atom_command else [], item_commands
        )

    def _rotation_drag_result(
        self, session: RotationDragSession
    ) -> tuple[dict[int, tuple[float, float]], list[tuple[QGraphicsItem, dict, dict]]]:
        angle_degrees = session.angle_degrees
        if angle_degrees == 0.0:
            # Rotating by nothing is the identity, which floating-point
            # rotation is not: hand back the captured positions themselves so
            # a drag that returns to its start restores the document exactly.
            return dict(session.before_positions), []
        angle_radians = math.radians(angle_degrees)
        after_positions: dict[int, tuple[float, float]] = {}
        for atom_id, (x, y) in session.before_positions.items():
            rotated = rotated_point(QPointF(x, y), session.center, angle_radians)
            after_positions[atom_id] = (rotated.x(), rotated.y())
        item_updates: list[tuple[QGraphicsItem, dict, dict]] = []
        for item, before_state in session.item_states:
            after_state = rotate_scene_item_state(
                item,
                before_state,
                center=session.center,
                angle_degrees=angle_degrees,
                transformed_atom_positions=after_positions,
                atoms=self._atoms,
                ts_bracket_rect_from_state=ts_bracket_rect_from_state,
            )
            if not before_state or not after_state or before_state == after_state:
                continue
            item_updates.append((item, before_state, after_state))
        return after_positions, item_updates


__all__ = ["RotationDragSession", "SceneTransformController"]
