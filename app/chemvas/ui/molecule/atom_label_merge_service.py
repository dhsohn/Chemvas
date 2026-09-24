from __future__ import annotations

from typing import TYPE_CHECKING, cast

from chemvas.features.rendering import STANDARD_BOND_STYLES
from chemvas.ui.annotations.state import atom_state_dict_for, bond_state_dict
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    pop_atom_dot_for,
    pop_atom_item_for,
)
from chemvas.ui.canvas.canvas_bond_graphics_state import pop_bond_items_for
from chemvas.ui.molecule.atom_coords_access import pop_atom_coords_3d_for
from chemvas.ui.scene.scene_item_access import (
    remove_item_from_canvas_scene,
    remove_items_from_canvas_scene,
)

if TYPE_CHECKING:
    from chemvas.domain.document import Bond


class AtomLabelMergeService:
    def __init__(self, canvas, *, graph_service) -> None:
        self.canvas = canvas
        self.graph_service = graph_service

    def merge_overlapping_atoms(self, atom_id: int) -> tuple[list[int], dict]:
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return [], {}
        merge_ids = self._overlapping_atom_ids(atom_id)
        if not merge_ids:
            return [], {}
        merge_info = {
            "atom_states": {
                mid: atom_state_dict_for(self.canvas, mid) for mid in merge_ids
            },
            "bond_before_states": {},
            "deleted_bond_ids": [],
        }
        stored_coords_3d = self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
        atom_coords_3d = {
            atom_id: stored_coords_3d[atom_id]
            for atom_id in merge_ids
            if atom_id in stored_coords_3d
        }
        if atom_coords_3d:
            merge_info["atom_coords_3d"] = atom_coords_3d
        self._capture_bond_states_touching_merged_atoms(merge_ids, merge_info)
        self._remove_merged_atom_items(merge_ids)
        self._retarget_bonds(merge_ids, atom_id)
        self._delete_self_loop_bonds(merge_info)
        self._delete_duplicate_bonds(merge_info)
        for other_id in merge_ids:
            self.canvas.model.pop_atom(other_id)
            pop_atom_coords_3d_for(self.canvas, other_id)
        self.graph_service.rebuild_bond_adjacency()
        return merge_ids, merge_info

    def _overlapping_atom_ids(self, atom_id: int) -> list[int]:
        atom = self.canvas.model.atom_for_id(atom_id)
        if atom is None:
            return []
        tol = max(0.5, self.canvas.renderer.style.bond_length_px * 0.05)
        tol_sq = tol * tol
        merge_ids = []
        for other_id, other in self.canvas.model.atoms.items():
            if other_id == atom_id:
                continue
            dx = other.x - atom.x
            dy = other.y - atom.y
            if dx * dx + dy * dy <= tol_sq:
                merge_ids.append(other_id)
        return merge_ids

    def _capture_bond_states_touching_merged_atoms(
        self, merge_ids: list[int], merge_info: dict
    ) -> None:
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a in merge_ids or bond.b in merge_ids:
                merge_info["bond_before_states"][bond_id] = bond_state_dict(bond)

    def _remove_merged_atom_items(self, merge_ids: list[int]) -> None:
        for other_id in merge_ids:
            label = pop_atom_item_for(self.canvas, other_id)
            if label is not None:
                remove_item_from_canvas_scene(self.canvas, label)
            dot = pop_atom_dot_for(self.canvas, other_id)
            if dot is not None:
                remove_item_from_canvas_scene(self.canvas, dot)

    def _retarget_bonds(self, merge_ids: list[int], atom_id: int) -> None:
        for bond in self.canvas.model.bonds:
            if bond is None:
                continue
            if bond.a in merge_ids:
                bond.a = atom_id
            if bond.b in merge_ids:
                bond.b = atom_id

    def _delete_self_loop_bonds(self, merge_info: dict) -> None:
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            if bond.a == bond.b:
                self._delete_bond(bond_id, merge_info)

    def _delete_duplicate_bonds(self, merge_info: dict) -> None:
        pair_keep: dict[tuple[int, int], int] = {}
        duplicate_ids: set[int] = set()
        for bond_id, bond in enumerate(self.canvas.model.bonds):
            if bond is None:
                continue
            key = (bond.a, bond.b) if bond.a <= bond.b else (bond.b, bond.a)
            keep_id = pair_keep.get(key)
            if keep_id is None:
                pair_keep[key] = bond_id
                continue
            keep_bond = cast("Bond", self.canvas.model.bond_for_id(keep_id))
            if self._bond_rank(bond, bond_id) > self._bond_rank(keep_bond, keep_id):
                duplicate_ids.add(keep_id)
                pair_keep[key] = bond_id
            else:
                duplicate_ids.add(bond_id)
        for bond_id in sorted(duplicate_ids):
            self._delete_bond(bond_id, merge_info)

    def _delete_bond(self, bond_id: int, merge_info: dict) -> None:
        bond = cast("Bond", self.canvas.model.bond_for_id(bond_id))
        if bond_id not in merge_info["bond_before_states"]:
            merge_info["bond_before_states"][bond_id] = bond_state_dict(bond)
        remove_items_from_canvas_scene(
            self.canvas,
            self.canvas.runtime_state.bond_graphics_state.bond_items.get(bond_id, []),
        )
        pop_bond_items_for(self.canvas, bond_id)
        self.canvas.model.clear_bond(bond_id)
        merge_info["deleted_bond_ids"].append(bond_id)

    @staticmethod
    def _bond_rank(bond: Bond, bond_id: int) -> tuple[int, int, int]:
        order = int(bond.order or 1)
        special_style = 1 if bond.style not in STANDARD_BOND_STYLES else 0
        if bond.style == "double_either":
            # For equal orders, retain explicit unknown stereo before a purely
            # visual style; bond-list order must not erase the chemical marker.
            special_style = 2
        return (order, special_style, -bond_id)


__all__ = ["AtomLabelMergeService"]
