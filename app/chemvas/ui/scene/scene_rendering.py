"""Assemble drawing collaborators without an editor or a graphics view."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemvas.ui.annotations.arrows import ArrowRenderer
from chemvas.ui.annotations.graphics import (
    AnnotationGraphics,
)
from chemvas.ui.molecule.atom_label_renderer import AtomLabelRenderer
from chemvas.ui.molecule.bond_renderer import BondRenderer
from chemvas.ui.scene.scene_geometry import SceneGeometry
from chemvas.ui.scene.scene_render_context import SceneRenderContext

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QGraphicsScene

    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.scene.scene_render_context import (
        SceneRenderState,
        SceneStyleRenderer,
    )


def build_scene_render_context(
    *,
    scene_provider: Callable[[], QGraphicsScene],
    model_provider: Callable[[], MoleculeModel],
    renderer: SceneStyleRenderer,
    state: SceneRenderState,
) -> SceneRenderContext:
    context = SceneRenderContext(
        scene_provider=scene_provider,
        model_provider=model_provider,
        renderer=renderer,
        state=state,
    )
    context.geometry = SceneGeometry(context)
    context.atom_labels = AtomLabelRenderer(context)
    context.bonds = BondRenderer(context)
    context.decorations = AnnotationGraphics(context)
    context.arrows = ArrowRenderer(context)
    return context
