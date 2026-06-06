from __future__ import annotations

from types import SimpleNamespace

from ui.history_canvas_ports import (
    history_atom_mutation_service_for,
    history_bond_mutation_service_for,
    history_hit_testing_service_for,
)


def test_history_canvas_ports_return_explicit_services() -> None:
    hit_testing_service = object()
    atom_mutation_service = object()
    bond_mutation_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(
            hit_testing_service=hit_testing_service,
            canvas_atom_mutation_service=atom_mutation_service,
            canvas_bond_mutation_service=bond_mutation_service,
        )
    )

    assert history_hit_testing_service_for(canvas) is hit_testing_service
    assert history_atom_mutation_service_for(canvas) is atom_mutation_service
    assert history_bond_mutation_service_for(canvas) is bond_mutation_service
