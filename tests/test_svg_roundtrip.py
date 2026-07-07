import base64
import json
import tempfile
import unittest
import zlib
from decimal import Decimal
from pathlib import Path
from unittest import mock
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


def _encoded_payload(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.b64encode(zlib.compress(raw)).decode("ascii")


def _write_svg_with_unsupported_encoding(path: Path) -> None:
    path.write_bytes(b'<?xml version="1.0" encoding="BOGUS"?><svg/>')


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

    def test_embed_rejects_extra_svg_payload_key_before_normalizing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            extra = []
            for _ in range(2000):
                extra = [extra]
            payload["extra"] = extra

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas SVG payload"):
                embed_chemvas_document_in_svg(path, payload)

    def test_embed_rejects_unhashable_svg_metadata_values_as_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            for mutation in (
                lambda candidate: candidate.update({"scope": []}),
                lambda candidate: candidate["document"].update({"version": []}),
            ):
                with self.subTest(mutation=mutation):
                    candidate = json.loads(json.dumps(payload))
                    mutation(candidate)
                    with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas SVG payload"):
                        embed_chemvas_document_in_svg(path, candidate)

    def test_embed_normalizes_decimal_document_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            state = _sheet_state()
            state["notes"][0]["x"] = Decimal("1.25")
            payload = create_editable_svg_payload(
                state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )

            embed_chemvas_document_in_svg(path, payload)
            extracted = extract_chemvas_document_from_svg(path)

        self.assertEqual(extracted.state["notes"][0]["x"], 1.25)

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

    def test_embed_removes_existing_chemvas_sources_from_all_root_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            stale = create_editable_svg_payload(
                _sheet_state("stale"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            fresh_state = _sheet_state("fresh")
            fresh = create_editable_svg_payload(
                fresh_state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata><title>external metadata</title>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(stale)}</chemvas:source>'
                '</metadata>'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(stale)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            embed_chemvas_document_in_svg(path, fresh)

            root = ET.parse(path).getroot()
            sources = list(root.iter(f"{{{CHEMVAS_SVG_NAMESPACE}}}source"))
            self.assertEqual(len(sources), 1)
            self.assertEqual(extract_chemvas_document_from_svg(path).state, fresh_state)

    def test_embed_rejects_malformed_svg_without_leaking_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            path.write_text("<svg><metadata>", encoding="utf-8")
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )

            with self.assertRaisesRegex(ValueError, "Invalid SVG file"):
                embed_chemvas_document_in_svg(path, payload)

    def test_embed_rejects_unsupported_svg_encoding_without_leaking_lookup_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            _write_svg_with_unsupported_encoding(path)
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )

            with self.assertRaisesRegex(ValueError, "Invalid SVG file"):
                embed_chemvas_document_in_svg(path, payload)

    def test_extract_uses_root_metadata_source_not_nested_shadow_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            shadow = create_editable_svg_payload(
                _sheet_state("shadow"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            good_state = _sheet_state("good")
            good = create_editable_svg_payload(
                good_state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<defs>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(shadow)}</chemvas:source>'
                '</defs>'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(good)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            self.assertEqual(extract_chemvas_document_from_svg(path).state, good_state)

    def test_extract_rejects_unsafe_decimal_float_token_before_normalizing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            payload = create_editable_svg_payload(
                _sheet_state("unsafe"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            payload["document"]["state"]["notes"][0]["x"] = "__UNSAFE_FLOAT__"
            raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).replace(
                '"__UNSAFE_FLOAT__"',
                "9007199254740990.5",
            )
            encoded = base64.b64encode(zlib.compress(raw.encode("utf-8"))).decode("ascii")
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                "<metadata>"
                f'<chemvas:source encoding="base64+zlib+json">{encoded}</chemvas:source>'
                "</metadata>"
                "</svg>",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas"):
                extract_chemvas_document_from_svg(path)

    def test_extract_searches_all_root_metadata_but_rejects_duplicate_root_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            good_state = _sheet_state("good")
            good = create_editable_svg_payload(
                good_state,
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata><title>external metadata</title></metadata>'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(good)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            self.assertEqual(extract_chemvas_document_from_svg(path).state, good_state)

            shadow = create_editable_svg_payload(
                _sheet_state("shadow"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(shadow)}</chemvas:source>'
                '</metadata>'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(good)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

    def test_extract_rejects_multiple_root_metadata_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            first = create_editable_svg_payload(
                _sheet_state("first"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            second = create_editable_svg_payload(
                _sheet_state("second"),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(first)}</chemvas:source>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(second)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

    def test_extract_rejects_oversized_encoded_or_decompressed_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            encoded = _encoded_payload(payload)
            source = (
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{encoded}</chemvas:source>'
                '</metadata>'
                '</svg>'
            )
            path.write_text(source, encoding="utf-8")

            with mock.patch("core.svg_roundtrip._MAX_SVG_SOURCE_TEXT_BYTES", len(encoded) - 1):
                with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                    extract_chemvas_document_from_svg(path)

            raw_len = len(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
            with mock.patch("core.svg_roundtrip._MAX_SVG_PAYLOAD_BYTES", raw_len - 1):
                with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                    extract_chemvas_document_from_svg(path)

            with mock.patch("core.svg_roundtrip._MAX_SVG_PAYLOAD_BYTES", raw_len):
                self.assertEqual(extract_chemvas_document_from_svg(path).state, _sheet_state())

    def test_extract_rejects_malformed_svg_without_leaking_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            path.write_text("<svg><metadata>", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

    def test_extract_rejects_unsupported_svg_encoding_without_leaking_lookup_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            _write_svg_with_unsupported_encoding(path)

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

    def test_extract_rejects_invalid_embedded_document_without_leaking_file_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            payload = create_editable_svg_payload(
                _sheet_state(),
                document_version=CANVAS_FILE_VERSION,
                scope=CHEMVAS_SVG_SCOPE_SHEET,
            )
            payload["document"]["state"] = {}
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{_encoded_payload(payload)}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas SVG payload"):
                extract_chemvas_document_from_svg(path)

    def test_extract_rejects_deep_metadata_json_without_leaking_recursion_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            deep_json = "[" * 20_000 + "0" + "]" * 20_000
            encoded = base64.b64encode(zlib.compress(deep_json.encode("utf-8"))).decode("ascii")
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xmlns:chemvas="https://chemvas.app/ns/svg-source/1">'
                '<metadata>'
                f'<chemvas:source encoding="base64+zlib+json">{encoded}</chemvas:source>'
                '</metadata>'
                '</svg>',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)

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

    def test_extract_rejects_doctype_declarations(self) -> None:
        # xml.etree expands internal entities, so a DTD could be used for a
        # billion-laughs memory blowup; Chemvas SVGs never carry a DOCTYPE.
        with tempfile.TemporaryDirectory() as tmp:
            path = self._svg_path(tmp)
            path.write_text(
                '<?xml version="1.0"?>'
                '<!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">]>'
                '<svg xmlns="http://www.w3.org/2000/svg"><metadata/></svg>',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Invalid editable Chemvas metadata"):
                extract_chemvas_document_from_svg(path)


if __name__ == "__main__":
    unittest.main()
