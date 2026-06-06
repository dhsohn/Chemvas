from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ui.canvas_atom_mutation_service import CanvasAtomMutationService
from ui.canvas_bond_mutation_service import CanvasBondMutationService
from ui.insert_controller import InsertController
from ui.structure_build_service import StructureBuildService

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


@dataclass(slots=True)
class StructureServiceBundle:
    canvas_atom_mutation_service: CanvasAtomMutationService
    canvas_bond_mutation_service: CanvasBondMutationService
    structure_build_service: StructureBuildService
    insert_controller: InsertController


def build_structure_services(
    canvas: CanvasView | Any,
    *,
    hit_testing_service: Any,
    graph_service: Any,
    move_controller: Any,
    insert_state: Any,
    history_service: Any,
) -> StructureServiceBundle:
    canvas_atom_mutation_service = CanvasAtomMutationService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
    )
    canvas_bond_mutation_service = CanvasBondMutationService(
        canvas,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
    )
    structure_build_service = StructureBuildService(
        canvas,
        hit_testing_service=hit_testing_service,
        move_controller=move_controller,
        graph_service=graph_service,
    )
    insert_controller = InsertController(
        canvas,
        insert_state=insert_state,
        hit_testing_service=hit_testing_service,
        graph_service=graph_service,
        structure_build_service=structure_build_service,
        history_service=history_service,
    )
    return StructureServiceBundle(
        canvas_atom_mutation_service=canvas_atom_mutation_service,
        canvas_bond_mutation_service=canvas_bond_mutation_service,
        structure_build_service=structure_build_service,
        insert_controller=insert_controller,
    )


__all__ = ["StructureServiceBundle", "build_structure_services"]
