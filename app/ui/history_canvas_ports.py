from __future__ import annotations

from ui.canvas_service_access import canvas_services_for


def history_hit_testing_service_for(canvas):
    return canvas_services_for(canvas).hit_testing_service


def history_atom_mutation_service_for(canvas):
    return canvas_services_for(canvas).canvas_atom_mutation_service


def history_bond_mutation_service_for(canvas):
    return canvas_services_for(canvas).canvas_bond_mutation_service


__all__ = [
    "history_atom_mutation_service_for",
    "history_bond_mutation_service_for",
    "history_hit_testing_service_for",
]
