"""Typed, feature-grouped runtime services for a canvas.

Group fields hold the concrete ``*ServiceBundle`` dataclasses built in
``chemvas.ui.canvas_services``. They are annotated ``Any`` here because naming
the bundle classes — even under ``TYPE_CHECKING`` — would put this module in a
type-only import cycle with the history/transaction cluster, which the
architecture boundary tests keep acyclic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chemvas.ui.hover import HoverController


@dataclass(slots=True)
class CanvasRuntimeServices:
    document: Any
    graph_service: Any
    input: Any
    interaction: Any
    scene_view: Any
    handles: Any
    hover: HoverController
    scene_decoration: Any
    scene_operations: Any
    selection: Any
    structure: Any
    tool_controller: Any
    atom_label_service: Any
    history_service: Any


__all__ = ["CanvasRuntimeServices"]
