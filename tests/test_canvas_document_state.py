import copy
import unittest
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import (
    AnnotationCollection,
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
    ts_bracket_from_state,
)
from chemvas.domain.document.notes import Note
from chemvas.domain.document.orbitals import orbital_from_state
from chemvas.features.document_composition import compose_document_state
from chemvas.features.graph import build_bond_adjacency_index
from chemvas.ui.annotations.records import (
    require_shape_record,
    require_ts_bracket_record,
)
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    set_atom_items_for,
)
from chemvas.ui.canvas.canvas_calculation_plan_state import CanvasCalculationPlanState
from chemvas.ui.canvas.canvas_document_state import (
    snapshot_canvas_document_state,
)
from chemvas.ui.canvas.canvas_group_state import CanvasGroupState
from chemvas.ui.canvas.canvas_rotation_state import CanvasRotationState
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas.canvas_smiles_input_state import (
    CanvasSmilesInputState,
)
from chemvas.ui.canvas.canvas_text_style_state import (
    CanvasTextStyleState,
)
from chemvas.ui.canvas.canvas_tool_settings_state import (
    CanvasToolSettingsState,
)
from chemvas.ui.canvas.document_scene import populate_document_scene
from chemvas.ui.canvas.sheet_setup_state import SheetSetupState
from chemvas.ui.molecule.atom_coords_access import (
    CanvasAtomCoords3DState,
    set_atom_coords_3d_for,
)
from chemvas.ui.scene.scene_render_context import SceneRenderState
from chemvas.ui.scene.scene_rendering import build_scene_render_context
from tests.mark_support import seed_mark_items
from tests.ring_support import seed_ring_items
from tests.runtime_state import canvas_runtime_state


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
    def test_snapshot_skips_disposed_unmigrated_items_and_reads_bracket_document(
        self,
    ) -> None:
        scene_obj = object()
        ring_item = _SceneItem(
            scene_obj,
            {
                "points": [(10.0, 20.0), (0.0, 0.0), (5.0, 5.0)],
                "atom_ids": [1, 2, 3],
                "color": "#abcdef",
                "alpha": 0.25,
            },
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
        ts_item = _SceneItem(
            scene_obj,
            {
                "kind": "ts_bracket",
                "left": 0.0,
                "top": 0.0,
                "right": 1.0,
                "bottom": 1.0,
                "bracket_kind": "square_pair",
            },
        )
        orbital_item = _SceneItem(
            scene_obj,
            {"orbital_kind": "p", "center": (2.0, 3.0), "scale": 2.0, "rotation": 45.0},
        )

        canvas = SimpleNamespace(
            model=MoleculeModel(
                atoms={
                    1: Atom("C", 10.0, 20.0),
                    2: Atom("C", 0.0, 0.0),
                    3: Atom("C", 5.0, 5.0),
                },
                bonds=[Bond(1, 2, 1), Bond(2, 3, 1), Bond(1, 3, 1)],
            ),
            renderer=SimpleNamespace(
                style=SimpleNamespace(bond_length_px=18.0),
                set_bond_length=mock.Mock(),
            ),
            scene=lambda: scene_obj,
            runtime_state=canvas_runtime_state(
                atom_coords_3d_state=CanvasAtomCoords3DState(),
                atom_graphics_state=CanvasAtomGraphicsState(),
                calculation_plan_state=CanvasCalculationPlanState(),
                group_state=CanvasGroupState(),
                rotation_state=CanvasRotationState(),
                note_state=AnnotationCollection(
                    records={12: Note(text="note", x=1.0, y=2.0)}, order=[12]
                ),
                ts_bracket_state=AnnotationCollection(
                    records={10: ts_bracket_from_state(ts_item.data(9))}, order=[10]
                ),
                orbital_state=AnnotationCollection(
                    records={11: orbital_from_state(orbital_item.data(9))}, order=[11]
                ),
                scene_items_state=CanvasSceneItemsState(
                    note_items={12: note_item},
                    ts_bracket_items={10: ts_item},
                    orbital_items={11: orbital_item},
                ),
                smiles_input_state=CanvasSmilesInputState(last_smiles_input="CCO"),
                sheet_setup_state=SheetSetupState(
                    size_name="A4", orientation="portrait"
                ),
                tool_settings_state=CanvasToolSettingsState(
                    arrow_line_width=1.5,
                    arrow_head_scale=0.4,
                    orbital_phase_enabled=True,
                ),
                text_style_state=CanvasTextStyleState(
                    text_font_family="Courier New",
                    text_font_size=13,
                    text_font_weight=600,
                    text_italic=False,
                    text_color=QColor("#123456"),
                    text_alignment=Qt.AlignmentFlag.AlignRight,
                    text_line_spacing=1.25,
                    note_box_enabled=True,
                    note_box_color=QColor("#abcdef"),
                    note_box_alpha=0.4,
                    note_border_enabled=True,
                    note_border_color=QColor("#654321"),
                    note_border_width=1.7,
                    note_padding=9.0,
                ),
            ),
        )
        set_atom_items_for(canvas, {1: object()})
        set_atom_coords_3d_for(
            canvas,
            {
                1: (10.0, 20.0, 30.0),
                2: (100.0, 100.0, 5.0),
                99: (90.0, 90.0, 90.0),
            },
        )
        rotation = canvas.runtime_state.rotation_state
        rotation.projection_center_3d = (10.0, 20.0, 30.0)
        rotation.projection_anchor_2d = (10.0, 20.0)

        seed_ring_items(canvas, [ring_item])
        seed_mark_items(canvas, [mark_item])
        state = snapshot_canvas_document_state(canvas)

        self.assertTrue(state["model"]["atoms"][1]["explicit_label"])
        self.assertEqual(
            state["perspective"],
            {
                "atom_coords_3d": {1: (10.0, 20.0, 30.0)},
                "projection_center_3d": (10.0, 20.0, 30.0),
                "projection_anchor_2d": (10.0, 20.0),
            },
        )
        self.assertEqual(
            state["ring_fills"],
            [
                {
                    "points": [(10.0, 20.0), (0.0, 0.0), (5.0, 5.0)],
                    "atom_ids": [1, 2, 3],
                    "color": "#abcdef",
                    "alpha": 0.25,
                }
            ],
        )
        self.assertEqual(
            state["notes"], [{"text": "note", "html": "", "x": 1.0, "y": 2.0}]
        )
        self.assertEqual(
            state["marks"],
            [
                {
                    "kind": "plus",
                    "text": "+",
                    "atom_id": 1,
                    "dx": 0.5,
                    "dy": -0.5,
                    "x": 3.0,
                    "y": 4.0,
                }
            ],
        )
        self.assertEqual(state["arrows"], [])
        self.assertEqual(
            state["ts_brackets"],
            [
                {
                    "kind": "ts_bracket",
                    "left": 0.0,
                    "top": 0.0,
                    "right": 1.0,
                    "bottom": 1.0,
                    "bracket_kind": "square_pair",
                }
            ],
        )
        self.assertEqual(
            state["orbitals"],
            [{"kind": "p", "center": (2.0, 3.0), "scale": 2.0, "rotation": 45.0}],
        )
        self.assertNotIn("style_preset", state["settings"])
        self.assertEqual(state["settings"]["text_font_family"], "Courier New")
        self.assertEqual(state["settings"]["text_color"], "#123456")
        self.assertEqual(state["settings"]["text_alignment"], "right")
        self.assertEqual(state["settings"]["text_line_spacing"], 1.25)
        self.assertTrue(state["settings"]["note_box_enabled"])
        self.assertEqual(state["settings"]["note_box_color"], "#abcdef")
        self.assertEqual(state["settings"]["note_box_alpha"], 0.4)
        self.assertTrue(state["settings"]["note_border_enabled"])
        self.assertEqual(state["settings"]["note_border_color"], "#654321")
        self.assertEqual(state["settings"]["note_border_width"], 1.7)
        self.assertEqual(state["settings"]["note_padding"], 9.0)
        self.assertEqual(state["settings"]["sheet_size"], "A4")
        self.assertEqual(state["settings"]["sheet_orientation"], "portrait")
        self.assertEqual(state["last_smiles_input"], "CCO")

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _state(self, **records):
        return compose_document_state(
            {
                "format": "chemvas-document-composition",
                "version": 1,
                "atoms": [],
                "bonds": [],
                **records,
            }
        )

    def _context(self, state):
        model = deserialize_model_state(state["model"])
        drawing = SceneRenderState()
        graph = drawing.graph_state
        graph.atom_neighbors, graph.atom_bond_ids = build_bond_adjacency_index(
            model.atoms, model.bonds
        )
        scene = QGraphicsScene()
        context = build_scene_render_context(
            scene_provider=lambda: scene,
            model_provider=lambda: model,
            renderer=Renderer(),
            state=drawing,
        )
        self.addCleanup(context.scene.clear)
        return context

    def test_materializer_applies_native_settings_and_note_typography(self):
        state = self._state(notes=[{"text": "first\nsecond", "x": 2, "y": 3}])
        state["settings"].update(
            bond_length_px=22.0,
            arrow_line_width=1.7,
            arrow_head_scale=0.5,
            orbital_phase_enabled=True,
            text_font_family="Helvetica",
            text_font_size=14,
            text_font_weight=500,
            text_italic=True,
            text_color="#445566",
            text_alignment="center",
            text_line_spacing=1.3,
            note_box_enabled=True,
            note_box_color="#ffffff",
            note_box_alpha=0.5,
            note_border_enabled=True,
            note_border_color="#111111",
            note_border_width=1.4,
            note_padding=8.0,
            sheet_size="A4",
            sheet_orientation="portrait",
        )
        context = self._context(state)
        populate_document_scene(context, state)
        self.assertEqual(context.renderer.style.bond_length_px, 22.0)
        tools = context.state.tool_settings_state
        self.assertEqual((tools.arrow_line_width, tools.arrow_head_scale), (1.7, 0.5))
        self.assertTrue(tools.orbital_phase_enabled)
        note = next(iter(context.state.scene_items_state.note_items.values()))
        self.assertEqual(note.font().family(), "Helvetica")
        self.assertEqual(note.font().pointSize(), 14)
        self.assertEqual(note.font().weight(), 500)
        self.assertTrue(note.font().italic())
        self.assertEqual(note.defaultTextColor().name(), "#445566")
        self.assertEqual(
            note.document().defaultTextOption().alignment(),
            Qt.AlignmentFlag.AlignHCenter,
        )
        self.assertEqual(note.document().begin().blockFormat().lineHeight(), 130)
        self.assertEqual((note.pos().x(), note.pos().y()), (2, 3))
        box = note.data(20)
        self.assertAlmostEqual(box.brush().color().alphaF(), 0.5, places=3)
        self.assertEqual(box.pen().color().name(), "#111111")
        self.assertEqual(box.pen().widthF(), 1.4)
        self.assertEqual(box.rect(), note.boundingRect().adjusted(-8, -8, 8, 8))
        self.assertEqual(context.state.sheet_setup_state.size_name, "A4")
        self.assertEqual(context.state.sheet_setup_state.orientation, "portrait")

    def test_materializer_requires_all_current_text_note_settings(self):
        state = self._state()
        del state["settings"]["text_font_family"]
        with self.assertRaises(KeyError):
            populate_document_scene(self._context(state), state)

    def test_materializer_normalizes_sheet_settings_like_native_open(self):
        state = self._state()
        state["settings"].update(sheet_size="A3", sheet_orientation=" PORTRAIT ")
        context = self._context(state)
        populate_document_scene(context, state)
        self.assertEqual(context.state.sheet_setup_state.size_name, "A4")
        self.assertEqual(context.state.sheet_setup_state.orientation, "portrait")

    def test_materializer_restores_projection_before_drawing(self):
        state = self._state()
        state["perspective"] = {
            "atom_coords_3d": {"3": [1, 2.5, 4]},
            "projection_center_3d": [5, 6.5, 7],
            "projection_anchor_2d": [8, 9.5],
        }
        context = self._context(state)
        populate_document_scene(context, state)
        self.assertEqual(
            context.state.atom_coords_3d_state.atom_coords_3d, {3: (1.0, 2.5, 4.0)}
        )
        rotation = context.state.rotation_state
        self.assertEqual(rotation.projection_center_3d, (5.0, 6.5, 7.0))
        self.assertEqual(rotation.projection_anchor_2d, (8.0, 9.5))

    def test_materializer_clears_missing_optional_projection(self):
        state = self._state()
        context = self._context(state)
        context.state.atom_coords_3d_state.atom_coords_3d = {3: (1.0, 2.0, 3.0)}
        rotation = context.state.rotation_state
        rotation.projection_center_3d = (4.0, 5.0, 6.0)
        rotation.projection_anchor_2d = (7.0, 8.0)
        populate_document_scene(context, state)
        self.assertEqual(context.state.atom_coords_3d_state.atom_coords_3d, {})
        self.assertIsNone(rotation.projection_center_3d)
        self.assertIsNone(rotation.projection_anchor_2d)

    def test_materializer_builds_all_annotation_kinds_without_an_editor(self):
        state = self._state(
            atoms=[{"id": 0, "element": "N", "x": 0, "y": 0}],
            notes=[{"text": "note", "x": 1.0, "y": 2.0}],
            arrows=[
                {
                    "kind": "curved_double",
                    "start": [0, 0],
                    "end": [30, 0],
                    "control": [15, 10],
                    "labels": {"above": "THF"},
                }
            ],
            ts_brackets=[
                {
                    "left": 0,
                    "top": 0,
                    "right": 12,
                    "bottom": 20,
                    "bracket_kind": "double_dagger",
                }
            ],
            shapes=[
                {
                    "left": 30,
                    "top": 0,
                    "right": 42,
                    "bottom": 20,
                    "shape_kind": "rect",
                    "stroke_style": "dashed",
                    "fill": "#123456",
                    "fill_alpha": 0.4,
                }
            ],
        )
        state["orbitals"] = [
            {"kind": "p", "center": [3, 4], "scale": 2.0, "rotation": 45.0}
        ]
        state["ring_fills"] = [{"points": [(0.0, 0.0), (30.0, 0.0), (15.0, 20.0)]}]
        state["marks"] = [
            {
                "kind": "minus",
                "text": "-",
                "atom_id": 0,
                "dx": 1.0,
                "dy": 2.0,
                "x": 1.0,
                "y": 2.0,
            }
        ]
        original = copy.deepcopy(state)
        context = self._context(state)
        original_model = copy.deepcopy(context.model)
        populate_document_scene(context, state)
        items = context.state.scene_items_state
        for collection in (
            list(items.ring_items.values()),
            list(items.note_items.values()),
            list(items.mark_items.values()),
            list(items.arrow_items.values()),
            list(items.ts_bracket_items.values()),
            list(items.shape_items.values()),
            list(items.orbital_items.values()),
        ):
            self.assertEqual(len(collection), 1)
            self.assertIs(collection[0].scene(), context.scene)
        self.assertEqual(
            context.state.mark_registry.get_for_atom(0), list(items.mark_items.values())
        )
        self.assertEqual(
            require_ts_bracket_record(
                context, items.ts_bracket_items[context.state.ts_bracket_state.order[0]]
            ).bracket_kind,
            "double_dagger",
        )
        self.assertIsNotNone(
            items.ts_bracket_items[
                context.state.ts_bracket_state.order[0]
            ].export_glyph_run()
        )
        self.assertEqual(
            require_shape_record(
                context, items.shape_items[context.state.shape_state.order[0]]
            ).fill,
            "#123456",
        )
        self.assertAlmostEqual(
            items.shape_items[context.state.shape_state.order[0]]
            .brush()
            .color()
            .alphaF(),
            0.4,
            places=3,
        )
        self.assertEqual(
            context.arrows.record(
                items.arrow_items[context.state.arrow_state.order[0]]
            ).control,
            (15, 10),
        )
        self.assertEqual(state, original)
        self.assertEqual(context.model, original_model)
        self.assertFalse(hasattr(context, "services"))
        self.assertFalse(hasattr(context.state, "smiles_input_state"))
        self.assertFalse(hasattr(context.state, "group_state"))

    def test_materializer_requires_current_shapes_key(self):
        state = self._state()
        del state["shapes"]
        with self.assertRaises(KeyError):
            populate_document_scene(self._context(state), state)
