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
    from ui.canvas_rotation_preview_controller import CanvasRotationPreviewController
    from ui.canvas_rotation_preview_state import CanvasRotationPreviewState


def _controller_for(view, scene_transform=None):
    if scene_transform is None:
        scene_transform = SimpleNamespace(
            rotate_selected_items=mock.Mock(),
            rotation_selection_preview=mock.Mock(return_value=None),
        )
    return CanvasRotationPreviewController(view, scene_transform_controller=scene_transform)


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


class _FakeSelectedItem:
    def __init__(self, kind: str, item_id: int) -> None:
        self.kind = kind
        self.item_id = item_id

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None


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
        blocked_transform = SimpleNamespace(
            rotate_selected_items=mock.Mock(),
            rotation_selection_preview=mock.Mock(),
        )
        blocked_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState(group=object()))
        blocked_view.services = SimpleNamespace(
            rotation_preview_controller=_controller_for(blocked_view, blocked_transform)
        )
        self.assertFalse(blocked_view.services.rotation_preview_controller.begin_selection_rotation())
        blocked_transform.rotation_selection_preview.assert_not_called()

        empty_transform = SimpleNamespace(
            rotate_selected_items=mock.Mock(),
            rotation_selection_preview=mock.Mock(return_value=None),
        )
        empty_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState())
        empty_view.services = SimpleNamespace(
            rotation_preview_controller=_controller_for(empty_view, empty_transform)
        )
        self.assertFalse(empty_view.services.rotation_preview_controller.begin_selection_rotation())
        empty_transform.rotation_selection_preview.assert_called_once_with()

    def test_begin_selection_rotation_builds_group_from_transform_preview(self) -> None:
        selected_items = [
            _FakeSelectedItem("atom", 1),
            _FakeSelectedItem("arrow", None),
        ]
        scene = _FakeScene(selected_items)
        preview = SimpleNamespace(items=selected_items, center=QPointF(5.0, 6.0))
        transform = SimpleNamespace(
            rotate_selected_items=mock.Mock(),
            rotation_selection_preview=mock.Mock(return_value=preview),
        )
        view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(),
            scene=lambda: scene,
        )
        view.services = SimpleNamespace(rotation_preview_controller=_controller_for(view, transform))

        self.assertTrue(view.services.rotation_preview_controller.begin_selection_rotation())

        self.assertEqual(scene.created_with, selected_items)
        self.assertEqual(scene._group.origin, QPointF(5.0, 6.0))
        self.assertIs(view.rotation_preview_state.group, scene._group)

    def test_position_preview_snapshots_apply_during_drag_and_restore_before_commit(self) -> None:
        selected_items = [_FakeSelectedItem("atom", 1)]
        mark_item = _FakeSelectedItem("mark", {"atom_id": 1})
        scene = _FakeScene(selected_items)
        snapshot = object()
        preview = SimpleNamespace(
            items=selected_items,
            center=QPointF(5.0, 6.0),
            position_items=[mark_item],
        )
        transform = SimpleNamespace(
            rotate_selected_items=mock.Mock(),
            rotation_selection_preview=mock.Mock(return_value=preview),
            rotation_position_preview_snapshots=mock.Mock(return_value=[snapshot]),
            apply_rotation_position_preview=mock.Mock(),
            restore_rotation_position_preview=mock.Mock(),
        )
        view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(),
            scene=lambda: scene,
        )
        view.services = SimpleNamespace(rotation_preview_controller=_controller_for(view, transform))

        self.assertTrue(view.services.rotation_preview_controller.begin_selection_rotation())
        view.services.rotation_preview_controller.update_rotation_preview(33.0)
        view.services.rotation_preview_controller.commit_selection_rotation()

        transform.rotation_position_preview_snapshots.assert_called_once_with([mark_item])
        transform.apply_rotation_position_preview.assert_called_once_with(
            [snapshot],
            center=QPointF(5.0, 6.0),
            angle_degrees=33.0,
        )
        transform.restore_rotation_position_preview.assert_called_once_with([snapshot])
        transform.rotate_selected_items.assert_called_once_with(33.0)

    def test_update_rotation_preview_is_noop_without_group_and_updates_group_angle(self) -> None:
        idle_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState())
        idle_view.services = SimpleNamespace(rotation_preview_controller=_controller_for(idle_view))
        idle_view.services.rotation_preview_controller.update_rotation_preview(45.0)

        group = _FakeRotationGroup()
        active_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState(group=group))
        active_view.services = SimpleNamespace(rotation_preview_controller=_controller_for(active_view))
        active_view.services.rotation_preview_controller.update_rotation_preview(37.5)
        self.assertEqual(group.rotations, [37.5])

    def test_commit_selection_rotation_destroys_group_and_only_rotates_for_non_zero_angle(self) -> None:
        idle_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState())
        idle_view.services = SimpleNamespace(rotation_preview_controller=_controller_for(idle_view))
        idle_view.services.rotation_preview_controller.commit_selection_rotation()

        zero_group = _FakeRotationGroup(angle=0.0)
        zero_scene = _FakeScene(group=zero_group)
        zero_view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(group=zero_group),
            scene=lambda: zero_scene,
        )
        zero_transform = SimpleNamespace(rotate_selected_items=mock.Mock())
        zero_view.services = SimpleNamespace(rotation_preview_controller=_controller_for(zero_view, zero_transform))
        zero_view.services.rotation_preview_controller.commit_selection_rotation()
        self.assertEqual(zero_group.rotations, [0.0])
        self.assertIsNone(zero_view.rotation_preview_state.group)
        self.assertIs(zero_scene.destroyed_group, zero_group)
        zero_transform.rotate_selected_items.assert_not_called()

        angle_group = _FakeRotationGroup(angle=22.0)
        angle_scene = _FakeScene(group=angle_group)
        angle_view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(group=angle_group),
            scene=lambda: angle_scene,
        )
        angle_transform = SimpleNamespace(rotate_selected_items=mock.Mock())
        angle_view.services = SimpleNamespace(rotation_preview_controller=_controller_for(angle_view, angle_transform))
        angle_view.services.rotation_preview_controller.commit_selection_rotation()
        self.assertEqual(angle_group.rotations, [0.0])
        self.assertIsNone(angle_view.rotation_preview_state.group)
        self.assertIs(angle_scene.destroyed_group, angle_group)
        angle_transform.rotate_selected_items.assert_called_once_with(22.0)

if __name__ == "__main__":
    unittest.main()
