import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainterPath, QPen
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    Qt = None
    QColor = None
    QPainterPath = None
    QPen = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.canvas_arrow_build_service import CanvasArrowBuildService


class _RecordingScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas arrow build service tests")
class CanvasArrowBuildServiceTest(unittest.TestCase):
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
            arrow_line_width=2.5,
            arrow_head_scale=0.3,
            scene=lambda: scene,
        )
        return CanvasArrowBuildService(canvas), scene

    def test_build_arrow_item_dispatches_supported_kinds(self) -> None:
        service, _ = self._make_service()
        start = QPointF(1.0, 2.0)
        end = QPointF(8.0, 9.0)
        equilibrium = object()
        resonance = object()
        curved_single = object()
        curved_double = object()
        inhibit = object()
        dotted = object()
        default = object()

        service.build_equilibrium_item = mock.Mock(return_value=equilibrium)
        service.build_double_head_arrow = mock.Mock(return_value=resonance)
        service.build_curved_arrow = mock.Mock(side_effect=[curved_single, curved_double])
        service.build_inhibition_arrow = mock.Mock(return_value=inhibit)
        service.build_dotted_arrow = mock.Mock(return_value=dotted)
        service.build_single_head_arrow = mock.Mock(return_value=default)

        self.assertIs(service.build_arrow_item(start, end, "equilibrium"), equilibrium)
        self.assertIs(service.build_arrow_item(start, end, "resonance"), resonance)
        self.assertIs(service.build_arrow_item(start, end, "curved_single"), curved_single)
        self.assertIs(service.build_arrow_item(start, end, "curved_double"), curved_double)
        self.assertIs(service.build_arrow_item(start, end, "inhibit"), inhibit)
        self.assertIs(service.build_arrow_item(start, end, "dotted"), dotted)
        self.assertIs(service.build_arrow_item(start, end, "reaction"), default)

        service.build_equilibrium_item.assert_called_once_with(start, end)
        service.build_double_head_arrow.assert_called_once_with(start, end)
        self.assertEqual(
            service.build_curved_arrow.call_args_list,
            [mock.call(start, end, double=False), mock.call(start, end, double=True)],
        )
        service.build_inhibition_arrow.assert_called_once_with(start, end)
        service.build_dotted_arrow.assert_called_once_with(start, end)
        service.build_single_head_arrow.assert_called_once_with(start, end)

    def test_build_curved_arrow_sets_metadata_control_and_double_flag(self) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(10.0, 0.0)

        with mock.patch.object(service, "add_arrow_head", wraps=service.add_arrow_head) as add_arrow_head:
            item = service.build_curved_arrow(start, end, double=True)

        data = item.data(2) or {}
        control = data.get("control")
        self.assertFalse(item.path().isEmpty())
        self.assertEqual(data.get("start"), start)
        self.assertEqual(data.get("end"), end)
        self.assertTrue(data.get("double"))
        self.assertIsInstance(control, QPointF)
        self.assertAlmostEqual(control.x(), 5.0)
        self.assertAlmostEqual(control.y(), 3.0)
        self.assertEqual(add_arrow_head.call_count, 2)

    def test_preview_arrow_adds_built_item_to_scene(self) -> None:
        service, scene = self._make_service()
        start = QPointF(-5.0, 1.0)
        end = QPointF(9.0, 7.0)

        item = service.preview_arrow(start, end, "curved_single")

        self.assertIs(scene.items[-1], item)
        self.assertFalse(item.path().isEmpty())
        self.assertEqual(item.data(2)["start"], start)
        self.assertEqual(item.data(2)["end"], end)
        self.assertFalse(item.data(2)["double"])
        self.assertIsNotNone(item.data(2)["control"])

    def test_build_double_head_and_dotted_arrow_preserve_metadata_and_pen_style(self) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(12.0, 0.0)

        with mock.patch.object(service, "add_arrow_head", wraps=service.add_arrow_head) as add_arrow_head:
            double_head = service.build_double_head_arrow(start, end)
            dotted = service.build_dotted_arrow(start, end)

        self.assertEqual(add_arrow_head.call_args_list[:3], [
            mock.call(mock.ANY, start, end, double=False),
            mock.call(mock.ANY, end, start, double=False),
            mock.call(mock.ANY, start, end, double=False),
        ])
        self.assertEqual(double_head.data(2), {"start": start, "end": end, "control": None, "double": False})
        self.assertEqual(dotted.data(2), {"start": start, "end": end, "control": None, "double": False})
        self.assertEqual(dotted.pen().style(), Qt.PenStyle.DashLine)
        self.assertNotEqual(double_head.pen().style(), dotted.pen().style())
        self.assertFalse(double_head.path().isEmpty())
        self.assertFalse(dotted.path().isEmpty())

    def test_build_inhibition_and_equilibrium_items_cover_specialized_paths(self) -> None:
        service, _ = self._make_service()
        start = QPointF(0.0, 0.0)
        end = QPointF(10.0, 0.0)

        inhibition = service.build_inhibition_arrow(start, end)
        equilibrium = service.build_equilibrium_item(start, end)

        inhibition_path = inhibition.path()
        self.assertEqual(inhibition.data(2), {"start": start, "end": end, "control": None, "double": False})
        self.assertEqual(inhibition_path.elementCount(), 4)
        self.assertAlmostEqual(inhibition_path.elementAt(2).x, 10.0)
        self.assertAlmostEqual(abs(inhibition_path.elementAt(2).y), 4.0)
        self.assertAlmostEqual(inhibition_path.boundingRect().width(), 10.0, delta=1.0)

        self.assertEqual(equilibrium.data(2), {"start": start, "end": end, "control": None, "double": False})
        self.assertFalse(equilibrium.path().isEmpty())
        self.assertGreater(equilibrium.path().boundingRect().height(), 8.0)
        self.assertGreater(equilibrium.path().boundingRect().width(), 9.0)

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


if __name__ == "__main__":
    unittest.main()
