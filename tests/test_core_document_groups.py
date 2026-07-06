from __future__ import annotations

import unittest

from core.document_state import (
    CANVAS_FILE_VERSION,
    PERSPECTIVE_CANVAS_FILE_VERSION,
    build_document_payload,
    extract_document_state,
)


def _model_state() -> dict:
    return {
        "atoms": {
            "0": {"element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
            "1": {"element": "O", "x": 10.0, "y": 0.0, "color": "#000000", "explicit_label": True},
        },
        "bonds": [],
        "next_atom_id": 2,
    }


def _settings() -> dict:
    return {
        "bond_length_px": 20.0,
        "arrow_line_width": 1.2,
        "arrow_head_scale": 0.3,
        "orbital_phase_enabled": False,
        "text_font_size": 12,
        "text_font_weight": 400,
        "text_italic": False,
        "sheet_size": "A4",
        "sheet_orientation": "landscape",
    }


def _canvas_state(groups: list | None = None) -> dict:
    state = {
        "model": _model_state(),
        "ring_fills": [],
        "notes": [{"text": "note", "x": 0.0, "y": 0.0}],
        "marks": [
            {
                "kind": "plus",
                "text": "+",
                "atom_id": None,
                "dx": None,
                "dy": None,
                "x": 5.0,
                "y": 5.0,
            }
        ],
        "arrows": [
            {
                "kind": "arrow",
                "start": (0.0, 0.0),
                "end": (10.0, 0.0),
                "control": None,
                "double": False,
            }
        ],
        "ts_brackets": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }
    if groups is not None:
        state["groups"] = groups
    return state


class DocumentGroupsValidationTest(unittest.TestCase):
    def test_valid_groups_round_trip_through_payload(self) -> None:
        state = _canvas_state(
            groups=[{"atoms": [0, 1], "items": [["marks", 0], ["arrows", 0], ["notes", 0]]}],
        )

        payload = build_document_payload(state, CANVAS_FILE_VERSION)

        self.assertEqual(extract_document_state(payload), state)

    def test_groups_key_is_optional(self) -> None:
        payload = build_document_payload(_canvas_state(), CANVAS_FILE_VERSION)

        self.assertNotIn("groups", extract_document_state(payload))

    def test_groups_rejected_for_older_file_versions(self) -> None:
        state = _canvas_state(groups=[{"atoms": [0], "items": [["notes", 0]]}])

        with self.assertRaises(ValueError):
            build_document_payload(state, PERSPECTIVE_CANVAS_FILE_VERSION)

    def test_invalid_group_payloads_are_rejected(self) -> None:
        cases = (
            "not-a-list",
            [{"atoms": [0]}],
            [{"atoms": [0], "items": [], "extra": True}],
            [{"atoms": [], "items": []}],
            [{"atoms": [99], "items": []}],
            [{"atoms": [0, 0], "items": []}],
            [{"atoms": [0], "items": []}, {"atoms": [0], "items": []}],
            [{"atoms": [0], "items": [["shapes", 0]]}],
            [{"atoms": [0], "items": [["marks", 1]]}],
            [{"atoms": [0], "items": [["arrows", 1]]}],
            [{"atoms": [0], "items": [["arrows", -1]]}],
            [{"atoms": [0], "items": [["unknown", 0]]}],
            [{"atoms": [0], "items": [["arrows"]]}],
            [{"atoms": [0], "items": [["arrows", 0], ["arrows", 0]]}],
            [{"atoms": [0], "items": [["arrows", 0.5]]}],
        )
        for groups in cases:
            with self.subTest(groups=groups):
                with self.assertRaises(ValueError):
                    build_document_payload(
                        _canvas_state(groups=groups),
                        CANVAS_FILE_VERSION,
                    )


if __name__ == "__main__":
    unittest.main()
