"""The document drawing state shared by an editor and a standalone Qt scene.

An editor's runtime extends this state; the drawing context references that
same object. It never copies a document or owns input, selection or history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from chemvas.domain.document import AnnotationCollection, Arrow, Shape, TSBracket
from chemvas.features.graph import CanvasGraphState
from chemvas.ui.canvas.canvas_atom_graphics_state import CanvasAtomGraphicsState
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.canvas.sheet_setup_state import SheetSetupState
from chemvas.ui.molecule.atom_coords_access import CanvasAtomCoords3DState

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QBrush, QFont, QPen
    from PyQt6.QtWidgets import QGraphicsScene

    from chemvas.domain.document import Bond, MoleculeModel
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

    def bond_for_id(self, bond_id: int | None) -> Bond | None:
        bonds = self.model.bonds
        if bond_id is None or bond_id < 0 or bond_id >= len(bonds):
            return None
        return bonds[bond_id]
