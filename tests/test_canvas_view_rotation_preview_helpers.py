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
    from ui.canvas_rotation_preview_state import CanvasRotationPreviewState


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
        blocked_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState(group=object()))
        blocked_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(blocked_view))
        self.assertFalse(blocked_view.services.rotation_preview_controller.begin_selection_rotation())

        empty_scene = _FakeScene([])
        empty_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState(), scene=lambda: empty_scene)
        empty_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(empty_view))
        self.assertFalse(empty_view.services.rotation_preview_controller.begin_selection_rotation())

        centerless_scene = _FakeScene([_FakeSelectedItem("atom", 1)])
        centerless_view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(),
            scene=lambda: centerless_scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
        )
        centerless_view.services = SimpleNamespace(
            rotation_preview_controller=CanvasRotationPreviewController(centerless_view)
        )
        self.assertFalse(centerless_view.services.rotation_preview_controller.begin_selection_rotation())

    def test_begin_selection_rotation_builds_group_and_includes_atoms_from_selected_bonds(self) -> None:
        selected_items = [
            _FakeSelectedItem("atom", 1),
            _FakeSelectedItem("bond", 0),
            _FakeSelectedItem("bond", 1),
            _FakeSelectedItem("bond", 99),
        ]
        scene = _FakeScene(selected_items)
        view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(),
            scene=lambda: scene,
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
        view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(view))

        self.assertTrue(view.services.rotation_preview_controller.begin_selection_rotation())

        self.assertEqual(scene.created_with, selected_items)
        self.assertEqual(scene._group.origin, QPointF(5.0, 6.0))
        self.assertIs(view.rotation_preview_state.group, scene._group)

    def test_begin_selection_rotation_excludes_items_the_commit_does_not_rotate(self) -> None:
        atom_item = _FakeSelectedItem("atom", 1)
        note_item = _FakeSelectedItem("note", None)
        arrow_item = _FakeSelectedItem("arrow", None)
        bound_mark = _FakeSelectedItem("mark", {"kind": "plus", "atom_id": 1})
        foreign_mark = _FakeSelectedItem("mark", {"kind": "plus", "atom_id": 99})
        standalone_mark = _FakeSelectedItem("mark", {"kind": "plus", "atom_id": None})
        scene = _FakeScene([atom_item, note_item, arrow_item, bound_mark, foreign_mark, standalone_mark])
        view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(),
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 1.0)}, bonds=[]),
        )
        view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(view))

        self.assertTrue(view.services.rotation_preview_controller.begin_selection_rotation())

        # The commit (rotate_selection_for) rotates atoms/bonds/ring fills and
        # repositions marks bound to the rotated atoms; previewing anything
        # else (a grouped note, an arrow, a mark on an unrotated atom) would
        # show motion that snaps back.
        self.assertEqual(scene.created_with, [atom_item, bound_mark])

    def test_update_rotation_preview_is_noop_without_group_and_updates_group_angle(self) -> None:
        idle_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState())
        idle_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(idle_view))
        idle_view.services.rotation_preview_controller.update_rotation_preview(45.0)

        group = _FakeRotationGroup()
        active_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState(group=group))
        active_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(active_view))
        active_view.services.rotation_preview_controller.update_rotation_preview(37.5)
        self.assertEqual(group.rotations, [37.5])

    def test_commit_selection_rotation_destroys_group_and_only_rotates_for_non_zero_angle(self) -> None:
        idle_view = SimpleNamespace(rotation_preview_state=CanvasRotationPreviewState())
        idle_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(idle_view))
        idle_view.services.rotation_preview_controller.commit_selection_rotation()

        zero_group = _FakeRotationGroup(angle=0.0)
        zero_scene = _FakeScene(group=zero_group)
        zero_view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(group=zero_group),
            scene=lambda: zero_scene,
        )
        zero_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(zero_view))
        with mock.patch("ui.canvas_rotation_preview_controller.rotate_selection_for") as rotate_selection:
            zero_view.services.rotation_preview_controller.commit_selection_rotation()
        self.assertEqual(zero_group.rotations, [0.0])
        self.assertIsNone(zero_view.rotation_preview_state.group)
        self.assertIs(zero_scene.destroyed_group, zero_group)
        rotate_selection.assert_not_called()

        angle_group = _FakeRotationGroup(angle=22.0)
        angle_scene = _FakeScene(group=angle_group)
        angle_view = SimpleNamespace(
            rotation_preview_state=CanvasRotationPreviewState(group=angle_group),
            scene=lambda: angle_scene,
        )
        angle_view.services = SimpleNamespace(rotation_preview_controller=CanvasRotationPreviewController(angle_view))
        with mock.patch("ui.canvas_rotation_preview_controller.rotate_selection_for") as rotate_selection:
            angle_view.services.rotation_preview_controller.commit_selection_rotation()
        self.assertEqual(angle_group.rotations, [0.0])
        self.assertIsNone(angle_view.rotation_preview_state.group)
        self.assertIs(angle_scene.destroyed_group, angle_group)
        rotate_selection.assert_called_once_with(angle_view, 22.0)

if __name__ == "__main__":
    unittest.main()
