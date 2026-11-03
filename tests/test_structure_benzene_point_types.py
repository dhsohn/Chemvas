"""Benzene placement reads any x()/y() point, as both editors pass their own."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import dataclass

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from tests.canvas_factory import build_canvas_view


@dataclass(frozen=True)
class _Point:
    """A point that is not a QPointF, like the browser editor's."""

    px: float
    py: float

    def x(self) -> float:
        return self.px

    def y(self) -> float:
        return self.py


def test_default_ring_occupancy_check_accepts_a_non_qt_point():
    app = QApplication.instance() or QApplication([])
    canvas = build_canvas_view()
    try:
        build = canvas.services.structure_build_service
        build.add_benzene_ring(QPointF(100, 100))
        assert len(canvas.model.atoms) == 6
        builder = build.benzene_builder
        assert builder.center_inside_existing_ring is None

        def no_attachment(*_args):
            return None

        # The default check tests Qt ring polygons; a centre inside the drawn
        # ring is refused instead of failing on the point's type.
        placed = builder.benzene_ring_points(
            _Point(100, 100),
            regular_ring_points_for_bond=no_attachment,
            regular_ring_points_for_atom=no_attachment,
        )
        assert placed is None
        free = builder.benzene_ring_points(
            _Point(400, 400),
            regular_ring_points_for_bond=no_attachment,
            regular_ring_points_for_atom=no_attachment,
        )
        assert free is not None and len(free[0]) == 6
    finally:
        canvas.close()
        app.processEvents()
