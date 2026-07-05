from __future__ import annotations

from ui.canvas_service_access import optional_canvas_service_method
from ui.canvas_service_ports import structure_build_service_for_access
from ui.input_view_access import viewport_center_scene_pos_for
from ui.structure_template_commands import apply_structure_template_command


def _service_method(canvas, name: str):
    return optional_canvas_service_method(canvas, structure_build_service_for_access, name)


def add_structure_template_for(canvas, key: str) -> None:
    apply_structure_template_command(structure_build_service_for_access(canvas), key)


def add_benzene_template_for(canvas) -> None:
    center = viewport_center_scene_pos_for(canvas)
    structure_build_service_for_access(canvas).add_benzene_ring(center)


def sprout_bond_from_atom_for(canvas, atom_id: int, *, style: str, order: int, cyclic: bool = False) -> None:
    method = _service_method(canvas, "sprout_bond_from_atom")
    if method is not None:
        method(atom_id, style=style, order=order, cyclic=cyclic)


def sprout_acetyl_from_atom_for(canvas, atom_id: int) -> None:
    method = _service_method(canvas, "sprout_acetyl_from_atom")
    if method is not None:
        method(atom_id)


def sprout_dimethyl_from_atom_for(canvas, atom_id: int) -> None:
    method = _service_method(canvas, "sprout_dimethyl_from_atom")
    if method is not None:
        method(atom_id)


def sprout_benzene_from_atom_for(canvas, atom_id: int) -> None:
    method = _service_method(canvas, "sprout_benzene_from_atom")
    if method is not None:
        method(atom_id)


def sprout_regular_ring_from_atom_for(canvas, atom_id: int, n: int) -> None:
    method = _service_method(canvas, "sprout_regular_ring_from_atom")
    if method is not None:
        method(atom_id, n)


def fuse_benzene_to_bond_for(canvas, bond_id: int) -> None:
    method = _service_method(canvas, "fuse_benzene_to_bond")
    if method is not None:
        method(bond_id)


def fuse_regular_ring_to_bond_for(canvas, bond_id: int, n: int) -> None:
    method = _service_method(canvas, "fuse_regular_ring_to_bond")
    if method is not None:
        method(bond_id, n)


def fuse_chair_to_bond_for(canvas, bond_id: int, *, mirrored: bool = False) -> None:
    method = _service_method(canvas, "fuse_chair_to_bond")
    if method is not None:
        method(bond_id, mirrored=mirrored)


__all__ = [
    "add_benzene_template_for",
    "add_structure_template_for",
    "fuse_benzene_to_bond_for",
    "fuse_chair_to_bond_for",
    "fuse_regular_ring_to_bond_for",
    "sprout_acetyl_from_atom_for",
    "sprout_benzene_from_atom_for",
    "sprout_bond_from_atom_for",
    "sprout_dimethyl_from_atom_for",
    "sprout_regular_ring_from_atom_for",
]
