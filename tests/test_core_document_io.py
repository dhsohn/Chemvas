import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.document_io import (
    ChemvasDocument,
    create_document,
    parse_document,
    read_document,
    write_document,
)
from core.document_state import (
    CANVAS_FILE_VERSION,
    CHEMVAS_FILE_TYPE,
    LEGACY_CANVAS_FILE_VERSION,
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


class DocumentIOTest(unittest.TestCase):
    def test_create_document_wraps_state_in_chemvas_payload(self) -> None:
        state = _canvas_state()
        state["last_smiles_input"] = "CCO"

        document = create_document(state, version=CANVAS_FILE_VERSION)

        self.assertIsInstance(document, ChemvasDocument)
        self.assertEqual(
            document.payload,
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": state,
            },
        )
        self.assertIs(document.state, state)

    def test_parse_document_accepts_single_canvas_wrapped_payload(self) -> None:
        state = _canvas_state()
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": state,
        }

        wrapped = parse_document(payload)

        self.assertIs(wrapped.payload, payload)
        self.assertIs(wrapped.state, state)

    def test_parse_document_rejects_invalid_state_like_document_state(self) -> None:
        cases = (
            None,
            {},
            {"type": CHEMVAS_FILE_TYPE, "version": CANVAS_FILE_VERSION, "state": {}},
            {"type": "unexpected", "version": CANVAS_FILE_VERSION, "state": _canvas_state()},
            {"type": CHEMVAS_FILE_TYPE, "version": 3, "state": _canvas_state()},
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": {"active_sheet_index": 0, "sheets": []},
            },
            {"model": {"atoms": {}, "bonds": [], "next_atom_id": 0}, "version": CANVAS_FILE_VERSION},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_document(payload)

    def test_legacy_v1_payloads_are_still_valid(self) -> None:
        state = _canvas_state()
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": LEGACY_CANVAS_FILE_VERSION,
            "state": state,
        }

        self.assertIs(parse_document(payload).state, state)
        self.assertIs(create_document(state, version=LEGACY_CANVAS_FILE_VERSION).state, state)

    def test_workbook_shaped_payloads_are_invalid(self) -> None:
        workbook_payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": 2,
            "state": {
                "active_sheet_index": 0,
                "sheets": [{"name": "Canvas 1", "kind": "canvas", "content": _canvas_state()}],
            },
        }

        with self.assertRaises(ValueError):
            parse_document(workbook_payload)

    def test_create_document_rejects_unsupported_or_mismatched_versions(self) -> None:
        with self.assertRaises(ValueError):
            create_document(_canvas_state(), version=9)
        with self.assertRaises(ValueError):
            create_document({"active_sheet_index": 0, "sheets": []}, version=CANVAS_FILE_VERSION)

    def test_write_and_read_document_round_trip_wrapped_payload(self) -> None:
        state = _canvas_state(
            _model_state(
                {"0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False}},
                [],
                1,
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"

            written = write_document(path, state, version=CANVAS_FILE_VERSION)
            loaded = read_document(path)

        self.assertEqual(
            written.payload,
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": state,
            },
        )
        self.assertEqual(loaded.payload, written.payload)
        self.assertEqual(loaded.state, state)

    def test_read_document_rejects_deep_json_without_leaking_recursion_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            path.write_text("[" * 20_000 + "0" + "]" * 20_000, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                read_document(path)

    def test_write_document_is_atomic_and_preserves_file_on_failure(self) -> None:
        state = _canvas_state()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            path.write_text("ORIGINAL", encoding="utf-8")
            tmp_path = path.with_name(f".{path.name}.tmp")

            with mock.patch("core.document_io.os.fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    write_document(path, state, version=CANVAS_FILE_VERSION)

            self.assertEqual(path.read_text(encoding="utf-8"), "ORIGINAL")
            self.assertFalse(tmp_path.exists())

    def test_write_document_does_not_leave_temp_file_on_success(self) -> None:
        state = _canvas_state()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            write_document(path, state, version=CANVAS_FILE_VERSION)

            siblings = os.listdir(temp_dir)

        self.assertEqual(siblings, ["sample.chemvas"])


if __name__ == "__main__":
    unittest.main()
