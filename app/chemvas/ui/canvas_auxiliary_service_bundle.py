from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from chemvas.ui.atom_label_service import AtomLabelService
from chemvas.ui.structure_insert_service import StructureInsertService

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


@dataclass(slots=True)
class CanvasAuxiliaryServiceBundle:
    atom_label_service: AtomLabelService
    structure_insert_service: StructureInsertService


def build_canvas_auxiliary_services(
    canvas: CanvasView | Any,
    *,
    move_controller: Any,
    graph_service: Any,
    history_service: Any,
    hover_refresh: Any,
    note_controller: Any,
) -> CanvasAuxiliaryServiceBundle:
    atom_label_service = AtomLabelService(
        canvas,
        move_controller=move_controller,
        graph_service=graph_service,
        history_service=history_service,
        hover_refresh=hover_refresh,
    )
    structure_insert_service = StructureInsertService(
        canvas,
        note_controller=note_controller,
    )
    return CanvasAuxiliaryServiceBundle(
        atom_label_service=atom_label_service,
        structure_insert_service=structure_insert_service,
    )


__all__ = ["CanvasAuxiliaryServiceBundle", "build_canvas_auxiliary_services"]
