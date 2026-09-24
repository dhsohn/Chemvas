import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_state import canvas_runtime_state
from tests.scene_render_context import attach_scene_render_context

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication

from chemvas.ui.annotations.arrows import ArrowRenderer
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState


class _RecordingScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


class ArrowRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_service(self):
        scene = _RecordingScene()
        style = SimpleNamespace(
            bond_length_px=20.0,
            bond_spacing_px=6.0,
        )
        renderer = SimpleNamespace(
            style=style,
            bond_pen=lambda: QPen(QColor("#222222")),
        )
        canvas = SimpleNamespace(
            renderer=renderer,
            runtime_state=canvas_runtime_state(
                tool_settings_state=CanvasToolSettingsState(
                    arrow_line_width=2.5,
                    arrow_head_scale=0.3,
                )
            ),
            scene=lambda: scene,
        )
        return ArrowRenderer(attach_scene_render_context(canvas)), scene

    def test_preview_arrow_adds_built_item_to_scene(self) -> None:
        service, scene = self._make_service()
        start = QPointF(-5.0, 1.0)
        end = QPointF(9.0, 7.0)

        item = service.preview_arrow(start, end, "curved_single")

        self.assertIs(scene.items[-1], item)
        self.assertFalse(item.path().isEmpty())

    def test_build_double_head_and_dotted_arrow_preserve_metadata_and_pen_style(
        self,
    ) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(12.0, 0.0)

        with mock.patch.object(
            service, "add_arrow_head", wraps=service.add_arrow_head
        ) as add_arrow_head:
            double_head = service.build_double_head_arrow(start, end)
            dotted = service.build_dotted_arrow(start, end)

        self.assertEqual(
            add_arrow_head.call_args_list[:3],
            [
                mock.call(mock.ANY, start, end, double=False),
                mock.call(mock.ANY, end, start, double=False),
                mock.call(mock.ANY, start, end, double=False),
            ],
        )
        self.assertEqual(dotted.pen().style(), Qt.PenStyle.DashLine)
        self.assertNotEqual(double_head.pen().style(), dotted.pen().style())
        self.assertFalse(double_head.path().isEmpty())
        self.assertFalse(dotted.path().isEmpty())

    def test_build_inhibition_and_equilibrium_items_cover_specialized_paths(
        self,
    ) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(10.0, 0.0)

        inhibition = service.build_inhibition_arrow(start, end)
        equilibrium = service.build_equilibrium_item(start, end)

        inhibition_path = inhibition.path()
        self.assertEqual(inhibition_path.elementCount(), 4)
        self.assertAlmostEqual(inhibition_path.elementAt(2).x, 10.0)
        self.assertAlmostEqual(abs(inhibition_path.elementAt(2).y), 4.0)
        self.assertAlmostEqual(inhibition_path.boundingRect().width(), 10.0, delta=1.0)

        self.assertFalse(equilibrium.path().isEmpty())
        self.assertGreater(equilibrium.path().boundingRect().height(), 8.0)
        self.assertGreater(equilibrium.path().boundingRect().width(), 9.0)

    def test_equilibrium_shafts_use_one_bond_spacing(self) -> None:
        service, _ = self._make_service()
        start = QPointF(7.0, -11.0)
        for kind in ("equilibrium", "equilibrium_forward", "equilibrium_reverse"):
            for dx, dy in (
                (60.0, 0.0),
                (-60.0, 0.0),
                (0.0, 60.0),
                (0.0, -60.0),
                (36.0, 48.0),
            ):
                for spacing in (6.0, 10.0, 15.0):
                    with self.subTest(kind=kind, direction=(dx, dy), spacing=spacing):
                        service.context.renderer.style.bond_spacing_px = spacing
                        end = start + QPointF(dx, dy)
                        item = service.build_arrow_item(start, end, kind)
                        path = item.path()
                        length = math.hypot(dx, dy)
                        forward = path.elementAt(1)
                        reverse = path.elementAt(5)
                        gap = (
                            (reverse.x - forward.x) * -dy + (reverse.y - forward.y) * dx
                        ) / length
                        self.assertAlmostEqual(gap, spacing)

    def test_thick_equilibrium_shafts_keep_one_stroke_of_clearance(self) -> None:
        service, _ = self._make_service()
        for kind in ("equilibrium", "equilibrium_forward", "equilibrium_reverse"):
            for width in (4.0, 7.0):
                with self.subTest(kind=kind, width=width):
                    service.settings.arrow_line_width = width
                    path = service.build_arrow_item(
                        QPointF(0, 0), QPointF(60, 0), kind
                    ).path()
                    gap = path.elementAt(5).y - path.elementAt(1).y
                    self.assertAlmostEqual(gap - width, width)

    def test_build_equilibrium_item_draws_outward_facing_harpoons(self) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(10.0, 0.0)

        path = service.build_equilibrium_item(start, end).path()

        # Two harpoons, each a shaft (move + line) and one barb (move + line).
        # A full arrow head would add a second barb segment to every line.
        self.assertEqual(path.elementCount(), 8)
        forward_barb, forward_tip = path.elementAt(2), path.elementAt(3)
        reverse_barb, reverse_tip = path.elementAt(6), path.elementAt(7)
        # The forward harpoon runs start -> end along the upper line and the
        # reverse one runs back along the lower line.
        self.assertAlmostEqual(forward_tip.x, 10.0)
        self.assertAlmostEqual(reverse_tip.x, 0.0)
        self.assertLess(forward_tip.y, reverse_tip.y)
        # Both barbs stay outside the pair instead of filling the gap.
        self.assertLess(forward_barb.y, forward_tip.y)
        self.assertGreater(reverse_barb.y, reverse_tip.y)

    def test_build_equilibrium_item_keeps_barbs_outward_when_drawn_diagonally(
        self,
    ) -> None:
        service, _ = self._make_service()
        start = QPointF(-3.0, 2.0)
        end = QPointF(4.0, -6.0)

        path = service.build_equilibrium_item(start, end).path()

        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)

        def offset_from_axis(element) -> float:
            """Signed distance from the drag axis, positive on the reverse side."""
            return (
                (element.x - start.x()) * -dy + (element.y - start.y()) * dx
            ) / length

        forward_shaft = offset_from_axis(path.elementAt(1))
        reverse_shaft = offset_from_axis(path.elementAt(5))
        self.assertLess(forward_shaft, 0.0)
        self.assertGreater(reverse_shaft, 0.0)
        self.assertLess(offset_from_axis(path.elementAt(2)), forward_shaft)
        self.assertGreater(offset_from_axis(path.elementAt(6)), reverse_shaft)

    def test_add_arrow_head_supports_double_offset_heads(self) -> None:
        service, _ = self._make_service()
        path = QPainterPath()

        service.add_arrow_head(path, QPointF(0.0, 0.0), QPointF(10.0, 0.0), double=True)

        self.assertEqual(path.elementCount(), 6)
        tip_a = path.elementAt(1)
        tip_b = path.elementAt(4)
        self.assertAlmostEqual(tip_a.x, 10.0)
        self.assertAlmostEqual(tip_b.x, 10.0)
        self.assertLess(tip_a.y, 0.0)
        self.assertGreater(tip_b.y, 0.0)

    def test_arrow_pen_applies_line_width_and_optional_dash(self) -> None:
        service, _ = self._make_service()

        solid = service.arrow_pen()
        dotted = service.arrow_pen(dotted=True)

        self.assertAlmostEqual(solid.widthF(), 2.5)
        self.assertNotEqual(solid.style(), dotted.style())
