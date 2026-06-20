import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from core.document_state import CANVAS_FILE_VERSION, serialize_settings
from core.svg_roundtrip import (
    CHEMVAS_SVG_NAMESPACE,
    CHEMVAS_SVG_SCOPE_SHEET,
    create_editable_svg_payload,
    embed_chemvas_document_in_svg,
    extract_chemvas_document_from_svg,
    extract_chemvas_svg_payload,
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


def _sheet_state(text: str = "note") -> dict:
    return {
        "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
        "ring_fills": [],
        "notes": [{"text": text, "x": 1.0, "y": 2.0}],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }


class SvgRoundtripTest(unittest.TestCase):
    def _svg_path(self, tmp: str) -> Path:
        path = Path(tmp) / "figure.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            '<path d="M0 0 L10 10" />'
            "</svg>",
            encoding="utf-8",
        )
        return path

    def test_embed_and_extract_editable_document_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            state = _sheet_state()
            payload = create_editable_svg_payload(
                state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )

            embed_chemvas_document_in_svg(path, payload)

            root = ET.parse(path).getroot()
            sources = list(root.iter(f"{{{CHEMVAS_SVG_NAMESPACE}}}source"))
            self.assertEqual(len(sources), 1)
            self.assertEqual(extract_chemvas_svg_payload(path)["scope"], CHEMVAS_SVG_SCOPE_SHEET)
            self.assertEqual(extract_chemvas_document_from_svg(path).state, state)

    def test_embed_replaces_existing_chemvas_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            first = create_editable_svg_payload(
                _sheet_state("first"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            second_state = _sheet_state("second")
            second = create_editable_svg_payload(
                second_state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )

            embed_chemvas_document_in_svg(path, first)
            embed_chemvas_document_in_svg(path, second)

            root = ET.parse(path).getroot()
            sources = list(root.iter(f"{{{CHEMVAS_SVG_NAMESPACE}}}source"))
            self.assertEqual(len(sources), 1)
            self.assertEqual(extract_chemvas_document_from_svg(path).state, second_state)

    def test_extract_rejects_missing_or_invalid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)

            with self.assertRaisesRegex(ValueError, "No editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata><chemvas:source encoding="base64+zlib+json">not-base64</chemvas:source></metadata>'
                "</svg>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)


if __name__ == "__main__":
    unittest.main()
