"""Helpers for tests that build shape items by hand on a partial canvas."""

from __future__ import annotations

from unittest import mock

from PyQt6.QtGui import QPen

from chemvas.domain.document import Shape
from chemvas.ui.annotations.records import set_shape_record_for
from tests.scene_render_context import attach_scene_render_context


def _plain_context_for(canvas):
    context = attach_scene_render_context(canvas)
    context.decorations.shape_pen = lambda stroke_style: QPen()
    return context


# A partial canvas has no decoration build service to ask for the stroke pen.
plain_shape_pen = mock.patch(
    "chemvas.ui.annotations.records.scene_render_context_for",
    new=_plain_context_for,
)


def adopt_shape(
    canvas,
    item,
    *,
    rect=(0.0, 0.0, 10.0, 10.0),
    shape_kind="rect",
    stroke_style="solid",
) -> Shape:
    """Give a hand-built shape item the record every shape in a document has."""
    left, top, width, height = rect
    if not hasattr(canvas, "render_context"):
        attach_scene_render_context(canvas)
    return set_shape_record_for(
        canvas,
        item,
        Shape(
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            shape_kind=shape_kind,
            stroke_style=stroke_style,
        ),
    )


__all__ = ["adopt_shape", "plain_shape_pen"]
