"""Helpers for tests that build TS bracket items by hand on a partial canvas."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest import mock

from PyQt6.QtGui import QPainterPath

from chemvas.domain.document import TSBracket
from chemvas.ui.ts_bracket_record_access import set_ts_bracket_record_for


@contextmanager
def plain_ts_bracket_paint():
    """A partial canvas has no build service or renderer style to draw with."""
    with ExitStack() as stack:
        stack.enter_context(
            mock.patch(
                "chemvas.ui.ts_bracket_record_access.ts_bracket_path_for",
                new=lambda canvas, rect, bracket_kind: QPainterPath(),
            )
        )
        stack.enter_context(
            mock.patch(
                "chemvas.ui.ts_bracket_record_access.bond_color_for",
                new=lambda canvas: "#000000",
            )
        )
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
