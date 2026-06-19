import math
import unittest

from core.document_state import (
    CHEMVAS_FILE_TYPE,
    SINGLE_SHEET_FILE_VERSION,
    WORKBOOK_FILE_VERSION,
    atom_to_state,
    bond_to_state,
    build_document_payload,
    deserialize_model_state,
    extract_document_state,
    serialize_model_state,
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


def _single_sheet_state(model: dict | None = None) -> dict:
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
        self.assertEqual(state["bonds"][0]["a"], 0)
        self.assertIsNone(state["bonds"][1])
        self.assertEqual(state["next_atom_id"], 3)

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
            }
        )

        self.assertEqual(model.next_atom_id, 7)
        self.assertEqual(model.atoms[0].element, "C")
        self.assertEqual(model.atoms[2].color, "#ff0000")
        self.assertTrue(model.atoms[2].explicit_label)
        self.assertEqual(model.bonds[0].order, 3)
        self.assertEqual(model.bonds[0].style, "triple")
        self.assertIsNone(model.bonds[1])

    def test_deserialize_model_state_uses_serialized_next_atom_id(self) -> None:
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

        self.assertEqual(model.next_atom_id, 4)
        self.assertEqual(model.add_atom("N", 0.0, 0.0), 4)
        self.assertIn(7, model.atoms)
        self.assertIn(4, model.atoms)

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
        state = _single_sheet_state()
        state["settings"] = settings
        payload = build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

        self.assertEqual(payload["type"], CHEMVAS_FILE_TYPE)
        self.assertEqual(payload["version"], SINGLE_SHEET_FILE_VERSION)
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
        state = _single_sheet_state()
        state["settings"] = settings
        build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

    def test_settings_with_legacy_style_preset_still_valid(self) -> None:
        # Files written while journal presets existed may carry this key.
        settings = _settings()
        settings["style_preset"] = "Presentation"
        state = _single_sheet_state()
        state["settings"] = settings
        build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

    def test_settings_reject_non_string_style_preset(self) -> None:
        settings = _settings()
        settings["style_preset"] = 123
        state = _single_sheet_state()
        state["settings"] = settings
        with self.assertRaises(ValueError):
            build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

    def test_build_document_payload_accepts_valid_nested_scene_items(self) -> None:
        state = _single_sheet_state(
            _model_state(
                atoms={"0": _atom_state()},
                next_atom_id=1,
            )
        )
        state["ring_fills"] = [{"points": [(0.0, 0.0), (1.0, 0.0)], "atom_ids": [0], "color": "#abcdef", "alpha": 0.25}]
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

        build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

    def test_build_document_payload_accepts_legacy_ts_bracket_rect_state(self) -> None:
        state = _single_sheet_state()
        state["ts_brackets"] = [{"kind": "ts_bracket", "rect": (0.0, 0.0, 12.0, 8.0)}]

        build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

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
                state = _single_sheet_state()
                state[key] = value
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

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
                state = _single_sheet_state(_model_state(atoms={"0": _atom_state()}, next_atom_id=1))
                state[key] = value
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=SINGLE_SHEET_FILE_VERSION)

    def test_build_workbook_payload_rejects_malformed_nested_scene_items(self) -> None:
        content = _single_sheet_state(_model_state(atoms={"0": _atom_state()}, next_atom_id=1))
        content["marks"] = [{}]
        workbook_state = {
            "active_sheet_index": 0,
            "sheets": [{"name": "Sheet 1", "kind": "canvas", "content": content}],
        }

        with self.assertRaises(ValueError):
            build_document_payload(workbook_state, version=WORKBOOK_FILE_VERSION)

    def test_extract_document_state_accepts_workbook_state(self) -> None:
        sheet_state = _single_sheet_state()
        workbook_state = {
            "active_sheet_index": 0,
            "sheets": [
                {
                    "name": "Sheet 1",
                    "kind": "canvas",
                    "content": sheet_state,
                }
            ],
        }
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": WORKBOOK_FILE_VERSION,
            "state": workbook_state,
        }

        self.assertIs(extract_document_state(payload), workbook_state)

    def test_extract_document_state_rejects_legacy_wrapped_file_type(self) -> None:
        state = _single_sheet_state()
        payload = {
            "type": "litedraw",
            "version": SINGLE_SHEET_FILE_VERSION,
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
                    build_document_payload(_single_sheet_state(model), version=SINGLE_SHEET_FILE_VERSION)

    def test_extract_document_state_rejects_invalid_workbook_schema(self) -> None:
        valid_content = _single_sheet_state()
        invalid_states = [
            {"active_sheet_index": 2, "sheets": [{"kind": "canvas", "content": valid_content}]},
            {"active_sheet_index": 0, "sheets": ["not-a-sheet"]},
            {"active_sheet_index": 0, "sheets": [{"kind": "canvas", "content": {}}]},
            {"active_sheet_index": 0, "sheets": []},
            {"active_sheet_index": 0, "sheets": [{"name": "Result", "kind": "result", "content": valid_content}]},
            {
                "active_sheet_index": 0,
                "sheets": [{"name": "Sheet 1", "kind": "canvas", "content": valid_content}],
                "result_sheets": {"sheets": [], "active_index": 0},
            },
        ]

        for state in invalid_states:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    build_document_payload(state, version=WORKBOOK_FILE_VERSION)

    def test_build_document_payload_rejects_unsupported_or_mismatched_versions(self) -> None:
        single_sheet_state = _single_sheet_state()
        workbook_state = {
            "active_sheet_index": 0,
            "sheets": [{"name": "Sheet 1", "kind": "canvas", "content": single_sheet_state}],
        }

        with self.assertRaises(ValueError):
            build_document_payload(single_sheet_state, version=3)
        with self.assertRaises(ValueError):
            build_document_payload(workbook_state, version=SINGLE_SHEET_FILE_VERSION)
        with self.assertRaises(ValueError):
            build_document_payload(single_sheet_state, version=WORKBOOK_FILE_VERSION)

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
                    "version": SINGLE_SHEET_FILE_VERSION,
                    "state": _single_sheet_state(),
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": "1",
                    "state": _single_sheet_state(),
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": SINGLE_SHEET_FILE_VERSION,
                    "state": {"active_sheet_index": 0, "sheets": []},
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
                    "version": SINGLE_SHEET_FILE_VERSION,
                }
            )
        with self.assertRaises(ValueError):
            extract_document_state(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": SINGLE_SHEET_FILE_VERSION,
                    "state": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
