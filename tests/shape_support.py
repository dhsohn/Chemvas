"""Helpers for tests that build shape items by hand on a partial canvas."""

from __future__ import annotations

from unittest import mock

from PyQt6.QtGui import QPen

from chemvas.ui.shape_record_access import adopt_shape_item_for

# A partial canvas has no decoration build service to ask for the stroke pen.
plain_shape_pen = mock.patch(
    "chemvas.ui.shape_record_access.shape_pen_for",
    new=lambda canvas, stroke_style: QPen(),
)


def adopt_shape(canvas, item) -> None:
    """Give a hand-built shape item the record an attached shape always has."""
    adopt_shape_item_for(canvas, item)


__all__ = ["adopt_shape", "plain_shape_pen"]
