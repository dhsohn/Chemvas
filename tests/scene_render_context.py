"""Explicit rendering context wiring for focused editor and graphics doubles."""

from dataclasses import fields

from PyQt6.QtWidgets import QGraphicsScene

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import MoleculeModel
from chemvas.ui.atom_label_renderer import AtomLabelRenderer
from chemvas.ui.bond_renderer import BondRenderer
from chemvas.ui.canvas_arrow_build_service import CanvasArrowBuildService
from chemvas.ui.canvas_scene_decoration_build_service import (
    CanvasSceneDecorationBuildService,
)
from chemvas.ui.scene_geometry import SceneGeometry
from chemvas.ui.scene_render_context import SceneRenderContext, SceneRenderState


def attach_scene_render_context(canvas) -> SceneRenderContext:
    defaults = SceneRenderState()
    if not hasattr(canvas, "runtime_state"):
        canvas.runtime_state = defaults
    for field in fields(defaults):
        if not hasattr(canvas.runtime_state, field.name):
            setattr(canvas.runtime_state, field.name, getattr(defaults, field.name))
    if not hasattr(canvas, "model"):
        canvas.model = MoleculeModel()
    if not hasattr(canvas, "renderer"):
        canvas.renderer = Renderer()
    scene_getter = getattr(canvas, "scene", None)
    scene = scene_getter() if callable(scene_getter) else QGraphicsScene()
    context = SceneRenderContext(
        scene_provider=scene_getter if callable(scene_getter) else lambda: scene,
        model_provider=lambda: canvas.model,
        renderer=canvas.renderer,
        state=canvas.runtime_state,
    )
    context.geometry = SceneGeometry(context)
    context.atom_labels = AtomLabelRenderer(context)
    context.bonds = BondRenderer(context)
    context.decorations = CanvasSceneDecorationBuildService(context)
    context.arrows = CanvasArrowBuildService(context)
    canvas.render_context = context
    return context


def scene_geometry_for_test_canvas(canvas) -> SceneGeometry:
    return attach_scene_render_context(canvas).geometry


__all__ = ["attach_scene_render_context", "scene_geometry_for_test_canvas"]
