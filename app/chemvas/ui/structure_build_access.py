from __future__ import annotations

from chemvas.ui.canvas_service_ports import structure_build_service_for_access


def sprout_bond_from_atom_for(
    canvas, atom_id: int, *, style: str, order: int, cyclic: bool = False
) -> None:
    structure_build_service_for_access(canvas).sprout_bond_from_atom(
        atom_id, style=style, order=order, cyclic=cyclic
    )


def sprout_acetyl_from_atom_for(canvas, atom_id: int) -> None:
    structure_build_service_for_access(canvas).sprout_acetyl_from_atom(atom_id)


def sprout_dimethyl_from_atom_for(canvas, atom_id: int) -> None:
    structure_build_service_for_access(canvas).sprout_dimethyl_from_atom(atom_id)


def sprout_benzene_from_atom_for(canvas, atom_id: int) -> None:
    structure_build_service_for_access(canvas).sprout_benzene_from_atom(atom_id)


def sprout_regular_ring_from_atom_for(canvas, atom_id: int, n: int) -> None:
    structure_build_service_for_access(canvas).sprout_regular_ring_from_atom(atom_id, n)


def fuse_benzene_to_bond_for(canvas, bond_id: int) -> None:
    structure_build_service_for_access(canvas).fuse_benzene_to_bond(bond_id)


def fuse_regular_ring_to_bond_for(canvas, bond_id: int, n: int) -> None:
    structure_build_service_for_access(canvas).fuse_regular_ring_to_bond(bond_id, n)


def fuse_chair_to_bond_for(canvas, bond_id: int, *, mirrored: bool = False) -> None:
    structure_build_service_for_access(canvas).fuse_chair_to_bond(
        bond_id, mirrored=mirrored
    )


__all__ = [
    "fuse_benzene_to_bond_for",
    "fuse_chair_to_bond_for",
    "fuse_regular_ring_to_bond_for",
    "sprout_acetyl_from_atom_for",
    "sprout_benzene_from_atom_for",
    "sprout_bond_from_atom_for",
    "sprout_dimethyl_from_atom_for",
    "sprout_regular_ring_from_atom_for",
]
