from __future__ import annotations

import math
from typing import TYPE_CHECKING

from core.history import (
    CompositeCommand,
    HistoryCommand,
    MoveAtomsCommand,
    SetAtomPositionsCommand,
)

from ui.bond_graphics_access import add_bond_graphics_for
from ui.bond_graphics_logic import refresh_bond_graphics
from ui.canvas_bond_graphics_state import bond_items_for
from ui.canvas_graph_state import graph_state_for
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import (
    atoms_for,
    bonds_for,
)
from ui.canvas_smiles_input_state import last_smiles_input_for
from ui.history_canvas_access import set_atom_positions_for_history
from ui.history_commands import MoveItemsCommand, UpdateSceneItemCommand
from ui.history_recording_access import record_bond_update_for
from ui.move_access import move_atoms_for, move_item_for
from ui.scene_flip_geometry import bounds_from_points as bounds_from_points_logic
from ui.scene_flip_geometry import (
    center_for_flip_group,
    flip_bounds_for_item,
    flip_center_for_selection,
)
from ui.scene_flip_geometry import (
    flip_point as flip_point_logic,
)
from ui.scene_flip_grouping import (
    build_flip_atom_position_maps,
    group_items_for_flip_transform,
)
from ui.scene_flip_state import flip_scene_item_state
from ui.scene_item_access import (
    apply_scene_item_state as apply_scene_item_state_helper,
)
from ui.scene_item_access import remove_item_from_canvas_scene
from ui.scene_item_state import (
    bond_state_dict,
    scene_item_state_for,
    ts_bracket_rect_from_state,
)
from ui.scene_rotation_state import rotate_scene_item_state
from ui.scene_single_item_mutation_logic import (
    apply_bond_style_with_history,
    cycle_bond_style_with_history,
    flip_bond_direction_with_history,
)
from ui.scene_transform_apply_logic import (
    apply_component_flip_transform,
    apply_standalone_flip_transform,
)
from ui.selection_center_logic import (
    bounding_box_center_for_atoms as bounding_box_center_for_atoms_logic,
)
from ui.selection_collection_access import (
    independent_selection_items,
    selected_atom_ids_for_transform_for,
    selected_items_for_transform_for,
)
from ui.selection_rotation_logic import rotated_atom_positions
from ui.selection_service_access import refresh_selection_outline_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


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

    def _set_atom_positions(self, positions: dict[int, tuple[float, float]], *, update_selection: bool = True) -> None:
        set_atom_positions_for_history(self.canvas, positions, update_selection=update_selection)

    def _redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id, skip_bond_id=skip_bond_id)

    def _bond_state(self, bond) -> dict:
        return bond_state_dict(bond)

    def _scene_item_state(self, item) -> dict:
        return scene_item_state_for(self.canvas, item)

    def _record_bond_update(self, *args) -> None:
        record_bond_update_for(self.canvas, *args)

    def _bounding_box_center_for_atoms(self, atom_ids: set[int]):
        return bounding_box_center_for_atoms_logic(atom_ids, atoms=self._atoms)

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
            remove_scene_item=lambda item: remove_item_from_canvas_scene(self.canvas, item),
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

    def selected_atom_components_for_transform(self, atom_ids: set[int]) -> list[set[int]]:
        if not atom_ids:
            return []
        component_key = (frozenset(atom_ids), self.graph.graph_version)
        if component_key != self.graph.selection_component_cache_signature:
            self.graph.selection_component_cache_signature = component_key
            self.graph.selection_component_cache = self._graph_service().connected_components(atom_ids)
        return [set(component) for component in self.graph.selection_component_cache]

    def flip_selected_items(self, horizontal: bool) -> None:
        items = selected_items_for_transform_for(self.canvas)
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        if not atom_ids and not items:
            return

        commands: list[HistoryCommand] = []
        atom_components = self.selected_atom_components_for_transform(atom_ids)
        groups = group_items_for_flip_transform(
            items,
            atom_components=atom_components,
            marks_by_atom=self.marks.by_atom,
        )

        def flip_center(selected_atom_ids, selected_items):
            return flip_center_for_selection(
                selected_atom_ids,
                selected_items,
                atoms=self._atoms,
                flip_bounds_getter=self._flip_bounds_for_item,
            )

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

        for component, component_items in zip(atom_components, groups.component_items, strict=False):
            center = center_for_flip_group(
                component,
                component_items,
                bounding_box_center_for_atoms=self._bounding_box_center_for_atoms,
                flip_center_for_selection_getter=flip_center,
            )
            if center is None:
                continue
            position_maps = build_flip_atom_position_maps(
                sorted(component),
                atoms=self._atoms,
                center=center,
                flip_point=lambda point, pivot: flip_point_logic(point, pivot, horizontal),
            )
            commands.extend(
                apply_component_flip_transform(
                    component_items=component_items,
                    scene_item_state_getter=self._scene_item_state,
                    position_maps=position_maps,
                    center=center,
                    horizontal=horizontal,
                    flip_state_getter=flip_state,
                    set_atom_positions=self._set_atom_positions,
                    apply_scene_item_state=self._apply_scene_item_state,
                )
            )

        for item in groups.standalone_items:
            center = center_for_flip_group(
                set(),
                [item],
                bounding_box_center_for_atoms=self._bounding_box_center_for_atoms,
                flip_center_for_selection_getter=flip_center,
            )
            if center is None:
                continue
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
            commands.append(command)

        if not commands:
            return
        refresh_selection_outline_for(self.canvas)
        if len(commands) == 1:
            self.history.push(commands[0])
            return
        self.history.push(CompositeCommand(commands))

    def translate_selected_items(self, dx: float, dy: float) -> bool:
        if not dx and not dy:
            return False
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        items = independent_selection_items(selected_items_for_transform_for(self.canvas), atom_ids)
        if not atom_ids and not items:
            return False
        commands: list[HistoryCommand] = []
        if atom_ids:
            move_atoms_for(self.canvas, atom_ids, dx, dy, update_selection=False)
            commands.append(MoveAtomsCommand(atom_ids=set(atom_ids), dx=dx, dy=dy))
        if items:
            for item in items:
                move_item_for(self.canvas, item, dx, dy, update_selection=False)
            commands.append(MoveItemsCommand(items=list(items), dx=dx, dy=dy))
        refresh_selection_outline_for(self.canvas)
        if len(commands) == 1:
            self.history.push(commands[0])
        else:
            self.history.push(CompositeCommand(commands))
        return True

    def rotate_selected_items(self, angle_degrees: float) -> None:
        if not angle_degrees:
            return
        atom_ids = selected_atom_ids_for_transform_for(self.canvas)
        items = independent_selection_items(selected_items_for_transform_for(self.canvas), atom_ids)
        if not atom_ids and not items:
            return
        center = flip_center_for_selection(
            atom_ids,
            items,
            atoms=self._atoms,
            flip_bounds_getter=self._flip_bounds_for_item,
        )
        if center is None:
            return
        before_positions: dict[int, tuple[float, float]] = {}
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
        commands: list[HistoryCommand] = []
        if after_positions and before_positions != after_positions:
            self._set_atom_positions(after_positions, update_selection=False)
            commands.append(
                SetAtomPositionsCommand(
                    before_positions=before_positions,
                    after_positions=after_positions,
                )
            )
        for item in items:
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
            self._apply_scene_item_state(item, after_state)
            commands.append(UpdateSceneItemCommand(item, before_state, after_state))
        if not commands:
            return
        refresh_selection_outline_for(self.canvas)
        if len(commands) == 1:
            self.history.push(commands[0])
            return
        self.history.push(CompositeCommand(commands))


__all__ = ["SceneTransformController"]
