import unittest
from types import SimpleNamespace
from unittest import mock

from core.model import Atom, Bond, MoleculeModel
from ui.canvas_atom_graphics_state import set_atom_items_for
from ui.canvas_document_state import (
    apply_document_settings,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    snapshot_canvas_document_state,
)
from ui.canvas_scene_items_state import CanvasSceneItemsState
from ui.canvas_smiles_input_state import CanvasSmilesInputState, last_smiles_input_for
from ui.canvas_text_style_state import text_style_state_for
from ui.canvas_tool_settings_state import tool_settings_state_for


class _Canvas:
    def __init__(self) -> None:
        self.calls = []

    def restore_ring_from_state(self, ring_state):
        self.calls.append(("canvas_ring", dict(ring_state)))

    def restore_note_from_state(self, note_state):
        self.calls.append(("canvas_note", dict(note_state)))

    def restore_mark_from_state(self, mark_state):
        self.calls.append(("canvas_mark", dict(mark_state)))

    def restore_arrow_from_state(self, arrow_state):
        self.calls.append(("canvas_arrow", dict(arrow_state)))

    def restore_ts_bracket_from_state(self, ts_bracket_state):
        self.calls.append(("canvas_ts", dict(ts_bracket_state)))

    def restore_orbital_from_state(self, orbital_state):
        self.calls.append(("canvas_orbital", dict(orbital_state)))


class _Controller:
    def __init__(self, canvas: _Canvas) -> None:
        self.canvas = canvas

    def restore_ring_from_state(self, ring_state):
        self.canvas.calls.append(("controller_ring", dict(ring_state)))

    def restore_note_from_state(self, note_state):
        self.canvas.calls.append(("controller_note", dict(note_state)))

    def restore_mark_from_state(self, mark_state):
        self.canvas.calls.append(("controller_mark", dict(mark_state)))

    def restore_arrow_from_state(self, arrow_state):
        self.canvas.calls.append(("controller_arrow", dict(arrow_state)))

    def restore_ts_bracket_from_state(self, ts_bracket_state):
        self.canvas.calls.append(("controller_ts", dict(ts_bracket_state)))

    def restore_orbital_from_state(self, orbital_state):
        self.canvas.calls.append(("controller_orbital", dict(orbital_state)))


class _SceneItem:
    def __init__(self, scene_obj, state: dict | None = None) -> None:
        self._scene = scene_obj
        self._state = dict(state or {})

    def scene(self):
        return self._scene

    def data(self, key: int):
        if key == 9:
            return dict(self._state)
        return None


class _DisposedSceneItem:
    def scene(self):
        raise RuntimeError("disposed")


class CanvasDocumentStateTest(unittest.TestCase):
    def test_snapshot_canvas_document_state_skips_detached_disposed_and_empty_arrow_state(self) -> None:
        scene_obj = object()
        ring_item = _SceneItem(
            scene_obj,
            {"points": [(0.0, 0.0)], "atom_ids": [1], "color": "#abcdef", "alpha": 0.25},
        )
        note_item = _SceneItem(scene_obj, {"text": "note", "x": 1.0, "y": 2.0})
        mark_item = _SceneItem(
            scene_obj,
            {
                "mark_kind": "plus",
                "text": "+",
                "atom_id": 1,
                "dx": 0.5,
                "dy": -0.5,
                "x": 3.0,
                "y": 4.0,
            },
        )
        empty_arrow_item = _SceneItem(scene_obj, {})
        ts_item = _SceneItem(scene_obj, {"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0, 1.0)})
        orbital_item = _SceneItem(
            scene_obj,
            {"orbital_kind": "p", "center": (2.0, 3.0), "scale": 2.0, "rotation": 45.0},
        )
        detached = _SceneItem(object(), {"points": [(9.0, 9.0)]})
        disposed = _DisposedSceneItem()

        canvas = SimpleNamespace(
            model=MoleculeModel(atoms={1: Atom("C", 0.0, 0.0)}, bonds=[Bond(1, 1, 1)]),
            scene_items_state=CanvasSceneItemsState(
                ring_items=[ring_item, detached, disposed],
                note_items=[note_item, detached],
                mark_items=[mark_item],
                arrow_items=[empty_arrow_item, detached],
                ts_bracket_items=[ts_item],
                orbital_items=[orbital_item],
            ),
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
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="CCO"),
            scene=lambda: scene_obj,
        )
        set_atom_items_for(canvas, {1: object()})

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
        self.assertNotIn("style_preset", state["settings"])
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
            setSceneRect=mock.Mock(),
            viewport=lambda: SimpleNamespace(update=mock.Mock()),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="before"),
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
                    "sheet_size": "A4",
                    "sheet_orientation": "portrait",
                },
                "last_smiles_input": "after",
            },
        )

        canvas.renderer.set_bond_length.assert_called_once_with(22.0)
        self.assertEqual(canvas.sheet_size, "A4")
        self.assertEqual(canvas.sheet_orientation, "portrait")
        canvas.setSceneRect.assert_called_once()
        tool_settings = tool_settings_state_for(canvas)
        self.assertEqual(tool_settings.arrow_line_width, 1.7)
        self.assertEqual(tool_settings.arrow_head_scale, 0.5)
        self.assertTrue(tool_settings.orbital_phase_enabled)
        text_style = text_style_state_for(canvas)
        self.assertEqual(text_style.text_font_size, 14)
        self.assertEqual(text_style.text_font_weight, 500)
        self.assertTrue(text_style.text_italic)
        self.assertEqual(last_smiles_input_for(canvas), "after")

    def test_apply_document_settings_ignores_legacy_style_preset(self) -> None:
        from core.renderer import Renderer

        canvas = SimpleNamespace(
            renderer=Renderer(),
            arrow_line_width=1.0,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="landscape",
            setSceneRect=mock.Mock(),
            viewport=lambda: SimpleNamespace(update=mock.Mock()),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="x"),
        )
        settings = {
            "bond_length_px": 22.0,
            "arrow_line_width": 1.0,
            "arrow_head_scale": 0.3,
            "orbital_phase_enabled": False,
            "text_font_size": 12,
            "text_font_weight": 400,
            "text_italic": False,
            "sheet_size": "A4",
            "sheet_orientation": "portrait",
            "style_preset": "Presentation",
        }
        apply_document_settings(canvas, {"settings": settings, "last_smiles_input": "y"})

        self.assertEqual(canvas.renderer.style.font_size_pt, 12)
        self.assertEqual(canvas.renderer.style.bond_length_pt, 14.4)
        self.assertEqual(canvas.renderer.style.bond_length_px, 22.0)

    def test_restore_document_items_prefer_scene_item_controller(self) -> None:
        canvas = _Canvas()
        canvas.services = SimpleNamespace(scene_item_controller=_Controller(canvas))
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
