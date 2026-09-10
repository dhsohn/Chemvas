"""Render an inserted SMILES model exactly as the canvas will draw it.

The insertion preview used to sketch bonds as bare line pairs and every atom
as a dot, so ring double bonds and heteroatom labels looked nothing like the
structure that landed on click. Instead of keeping a second geometry path in
step with the renderer, the model is loaded into a throwaway offscreen canvas
through the same load path the canvas uses, and that scene is recorded into a
picture the preview item replays under the cursor.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QEvent, QRectF
from PyQt6.QtGui import QPainter, QPicture

from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_service_ports import insert_controller_for_access
from chemvas.ui.renderer_style_access import renderer_for, renderer_style_for
from chemvas.ui.scene_item_access import canvas_scene_for

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel

# Slack around the structure, in bond lengths, so that label glyphs, charge
# marks and hydrogen counts that paint past their atoms are recorded rather
# than clipped by the render rectangle.
PREVIEW_MARGIN_BOND_LENGTHS = 3.0


def render_smiles_preview_picture(
    canvas, model: MoleculeModel, smiles: str
) -> QPicture:
    """Record ``model`` as the live canvas's renderer would paint it.

    The picture is in model coordinates: the ghost canvas places atoms at
    their model positions, so translating the picture by the preview offset
    lands it exactly where the commit will place the structure. Its bounding
    rectangle is the rectangle that was rendered, so everything painted is
    inside it.
    """
    # The ghost canvas type lives above this module; resolve it at call time,
    # as the offscreen CLI does, so the canvas package does not import itself.
    from chemvas.ui.canvas_view import CanvasView

    # A shallow copy shares the immutable style and nothing else, so the ghost
    # draws with the live canvas's bond length, widths and fonts.
    ghost = CanvasView(renderer=copy.copy(renderer_for(canvas)))
    try:
        # The ghost takes its own copy: loading mutates the model it is given
        # and the preview model must stay untouched for the commit plan.
        insert_controller_for_access(ghost).smiles_service.load_model(
            copy.deepcopy(model), smiles
        )
        scene = canvas_scene_for(ghost)
        margin = renderer_style_for(canvas).bond_length_px * PREVIEW_MARGIN_BOND_LENGTHS
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
        schedule_canvas_deletion_for(ghost)
        QCoreApplication.sendPostedEvents(ghost, QEvent.Type.DeferredDelete)


__all__ = ["render_smiles_preview_picture"]
