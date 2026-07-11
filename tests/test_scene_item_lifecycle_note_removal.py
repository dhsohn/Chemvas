import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_scene_items_state import (
        CanvasSceneItemsState,
        add_selected_note_for,
        append_scene_item_for,
        selected_notes_for,
    )
    from ui.scene_item_lifecycle_service import SceneItemLifecycleService


if QApplication is not None:

    class _Canvas(QGraphicsView):
        def __init__(self) -> None:
            super().__init__(QGraphicsScene())
            self.selection_controller = SimpleNamespace(
                update_selection_outline=mock.Mock()
            )
            self.services = SimpleNamespace(
                selection_controller=self.selection_controller
            )

        def add_note(self, *, selected: bool) -> QGraphicsTextItem:
            note = QGraphicsTextItem("note")
            note.setData(0, "note")
            self.scene().addItem(note)
            append_scene_item_for(self, "note_items", note)
            if selected:
                add_selected_note_for(self, note)
            return note


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for lifecycle note removal tests"
)
class SceneItemLifecycleNoteRemovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_removing_selected_note_refreshes_selection_outline(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=True)
        service = SceneItemLifecycleService(canvas, graph_service=SimpleNamespace())

        # The DeleteTool erase path removes notes directly; the outline must be
        # redrawn or a notes-only group box would linger over the erased note.
        service.remove_scene_item(note)

        self.assertNotIn(note, selected_notes_for(canvas))
        self.assertIsNone(note.scene())
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_removing_unselected_note_skips_outline_refresh(self) -> None:
        canvas = _Canvas()
        note = canvas.add_note(selected=False)
        service = SceneItemLifecycleService(canvas, graph_service=SimpleNamespace())

        service.remove_scene_item(note)

        self.assertIsNone(note.scene())
        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_attach_uses_one_stable_scene_for_add_and_direct_rollback(self) -> None:
        class AttachThenFailScene(QGraphicsScene):
            add_port_reads = 0
            remove_port_reads = 0

            @property
            def addItem(self):
                self.add_port_reads += 1
                if self.add_port_reads == 1:
                    return self._add_then_fail
                return lambda _item: None

            def _add_then_fail(self, item) -> None:
                QGraphicsScene.addItem(self, item)
                raise RuntimeError("scene add failed after attachment")

            @property
            def removeItem(self):
                self.remove_port_reads += 1
                if self.remove_port_reads == 1:
                    return lambda item: QGraphicsScene.removeItem(self, item)
                return lambda _item: None

        first_scene = AttachThenFailScene()
        second_scene = QGraphicsScene()
        third_scene = AttachThenFailScene()

        class ChangingSceneCanvas:
            def __init__(self) -> None:
                self.scene_calls = 0
                self.scene_items_state = CanvasSceneItemsState()

            def scene(self):
                self.scene_calls += 1
                return {
                    1: first_scene,
                    2: second_scene,
                    3: third_scene,
                }.get(self.scene_calls, first_scene)

        canvas = ChangingSceneCanvas()
        service = SceneItemLifecycleService(
            canvas,
            graph_service=SimpleNamespace(),
        )

        class ChangingSceneItem(QGraphicsRectItem):
            scene_port_reads = 0

            @property
            def scene(self):
                self.scene_port_reads += 1
                if self.scene_port_reads == 1:
                    return lambda: QGraphicsRectItem.scene(self)
                return lambda: third_scene

        item = ChangingSceneItem()
        item.setData(0, "shape")

        with self.assertRaisesRegex(
            RuntimeError,
            "scene add failed after attachment",
        ):
            service.attach_scene_item(item)

        self.assertEqual(canvas.scene_calls, 1)
        self.assertEqual(item.scene_port_reads, 0)
        self.assertIsNone(QGraphicsRectItem.scene(item))
        self.assertEqual(first_scene.add_port_reads, 1)
        self.assertEqual(first_scene.remove_port_reads, 1)
        self.assertNotIn(item, first_scene.items())
        self.assertNotIn(item, second_scene.items())
        self.assertNotIn(item, third_scene.items())
        self.assertEqual(canvas.scene_items_state.shape_items, [])


if __name__ == "__main__":
    unittest.main()
