import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ui.scene_clipboard_access as access
from PyQt6.QtCore import QRectF


class _Canvas:
    def __init__(self, scene) -> None:
        self._scene = scene

    def scene(self):
        return self._scene


class _Scene:
    def __init__(self, items=None) -> None:
        self._items = list(items or [])
        self.items_calls = []
        self.render_calls = []

    def items(self, *args):
        self.items_calls.append(args)
        return list(self._items)

    def render(self, painter, target, source) -> None:
        self.render_calls.append((painter, target, source))


class _Item:
    def __init__(self, scene=None, *, data=None, visible=True) -> None:
        self._scene = scene
        self._data = dict(data or {})
        self._visible = visible

    def data(self, key):
        return self._data.get(key)

    def isVisible(self) -> bool:
        return self._visible

    def scene(self):
        return self._scene


class SceneClipboardAccessTest(unittest.TestCase):
    def test_clipboard_paste_state_helpers_read_and_write_canvas_state(self) -> None:
        canvas = SimpleNamespace()

        self.assertIsNone(access.clipboard_paste_source_json_for(canvas))
        self.assertEqual(access.clipboard_paste_count_for(canvas), 0)

        access.set_clipboard_paste_source_json_for(canvas, "payload")
        access.set_clipboard_paste_count_for(canvas, 3)

        self.assertEqual(access.clipboard_paste_source_json_for(canvas), "payload")
        self.assertEqual(access.clipboard_paste_count_for(canvas), 3)

    def test_build_selection_clipboard_payload_for_canvas_uses_canvas_scene_membership(self) -> None:
        scene = _Scene()
        other_scene = _Scene()
        canvas = _Canvas(scene)
        attached_ring = _Item(scene, data={0: "ring", 2: [1, 2], 9: {"kind": "ring", "id": "attached"}})
        detached_ring = _Item(other_scene, data={0: "ring", 2: [1, 2], 9: {"kind": "ring", "id": "detached"}})
        attached_mark = _Item(scene, data={0: "mark", 9: {"kind": "mark", "id": "attached"}})
        detached_mark = _Item(other_scene, data={0: "mark", 9: {"kind": "mark", "id": "detached"}})

        payload = access.build_selection_clipboard_payload_for_canvas(
            canvas,
            selected_items=[],
            explicit_atom_ids={1, 2},
            selected_bond_ids=set(),
            bonds=[],
            ring_items=[attached_ring, detached_ring],
            marks_by_atom={1: [attached_mark, detached_mark]},
            atom_state_getter=lambda atom_id: {"element": "C", "x": atom_id, "y": atom_id},
            bond_state_getter=lambda bond: {"bond": bond},
            scene_item_state_getter=lambda item: item.data(9),
            version=7,
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["version"], 7)
        self.assertEqual(payload["rings"], [{"kind": "ring", "id": "attached"}])
        self.assertEqual(payload["marks"], [{"kind": "mark", "id": "attached"}])

    def test_visible_canvas_items_to_hide_for_copy_queries_canvas_scene_source(self) -> None:
        selected = _Item(visible=True)
        visible_unselected = _Item(visible=True)
        hidden_unselected = _Item(visible=False)
        scene = _Scene([selected, visible_unselected, hidden_unselected])
        canvas = _Canvas(scene)
        source = QRectF(1, 2, 3, 4)

        hidden = access.visible_canvas_items_to_hide_for_copy(canvas, source, selected_items={selected})

        self.assertEqual(hidden, [visible_unselected])
        self.assertEqual(scene.items_calls, [(source,)])

    def test_render_canvas_scene_region_builds_target_from_source(self) -> None:
        scene = _Scene()
        canvas = _Canvas(scene)
        painter = object()
        source = QRectF(10, 20, 30, 40)

        access.render_canvas_scene_region(canvas, painter, source=source)

        self.assertEqual(len(scene.render_calls), 1)
        rendered_painter, target, rendered_source = scene.render_calls[0]
        self.assertIs(rendered_painter, painter)
        self.assertEqual(rendered_source, source)
        self.assertEqual(target, QRectF(0, 0, 30, 40))

    def test_render_canvas_selection_vector_bytes_uses_canvas_scene(self) -> None:
        scene = _Scene()
        canvas = _Canvas(scene)
        source = QRectF(1, 2, 3, 4)
        items = [_Item(scene)]

        with (
            patch.object(access, "render_scene_to_svg_bytes", return_value=b"svg") as svg_renderer,
            patch.object(access, "render_scene_to_pdf_bytes", return_value=b"pdf") as pdf_renderer,
        ):
            rendered = access.render_canvas_selection_vector_bytes(
                canvas,
                source=source,
                items=items,
                title="Chemvas selection",
            )

        self.assertEqual(rendered, (b"svg", b"pdf"))
        svg_renderer.assert_called_once_with(scene, source=source, items=items, title="Chemvas selection")
        pdf_renderer.assert_called_once_with(scene, source=source, items=items, title="Chemvas selection")


if __name__ == "__main__":
    unittest.main()
