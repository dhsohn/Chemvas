import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.document_state import (
    LITEDRAW_FILE_TYPE,
    atom_to_state,
    bond_to_state,
    build_document_payload,
    deserialize_model_state,
    extract_document_state,
    serialize_model_state,
    serialize_settings,
)
from core.model import Atom, Bond, MoleculeModel


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
                    "0": {"element": "C", "x": 1.0, "y": 2.0, "color": "#000000"},
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

    def test_settings_and_payload_helpers_round_trip(self) -> None:
        settings = serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
        )
        state = {"model": {"atoms": {}, "bonds": [], "next_atom_id": 0}, "settings": settings}
        payload = build_document_payload(state, version=4)

        self.assertEqual(payload["type"], LITEDRAW_FILE_TYPE)
        self.assertEqual(payload["version"], 4)
        self.assertIs(extract_document_state(payload), state)
        self.assertIs(extract_document_state(state), state)

    def test_extract_document_state_accepts_workbook_state(self) -> None:
        workbook_state = {
            "active_sheet_index": 0,
            "sheets": [
                {
                    "name": "Sheet 1",
                    "kind": "canvas",
                    "content": {"model": {"atoms": {}, "bonds": [], "next_atom_id": 0}},
                }
            ],
            "result_sheets": {"sheets": [], "active_index": 0},
        }
        payload = {
            "type": LITEDRAW_FILE_TYPE,
            "version": 2,
            "state": workbook_state,
        }

        self.assertIs(extract_document_state(payload), workbook_state)
        self.assertIs(extract_document_state(workbook_state), workbook_state)

    def test_extract_document_state_rejects_invalid_payloads(self) -> None:
        with self.assertRaises(ValueError):
            extract_document_state(None)
        with self.assertRaises(ValueError):
            extract_document_state({})
        with self.assertRaises(ValueError):
            extract_document_state({"state": []})
        with self.assertRaises(ValueError):
            extract_document_state({"state": {"sheets": "not-a-list"}})


if __name__ == "__main__":
    unittest.main()
