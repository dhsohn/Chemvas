from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def structure_mutation_atom_service(canvas):
    return canvas_services_for(canvas).canvas_atom_mutation_service


def structure_mutation_bond_service(canvas):
    return canvas_services_for(canvas).canvas_bond_mutation_service


def structure_mutation_build_service(canvas):
    return canvas_services_for(canvas).structure_build_service


__all__ = [
    "structure_mutation_atom_service",
    "structure_mutation_bond_service",
    "structure_mutation_build_service",
]
