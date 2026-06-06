from __future__ import annotations

from types import SimpleNamespace

from ui.structure_mutation_ports import (
    structure_mutation_atom_service,
    structure_mutation_bond_service,
    structure_mutation_build_service,
)


def test_structure_mutation_ports_return_explicit_services() -> None:
    atom_service = object()
    bond_service = object()
    build_service = object()
    canvas = SimpleNamespace(
        services=SimpleNamespace(
            canvas_atom_mutation_service=atom_service,
            canvas_bond_mutation_service=bond_service,
            structure_build_service=build_service,
        )
    )

    assert structure_mutation_atom_service(canvas) is atom_service
    assert structure_mutation_bond_service(canvas) is bond_service
    assert structure_mutation_build_service(canvas) is build_service
