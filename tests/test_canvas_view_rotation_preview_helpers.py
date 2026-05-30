import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
    from ui.canvas_view import CanvasView


class _FakeRotationGroup:
    def __init__(self, angle: float = 0.0) -> None:
        self.origin = None
        self.rotations = []
        self._angle = angle

    def setTransformOriginPoint(self, point: QPointF) -> None:
        self.origin = point

    def setRotation(self, angle: float) -> None:
        self.rotations.append(angle)
        self._angle = angle

    def rotation(self) -> float:
        return self._angle


class _FakeScene:
    def __init__(self, selected_items=None, group=None) -> None:
        self._selected_items = list(selected_items or [])
        self._group = group or _FakeRotationGroup()
        self.created_with = None
        self.destroyed_group = None

    def selectedItems(self):
        return list(self._selected_items)

    def createItemGroup(self, items):
        self.created_with = list(items)
        return self._group

    def destroyItemGroup(self, group) -> None:
        self.destroyed_group = group


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewRotationPreviewHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_begin_selection_rotation_rejects_existing_group_empty_selection_and_missing_center(self) -> None:
        blocked_view = SimpleNamespace(_rotation_group=object())
        blocked_view._rotation_preview_controller = CanvasRotationPreviewController(blocked_view)
        self.assertFalse(CanvasView.begin_selection_rotation(blocked_view))

        empty_scene = _FakeScene([])
        empty_view = SimpleNamespace(_rotation_group=None, scene=lambda: empty_scene)
        empty_view._rotation_preview_controller = CanvasRotationPreviewController(empty_view)
        self.assertFalse(CanvasView.begin_selection_rotation(empty_view))

        centerless_scene = _FakeScene([object()])
        centerless_view = SimpleNamespace(
            _rotation_group=None,
            scene=lambda: centerless_scene,
            _selected_ids=mock.Mock(return_value=({1}, set())),
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        centerless_view._rotation_preview_controller = CanvasRotationPreviewController(centerless_view)
        self.assertFalse(CanvasView.begin_selection_rotation(centerless_view))

    def test_begin_selection_rotation_builds_group_and_includes_atoms_from_selected_bonds(self) -> None:
        selected_items = [object(), object()]
        scene = _FakeScene(selected_items)
        view = SimpleNamespace(
            _rotation_group=None,
            scene=lambda: scene,
            _selected_ids=mock.Mock(return_value=({1}, {0, 1, 99})),
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 1.0, 1.0),
                    2: Atom("C", 4.0, 7.0),
                    3: Atom("C", 10.0, 10.0),
                },
                bonds=[
                    Bond(2, 3, 1),
                    None,
                ]
            ),
        )
        view._rotation_preview_controller = CanvasRotationPreviewController(view)

        self.assertTrue(CanvasView.begin_selection_rotation(view))

        self.assertEqual(scene.created_with, selected_items)
        self.assertEqual(scene._group.origin, QPointF(5.0, 6.0))
        self.assertIs(view._rotation_group, scene._group)

    def test_update_rotation_preview_is_noop_without_group_and_updates_group_angle(self) -> None:
        idle_view = SimpleNamespace(_rotation_group=None)
        idle_view._rotation_preview_controller = CanvasRotationPreviewController(idle_view)
        CanvasView.update_rotation_preview(idle_view, 45.0)

        group = _FakeRotationGroup()
        active_view = SimpleNamespace(_rotation_group=group)
        active_view._rotation_preview_controller = CanvasRotationPreviewController(active_view)
        CanvasView.update_rotation_preview(active_view, 37.5)
        self.assertEqual(group.rotations, [37.5])

    def test_commit_selection_rotation_destroys_group_and_only_rotates_for_non_zero_angle(self) -> None:
        idle_view = SimpleNamespace(_rotation_group=None)
        idle_view._rotation_preview_controller = CanvasRotationPreviewController(idle_view)
        CanvasView.commit_selection_rotation(idle_view)

        zero_group = _FakeRotationGroup(angle=0.0)
        zero_scene = _FakeScene(group=zero_group)
        zero_view = SimpleNamespace(
            _rotation_group=zero_group,
            scene=lambda: zero_scene,
            rotate_selection=mock.Mock(),
        )
        zero_view._rotation_preview_controller = CanvasRotationPreviewController(zero_view)
        CanvasView.commit_selection_rotation(zero_view)
        self.assertEqual(zero_group.rotations, [0.0])
        self.assertIsNone(zero_view._rotation_group)
        self.assertIs(zero_scene.destroyed_group, zero_group)
        zero_view.rotate_selection.assert_not_called()

        angle_group = _FakeRotationGroup(angle=22.0)
        angle_scene = _FakeScene(group=angle_group)
        angle_view = SimpleNamespace(
            _rotation_group=angle_group,
            scene=lambda: angle_scene,
            rotate_selection=mock.Mock(),
        )
        angle_view._rotation_preview_controller = CanvasRotationPreviewController(angle_view)
        CanvasView.commit_selection_rotation(angle_view)
        self.assertEqual(angle_group.rotations, [0.0])
        self.assertIsNone(angle_view._rotation_group)
        self.assertIs(angle_scene.destroyed_group, angle_group)
        angle_view.rotate_selection.assert_called_once_with(22.0)

    def test_rotation_preview_wrappers_delegate_to_controller(self) -> None:
        view = SimpleNamespace()
        controller = mock.Mock()
        controller.begin_selection_rotation.return_value = True

        with mock.patch("ui.canvas_view._rotation_preview_controller_for", return_value=controller):
            self.assertTrue(CanvasView.begin_selection_rotation(view))
            CanvasView.update_rotation_preview(view, 18.0)
            CanvasView.commit_selection_rotation(view)

        controller.begin_selection_rotation.assert_called_once_with()
        controller.update_rotation_preview.assert_called_once_with(18.0)
        controller.commit_selection_rotation.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
