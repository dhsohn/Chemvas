import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.scene_item_access import (
    apply_scene_item_state,
    attach_scene_item,
    create_scene_item_from_state,
    remove_scene_item,
    restore_arrow_from_state,
    restore_mark_from_state,
    restore_note_from_state,
    restore_orbital_from_state,
    restore_ring_from_state,
    restore_scene_item,
    restore_ts_bracket_from_state,
)


class _Canvas:
    def __init__(self) -> None:
        self.calls = []

    def _restore_mark_from_state(self, mark_state) -> None:
        self.calls.append(("canvas_restore_mark", dict(mark_state)))

    def _restore_ring_from_state(self, ring_state):
        self.calls.append(("canvas_restore_ring", dict(ring_state)))
        return ("canvas_ring", dict(ring_state))

    def _restore_note_from_state(self, note_state):
        self.calls.append(("canvas_restore_note", dict(note_state)))
        return ("canvas_note", dict(note_state))

    def _restore_arrow_from_state(self, arrow_state):
        self.calls.append(("canvas_restore_arrow", dict(arrow_state)))
        return ("canvas_arrow", dict(arrow_state))

    def _restore_ts_bracket_from_state(self, ts_bracket_state):
        self.calls.append(("canvas_restore_ts", dict(ts_bracket_state)))
        return ("canvas_ts", dict(ts_bracket_state))

    def _restore_orbital_from_state(self, orbital_state):
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


class _Controller:
    def __init__(self, canvas: _Canvas) -> None:
        self.canvas = canvas

    def _restore_mark_from_state(self, mark_state) -> None:
        self.canvas.calls.append(("controller_restore_mark", dict(mark_state)))

    def _restore_ring_from_state(self, ring_state):
        self.canvas.calls.append(("controller_restore_ring", dict(ring_state)))
        return ("controller_ring", dict(ring_state))

    def _restore_note_from_state(self, note_state):
        self.canvas.calls.append(("controller_restore_note", dict(note_state)))
        return ("controller_note", dict(note_state))

    def _restore_arrow_from_state(self, arrow_state):
        self.canvas.calls.append(("controller_restore_arrow", dict(arrow_state)))
        return ("controller_arrow", dict(arrow_state))

    def _restore_ts_bracket_from_state(self, ts_bracket_state):
        self.canvas.calls.append(("controller_restore_ts", dict(ts_bracket_state)))
        return ("controller_ts", dict(ts_bracket_state))

    def _restore_orbital_from_state(self, orbital_state):
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


class SceneItemAccessTest(unittest.TestCase):
    def test_helpers_prefer_scene_item_controller_when_available(self) -> None:
        canvas = _Canvas()
        canvas._scene_item_controller = _Controller(canvas)
        item = object()

        self.assertEqual(restore_ring_from_state(canvas, {"kind": "ring"}), ("controller_ring", {"kind": "ring"}))
        self.assertEqual(restore_note_from_state(canvas, {"kind": "note"}), ("controller_note", {"kind": "note"}))
        self.assertEqual(create_scene_item_from_state(canvas, {"id": 1}), ("controller", {"id": 1}))
        attach_scene_item(canvas, item)
        restore_scene_item(canvas, item)
        remove_scene_item(canvas, item)
        apply_scene_item_state(canvas, item, {"x": 2})
        restore_mark_from_state(canvas, {"atom_id": 3})
        self.assertEqual(restore_arrow_from_state(canvas, {"kind": "arrow"}), ("controller_arrow", {"kind": "arrow"}))
        self.assertEqual(
            restore_ts_bracket_from_state(canvas, {"kind": "ts"}),
            ("controller_ts", {"kind": "ts"}),
        )
        self.assertEqual(
            restore_orbital_from_state(canvas, {"kind": "orbital"}),
            ("controller_orbital", {"kind": "orbital"}),
        )

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
            ],
        )

    def test_helpers_fall_back_to_canvas_methods_without_controller(self) -> None:
        canvas = _Canvas()
        item = object()

        self.assertEqual(restore_ring_from_state(canvas, {"kind": "ring"}), ("canvas_ring", {"kind": "ring"}))
        self.assertEqual(restore_note_from_state(canvas, {"kind": "note"}), ("canvas_note", {"kind": "note"}))
        self.assertEqual(create_scene_item_from_state(canvas, {"id": 1}), ("canvas", {"id": 1}))
        attach_scene_item(canvas, item)
        restore_scene_item(canvas, item)
        remove_scene_item(canvas, item)
        apply_scene_item_state(canvas, item, {"x": 2})
        restore_mark_from_state(canvas, {"atom_id": 3})
        self.assertEqual(restore_arrow_from_state(canvas, {"kind": "arrow"}), ("canvas_arrow", {"kind": "arrow"}))
        self.assertEqual(restore_ts_bracket_from_state(canvas, {"kind": "ts"}), ("canvas_ts", {"kind": "ts"}))
        self.assertEqual(
            restore_orbital_from_state(canvas, {"kind": "orbital"}),
            ("canvas_orbital", {"kind": "orbital"}),
        )

        self.assertEqual(
            canvas.calls,
            [
                ("canvas_restore_ring", {"kind": "ring"}),
                ("canvas_restore_note", {"kind": "note"}),
                ("canvas_create", {"id": 1}),
                ("canvas_attach", item),
                ("canvas_restore", item),
                ("canvas_remove", item),
                ("canvas_apply", item, {"x": 2}),
                ("canvas_restore_mark", {"atom_id": 3}),
                ("canvas_restore_arrow", {"kind": "arrow"}),
                ("canvas_restore_ts", {"kind": "ts"}),
                ("canvas_restore_orbital", {"kind": "orbital"}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
