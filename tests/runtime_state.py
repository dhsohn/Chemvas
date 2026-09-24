from __future__ import annotations

from dataclasses import field, fields, make_dataclass
from typing import Any

from chemvas.domain.document import AnnotationCollection
from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_document_metadata_state import CanvasDocumentMetadataState
from chemvas.ui.canvas.canvas_runtime_state import CanvasRuntimeState
from chemvas.ui.scene.scene_render_context import SceneRenderState
from chemvas.ui.selection.selection_state import SelectionState

CANVAS_RUNTIME_STATE_FIELDS = frozenset(
    field.name for field in fields(CanvasRuntimeState)
)


_EDITOR_ONLY_FIELDS = sorted(
    CANVAS_RUNTIME_STATE_FIELDS - {field.name for field in fields(SceneRenderState)}
)

# The drawing state is real, so its scene-item methods work; the editor-only
# fields (selection, history, timers, ...) default to None and tests supply
# the ones they exercise. No slots: a test may still hang extra attributes on it.
_TestRuntimeState = make_dataclass(
    "_TestRuntimeState",
    [(name, Any, field(default=None)) for name in _EDITOR_ONLY_FIELDS],
    bases=(SceneRenderState,),
    kw_only=True,
)


def canvas_runtime_state(**states: Any) -> Any:
    """Partial canonical state container for focused legacy UI tests.

    State accessors read their field straight off ``canvas.runtime_state``, so a
    double needs one too. Names are checked against the real container: a test
    that invents a field would otherwise pin an accessor the product does not
    have.
    """
    unknown = sorted(set(states) - CANVAS_RUNTIME_STATE_FIELDS)
    if unknown:
        raise AssertionError(f"not CanvasRuntimeState fields: {unknown}")
    states.setdefault("atom_graphics_state", CanvasAtomGraphicsState())
    states.setdefault("bond_graphics_state", CanvasBondGraphicsState())
    states.setdefault("selection_state", SelectionState())
    states.setdefault("document_metadata_state", CanvasDocumentMetadataState())
    states.setdefault("shape_state", AnnotationCollection())
    states.setdefault("arrow_state", AnnotationCollection())
    states.setdefault("ts_bracket_state", AnnotationCollection())
    states.setdefault("image_state", AnnotationCollection())
    states.setdefault("orbital_state", AnnotationCollection())
    states.setdefault("ring_state", AnnotationCollection())
    states.setdefault("note_state", AnnotationCollection())
    states.setdefault("mark_state", AnnotationCollection())
    return _TestRuntimeState(**states)


__all__ = ["CANVAS_RUNTIME_STATE_FIELDS", "canvas_runtime_state"]
