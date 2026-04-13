import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.document_io import (
    LiteDrawDocument,
    create_document,
    parse_document,
    read_document,
    write_document,
)
from core.document_state import LITEDRAW_FILE_TYPE


class DocumentIOTest(unittest.TestCase):
    def test_create_document_wraps_state_in_litedraw_payload(self) -> None:
        state = {
            "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
            "last_smiles_input": "CCO",
        }

        document = create_document(state, version=4)

        self.assertIsInstance(document, LiteDrawDocument)
        self.assertEqual(
            document.payload,
            {
                "type": LITEDRAW_FILE_TYPE,
                "version": 4,
                "state": state,
            },
        )
        self.assertIs(document.state, state)

    def test_parse_document_accepts_wrapped_payload_and_bare_state(self) -> None:
        state = {"model": {"atoms": {}, "bonds": [], "next_atom_id": 0}}
        payload = {"type": "unexpected", "version": "legacy", "state": state}

        wrapped = parse_document(payload)
        bare = parse_document(state)

        self.assertIs(wrapped.payload, payload)
        self.assertIs(wrapped.state, state)
        self.assertIs(bare.payload, state)
        self.assertIs(bare.state, state)

    def test_parse_document_rejects_invalid_state_like_document_state(self) -> None:
        with self.assertRaises(ValueError):
            parse_document(None)
        with self.assertRaises(ValueError):
            parse_document({})
        with self.assertRaises(ValueError):
            parse_document({"type": LITEDRAW_FILE_TYPE, "version": 1, "state": {}})

    def test_write_and_read_document_round_trip_wrapped_payload(self) -> None:
        state = {
            "model": {"atoms": {"0": {"element": "C"}}, "bonds": [], "next_atom_id": 1},
            "settings": {"bond_length_px": 18.0},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.litedraw"

            written = write_document(path, state, version=7)
            loaded = read_document(path)

        self.assertEqual(
            written.payload,
            {
                "type": LITEDRAW_FILE_TYPE,
                "version": 7,
                "state": state,
            },
        )
        self.assertEqual(loaded.payload, written.payload)
        self.assertEqual(loaded.state, state)

    def test_read_document_accepts_bare_state_files(self) -> None:
        state = {"model": {"atoms": {}, "bonds": [], "next_atom_id": 0}, "notes": []}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.json"
            path.write_text(json.dumps(state), encoding="utf-8")

            loaded = read_document(path)

        self.assertEqual(loaded.payload, state)
        self.assertEqual(loaded.state, state)


if __name__ == "__main__":
    unittest.main()
