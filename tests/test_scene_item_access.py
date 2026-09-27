import unittest

from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF
from PyQt6.QtWidgets import QGraphicsRectItem

from chemvas.ui.scene.scene_item_access import (
    add_item_to_canvas_scene,
    attached_canvas_scene_items,
    item_is_in_canvas_scene,
    remove_attached_item_from_canvas_scene,
    remove_item_from_canvas_scene,
    remove_items_from_canvas_scene,
)


class _Canvas:
    pass


class _Scene:
    def __init__(self) -> None:
        self.items = []
        self.removed_items = []

    def addItem(self, item) -> None:
        self.items.append(item)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)


class _SceneItem:
    def __init__(self, scene=None, *, raises: bool = False) -> None:
        self._scene = scene
        self.raises = raises

    def scene(self):
        if self.raises:
            raise RuntimeError("deleted")
        return self._scene


class SceneItemAccessTest(unittest.TestCase):
    def test_add_item_to_canvas_scene_adds_and_returns_item(self) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        item = object()

        self.assertIs(add_item_to_canvas_scene(canvas, item), item)

        self.assertEqual(scene.items, [item])

    def test_item_is_in_canvas_scene_handles_attached_detached_and_deleted_items(
        self,
    ) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        deleted_canvas = _Canvas()
        deleted_canvas.scene = lambda: (_ for _ in ()).throw(RuntimeError("deleted"))

        self.assertTrue(item_is_in_canvas_scene(canvas, _SceneItem(scene)))
        self.assertFalse(item_is_in_canvas_scene(canvas, _SceneItem(_Scene())))
        self.assertFalse(item_is_in_canvas_scene(canvas, None))
        self.assertFalse(item_is_in_canvas_scene(deleted_canvas, None))
        with self.assertRaisesRegex(RuntimeError, "deleted"):
            item_is_in_canvas_scene(canvas, _SceneItem(scene, raises=True))
        with self.assertRaisesRegex(RuntimeError, "deleted"):
            item_is_in_canvas_scene(deleted_canvas, _SceneItem(scene))

        deleted_item = QGraphicsRectItem(QRectF(0.0, 0.0, 1.0, 1.0))
        sip.delete(deleted_item)
        self.assertFalse(item_is_in_canvas_scene(canvas, deleted_item))
        self.assertFalse(item_is_in_canvas_scene(deleted_canvas, deleted_item))
        deleted_qobject_canvas = QObject()
        sip.delete(deleted_qobject_canvas)
        self.assertFalse(
            item_is_in_canvas_scene(deleted_qobject_canvas, _SceneItem(scene))
        )

    def test_remove_item_from_canvas_scene_removes_only_attached_items(self) -> None:
        scene = _Scene()
        other_scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        deleted_canvas = _Canvas()
        deleted_canvas.scene = lambda: (_ for _ in ()).throw(RuntimeError("deleted"))
        attached = _SceneItem(scene)
        detached = _SceneItem(other_scene)
        floating = _SceneItem(None)
        deleted = _SceneItem(scene, raises=True)
        fake_item = object()

        self.assertTrue(remove_item_from_canvas_scene(canvas, attached))
        self.assertFalse(remove_item_from_canvas_scene(canvas, detached))
        self.assertFalse(remove_item_from_canvas_scene(canvas, floating))
        self.assertFalse(remove_item_from_canvas_scene(canvas, deleted))
        self.assertTrue(remove_item_from_canvas_scene(canvas, fake_item))
        self.assertFalse(remove_item_from_canvas_scene(canvas, None))
        self.assertFalse(remove_item_from_canvas_scene(deleted_canvas, attached))

        self.assertEqual(scene.removed_items, [attached, fake_item])

    def test_remove_attached_item_from_canvas_scene_reports_detached_and_deleted_items(
        self,
    ) -> None:
        scene = _Scene()
        other_scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        deleted_canvas = _Canvas()
        deleted_canvas.scene = lambda: (_ for _ in ()).throw(RuntimeError("deleted"))
        attached = _SceneItem(scene)
        detached = _SceneItem(other_scene)
        deleted = _SceneItem(scene, raises=True)
        fake_item = object()

        self.assertTrue(remove_attached_item_from_canvas_scene(canvas, attached))
        self.assertFalse(remove_attached_item_from_canvas_scene(canvas, detached))
        self.assertIsNone(remove_attached_item_from_canvas_scene(canvas, deleted))
        self.assertTrue(remove_attached_item_from_canvas_scene(canvas, fake_item))
        self.assertFalse(remove_attached_item_from_canvas_scene(canvas, None))
        self.assertIsNone(
            remove_attached_item_from_canvas_scene(deleted_canvas, attached)
        )

        self.assertEqual(scene.removed_items, [attached, fake_item])

    def test_remove_items_from_canvas_scene_removes_each_attached_item(self) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        first = _SceneItem(scene)
        second = _SceneItem(scene)

        remove_items_from_canvas_scene(canvas, [first, second])

        self.assertEqual(scene.removed_items, [first, second])

    def test_attached_canvas_scene_items_filters_detached_and_deleted_items(
        self,
    ) -> None:
        scene = _Scene()
        other_scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        deleted_canvas = _Canvas()
        deleted_canvas.scene = lambda: (_ for _ in ()).throw(RuntimeError("deleted"))
        attached = _SceneItem(scene)
        detached = _SceneItem(other_scene)
        deleted = _SceneItem(scene, raises=True)

        self.assertEqual(
            attached_canvas_scene_items(canvas, [attached, detached, deleted]),
            [attached],
        )
        self.assertEqual(attached_canvas_scene_items(deleted_canvas, [attached]), [])
