import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ui.canvas_document_state import restore_document_post_model_items, restore_document_pre_model_items


class _Canvas:
    def __init__(self) -> None:
        self.calls = []

    def _restore_ring_from_state(self, ring_state):
        self.calls.append(("canvas_ring", dict(ring_state)))

    def _restore_note_from_state(self, note_state):
        self.calls.append(("canvas_note", dict(note_state)))

    def _restore_mark_from_state(self, mark_state):
        self.calls.append(("canvas_mark", dict(mark_state)))

    def _restore_arrow_from_state(self, arrow_state):
        self.calls.append(("canvas_arrow", dict(arrow_state)))

    def _restore_ts_bracket_from_state(self, ts_bracket_state):
        self.calls.append(("canvas_ts", dict(ts_bracket_state)))

    def _restore_orbital_from_state(self, orbital_state):
        self.calls.append(("canvas_orbital", dict(orbital_state)))


class _Controller:
    def __init__(self, canvas: _Canvas) -> None:
        self.canvas = canvas

    def _restore_ring_from_state(self, ring_state):
        self.canvas.calls.append(("controller_ring", dict(ring_state)))

    def _restore_note_from_state(self, note_state):
        self.canvas.calls.append(("controller_note", dict(note_state)))

    def _restore_mark_from_state(self, mark_state):
        self.canvas.calls.append(("controller_mark", dict(mark_state)))

    def _restore_arrow_from_state(self, arrow_state):
        self.canvas.calls.append(("controller_arrow", dict(arrow_state)))

    def _restore_ts_bracket_from_state(self, ts_bracket_state):
        self.canvas.calls.append(("controller_ts", dict(ts_bracket_state)))

    def _restore_orbital_from_state(self, orbital_state):
        self.canvas.calls.append(("controller_orbital", dict(orbital_state)))


class CanvasDocumentStateTest(unittest.TestCase):
    def test_restore_document_items_prefer_scene_item_controller(self) -> None:
        canvas = _Canvas()
        canvas._scene_item_controller = _Controller(canvas)
        state = {
            "ring_fills": [{"points": [(0.0, 0.0)]}],
            "notes": [{"text": "note", "x": 1.0, "y": 2.0}],
            "marks": [{"kind": "minus", "text": "-", "atom_id": 3, "dx": 1.0, "dy": 2.0, "x": 4.0, "y": 5.0}],
            "arrows": [{"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)}],
            "ts_brackets": [{"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0, 1.0)}],
            "orbitals": [{"kind": "p", "center": (3.0, 4.0), "scale": 2.0, "rotation": 45.0}],
        }

        restore_document_pre_model_items(canvas, state)
        restore_document_post_model_items(canvas, state)

        self.assertEqual(
            canvas.calls,
            [
                ("controller_ring", {"points": [(0.0, 0.0)]}),
                ("controller_note", {"text": "note", "x": 1.0, "y": 2.0}),
                (
                    "controller_mark",
                    {
                        "kind": "mark",
                        "mark_kind": "minus",
                        "text": "-",
                        "atom_id": 3,
                        "dx": 1.0,
                        "dy": 2.0,
                        "x": 4.0,
                        "y": 5.0,
                    },
                ),
                ("controller_arrow", {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)}),
                ("controller_ts", {"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0, 1.0)}),
                (
                    "controller_orbital",
                    {
                        "kind": "orbital",
                        "orbital_kind": "p",
                        "center": (3.0, 4.0),
                        "scale": 2.0,
                        "rotation": 45.0,
                    },
                ),
            ],
        )

    def test_restore_document_items_fall_back_to_canvas_wrappers(self) -> None:
        canvas = _Canvas()
        state = {
            "ring_fills": [{"points": [(0.0, 0.0)]}],
            "notes": [{"text": "note", "x": 1.0, "y": 2.0}],
            "marks": [{"kind": "plus", "text": "+", "atom_id": None, "dx": None, "dy": None, "x": 4.0, "y": 5.0}],
            "arrows": [{"kind": "equilibrium"}],
            "ts_brackets": [{"kind": "ts_bracket", "rect": (0.0, 0.0, 2.0, 2.0)}],
            "orbitals": [{"center": (3.0, 4.0)}],
        }

        restore_document_pre_model_items(canvas, state)
        restore_document_post_model_items(canvas, state)

        self.assertEqual(
            canvas.calls,
            [
                ("canvas_ring", {"points": [(0.0, 0.0)]}),
                ("canvas_note", {"text": "note", "x": 1.0, "y": 2.0}),
                (
                    "canvas_mark",
                    {
                        "kind": "mark",
                        "mark_kind": "plus",
                        "text": "+",
                        "atom_id": None,
                        "dx": None,
                        "dy": None,
                        "x": 4.0,
                        "y": 5.0,
                    },
                ),
                ("canvas_arrow", {"kind": "equilibrium"}),
                ("canvas_ts", {"kind": "ts_bracket", "rect": (0.0, 0.0, 2.0, 2.0)}),
                (
                    "canvas_orbital",
                    {
                        "kind": "orbital",
                        "orbital_kind": "s",
                        "center": (3.0, 4.0),
                        "scale": 1.0,
                        "rotation": 0.0,
                    },
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
