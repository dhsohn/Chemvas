import math
import unittest

from core.document_state import (
    CANVAS_FILE_VERSION,
    CHEMVAS_FILE_TYPE,
    GROUPS_CANVAS_FILE_VERSION,
    LEGACY_CANVAS_FILE_VERSION,
    atom_to_state,
    bond_to_state,
    build_document_payload,
    deserialize_model_state,
    extract_document_state,
    selection_payload_to_canvas_state,
    serialize_model_state,
    serialize_model_state_with_warnings,
    serialize_settings,
)
from core.model import Atom, Bond, MoleculeModel


def _settings() -> dict:
    return serialize_settings(
        bond_length_px=18.0,
        arrow_line_width=1.5,
        arrow_head_scale=0.4,
        orbital_phase_enabled=True,
        text_font_size=13,
        text_font_weight=600,
        text_italic=False,
        sheet_size="A4",
        sheet_orientation="portrait",
    )


def _model_state(
    atoms: dict | None = None,
    bonds: list | None = None,
    next_atom_id: int = 0,
) -> dict:
    return {
        "atoms": atoms or {},
        "bonds": bonds or [],
        "next_atom_id": next_atom_id,
    }


def _canvas_state(model: dict | None = None) -> dict:
    return {
        "model": model or _model_state(),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }


def _atom_state() -> dict:
    return {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False}


