import math
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtWidgets import QApplication, QGraphicsPathItem
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.domain.document import Atom
    from chemvas.ui.canvas_mark_scene_service import CanvasMarkSceneService
    from chemvas.ui.canvas_scene_decoration_build_service import (
        CanvasSceneDecorationBuildService,
    )
    from chemvas.ui.canvas_tool_settings_state import CanvasToolSettingsState
    from chemvas.ui.graphics_items import AtomDotItem, AtomLabelItem
    from chemvas.ui.mark_item_access import (
        build_mark_item_for,
        mark_center_for,
        mark_center_for_pointer_for,
        mark_offset_from_click_for,
        mark_selection_radius_for,
        remove_mark_item_for,
        remove_marks_for_atom_for,
        set_mark_center_for,
    )
    from chemvas.ui.scene_decoration_access import add_mark_for, add_mark_for_atom_for


class _FakeScene:
    def __init__(self) -> None:
        self.items = []

    def addItem(self, item) -> None:
        self.items.append(item)


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view tests"
)
class CanvasViewMarkHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _renderer(
        self, bond_line_width: float = 2.0, bond_length_px: float = 50.0
    ) -> SimpleNamespace:
        font = QFont("DejaVu Sans", 11)
        return SimpleNamespace(
            style=SimpleNamespace(
                bond_line_width=bond_line_width,
                bond_length_px=bond_length_px,
                atom_color=QColor(16, 32, 48),
            ),
            atom_font=lambda: font,
        )

    def test_build_mark_item_returns_kind_specific_items_and_hit_metadata(self) -> None:
        view = SimpleNamespace(
            renderer=self._renderer(),
        )
        view.services = canvas_runtime_services(
            scene_decoration_build_service=CanvasSceneDecorationBuildService(view)
        )
        selection_radius = mark_selection_radius_for(view)

        radical = build_mark_item_for(view, "radical")
        self.assertIsInstance(radical, AtomDotItem)
        self.assertAlmostEqual(radical.rect().left(), -1.4)
        self.assertAlmostEqual(radical.rect().width(), 2.8)
        self.assertEqual(radical.brush().color(), QColor(16, 32, 48))
        self.assertEqual(radical.pen().style(), Qt.PenStyle.NoPen)

        plus = build_mark_item_for(view, "plus")
        self.assertIsInstance(plus, AtomLabelItem)
        self.assertEqual(plus.toPlainText(), "+")
        self.assertEqual(plus.defaultTextColor(), QColor(16, 32, 48))
        self.assertEqual(plus.font().family(), view.renderer.atom_font().family())
        self.assertEqual(plus._hit_radius, selection_radius)

        minus = build_mark_item_for(view, "minus")
        self.assertIsInstance(minus, AtomLabelItem)
        self.assertEqual(minus.toPlainText(), "-")
        self.assertEqual(minus._hit_radius, selection_radius)

        circled_plus = build_mark_item_for(view, "circled_plus")
        circled_minus = build_mark_item_for(view, "circled_minus")
        self.assertIsInstance(circled_plus, QGraphicsPathItem)
        self.assertIsInstance(circled_minus, QGraphicsPathItem)
        self.assertEqual(circled_plus.pen().color(), QColor(16, 32, 48))
        self.assertEqual(circled_minus.pen().color(), QColor(16, 32, 48))
        self.assertGreater(
            circled_plus.boundingRect().width(),
            circled_plus.path().boundingRect().width(),
        )

        self.assertIsNone(build_mark_item_for(view, "unsupported"))

    def test_mark_offset_from_click_handles_zero_length_and_label_aware_target(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            renderer=self._renderer(bond_length_px=50.0),
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        mark_target_distance = mock.Mock(return_value=20.0)
        view.services = canvas_runtime_services(
            geometry_controller=SimpleNamespace(
                mark_target_distance_for_atom=mark_target_distance
            )
        )
        view.services.scene_decoration.canvas_mark_scene_service = (
            CanvasMarkSceneService(view)
        )

        offset = mark_offset_from_click_for(view, 7, QPointF(10.0, 20.0), kind="minus")

        expected = 12.5 / math.sqrt(2.0)
        self.assertAlmostEqual(offset.x(), expected)
        self.assertAlmostEqual(offset.y(), -expected)

        call = mark_target_distance.call_args
        self.assertEqual(call.args[0], 7)
        self.assertAlmostEqual(call.args[1], 1.0 / math.sqrt(2.0))
        self.assertAlmostEqual(call.args[2], -1.0 / math.sqrt(2.0))
        self.assertEqual(call.args[3], "minus")

    def test_mark_offset_from_click_uses_view_mark_kind_when_kind_is_missing(
        self,
    ) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={7: Atom("C", 10.0, 20.0)}),
            renderer=self._renderer(bond_length_px=50.0),
            tool_settings_state=CanvasToolSettingsState(mark_kind="radical"),
        )
        mark_target_distance = mock.Mock(return_value=0.0)
        view.services = canvas_runtime_services(
            geometry_controller=SimpleNamespace(
                mark_target_distance_for_atom=mark_target_distance
            )
        )
        view.services.scene_decoration.canvas_mark_scene_service = (
            CanvasMarkSceneService(view)
        )

        offset = mark_offset_from_click_for(view, 7, QPointF(13.0, 24.0))

        self.assertAlmostEqual(offset.x(), 6.0)
        self.assertAlmostEqual(offset.y(), 8.0)
        mark_target_distance.assert_called_once_with(7, 0.6, 0.8, "radical")

    def test_add_mark_delegates_to_scene_decoration_service(self) -> None:
        service = mock.Mock(return_value="mark-item")
        view = SimpleNamespace(
            services=canvas_runtime_services(
                scene_decoration_service=SimpleNamespace(add_mark=service)
            )
        )

        item = add_mark_for(
            view,
            QPointF(4.0, 5.0),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=False,
        )

        self.assertEqual(item, "mark-item")
        service.assert_called_once_with(
            QPointF(4.0, 5.0),
            kind="minus",
            atom_id=7,
            offset=QPointF(1.5, -2.5),
            record=False,
        )

    def test_mark_build_wrappers_delegate_to_scene_decoration_build_service(
        self,
    ) -> None:
        build_service = mock.Mock()
        mark_item = object()
        center = QPointF(6.0, 7.0)
        view = SimpleNamespace(
            services=canvas_runtime_services(
                scene_decoration_build_service=build_service
            )
        )

        build_service.build_mark_item.return_value = mark_item
        build_service.mark_center.return_value = center

        self.assertIs(build_mark_item_for(view, "plus"), mark_item)
        self.assertEqual(mark_center_for(view, mark_item), center)
        set_mark_center_for(view, mark_item, QPointF(8.0, 9.0))

        build_service.build_mark_item.assert_called_once_with("plus")
        build_service.mark_center.assert_called_once_with(mark_item)
        build_service.set_mark_center.assert_called_once_with(
            mark_item, QPointF(8.0, 9.0)
        )

    def test_mark_scene_wrappers_delegate_to_mark_scene_service(self) -> None:
        scene_service = mock.Mock()
        mark_item = object()
        center = QPointF(4.0, 5.0)
        offset = QPointF(1.5, -2.5)
        view = SimpleNamespace(
            services=canvas_runtime_services(canvas_mark_scene_service=scene_service)
        )

        scene_service.add_mark_for_atom.return_value = mark_item
        scene_service.mark_offset_from_click.return_value = offset
        scene_service.mark_center_for_pointer.return_value = center

        self.assertIs(
            add_mark_for_atom_for(
                view, 7, QPointF(12.0, 13.0), kind="minus", record=False
            ),
            mark_item,
        )
        self.assertEqual(
            mark_offset_from_click_for(view, 7, QPointF(12.0, 13.0), kind="minus"),
            offset,
        )
        remove_mark_item_for(view, mark_item)
        remove_marks_for_atom_for(view, 7)
        self.assertEqual(
            mark_center_for_pointer_for(view, QPointF(12.0, 13.0), 7, kind="minus"),
            center,
        )

        scene_service.add_mark_for_atom.assert_called_once_with(
            7, QPointF(12.0, 13.0), kind="minus", record=False
        )
        scene_service.mark_offset_from_click.assert_called_once_with(
            7, QPointF(12.0, 13.0), kind="minus"
        )
        scene_service.remove_mark_item.assert_called_once_with(mark_item)
        scene_service.remove_marks_for_atom.assert_called_once_with(7)
        scene_service.mark_center_for_pointer.assert_called_once_with(
            QPointF(12.0, 13.0), 7, kind="minus"
        )
