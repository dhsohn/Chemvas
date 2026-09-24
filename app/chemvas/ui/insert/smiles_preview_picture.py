"""Record the shared molecular drawing in a picture, without an editor or history."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QRectF
from PyQt6.QtGui import QPainter, QPicture
from PyQt6.QtWidgets import QGraphicsScene

from chemvas.features.graph import build_bond_adjacency_index
from chemvas.features.insertion import (
    annotation_mark_direction,
    annotation_mark_kinds,
    normalized_atom_annotation,
)
from chemvas.ui.canvas.molecule_scene_renderer import (
    prepare_molecule_for_scene,
    render_molecule,
)
from chemvas.ui.scene.scene_render_context import SceneRenderState
from chemvas.ui.scene.scene_rendering import build_scene_render_context

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.scene.scene_render_context import SceneStyleRenderer

# Slack around the structure, in bond lengths, so that label glyphs, charge
# marks and hydrogen counts that paint past their atoms are recorded rather
# than clipped by the render rectangle.
PREVIEW_MARGIN_BOND_LENGTHS = 3.0


def render_smiles_preview_picture(
    renderer: SceneStyleRenderer, model: MoleculeModel
) -> QPicture:
    """Keep model coordinates and caller-owned model/style/application unchanged."""
    preview_model = copy.deepcopy(model)
    prepare_molecule_for_scene(preview_model)
    state = SceneRenderState()
    state.graph_state.atom_neighbors, state.graph_state.atom_bond_ids = (
        build_bond_adjacency_index(preview_model.atoms, preview_model.bonds)
    )
    scene = QGraphicsScene()
    try:
        context = build_scene_render_context(
            scene_provider=lambda: scene,
            model_provider=lambda: preview_model,
            renderer=copy.copy(renderer),
            state=state,
        )
        render_molecule(context)
        # Use the insertion policy for direction and the shared label geometry
        # for distance; previews have no editor mark registry or history to update.
        for atom_id, annotation in preview_model.atom_annotations.items():
            atom = preview_model.atoms.get(atom_id)
            if atom is None:
                continue
            kinds = annotation_mark_kinds(normalized_atom_annotation(annotation))
            for index, kind in enumerate(kinds):
                dx, dy = annotation_mark_direction(
                    index, model=preview_model, atom_id=atom_id
                )
                offset = context.geometry.mark_offset_from_click(
                    atom_id, QPointF(atom.x + dx, atom.y + dy), kind=kind
                )
                item = context.decorations.build_mark_item(kind)
                if item is not None:
                    scene.addItem(item)
                    context.decorations.set_mark_center(
                        item, QPointF(atom.x + offset.x(), atom.y + offset.y())
                    )
        margin = renderer.style.bond_length_px * PREVIEW_MARGIN_BOND_LENGTHS
        left, top, right, bottom = model.bounds()
        bounds = (
            QRectF(left, top, right - left, bottom - top)
            .united(scene.itemsBoundingRect())
            .adjusted(-margin, -margin, margin, margin)
        )
        picture = QPicture()
        painter = QPainter(picture)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            # Equal target and source rectangles keep picture coordinates
            # identical to scene (model) coordinates.
            scene.render(painter, bounds, bounds)
        finally:
            painter.end()
        picture.setBoundingRect(bounds.toAlignedRect())
        return picture
    finally:
        scene.deleteLater()
        QCoreApplication.sendPostedEvents(scene, QEvent.Type.DeferredDelete)


__all__ = ["render_smiles_preview_picture"]
