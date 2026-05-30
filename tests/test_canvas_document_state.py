import unittest
from types import SimpleNamespace
from unittest import mock

from core.model import Atom, Bond, MoleculeModel
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    snapshot_canvas_document_state,
)


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


class _SceneItem:
    def __init__(self, scene_obj) -> None:
        self._scene = scene_obj

    def scene(self):
        return self._scene


class _DisposedSceneItem:
    def scene(self):
        raise RuntimeError("disposed")


class CanvasDocumentStateTest(unittest.TestCase):
    def test_snapshot_canvas_document_state_skips_detached_disposed_and_empty_arrow_state(self) -> None:
        scene_obj = object()
        attached = _SceneItem(scene_obj)
        detached = _SceneItem(object())
        disposed = _DisposedSceneItem()

        canvas = SimpleNamespace(
            model=MoleculeModel(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 1, 1)]),
            atom_items={1: object()},
            ring_items=[attached, detached, disposed],
            note_items=[attached, detached],
            mark_items=[attached],
            arrow_items=[attached, detached],
            ts_bracket_items=[attached],
            orbital_items=[attached],
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=18.0),
                set_bond_length=mock.Mock(),
            ),
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
            last_smiles_input="CCO",
            scene=lambda: scene_obj,
            _ring_state_dict=lambda item: {"points": [(0.0, 0.0)], "atom_ids": [1], "color": "#abcdef", "alpha": 0.25},
            _note_state_dict=lambda item: {"text": "note", "x": 1.0, "y": 2.0},
            _mark_state_dict=lambda item: {"mark_kind": "plus", "text": "+", "atom_id": 1, "dx": 0.5, "dy": -0.5, "x": 3.0, "y": 4.0},
            _arrow_state_dict=lambda item: {} if item is attached else {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)},
            _ts_bracket_state_dict=lambda item: {"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0, 1.0)},
            _orbital_state_dict=lambda item: {"orbital_kind": "p", "center": (2.0, 3.0), "scale": 2.0, "rotation": 45.0},
        )

        state = snapshot_canvas_document_state(canvas)

        self.assertTrue(state["model"]["atoms"][1]["explicit_label"])
        self.assertEqual(state["ring_fills"], [{"points": [(0.0, 0.0)], "atom_ids": [1], "color": "#abcdef", "alpha": 0.25}])
        self.assertEqual(state["notes"], [{"text": "note", "x": 1.0, "y": 2.0}])
        self.assertEqual(
            state["marks"],
            [{"kind": "plus", "text": "+", "atom_id": 1, "dx": 0.5, "dy": -0.5, "x": 3.0, "y": 4.0}],
        )
        self.assertEqual(state["arrows"], [])
        self.assertEqual(state["ts_brackets"], [{"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0, 1.0)}])
        self.assertEqual(
            state["orbitals"],
            [{"kind": "p", "center": (2.0, 3.0), "scale": 2.0, "rotation": 45.0}],
        )
        self.assertEqual(state["settings"]["sheet_size"], "A4")
        self.assertEqual(state["settings"]["sheet_orientation"], "portrait")
        self.assertEqual(state["last_smiles_input"], "CCO")

    def test_apply_document_settings_uses_state_values(self) -> None:
        canvas = SimpleNamespace(
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=18.0),
                set_bond_length=mock.Mock(),
            ),
            arrow_line_width=1.0,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="landscape",
            set_sheet_setup=mock.Mock(),
            last_smiles_input="before",
        )

        apply_document_settings(
            canvas,
            {
                "settings": {
                    "bond_length_px": 22.0,
                    "arrow_line_width": 1.7,
                    "arrow_head_scale": 0.5,
                    "orbital_phase_enabled": True,
                    "text_font_size": 14,
                    "text_font_weight": 500,
                    "text_italic": True,
                    "sheet_size": "Letter",
                    "sheet_orientation": "portrait",
                },
                "last_smiles_input": "after",
            },
        )

        canvas.renderer.set_bond_length.assert_called_once_with(22.0)
        canvas.set_sheet_setup.assert_called_once_with("Letter", "portrait")
        self.assertEqual(canvas.arrow_line_width, 1.7)
        self.assertEqual(canvas.arrow_head_scale, 0.5)
        self.assertTrue(canvas.orbital_phase_enabled)
        self.assertEqual(canvas.text_font_size, 14)
        self.assertEqual(canvas.text_font_weight, 500)
        self.assertTrue(canvas.text_italic)
        self.assertEqual(canvas.last_smiles_input, "after")

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

    def test_restore_document_items_require_scene_item_controller(self) -> None:
        canvas = _Canvas()
        state = {
            "ring_fills": [{"points": [(0.0, 0.0)]}],
            "notes": [{"text": "note", "x": 1.0, "y": 2.0}],
            "marks": [{"kind": "plus", "text": "+", "atom_id": None, "dx": None, "dy": None, "x": 4.0, "y": 5.0}],
            "arrows": [{"kind": "equilibrium"}],
            "ts_brackets": [{"kind": "ts_bracket", "rect": (0.0, 0.0, 2.0, 2.0)}],
            "orbitals": [{"center": (3.0, 4.0)}],
        }

        with self.assertRaises(AttributeError):
            restore_document_pre_model_items(canvas, state)


if __name__ == "__main__":
    unittest.main()
