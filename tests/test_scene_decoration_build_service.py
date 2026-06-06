import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QPen
    from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_scene_decoration_build_service import (
        CanvasSceneDecorationBuildService,
    )
    from ui.canvas_tool_settings_state import CanvasToolSettingsState


class _RecordingScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene decoration build service tests")
class CanvasSceneDecorationBuildServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _make_service(self, *, orbital_phase_enabled: bool = True, arrow_build_service=None):
        scene = _RecordingScene()
        style = SimpleNamespace(
            bond_length_px=20.0,
            bond_spacing_px=6.0,
            bond_line_width=2.0,
            font_family="Helvetica",
            bond_color="#123456",
            orbital_positive_color="#ff3300",
            orbital_negative_color="#0033ff",
            orbital_alpha=0.4,
        )
        renderer = SimpleNamespace(
            style=style,
            bond_pen=lambda: QPen(QColor("#222222")),
        )
        canvas = SimpleNamespace(
            renderer=renderer,
            tool_settings_state=CanvasToolSettingsState(
                arrow_line_width=2.5,
                arrow_head_scale=0.3,
                orbital_phase_enabled=orbital_phase_enabled,
            ),
            scene=lambda: scene,
        )
        return CanvasSceneDecorationBuildService(canvas, arrow_build_service=arrow_build_service), scene, style

    def test_build_arrow_item_delegates_to_arrow_build_service(self) -> None:
        arrow_service = mock.Mock()
        service, _, _ = self._make_service(arrow_build_service=arrow_service)
        arrow_service.build_arrow_item.return_value = "arrow"

        self.assertEqual(service.build_arrow_item(QPointF(1.0, 2.0), QPointF(8.0, 9.0), "equilibrium"), "arrow")
        arrow_service.build_arrow_item.assert_called_once_with(
            QPointF(1.0, 2.0),
            QPointF(8.0, 9.0),
            "equilibrium",
        )

    def test_curved_arrow_helpers_delegate_to_arrow_build_service(self) -> None:
        arrow_service = mock.Mock()
        service, _, _ = self._make_service(arrow_build_service=arrow_service)
        arrow_service.build_curved_arrow.return_value = "curved"

        result = service.build_curved_arrow(QPointF(0.0, 0.0), QPointF(10.0, 0.0), double=True)

        self.assertEqual(result, "curved")
        arrow_service.build_curved_arrow.assert_called_once_with(QPointF(0.0, 0.0), QPointF(10.0, 0.0), True)

    def test_ts_bracket_rect_from_points_applies_minimum_size_and_normalization(self) -> None:
        service, _, _ = self._make_service()

        tiny_rect = service.ts_bracket_rect_from_points(QPointF(10.0, 20.0), QPointF(11.0, 21.0))
        self.assertAlmostEqual(tiny_rect.left(), -8.0)
        self.assertAlmostEqual(tiny_rect.top(), -4.0)
        self.assertAlmostEqual(tiny_rect.width(), 36.0)
        self.assertAlmostEqual(tiny_rect.height(), 48.0)

        normalized_rect = service.ts_bracket_rect_from_points(QPointF(30.0, 50.0), QPointF(10.0, 10.0))
        self.assertAlmostEqual(normalized_rect.center().x(), 20.0)
        self.assertAlmostEqual(normalized_rect.center().y(), 30.0)
        self.assertAlmostEqual(normalized_rect.width(), 36.0)
        self.assertAlmostEqual(normalized_rect.height(), 48.0)

    def test_build_ts_bracket_item_sets_metadata_brush_and_no_pen(self) -> None:
        service, _, _ = self._make_service()
        rect = QRectF(QPointF(24.0, 18.0), QPointF(6.0, -2.0))

        item = service.build_ts_bracket_item(rect)

        self.assertFalse(item.path().isEmpty())
        self.assertEqual(item.data(0), "ts_bracket")
        self.assertEqual(item.data(1)["rect"], QRectF(rect).normalized())
        self.assertEqual(item.pen().style(), Qt.PenStyle.NoPen)
        self.assertEqual(item.brush().color().name(), "#123456")

    def test_build_orbital_items_are_phase_aware_for_mo_antibonding(self) -> None:
        phase_service, _, phase_style = self._make_service(orbital_phase_enabled=True)
        no_phase_service, _, _ = self._make_service(orbital_phase_enabled=False)
        center = QPointF(4.0, -3.0)

        phase_items = phase_service.build_orbital_items(center, "mo_antibonding")
        no_phase_items = no_phase_service.build_orbital_items(center, "mo_antibonding")

        self.assertEqual(len(phase_items), 3)
        self.assertEqual(len(no_phase_items), 3)
        self.assertTrue(all(isinstance(item, QGraphicsEllipseItem) for item in phase_items[:2]))
        self.assertEqual(phase_items[0].brush().color().name(), "#ff3300")
        self.assertEqual(phase_items[1].brush().color().name(), "#0033ff")
        self.assertAlmostEqual(phase_items[0].brush().color().alphaF(), phase_style.orbital_alpha, places=2)
        self.assertAlmostEqual(phase_items[1].brush().color().alphaF(), phase_style.orbital_alpha, places=2)
        self.assertEqual(no_phase_items[0].brush().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(no_phase_items[1].brush().style(), Qt.BrushStyle.NoBrush)

    def test_preview_arrow_adds_built_item_to_scene(self) -> None:
        service, scene, _ = self._make_service()
        start = QPointF(-5.0, 1.0)
        end = QPointF(9.0, 7.0)

        item = service.preview_arrow(start, end, "curved_single")

        self.assertIs(scene.items[-1], item)
        self.assertFalse(item.path().isEmpty())
        self.assertEqual(item.data(2)["start"], start)
        self.assertEqual(item.data(2)["end"], end)
        self.assertFalse(item.data(2)["double"])
        self.assertIsNotNone(item.data(2)["control"])

    def test_preview_ts_bracket_adds_preview_item_to_scene_with_preview_brush(self) -> None:
        service, scene, _ = self._make_service()

        item = service.preview_ts_bracket(QPointF(3.0, 4.0), QPointF(4.0, 5.0))

        self.assertIs(scene.items[-1], item)
        self.assertEqual(item.data(0), "ts_bracket")
        self.assertEqual(item.brush().color().alpha(), 140)
        rect = item.data(1)["rect"]
        self.assertAlmostEqual(rect.width(), 36.0)
        self.assertAlmostEqual(rect.height(), 48.0)


if __name__ == "__main__":
    unittest.main()
