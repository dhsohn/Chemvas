import unittest

from chemvas.ui.scene_item_access import (
    add_item_to_canvas_scene,
    apply_scene_item_state,
    attach_scene_item,
    attached_canvas_scene_items,
    bond_ids_for_ring_item,
    clear_canvas_scene,
    clear_canvas_scene_item_list_map,
    clear_canvas_scene_item_map,
    create_scene_item_from_state,
    create_scene_item_group,
    destroy_scene_item_group,
    item_can_be_added_to_canvas_scene,
    item_is_in_canvas_scene,
    refresh_bond_geometry_for_ring_item,
    remove_attached_item_from_canvas_scene,
    remove_item_from_canvas_scene,
    remove_items_from_canvas_scene,
    remove_scene_item,
    restore_arrow_from_state,
    restore_mark_from_state,
    restore_note_from_state,
    restore_orbital_from_state,
    restore_ring_from_state,
    restore_scene_item,
    restore_ts_bracket_from_state,
)
from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF
from PyQt6.QtWidgets import QGraphicsRectItem

from tests.runtime_services import canvas_runtime_services


class _Canvas:
    def __init__(self) -> None:
        self.calls = []

    def restore_mark_from_state(self, mark_state) -> None:
        self.calls.append(("canvas_restore_mark", dict(mark_state)))

    def restore_ring_from_state(self, ring_state):
        self.calls.append(("canvas_restore_ring", dict(ring_state)))
        return ("canvas_ring", dict(ring_state))

    def restore_note_from_state(self, note_state):
        self.calls.append(("canvas_restore_note", dict(note_state)))
        return ("canvas_note", dict(note_state))

    def restore_arrow_from_state(self, arrow_state):
        self.calls.append(("canvas_restore_arrow", dict(arrow_state)))
        return ("canvas_arrow", dict(arrow_state))

    def restore_ts_bracket_from_state(self, ts_bracket_state):
        self.calls.append(("canvas_restore_ts", dict(ts_bracket_state)))
        return ("canvas_ts", dict(ts_bracket_state))

    def restore_orbital_from_state(self, orbital_state):
        self.calls.append(("canvas_restore_orbital", dict(orbital_state)))
        return ("canvas_orbital", dict(orbital_state))

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

    def restore_mark_from_state(self, mark_state) -> None:
        self.canvas.calls.append(("controller_restore_mark", dict(mark_state)))

    def restore_ring_from_state(self, ring_state):
        self.canvas.calls.append(("controller_restore_ring", dict(ring_state)))
        return ("controller_ring", dict(ring_state))

    def restore_note_from_state(self, note_state):
        self.canvas.calls.append(("controller_restore_note", dict(note_state)))
        return ("controller_note", dict(note_state))

    def restore_arrow_from_state(self, arrow_state):
        self.canvas.calls.append(("controller_restore_arrow", dict(arrow_state)))
        return ("controller_arrow", dict(arrow_state))

    def restore_ts_bracket_from_state(self, ts_bracket_state):
        self.canvas.calls.append(("controller_restore_ts", dict(ts_bracket_state)))
        return ("controller_ts", dict(ts_bracket_state))

    def restore_orbital_from_state(self, orbital_state):
        self.canvas.calls.append(("controller_restore_orbital", dict(orbital_state)))
        return ("controller_orbital", dict(orbital_state))

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
        self.calls = []
        self.items = []
        self.removed_items = []
        self.clear_calls = 0

    def addItem(self, item) -> None:
        self.items.append(item)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def clear(self) -> None:
        self.clear_calls += 1

    def createItemGroup(self, items):
        self.calls.append(("create_group", list(items)))
        return ("group", tuple(items))

    def destroyItemGroup(self, group) -> None:
        self.calls.append(("destroy_group", group))


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

        self.assertEqual(
            restore_ring_from_state(canvas, {"kind": "ring"}),
            ("controller_ring", {"kind": "ring"}),
        )
        self.assertEqual(
            restore_note_from_state(canvas, {"kind": "note"}),
            ("controller_note", {"kind": "note"}),
        )
        self.assertEqual(
            create_scene_item_from_state(canvas, {"id": 1}), ("controller", {"id": 1})
        )
        attach_scene_item(canvas, item)
        restore_scene_item(canvas, item)
        remove_scene_item(canvas, item)
        apply_scene_item_state(canvas, item, {"x": 2})
        self.assertIsNone(restore_mark_from_state(canvas, {"atom_id": 3}))
        self.assertEqual(
            restore_arrow_from_state(canvas, {"kind": "arrow"}),
            ("controller_arrow", {"kind": "arrow"}),
        )
        self.assertEqual(
            restore_ts_bracket_from_state(canvas, {"kind": "ts"}),
            ("controller_ts", {"kind": "ts"}),
        )
        self.assertEqual(
            restore_orbital_from_state(canvas, {"kind": "orbital"}),
            ("controller_orbital", {"kind": "orbital"}),
        )
        self.assertEqual(bond_ids_for_ring_item(canvas, item), {"controller-bond"})
        refresh_bond_geometry_for_ring_item(canvas, item)

        self.assertEqual(
            canvas.calls,
            [
                ("controller_restore_ring", {"kind": "ring"}),
                ("controller_restore_note", {"kind": "note"}),
                ("controller_create", {"id": 1}),
                ("controller_attach", item),
                ("controller_restore", item),
                ("controller_remove", item),
                ("controller_apply", item, {"x": 2}),
                ("controller_restore_mark", {"atom_id": 3}),
                ("controller_restore_arrow", {"kind": "arrow"}),
                ("controller_restore_ts", {"kind": "ts"}),
                ("controller_restore_orbital", {"kind": "orbital"}),
                ("controller_bond_ids_for_ring", item),
                ("controller_refresh_ring", item),
            ],
        )

    def test_helpers_require_scene_item_controller(self) -> None:
        canvas = _Canvas()

        with self.assertRaises(AttributeError):
            restore_ring_from_state(canvas, {"kind": "ring"})

    def test_attach_scene_item_requires_controller_attach_method(self) -> None:
        canvas = _Canvas()
        item = object()
        canvas.services = canvas_runtime_services(scene_item_controller=object())

        with self.assertRaises(AttributeError):
            attach_scene_item(canvas, item)

    def test_scene_group_helpers_delegate_to_scene(self) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        items = [object(), object()]

        group = create_scene_item_group(canvas, items)
        destroy_scene_item_group(canvas, group)

        self.assertEqual(group, ("group", tuple(items)))
        self.assertEqual(
            scene.calls, [("create_group", items), ("destroy_group", group)]
        )

    def test_add_item_to_canvas_scene_adds_and_returns_item(self) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        item = object()

        self.assertIs(add_item_to_canvas_scene(canvas, item), item)

        self.assertEqual(scene.calls, [])
        self.assertEqual(scene.items, [item])

    def test_clear_canvas_scene_delegates_to_scene_clear(self) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene

        clear_canvas_scene(canvas)

        self.assertEqual(scene.clear_calls, 1)

    def test_canvas_scene_item_map_helpers_remove_items_and_return_empty_maps(
        self,
    ) -> None:
        scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        first = object()
        second = object()
        label = object()

        self.assertEqual(
            clear_canvas_scene_item_list_map(canvas, {1: [first], 2: [second]}), {}
        )
        self.assertEqual(clear_canvas_scene_item_map(canvas, {3: label}), {})

        self.assertEqual(scene.removed_items, [first, second, label])

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

        class BrokenSceneDescriptor:
            @property
            def scene(self):
                raise AttributeError("live item scene descriptor failed")

        with self.assertRaisesRegex(AttributeError, "scene descriptor failed"):
            item_is_in_canvas_scene(canvas, BrokenSceneDescriptor())

        deleted_item = QGraphicsRectItem(QRectF(0.0, 0.0, 1.0, 1.0))
        sip.delete(deleted_item)
        self.assertFalse(item_is_in_canvas_scene(canvas, deleted_item))
        self.assertFalse(item_is_in_canvas_scene(deleted_canvas, deleted_item))
        deleted_qobject_canvas = QObject()
        sip.delete(deleted_qobject_canvas)
        self.assertFalse(
            item_is_in_canvas_scene(deleted_qobject_canvas, _SceneItem(scene))
        )

    def test_item_can_be_added_to_canvas_scene_distinguishes_attached_and_deleted_items(
        self,
    ) -> None:
        scene = _Scene()
        other_scene = _Scene()
        canvas = _Canvas()
        canvas.scene = lambda: scene
        deleted_canvas = _Canvas()
        deleted_canvas.scene = lambda: (_ for _ in ()).throw(RuntimeError("deleted"))

        self.assertFalse(item_can_be_added_to_canvas_scene(canvas, _SceneItem(scene)))
        self.assertTrue(
            item_can_be_added_to_canvas_scene(canvas, _SceneItem(other_scene))
        )
        self.assertTrue(item_can_be_added_to_canvas_scene(canvas, object()))
        self.assertFalse(item_can_be_added_to_canvas_scene(canvas, None))
        self.assertFalse(item_can_be_added_to_canvas_scene(deleted_canvas, None))
        with self.assertRaisesRegex(RuntimeError, "deleted"):
            item_can_be_added_to_canvas_scene(canvas, _SceneItem(scene, raises=True))
        with self.assertRaisesRegex(RuntimeError, "deleted"):
            item_can_be_added_to_canvas_scene(deleted_canvas, _SceneItem(other_scene))

        class BrokenSceneDescriptor:
            @property
            def scene(self):
                raise AttributeError("live item scene descriptor failed")

        with self.assertRaisesRegex(AttributeError, "scene descriptor failed"):
            item_can_be_added_to_canvas_scene(canvas, BrokenSceneDescriptor())

        deleted_item = QGraphicsRectItem(QRectF(0.0, 0.0, 1.0, 1.0))
        sip.delete(deleted_item)
        self.assertFalse(item_can_be_added_to_canvas_scene(canvas, deleted_item))
        self.assertFalse(
            item_can_be_added_to_canvas_scene(deleted_canvas, deleted_item)
        )
        deleted_qobject_canvas = QObject()
        sip.delete(deleted_qobject_canvas)
        self.assertFalse(
            item_can_be_added_to_canvas_scene(
                deleted_qobject_canvas,
                _SceneItem(other_scene),
            )
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


if __name__ == "__main__":
    unittest.main()
