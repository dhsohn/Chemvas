import tempfile
import unittest
from pathlib import Path

from core.document_io import (
    ChemvasDocument,
    create_document,
    parse_document,
    read_document,
    write_document,
)
from core.document_state import (
    CHEMVAS_FILE_TYPE,
    SINGLE_SHEET_FILE_VERSION,
    WORKBOOK_FILE_VERSION,
    serialize_settings,
)


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


class DocumentIOTest(unittest.TestCase):
    def test_create_document_wraps_state_in_chemvas_payload(self) -> None:
        state = _single_sheet_state()
        state["last_smiles_input"] = "CCO"

        document = create_document(state, version=SINGLE_SHEET_FILE_VERSION)

        self.assertIsInstance(document, ChemvasDocument)
        self.assertEqual(
            document.payload,
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": SINGLE_SHEET_FILE_VERSION,
                "state": state,
            },
        )
        self.assertIs(document.state, state)

    def test_parse_document_accepts_wrapped_payloads(self) -> None:
        state = _single_sheet_state()
        workbook_state = {
            "active_sheet_index": 0,
            "sheets": [
                {
                    "name": "Sheet 1",
                    "kind": "canvas",
                    "content": state,
                }
            ],
        }
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": SINGLE_SHEET_FILE_VERSION,
            "state": state,
        }
        workbook_payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": WORKBOOK_FILE_VERSION,
            "state": workbook_state,
        }

        wrapped = parse_document(payload)
        workbook = parse_document(workbook_payload)

        self.assertIs(wrapped.payload, payload)
        self.assertIs(wrapped.state, state)
        self.assertIs(workbook.state, workbook_state)

    def test_parse_document_rejects_invalid_state_like_document_state(self) -> None:
        with self.assertRaises(ValueError):
            parse_document(None)
        with self.assertRaises(ValueError):
            parse_document({})
        with self.assertRaises(ValueError):
            parse_document({"type": CHEMVAS_FILE_TYPE, "version": SINGLE_SHEET_FILE_VERSION, "state": {}})
        with self.assertRaises(ValueError):
            parse_document(
                {
                    "type": "unexpected",
                    "version": SINGLE_SHEET_FILE_VERSION,
                    "state": _single_sheet_state(),
                }
            )
        with self.assertRaises(ValueError):
            parse_document(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": 3,
                    "state": _single_sheet_state(),
                }
            )
        with self.assertRaises(ValueError):
            parse_document(
                {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": SINGLE_SHEET_FILE_VERSION,
                    "state": {"active_sheet_index": 0, "sheets": []},
                }
            )
        with self.assertRaises(ValueError):
            parse_document(
                {
                    "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
                    "version": SINGLE_SHEET_FILE_VERSION,
                }
            )

    def test_create_document_rejects_unsupported_or_mismatched_versions(self) -> None:
        with self.assertRaises(ValueError):
            create_document(_single_sheet_state(), version=9)
        with self.assertRaises(ValueError):
            create_document({"active_sheet_index": 0, "sheets": []}, version=SINGLE_SHEET_FILE_VERSION)

    def test_write_and_read_document_round_trip_wrapped_payload(self) -> None:
        state = _single_sheet_state(
            _model_state(
                {"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False}},
                [],
                1,
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"

            written = write_document(path, state, version=SINGLE_SHEET_FILE_VERSION)
            loaded = read_document(path)

        self.assertEqual(
            written.payload,
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": SINGLE_SHEET_FILE_VERSION,
                "state": state,
            },
        )
        self.assertEqual(loaded.payload, written.payload)
        self.assertEqual(loaded.state, state)

    def test_write_and_read_document_round_trip_workbook_payload(self) -> None:
        state = {
            "active_sheet_index": 1,
            "sheets": [
                {
                    "name": "Sheet 1",
                    "kind": "canvas",
                    "content": _single_sheet_state(),
                },
                {
                    "name": "Sheet 2",
                    "kind": "canvas",
                    "content": _single_sheet_state(
                        _model_state(
                            {
                                "0": {
                                    "element": "O",
                                    "x": 0.0,
                                    "y": 0.0,
                                    "color": "#000000",
                                    "explicit_label": False,
                                }
                            },
                            [],
                            1,
                        )
                    ),
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workbook.chemvas"

            written = write_document(path, state, version=WORKBOOK_FILE_VERSION)
            loaded = read_document(path)

        self.assertEqual(loaded.payload, written.payload)
        self.assertEqual(loaded.state, state)


if __name__ == "__main__":
    unittest.main()
