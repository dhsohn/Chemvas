"""Helpers for tests that build TS bracket items by hand on a partial canvas."""

from __future__ import annotations

from contextlib import contextmanager
from unittest import mock

from PyQt6.QtGui import QPainterPath

from chemvas.domain.document import TSBracket
from chemvas.ui.annotations.records import set_ts_bracket_record_for
from tests.scene_render_context import attach_scene_render_context


@contextmanager
def plain_ts_bracket_paint():
    """A partial canvas has no build service or renderer style to draw with."""

    def context_for(canvas):
        context = attach_scene_render_context(canvas)
        context.decorations.ts_bracket_path = lambda rect, bracket_kind: QPainterPath()
        return context

    with mock.patch(
        "chemvas.ui.annotations.records.scene_render_context_for", new=context_for
    ):
        yield


def adopt_ts_bracket(
    canvas,
    item,
    *,
    rect=(0.0, 0.0, 10.0, 10.0),
    bracket_kind="square_pair",
) -> TSBracket:
    """Give a hand-built bracket item the record every bracket in a document has."""
    left, top, width, height = rect
    if not hasattr(canvas, "render_context"):
        attach_scene_render_context(canvas)
    return set_ts_bracket_record_for(
        canvas,
        item,
        TSBracket(
            left=left,
            top=top,
            right=left + width,
            bottom=top + height,
            bracket_kind=bracket_kind,
        ),
    )


__all__ = ["adopt_ts_bracket", "plain_ts_bracket_paint"]
