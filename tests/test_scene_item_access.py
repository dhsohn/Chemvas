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
from tests.runtime_services import canvas_runtime_services


class _Canvas:
    def __init__(self) -> None:
        self.calls = []

    def apply_scene_item_state(self, item, state) -> None:
        self.calls.append(("canvas_apply", item, dict(state)))

    def create_scene_item_from_state(self, state):
        self.calls.append(("canvas_create", dict(state)))
        return ("canvas", dict(state))

    def restore_scene_item(self, item) -> None:
        self.calls.append(("canvas_restore", item))

    def attach_scene_item(self, item) -> None:
        self.calls.append(("canvas_attach", item))

    def remove_scene_item(self, item) -> None:
        self.calls.append(("canvas_remove", item))

    def bond_ids_for_ring_item(self, item):
        self.calls.append(("canvas_bond_ids_for_ring", item))
        return {"canvas-bond"}

    def refresh_bond_geometry_for_ring_item(self, item) -> None:
        self.calls.append(("canvas_refresh_ring", item))


class _Controller:
    def __init__(self, canvas: _Canvas) -> None:
        self.canvas = canvas

    def apply_scene_item_state(self, item, state) -> None:
        self.canvas.calls.append(("controller_apply", item, dict(state)))

    def create_scene_item_from_state(self, state):
        self.canvas.calls.append(("controller_create", dict(state)))
        return ("controller", dict(state))

    def restore_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_restore", item))

    def attach_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_attach", item))

    def remove_scene_item(self, item) -> None:
        self.canvas.calls.append(("controller_remove", item))

    def bond_ids_for_ring_item(self, item):
        self.canvas.calls.append(("controller_bond_ids_for_ring", item))
        return {"controller-bond"}

    def refresh_bond_geometry_for_ring_item(self, item) -> None:
        self.canvas.calls.append(("controller_refresh_ring", item))


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
    def test_helpers_prefer_scene_item_controller_when_available(self) -> None:
        canvas = _Canvas()
        canvas.services = canvas_runtime_services(
            scene_item_controller=_Controller(canvas)
        )
        item = object()

        for kind in ("ring", "note", "mark", "arrow", "ts_bracket", "orbital"):
            self.assertEqual(
                canvas.services.scene_item_controller.create_scene_item_from_state(
                    {"kind": kind}
                ),
                ("controller", {"kind": kind}),
            )
        canvas.services.scene_item_controller.attach_scene_item(item)
        canvas.services.scene_item_controller.restore_scene_item(item)
        canvas.services.scene_item_controller.remove_scene_item(item)
        canvas.services.scene_item_controller.apply_scene_item_state(item, {"x": 2})
        self.assertEqual(
            canvas.services.scene_item_controller.bond_ids_for_ring_item(item),
            {"controller-bond"},
        )
        canvas.services.scene_item_controller.refresh_bond_geometry_for_ring_item(item)
        self.assertEqual(
            canvas.calls,
            [
                ("controller_create", {"kind": kind})
                for kind in ("ring", "note", "mark", "arrow", "ts_bracket", "orbital")
            ]
            + [
                ("controller_attach", item),
                ("controller_restore", item),
                ("controller_remove", item),
                ("controller_apply", item, {"x": 2}),
                ("controller_bond_ids_for_ring", item),
                ("controller_refresh_ring", item),
            ],
        )

    def test_helpers_require_scene_item_controller(self) -> None:
        canvas = _Canvas()

        with self.assertRaises(AttributeError):
            canvas.services.scene_item_controller.create_scene_item_from_state(
                {"kind": "ring"}
            )

    def test_attach_scene_item_requires_controller_attach_method(self) -> None:
        canvas = _Canvas()
        item = object()
        canvas.services = canvas_runtime_services(scene_item_controller=object())

        with self.assertRaises(AttributeError):
            canvas.services.scene_item_controller.attach_scene_item(item)

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
