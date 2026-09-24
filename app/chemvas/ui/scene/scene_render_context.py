"""The document drawing state shared by an editor and a standalone Qt scene.

An editor's runtime extends this state; the drawing context references that
same object. It never copies a document or owns input, selection or history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

from PyQt6 import sip

from chemvas.domain.document import AnnotationCollection, Arrow, Shape, TSBracket
from chemvas.features.graph import CanvasGraphState
from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.canvas_scene_items_state import (
    DOCUMENT_COLLECTION_STATES,
    SCENE_ITEM_COLLECTION_ATTRS,
    CanvasSceneItemsState,
    require_scene_record_id,
)
from chemvas.ui.canvas.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas.sheet_setup_state import SheetSetupState
from chemvas.ui.molecule.atom_coords_access import CanvasAtomCoords3DState

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QBrush, QFont, QPen
    from PyQt6.QtWidgets import QGraphicsScene

    from chemvas.domain.document import MoleculeModel
    from chemvas.domain.document.images import Image
    from chemvas.domain.document.marks import Mark
    from chemvas.domain.document.notes import Note
    from chemvas.domain.document.orbitals import Orbital
    from chemvas.domain.document.ring_fills import RingFill
    from chemvas.features.rendering import ACS1996Style
    from chemvas.ui.annotations.arrows import ArrowRenderer
    from chemvas.ui.annotations.graphics import (
        AnnotationGraphics,
    )
    from chemvas.ui.molecule.atom_label_renderer import AtomLabelRenderer
    from chemvas.ui.molecule.bond_renderer import BondRenderer
    from chemvas.ui.scene.scene_geometry import SceneGeometry


class SceneStyleRenderer(Protocol):
    style: ACS1996Style

    def set_bond_length(self, length_px: float) -> None: ...
    def metric_scale(self) -> float: ...
    def scaled_style_metric(self, value: float) -> float: ...
    def bond_line_width(self) -> float: ...
    def bold_bond_width(self) -> float: ...
    def bond_spacing(self) -> float: ...
    def hash_spacing(self) -> float: ...
    def atom_font_size_pt(self) -> int: ...
    def bond_pen(self) -> QPen: ...
    def dotted_bond_pen(self) -> QPen: ...
    def bold_bond_pen(self) -> QPen: ...
    def atom_font(self) -> QFont: ...
    def ring_fill_brush(self, color: str | None = None) -> QBrush: ...


@dataclass(slots=True, kw_only=True)
class SceneRenderState:
    graph_state: CanvasGraphState = field(default_factory=CanvasGraphState)
    atom_coords_3d_state: CanvasAtomCoords3DState = field(
        default_factory=CanvasAtomCoords3DState
    )
    atom_graphics_state: CanvasAtomGraphicsState = field(
        default_factory=CanvasAtomGraphicsState
    )
    bond_graphics_state: CanvasBondGraphicsState = field(
        default_factory=CanvasBondGraphicsState
    )
    mark_registry: CanvasMarkRegistry = field(default_factory=CanvasMarkRegistry)
    rotation_state: CanvasRotationState = field(default_factory=CanvasRotationState)
    scene_items_state: CanvasSceneItemsState = field(
        default_factory=CanvasSceneItemsState
    )
    shape_state: AnnotationCollection[Shape] = field(
        default_factory=AnnotationCollection
    )
    arrow_state: AnnotationCollection[Arrow] = field(
        default_factory=AnnotationCollection
    )
    ts_bracket_state: AnnotationCollection[TSBracket] = field(
        default_factory=AnnotationCollection
    )
    image_state: AnnotationCollection[Image] = field(
        default_factory=AnnotationCollection
    )
    orbital_state: AnnotationCollection[Orbital] = field(
        default_factory=AnnotationCollection
    )
    ring_state: AnnotationCollection[RingFill] = field(
        default_factory=AnnotationCollection
    )
    note_state: AnnotationCollection[Note] = field(default_factory=AnnotationCollection)
    mark_state: AnnotationCollection[Mark] = field(default_factory=AnnotationCollection)
    text_style_state: CanvasTextStyleState = field(default_factory=CanvasTextStyleState)
    tool_settings_state: CanvasToolSettingsState = field(
        default_factory=CanvasToolSettingsState
    )
    sheet_setup_state: SheetSetupState = field(default_factory=SheetSetupState)

    # Scene item projections are read through the document order so saved
    # arrays and group references keep their indices; a missing view is None.

    def document_collection(self, name: str) -> AnnotationCollection[Any]:
        return cast(
            "AnnotationCollection[Any]", getattr(self, DOCUMENT_COLLECTION_STATES[name])
        )

    def scene_items(self, name: str) -> list[Any]:
        views = getattr(self.scene_items_state, name)
        return [
            views.get(record_id) for record_id in self.document_collection(name).order
        ]

    def append_scene_item(self, name: str, item: Any) -> None:
        record_id = require_scene_record_id(item)
        self.document_collection(name).add(record_id)
        getattr(self.scene_items_state, name)[record_id] = item
        self.scene_items_state.projections[record_id] = item

    def remove_scene_item(self, name: str, item: Any) -> bool:
        record_id = item.data(3)
        if type(record_id) is not int:
            return False
        removed = self.document_collection(name).remove(record_id)
        getattr(self.scene_items_state, name).pop(record_id, None)
        return removed

    def clear_scene_items(self) -> None:
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            self.document_collection(name).clear()
            setattr(self.scene_items_state, name, {})

    def restore_scene_item_order(
        self, name: str, entries: list[tuple[int, Any]]
    ) -> None:
        document = self.document_collection(name)
        order = list(document.order)
        ids = [(index, require_scene_record_id(item)) for index, item in entries]
        for _, record_id in ids:
            order.remove(record_id)
        for index, record_id in ids:
            order.insert(index, record_id)
        document.reorder(order)

    def _live_scene_items(self, name: str) -> list[Any]:
        return [item for item in self.scene_items(name) if item is not None]

    def note_items(self) -> list[Any]:
        return self._live_scene_items("note_items")

    def mark_items(self) -> list[Any]:
        return self._live_scene_items("mark_items")

    def arrow_items(self) -> list[Any]:
        return self._live_scene_items("arrow_items")

    def ts_bracket_items(self) -> list[Any]:
        return self._live_scene_items("ts_bracket_items")

    def shape_items(self) -> list[Any]:
        return self._live_scene_items("shape_items")

    def image_items(self) -> list[Any]:
        return self.scene_items("image_items")

    def orbital_items(self) -> list[Any]:
        return self.scene_items("orbital_items")

    def ring_items(self) -> list[Any]:
        return [
            item
            for item in self.scene_items("ring_items")
            if item is not None and not _ring_item_is_deleted(item)
        ]

    def ring_items_for_atoms(self, atom_ids: set[int]) -> list[Any]:
        """Ring items whose atom-id payload intersects ``atom_ids``.

        Skips sip-deleted wrappers so gesture-scoped discovery survives Qt
        teardown of individual rings.
        """
        affected: list[Any] = []
        for ring in self.ring_items():
            ring_atom_ids = ring.data(2)
            if isinstance(ring_atom_ids, list) and not atom_ids.isdisjoint(
                ring_atom_ids
            ):
                affected.append(ring)
        return affected


def _ring_item_is_deleted(item: Any) -> bool:
    try:
        return sip.isdeleted(item)
    except TypeError:
        return False


@dataclass(slots=True, kw_only=True)
class SceneRenderContext:
    scene_provider: Callable[[], QGraphicsScene]
    model_provider: Callable[[], MoleculeModel]
    renderer: SceneStyleRenderer
    state: SceneRenderState
    geometry: SceneGeometry = field(init=False)
    atom_labels: AtomLabelRenderer = field(init=False)
    bonds: BondRenderer = field(init=False)
    decorations: AnnotationGraphics = field(init=False)
    arrows: ArrowRenderer = field(init=False)

    @property
    def scene(self) -> QGraphicsScene:
        # A view may replace its scene through Qt's public setScene API.
        return self.scene_provider()

    @property
    def model(self) -> MoleculeModel:
        # GUI document replacement/rollback may replace its model. Read the
        # current owner instead of retaining a second, potentially stale model.
        return self.model_provider()