class DocumentStateTest(unittest.TestCase):
    def test_atom_and_bond_state_helpers_preserve_fields(self) -> None:
        atom = Atom("N", 1.5, -2.0, color="#112233", explicit_label=False)
        bond = Bond(1, 2, order=2, style="double", color="#445566")

        self.assertEqual(
            atom_to_state(atom, explicit_label=True),
            {
                "element": "N",
                "x": 1.5,
                "y": -2.0,
                "color": "#112233",
                "explicit_label": True,
            },
        )
        self.assertEqual(
            bond_to_state(bond),
            {
                "a": 1,
                "b": 2,
                "order": 2,
                "style": "double",
                "color": "#445566",
            },
        )
        self.assertIsNone(bond_to_state(None))

    def test_serialize_model_state_marks_visible_carbon_labels_explicit(self) -> None:
        model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0, explicit_label=False),
                1: Atom("O", 2.0, 0.0, explicit_label=True),
            },
            bonds=[Bond(0, 1, 1), None],
        )
        model.next_atom_id = 3

        state = serialize_model_state(model, explicit_label_atom_ids={0})

        self.assertTrue(state["atoms"][0]["explicit_label"])
        self.assertTrue(state["atoms"][1]["explicit_label"])
        # v4 serialization is compact: the in-memory tombstone slot is dropped.
        self.assertEqual([bond["a"] for bond in state["bonds"]], [0])
        self.assertEqual(state["next_atom_id"], 3)

    def test_serialize_model_state_round_trips_atom_annotations(self) -> None:
        model = MoleculeModel(
            atoms={
                0: Atom("N", 0.0, 0.0),
                1: Atom("C", 2.0, 0.0),
            },
            bonds=[Bond(0, 1, 1)],
        )
        model.atom_annotations = {
            0: {"formal_charge": 1, "radical_electrons": 1},
            1: {"radical_electrons": 0},
            99: {"formal_charge": -1},
        }

        state = serialize_model_state(model)
        restored = deserialize_model_state(state)

        self.assertEqual(state["atom_annotations"], {0: {"formal_charge": 1, "radical_electrons": 1}})
        self.assertEqual(restored.atom_annotations, {0: {"formal_charge": 1, "radical_electrons": 1}})

    def test_bold_double_positions_round_trip_through_document_payload(self) -> None:
        model = MoleculeModel(
            atoms={
                0: Atom("C", 0.0, 0.0),
                1: Atom("C", 10.0, 0.0),
                2: Atom("C", 20.0, 0.0),
                3: Atom("C", 30.0, 0.0),
            },
            bonds=[
                Bond(0, 1, 2, style="bold_in"),
                Bond(1, 2, 2, style="bold_center"),
                Bond(2, 3, 2, style="bold_out"),
            ],
        )

        state = serialize_model_state(model)
        payload = build_document_payload(_canvas_state(state), version=CANVAS_FILE_VERSION)
        restored = deserialize_model_state(payload["state"]["model"])

        self.assertEqual(
            [bond.style for bond in restored.bonds if bond is not None],
            ["bold_in", "bold_center", "bold_out"],
        )

    def test_serialize_model_state_with_warnings_reports_repairs(self) -> None:
        model = MoleculeModel(
            atoms={
                0: Atom("", math.nan, 0.0, color="red"),
                1: Atom("O", 20.0, 0.0),
            },
            bonds=[
                Bond(0, 1, 4, "bogus", "blue"),
                Bond(0, 99, 1),
                Bond(1, 1, 1),
                Bond(1, 0, 1),
            ],
        )
        model.atom_annotations = {
            1: {"formal_charge": 0, "radical_electrons": 0},
            88: {"formal_charge": 0},
            99: {"formal_charge": 1},
        }

        state, warnings = serialize_model_state_with_warnings(model)

        self.assertEqual(state["atoms"][0]["element"], "C")
        self.assertEqual(state["atoms"][0]["x"], 0.0)
        self.assertEqual(state["atoms"][0]["color"], "#000000")
        self.assertEqual(state["bonds"], [{"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"}])
        self.assertNotIn("atom_annotations", state)
        self.assertIn("1 atom label was replaced with carbon.", warnings)
        self.assertIn("1 atom position was reset to a finite coordinate.", warnings)
        self.assertIn("1 atom color was reset to black.", warnings)
        self.assertIn("2 invalid bonds were omitted.", warnings)
        self.assertIn("1 duplicate bond was omitted.", warnings)
        self.assertIn("1 bond order was reset.", warnings)
        self.assertIn("1 bond style was reset.", warnings)
        self.assertIn("1 bond color was reset to black.", warnings)
        self.assertIn("1 stale atom annotation was omitted.", warnings)
        self.assertEqual(warnings.count("1 stale atom annotation was omitted."), 1)

    def test_deserialize_model_state_rebuilds_model(self) -> None:
        model = deserialize_model_state(
            {
                "atoms": {
                    "0": {"element": "C", "x": 1.0, "y": 2.0, "color": "#000000", "explicit_label": False},
                    "2": {
                        "element": "N",
                        "x": -1.0,
                        "y": 0.5,
                        "color": "#ff0000",
                        "explicit_label": True,
                    },
                },
                "bonds": [
                    {"a": 0, "b": 2, "order": 3, "style": "triple", "color": "#123456"},
                    None,
                ],
                "next_atom_id": 7,
                "atom_annotations": {"2": {"formal_charge": -1}},
            }
        )

        self.assertEqual(model.next_atom_id, 7)
        self.assertEqual(model.atoms[0].element, "C")
        self.assertEqual(model.atoms[2].color, "#ff0000")
        self.assertTrue(model.atoms[2].explicit_label)
        self.assertEqual(model.bonds[0].order, 3)
        self.assertEqual(model.bonds[0].style, "triple")
        self.assertIsNone(model.bonds[1])
        self.assertEqual(model.atom_annotations, {2: {"formal_charge": -1}})

    def test_deserialize_model_state_clamps_low_next_atom_id(self) -> None:
        model = deserialize_model_state(
            {
                "atoms": {
                    "3": {"element": "C", "x": 1.0, "y": 2.0, "color": "#000000", "explicit_label": False},
                    "7": {"element": "O", "x": -1.0, "y": 0.5, "color": "#ff0000", "explicit_label": True},
                },
                "bonds": [],
                "next_atom_id": 4,
            }
        )

        self.assertEqual(model.next_atom_id, 8)
        self.assertEqual(model.add_atom("N", 0.0, 0.0), 8)
        self.assertIn(7, model.atoms)
        self.assertIn(8, model.atoms)

    def test_deserialize_model_state_requires_complete_model_payload(self) -> None:
        with self.assertRaises(KeyError):
            deserialize_model_state({"atoms": {}, "bonds": []})
        with self.assertRaises(KeyError):
            deserialize_model_state({"atoms": {"1": {"x": 1.5}}, "bonds": [], "next_atom_id": 2})
        with self.assertRaises(TypeError):
            deserialize_model_state({"atoms": {}, "bonds": ["bad-entry"], "next_atom_id": 2})

    def test_settings_and_payload_helpers_round_trip(self) -> None:
        settings = serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        )
        state = _canvas_state()
        state["settings"] = settings
        payload = build_document_payload(state, version=CANVAS_FILE_VERSION)

        self.assertEqual(payload["type"], CHEMVAS_FILE_TYPE)
        self.assertEqual(payload["version"], CANVAS_FILE_VERSION)
        self.assertIs(extract_document_state(payload), state)

    def test_settings_serialize_omits_legacy_style_preset(self) -> None:
        settings = serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.3,
            orbital_phase_enabled=False,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        )
        self.assertNotIn("style_preset", settings)
        state = _canvas_state()
        state["settings"] = settings
        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_accepts_legacy_settings_without_text_note_keys(self) -> None:
        settings = _settings()
        for key in (
            "text_font_family",
            "text_color",
            "text_alignment",
            "text_line_spacing",
            "note_box_enabled",
            "note_box_color",
            "note_box_alpha",
            "note_border_enabled",
            "note_border_color",
            "note_border_width",
            "note_padding",
        ):
            settings.pop(key)
        state = _canvas_state()
        state["settings"] = settings

        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_accepts_legacy_v1_canvas_state(self) -> None:
        build_document_payload(_canvas_state(), version=LEGACY_CANVAS_FILE_VERSION)

    def test_document_payload_accepts_optional_perspective_state(self) -> None:
        state = _canvas_state(
            _model_state(
                atoms={0: _atom_state()},
                next_atom_id=1,
            )
        )
        state["perspective"] = {
            "atom_coords_3d": {"0": [1.0, 2.0, 3.0]},
            "projection_center_3d": [4.0, 5.0, 6.0],
            "projection_anchor_2d": [7.0, 8.0],
        }

        build_document_payload(state, version=CANVAS_FILE_VERSION)

        with self.assertRaises(ValueError):
            build_document_payload(state, version=LEGACY_CANVAS_FILE_VERSION)

    def test_document_payload_rejects_duplicate_bond_pairs(self) -> None:
        atoms = {
            0: _atom_state(),
            1: {**_atom_state(), "x": 1.0},
        }
        state = _canvas_state(
            _model_state(
                atoms=atoms,
                bonds=[
                    {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                    {"a": 1, "b": 0, "order": 2, "style": "double", "color": "#000000"},
                ],
                next_atom_id=2,
            )
        )

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_degenerate_ring_fill_points(self) -> None:
        atoms = {
            0: _atom_state(),
            1: {**_atom_state(), "x": 1.0},
            2: {**_atom_state(), "x": 0.5, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(0.0, 0.0), (1.0, 0.0)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_degenerate_ring_fill_atom_cycle(self) -> None:
        atoms = {
            0: _atom_state(),
            1: {**_atom_state(), "x": 1.0},
            2: {**_atom_state(), "x": 0.5, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]

        cases = [
            ("null", None, bonds),
            ("empty", [], bonds),
            ("short", [0, 1], bonds),
            ("duplicate", [0, 1, 0], bonds),
            ("missing closing bond", [0, 1, 2], bonds[:2]),
        ]
        for name, atom_ids, case_bonds in cases:
            with self.subTest(name=name):
                state = _canvas_state(_model_state(atoms=atoms, bonds=case_bonds, next_atom_id=3))
                state["ring_fills"] = [
                    {
                        "points": [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
                        "atom_ids": atom_ids,
                        "color": "#000000",
                        "alpha": 0.4,
                    }
                ]
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_ring_fill_point_atom_count_mismatch(self) -> None:
        atoms = {
            0: _atom_state(),
            1: {**_atom_state(), "x": 1.0},
            2: {**_atom_state(), "x": 0.5, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0), (0.0, 0.5)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_large_coordinate_ring_point_mismatch(self) -> None:
        atoms = {
            0: {**_atom_state(), "x": 1_000_000_000.0},
            1: {**_atom_state(), "x": 1_000_000_001.0},
            2: {**_atom_state(), "x": 1_000_000_000.5, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(1_000_000_000.5, 0.0), (1_000_000_001.0, 0.0), (1_000_000_000.5, 1.0)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_huge_integer_ring_point_mismatch(self) -> None:
        huge = 10**20
        atoms = {
            0: {**_atom_state(), "x": huge},
            1: {**_atom_state(), "x": huge + 1},
            2: {**_atom_state(), "x": huge, "y": 1},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(huge + 1000, 0), (huge + 1, 0), (huge, 1)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_unrepresentable_integer_coordinates(self) -> None:
        huge = 10**20 + 1
        atoms = {
            0: {**_atom_state(), "x": huge},
            1: {**_atom_state(), "x": huge + 1000},
            2: {**_atom_state(), "x": huge, "y": 1},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(huge, 0), (huge + 1000, 0), (huge, 1)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_unsafe_float_coordinates(self) -> None:
        huge = 1e20
        atoms = {
            0: {**_atom_state(), "x": huge},
            1: {**_atom_state(), "x": huge + 1.0},
            2: {**_atom_state(), "x": huge, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
        state["ring_fills"] = [
            {
                "points": [(huge, 0.0), (huge + 1.0, 0.0), (huge, 1.0)],
                "atom_ids": [0, 1, 2],
                "color": "#000000",
                "alpha": 0.4,
            }
        ]

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_out_of_range_scene_alpha(self) -> None:
        atoms = {
            0: _atom_state(),
            1: {**_atom_state(), "x": 1.0},
            2: {**_atom_state(), "x": 0.5, "y": 1.0},
        }
        bonds = [
            {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
            {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
        ]
        cases = [
            (
                "ring_fills",
                [
                    {
                        "points": [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
                        "atom_ids": [0, 1, 2],
                        "color": "#000000",
                        "alpha": 1.1,
                    }
                ],
            ),
            (
                "shapes",
                [
                    {
                        "kind": "shape",
                        "left": 0.0,
                        "top": 0.0,
                        "right": 1.0,
                        "bottom": 1.0,
                        "shape_kind": "rect",
                        "stroke_style": "solid",
                        "fill": "#000000",
                        "fill_alpha": -0.1,
                    }
                ],
            ),
        ]
        for key, value in cases:
            with self.subTest(key=key):
                state = _canvas_state(_model_state(atoms=atoms, bonds=bonds, next_atom_id=3))
                state[key] = value
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_document_payload_rejects_invalid_optional_perspective_state(self) -> None:
        state = _canvas_state(
            _model_state(
                atoms={0: _atom_state()},
                next_atom_id=1,
            )
        )
        invalid_states = [
            {"perspective": {"atom_coords_3d": {"99": [1.0, 2.0, 3.0]}, "projection_center_3d": None, "projection_anchor_2d": None}},
            {"perspective": {"atom_coords_3d": {"0": [1.0, 2.0]}, "projection_center_3d": None, "projection_anchor_2d": None}},
            {"perspective": {"atom_coords_3d": {"0": [1.0, 2.0, 3.0]}, "projection_center_3d": [1.0, 2.0], "projection_anchor_2d": None}},
            {"perspective": {"atom_coords_3d": {"0": [1.0, 2.0, 3.0]}, "projection_center_3d": None, "projection_anchor_2d": [1.0, 2.0, 3.0]}},
            {"perspective": {"atom_coords_3d": {"0": [1.0, 2.0, 3.0]}, "projection_center_3d": [1.0, math.inf, 3.0], "projection_anchor_2d": None}},
            {"perspective": {"atom_coords_3d": {"0": [1.0, 2.0, 3.0]}}},
        ]
        for invalid_state in invalid_states:
            with self.subTest(invalid_state=invalid_state):
                candidate = dict(state)
                candidate.update(invalid_state)
                with self.assertRaises(ValueError):
                    build_document_payload(candidate, version=CANVAS_FILE_VERSION)

    def test_settings_reject_extra_style_preset_key(self) -> None:
        settings = _settings()
        settings["style_preset"] = "Presentation"
        state = _canvas_state()
        state["settings"] = settings
        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_settings_reject_out_of_domain_values(self) -> None:
        cases = [
            ("bond_length_px", 0.0),
            ("arrow_line_width", 0.49),
            ("arrow_head_scale", 0.09),
            ("arrow_head_scale", 0.81),
            ("text_font_size", 5),
            ("text_font_weight", -1),
            ("text_font_weight", 0),
            ("text_font_weight", 1001),
            ("text_line_spacing", 0.79),
            ("note_box_alpha", -0.1),
            ("note_box_alpha", 1.1),
            ("note_border_width", 0.49),
            ("note_padding", 1.99),
            ("sheet_size", "Letter"),
            ("sheet_orientation", "vertical"),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                settings = _settings()
                settings[key] = value
                state = _canvas_state()
                state["settings"] = settings
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_selection_payload_to_canvas_state_maps_supported_items(self) -> None:
        settings = _settings()
        selection_payload = {
            "format": "chemvas-selection",
            "version": 1,
            "atoms": [
                {"id": 3, "element": "C", "x": 10.0, "y": 20.0, "color": "#111111", "explicit_label": True},
                {
                    "id": 7,
                    "element": "O",
                    "x": 30.0,
                    "y": 40.0,
                    "color": "#222222",
                    "explicit_label": False,
                    "annotation": {"formal_charge": -1},
                },
                {"id": 9, "element": "C", "x": 20.0, "y": 55.0, "color": "#111111", "explicit_label": False},
            ],
            "bonds": [
                {"a": 3, "b": 7, "order": 2, "style": "double", "color": "#333333"},
                {"a": 7, "b": 9, "order": 1, "style": "single", "color": "#333333"},
                {"a": 9, "b": 3, "order": 1, "style": "single", "color": "#333333"},
            ],
            "rings": [
                {
                    "kind": "ring",
                    "points": [(10.0, 20.0), (30.0, 40.0), (20.0, 55.0)],
                    "atom_ids": [3, 7, 9],
                    "color": "#abcdef",
                    "alpha": 0.2,
                }
            ],
            "marks": [
                {
                    "kind": "mark",
                    "mark_kind": None,
                    "text": "+",
                    "atom_id": 3,
                    "dx": 1.0,
                    "dy": 2.0,
                    "x": 11.0,
                    "y": 22.0,
                }
            ],
            "scene_items": [
                {"kind": "note", "text": "selected", "html": "<p><b>selected</b></p>", "x": 5.0, "y": 6.0},
                {"kind": "arrow", "start": (1.0, 2.0), "end": (3.0, 4.0), "control": None, "double": False},
                {"kind": "ts_bracket", "left": 1.0, "top": 2.0, "right": 3.0, "bottom": 4.0},
                {"kind": "orbital", "orbital_kind": "p", "center": (8.0, 9.0), "scale": 1.2, "rotation": 30.0},
            ],
        }

        state = selection_payload_to_canvas_state(selection_payload, settings)

        self.assertEqual(set(state["model"]["atoms"]), {3, 7, 9})
        self.assertEqual(state["model"]["atoms"][3]["element"], "C")
        self.assertEqual(state["model"]["atom_annotations"], {7: {"formal_charge": -1}})
        self.assertEqual(state["model"]["bonds"], selection_payload["bonds"])
        self.assertEqual(state["model"]["next_atom_id"], 10)
        self.assertEqual(state["ring_fills"][0]["atom_ids"], [3, 7, 9])
        self.assertEqual(state["marks"][0]["kind"], "plus")
        self.assertEqual(state["notes"][0]["text"], "selected")
        self.assertEqual(state["notes"][0]["html"], "<p><b>selected</b></p>")
        self.assertEqual(state["arrows"][0]["kind"], "arrow")
        self.assertEqual(state["ts_brackets"][0]["kind"], "ts_bracket")
        self.assertEqual(state["orbitals"][0]["kind"], "p")
        self.assertEqual(state["settings"], settings)
        self.assertIsNone(state["last_smiles_input"])
        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_selection_payload_to_canvas_state_maps_v2_perspective_state(self) -> None:
        settings = _settings()
        selection_payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 3, "element": "C", "x": 10.0, "y": 20.0, "color": "#111111", "explicit_label": True},
                {"id": 7, "element": "O", "x": 30.0, "y": 40.0, "color": "#222222", "explicit_label": False},
            ],
            "bonds": [{"a": 3, "b": 7, "order": 1, "style": "single", "color": "#333333"}],
            "rings": [],
            "marks": [],
            "scene_items": [],
            "perspective": {
                "atom_coords_3d": [
                    {"atom_id": 3, "coords": [10.0, 20.0, 5.0]},
                    {"atom_id": 7, "coords": [30.0, 40.0, -3.0]},
                ],
                "projection_center_3d": [20.0, 30.0, 1.0],
                "projection_anchor_2d": [21.0, 31.0],
            },
        }

        state = selection_payload_to_canvas_state(selection_payload, settings)

        self.assertEqual(
            state["perspective"],
            {
                "atom_coords_3d": {3: (10.0, 20.0, 5.0), 7: (30.0, 40.0, -3.0)},
                "projection_center_3d": (20.0, 30.0, 1.0),
                "projection_anchor_2d": (21.0, 31.0),
            },
        )
        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_build_document_payload_rejects_wedge_hash_on_non_single_bonds(self) -> None:
        state = _canvas_state(
            _model_state(
                atoms={"0": _atom_state(), "1": _atom_state()},
                bonds=[{"a": 0, "b": 1, "order": 2, "style": "wedge", "color": "#000000"}],
                next_atom_id=2,
            )
        )

        with self.assertRaises(ValueError):
            build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_build_document_payload_validates_atom_annotations(self) -> None:
        state = _canvas_state(
            _model_state(
                atoms={"0": _atom_state()},
                next_atom_id=1,
            )
        )
        state["model"]["atom_annotations"] = {"0": {"formal_charge": -1, "radical_electrons": 1}}
        build_document_payload(state, version=CANVAS_FILE_VERSION)

        invalid_cases = [
            {"1": {"formal_charge": 1}},
            {"0": {"formal_charge": "1"}},
            {"0": {"radical_electrons": -1}},
            {"0": {"unknown": 1}},
        ]
        for atom_annotations in invalid_cases:
            with self.subTest(atom_annotations=atom_annotations):
                state = _canvas_state(
                    _model_state(
                        atoms={"0": _atom_state()},
                        next_atom_id=1,
                    )
                )
                state["model"]["atom_annotations"] = atom_annotations
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_selection_payload_rejects_wedge_hash_on_non_single_bonds(self) -> None:
        payload = {
            "atoms": [
                {"id": 0, "element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
                {"id": 1, "element": "C", "x": 1.0, "y": 0.0, "color": "#000000", "explicit_label": False},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 2, "style": "hash", "color": "#000000"}],
        }

        with self.assertRaises(ValueError):
            selection_payload_to_canvas_state(payload, _settings())

    def test_selection_payload_to_canvas_state_rejects_invalid_payload(self) -> None:
        with self.assertRaises(ValueError):
            selection_payload_to_canvas_state({"atoms": "bad"}, _settings())

    def test_build_document_payload_accepts_valid_nested_scene_items(self) -> None:
        state = _canvas_state(
            _model_state(
                atoms={
                    "0": _atom_state(),
                    "1": {**_atom_state(), "x": 1.0},
                    "2": {**_atom_state(), "x": 0.5, "y": 1.0},
                },
                bonds=[
                    {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                    {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
                    {"a": 2, "b": 0, "order": 1, "style": "single", "color": "#000000"},
                ],
                next_atom_id=3,
            )
        )
        state["ring_fills"] = [
            {
                "points": [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)],
                "atom_ids": [0, 1, 2],
                "color": "#abcdef",
                "alpha": 0.25,
            }
        ]
        state["notes"] = [{"text": "note", "x": 1.0, "y": 2.0}]
        state["marks"] = [{"kind": "plus", "text": "+", "atom_id": 0, "dx": 1.0, "dy": 0.0, "x": 1.0, "y": 0.0}]
        state["arrows"] = [{"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0), "control": None, "double": False}]
        state["ts_brackets"] = [
            {
                "kind": "ts_bracket",
                "left": 0.0,
                "top": 0.0,
                "right": 2.0,
                "bottom": 3.0,
                "bracket_kind": "double_dagger",
            }
        ]
        state["orbitals"] = [{"kind": "p", "center": (0.0, 0.0), "scale": 1.5, "rotation": 45.0}]

        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_build_document_payload_accepts_legacy_ts_bracket_rect_state(self) -> None:
        state = _canvas_state()
        state["ts_brackets"] = [{"kind": "ts_bracket", "rect": (0.0, 0.0, 12.0, 8.0)}]

        build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_build_document_payload_rejects_unsupported_mark_and_orbital_kinds(self) -> None:
        cases = [
            (
                "marks",
                [
                    {
                        "kind": "unknown",
                        "text": "?",
                        "atom_id": None,
                        "dx": None,
                        "dy": None,
                        "x": 0.0,
                        "y": 0.0,
                    }
                ],
            ),
            ("orbitals", [{"kind": "f", "center": (0.0, 0.0), "scale": 1.0, "rotation": 0.0}]),
        ]

        for key, value in cases:
            with self.subTest(key=key):
                state = _canvas_state()
                state[key] = value
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_build_document_payload_rejects_malformed_nested_scene_items(self) -> None:
        cases = [
            ("ring_fills", [{}]),
            ("ring_fills", [{"points": [(0.0, 0.0)], "atom_ids": [99], "color": "#abcdef", "alpha": 0.25}]),
            ("ring_fills", [{"points": [(0.0, 0.0)], "atom_ids": [], "color": "red", "alpha": 0.25}]),
            ("notes", [{"text": "note", "x": 0.0, "y": math.inf}]),
            ("marks", [{}]),
            ("marks", [{"kind": "plus", "text": "+", "atom_id": 99, "dx": 1.0, "dy": 0.0, "x": 1.0, "y": 0.0}]),
            ("arrows", [{"kind": "unexpected", "start": (0.0, 0.0), "end": (1.0, 1.0)}]),
            ("arrows", [{"kind": "arrow", "start": (0.0, 0.0), "end": ("x", 1.0)}]),
            ("ts_brackets", [{"kind": "ts_bracket", "rect": (0.0, 0.0, 1.0)}]),
            (
                "ts_brackets",
                [{"kind": "ts_bracket", "left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0, "bracket_kind": "bad"}],
            ),
            ("orbitals", [{"center": (0.0, 0.0)}]),
        ]

        for key, value in cases:
            with self.subTest(key=key, value=value):
                state = _canvas_state(_model_state(atoms={"0": _atom_state()}, next_atom_id=1))
                state[key] = value
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=CANVAS_FILE_VERSION)

    def test_extract_document_state_rejects_legacy_wrapped_file_type(self) -> None:
        state = _canvas_state()
        payload = {
            "type": "litedraw",
            "version": CANVAS_FILE_VERSION,
            "state": state,
        }

        with self.assertRaises(ValueError):
            extract_document_state(payload)

    def test_extract_document_state_rejects_invalid_model_schema(self) -> None:
        valid_atoms = {"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False}}
        invalid_models = [
            _model_state(valid_atoms, [{"a": 0, "b": 9, "order": 1, "style": "single", "color": "#000000"}], 1),
            _model_state(valid_atoms, [{"a": 0, "b": 0, "order": 4, "style": "single", "color": "#000000"}], 1),
            _model_state({"0": {"element": "C", "x": float("nan"), "y": 0.0, "color": "#000000", "explicit_label": False}}, [], 1),
            _model_state({"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "red", "explicit_label": False}}, [], 1),
            _model_state(valid_atoms, [], 0),
            {"atoms": valid_atoms, "bonds": []},
            _model_state({"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000"}}, [], 1),
        ]

        for model in invalid_models:
            with self.subTest(model=model):
                with self.assertRaises(ValueError):
                    build_document_payload(_canvas_state(model), version=CANVAS_FILE_VERSION)

    def test_extract_document_state_rejects_self_bond(self) -> None:
        valid_atoms = {"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False}}
        self_bond_model = _model_state(
            valid_atoms,
            [{"a": 0, "b": 0, "order": 1, "style": "single", "color": "#000000"}],
            1,
        )
        with self.assertRaises(ValueError):
            build_document_payload(_canvas_state(self_bond_model), version=CANVAS_FILE_VERSION)

    def test_build_document_payload_rejects_unsupported_or_mismatched_versions(self) -> None:
        canvas_state = _canvas_state()

        with self.assertRaises(ValueError):
            build_document_payload(canvas_state, version=CANVAS_FILE_VERSION + 1)
        with self.assertRaises(ValueError):
            build_document_payload({"active_sheet_index": 0, "sheets": []}, version=CANVAS_FILE_VERSION)

    def test_extract_document_state_rejects_version_two_workbook_payload(self) -> None:
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": 2,
            "state": {
                "active_sheet_index": 0,
                "sheets": [{"name": "Canvas 1", "kind": "canvas", "content": _canvas_state()}],
            },
        }

        with self.assertRaises(ValueError):
            extract_document_state(payload)

    def test_extract_document_state_rejects_invalid_payloads(self) -> None:
        with self.assertRaises(ValueError):
            extract_document_state(None)
        with self.assertRaises(ValueError):
            extract_document_state({})
        with self.assertRaises(ValueError):
            extract_document_state({"state": []})
        with self.assertRaises(ValueError):
            extract_document_state({"state": {"sheets": "not-a-list"}})
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": "unexpected",
                    "version": CANVAS_FILE_VERSION,
                    "state": _canvas_state(),
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": "1",
                    "state": _canvas_state(),
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": CANVAS_FILE_VERSION,
                    "state": {"active_sheet_index": 0, "sheets": []},
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
                    "version": CANVAS_FILE_VERSION,
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": CANVAS_FILE_VERSION,
                    "state": [],
                }
            )


class UnhashableChoiceValueTest(unittest.TestCase):
    def test_document_validation_rejects_unhashable_bond_style_with_value_error(self) -> None:
        # A JSON array where a style string belongs must fail as an invalid
        # file, not escape the boundary as a TypeError.
        state = _canvas_state(
            _model_state(
                atoms={0: _atom_state(), 1: {**_atom_state(), "x": 10.0}},
                bonds=[{"a": 0, "b": 1, "order": 1, "style": ["single"], "color": "#000000"}],
                next_atom_id=2,
            )
        )

        with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
            build_document_payload(state, CANVAS_FILE_VERSION)


class CompactBondFormatTest(unittest.TestCase):
    """v4 bond lists are compact; tombstones remain readable in older files."""

    @staticmethod
    def _state_with_bond_tombstone() -> dict:
        return _canvas_state(
            _model_state(
                atoms={0: _atom_state(), 1: {**_atom_state(), "x": 10.0}},
                bonds=[
                    None,
                    {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                ],
                next_atom_id=2,
            )
        )

    def test_v4_rejects_bond_tombstones(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
            build_document_payload(self._state_with_bond_tombstone(), CANVAS_FILE_VERSION)

    def test_pre_v4_versions_accept_bond_tombstones(self) -> None:
        for version in (LEGACY_CANVAS_FILE_VERSION, GROUPS_CANVAS_FILE_VERSION):
            with self.subTest(version=version):
                payload = build_document_payload(self._state_with_bond_tombstone(), version)
                self.assertEqual(payload["version"], version)

    def test_deserialize_still_reads_pre_v4_tombstoned_bonds(self) -> None:
        model = deserialize_model_state(
            self._state_with_bond_tombstone()["model"]
        )

        self.assertEqual(len(model.bonds), 2)
        self.assertIsNone(model.bonds[0])
        self.assertEqual((model.bonds[1].a, model.bonds[1].b), (0, 1))

    def test_tombstoned_model_round_trips_to_compact_v4_state(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", 0.0, 0.0)
        b = model.add_atom("C", 10.0, 0.0)
        c = model.add_atom("C", 20.0, 0.0)
        model.add_bond(a, b, 1)
        model.add_bond(b, c, 2)
        model.bonds[0] = None  # simulate a deleted bond slot

        state = serialize_model_state(model)
        payload = build_document_payload(_canvas_state(state), CANVAS_FILE_VERSION)
        restored = deserialize_model_state(payload["state"]["model"])

        self.assertEqual(payload["version"], CANVAS_FILE_VERSION)
        self.assertEqual(len(restored.bonds), 1)
        self.assertEqual((restored.bonds[0].a, restored.bonds[0].b, restored.bonds[0].order), (b, c, 2))


class ModelInvariantTest(unittest.TestCase):
    def test_add_bond_rejects_duplicate_pair(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", 0.0, 0.0)
        b = model.add_atom("C", 10.0, 0.0)
        model.add_bond(a, b, 1)

        with self.assertRaisesRegex(ValueError, "already bonded"):
            model.add_bond(b, a, 2)


class SerializeModelStateHealingTest(unittest.TestCase):
    """Saving must survive in-memory drift instead of failing validation."""

    def test_duplicate_and_dangling_bonds_are_dropped(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", 0.0, 0.0)
        b = model.add_atom("C", 10.0, 0.0)
        model.add_bond(a, b, 1)
        model.bonds.append(Bond(b, a, 2))
        model.bonds.append(Bond(a, a, 1))
        model.bonds.append(Bond(a, 99, 1))

        state = serialize_model_state(model)

        self.assertEqual(len(state["bonds"]), 1)
        self.assertEqual((state["bonds"][0]["a"], state["bonds"][0]["b"]), (a, b))
        build_document_payload(_canvas_state(state), CANVAS_FILE_VERSION)

    def test_wedge_order_and_next_atom_id_are_normalized(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", 0.0, 0.0)
        b = model.add_atom("C", 10.0, 0.0)
        model.add_bond(a, b, 1)
        model.bonds[0].style = "wedge"
        model.bonds[0].order = 2
        model.next_atom_id = 0

        state = serialize_model_state(model)

        self.assertEqual(state["bonds"][0]["order"], 1)
        self.assertEqual(state["next_atom_id"], 2)
        build_document_payload(_canvas_state(state), CANVAS_FILE_VERSION)

    def test_non_finite_coordinates_and_bad_colors_are_normalized(self) -> None:
        model = MoleculeModel()
        a = model.add_atom("C", float("nan"), 0.0)
        model.atoms[a].color = "not-a-color"

        state = serialize_model_state(model)

        self.assertEqual(state["atoms"][a]["x"], 0.0)
        self.assertEqual(state["atoms"][a]["color"], "#000000")
        build_document_payload(_canvas_state(state), CANVAS_FILE_VERSION)


if __name__ == "__main__":
    unittest.main()
