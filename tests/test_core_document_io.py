import json
import os
import stat
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from chemvas.core.document_io import (
    ChemvasDocument,
    atomic_create_bytes,
    atomic_write_text,
    atomic_write_via_temp,
    create_document,
    parse_document,
    read_document,
    read_exact_document,
    write_document,
)
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CHEMVAS_FILE_TYPE,
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
        "shapes": [],
        "orbitals": [],
        "settings": _settings(),
        "last_smiles_input": None,
    }


class DocumentIOTest(unittest.TestCase):
    def test_read_exact_document_returns_the_bytes_it_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "document.chemvas"
            write_document(path, _canvas_state(), CANVAS_FILE_VERSION)

            source_bytes, document = read_exact_document(path)

            self.assertEqual(source_bytes, path.read_bytes())
            self.assertEqual(document.payload["version"], CANVAS_FILE_VERSION)

    def test_read_document_rejects_duplicate_json_object_keys(self) -> None:
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": _canvas_state(),
        }
        serialized = json.dumps(payload, separators=(",", ":"))
        nested_field = '"last_smiles_input":null'
        self.assertIn(nested_field, serialized)
        duplicate_payloads = (
            '{"type":"wrong",' + serialized[1:],
            serialized.replace(
                nested_field,
                '"last_smiles_input":"CC","last_smiles_input":null',
                1,
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.chemvas"
            for raw_payload in duplicate_payloads:
                with self.subTest(raw_payload=raw_payload):
                    path.write_text(raw_payload, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                        read_document(path)

    def test_atomic_create_bytes_never_replaces_an_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new.bin"

            atomic_create_bytes(path, b"first")
            self.assertEqual(path.read_bytes(), b"first")
            with self.assertRaisesRegex(ValueError, "already exists"):
                atomic_create_bytes(path, b"second")

            self.assertEqual(path.read_bytes(), b"first")
            self.assertEqual(list(path.parent.glob(f".{path.name}.staging-*")), [])

    def test_failed_publish_closes_no_descriptor_it_no_longer_owns(self) -> None:
        # The staging file object closes the descriptor on its way out, so a
        # second close in the failure path would land on a number the process
        # may already have handed to an unrelated file.
        real_close = os.close
        closed_while_invalid: list[int] = []

        def recording_close(fd: int) -> None:
            try:
                os.fstat(fd)
            except OSError:
                closed_while_invalid.append(fd)
                return
            real_close(fd)

        def failing_link(source, target) -> None:
            raise OSError("injected link failure")

        real_fdopen = os.fdopen
        handles: list = []

        def recording_fdopen(fd, *args, **kwargs):
            handle = real_fdopen(fd, *args, **kwargs)
            handles.append(handle)
            return handle

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new.bin"
            with (
                mock.patch("os.close", recording_close),
                mock.patch("os.fdopen", recording_fdopen),
                mock.patch("os.link", failing_link),
                self.assertRaisesRegex(OSError, "injected link failure"),
            ):
                atomic_create_bytes(path, b"payload")

            self.assertEqual(closed_while_invalid, [])
            # The other half of the same question: the staging file object has
            # to have closed it, so a leak is a failure here too.
            self.assertEqual([handle.closed for handle in handles], [True])
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(f".{path.name}.staging-*")), [])

    def test_failed_handover_closes_the_descriptor_it_still_owns(self) -> None:
        # The one case where the descriptor is still ours: os.fdopen never took
        # it. Nothing else can close it, so this path has to.
        real_close = os.close
        closed_while_valid: list[int] = []

        def recording_close(fd: int) -> None:
            try:
                os.fstat(fd)
            except OSError:
                real_close(fd)
                return
            closed_while_valid.append(fd)
            real_close(fd)

        def failing_fdopen(fd, *args, **kwargs):
            raise OSError("injected handover failure")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new.bin"
            with (
                mock.patch("os.close", recording_close),
                mock.patch("os.fdopen", failing_fdopen),
                self.assertRaisesRegex(OSError, "injected handover failure"),
            ):
                atomic_create_bytes(path, b"payload")

            self.assertEqual(len(closed_while_valid), 1)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(f".{path.name}.staging-*")), [])

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

    def test_parse_document_rejects_extra_wrapper_key_before_normalizing(self) -> None:
        state = _canvas_state()
        extra = []
        for _ in range(2000):
            extra = [extra]
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": state,
            "extra": extra,
        }

        with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
            parse_document(payload)

    def test_create_and_write_document_normalize_decimal_numbers(self) -> None:
        state = _canvas_state(
            _model_state(
                {
                    "0": {
                        "element": "C",
                        "x": Decimal("1.25"),
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    }
                },
                [],
                1,
            )
        )

        document = create_document(state, version=CANVAS_FILE_VERSION)

        self.assertEqual(document.state["model"]["atoms"]["0"]["x"], 1.25)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "decimal.chemvas"
            write_document(path, state, version=CANVAS_FILE_VERSION)
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["state"]["model"]["atoms"]["0"]["x"], 1.25)

    def test_create_and_write_document_normalize_decimal_numbers_inside_tuples(
        self,
    ) -> None:
        state = _canvas_state()
        state["arrows"] = [
            {
                "kind": "arrow",
                "start": (Decimal("1.25"), 0.0),
                "end": (2.0, Decimal("3.5")),
            }
        ]

        document = create_document(state, version=CANVAS_FILE_VERSION)

        self.assertEqual(document.state["arrows"][0]["start"], (1.25, 0.0))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tuple-decimal.chemvas"
            write_document(path, state, version=CANVAS_FILE_VERSION)
            loaded = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["state"]["arrows"][0]["start"], [1.25, 0.0])
        self.assertEqual(loaded["state"]["arrows"][0]["end"], [2.0, 3.5])

    def test_parse_document_rejects_invalid_state_like_document_state(self) -> None:
        cases = (
            None,
            {},
            {"type": CHEMVAS_FILE_TYPE, "version": CANVAS_FILE_VERSION, "state": {}},
            {
                "type": "unexpected",
                "version": CANVAS_FILE_VERSION,
                "state": _canvas_state(),
            },
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION + 1,
                "state": _canvas_state(),
            },
            {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": {"active_sheet_index": 0, "sheets": []},
            },
            {
                "model": {"atoms": {}, "bonds": [], "next_atom_id": 0},
                "version": CANVAS_FILE_VERSION,
            },
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_document(payload)

    def test_versions_before_v7_are_rejected(self) -> None:
        state = _canvas_state()
        for version in range(1, CANVAS_FILE_VERSION):
            with self.subTest(version=version):
                payload = {
                    "type": CHEMVAS_FILE_TYPE,
                    "version": version,
                    "state": state,
                }
                with self.assertRaises(ValueError):
                    parse_document(payload)
                with self.assertRaises(ValueError):
                    create_document(state, version=version)

    def test_workbook_shaped_payloads_are_invalid(self) -> None:
        workbook_payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": 2,
            "state": {
                "active_sheet_index": 0,
                "sheets": [
                    {"name": "Canvas 1", "kind": "canvas", "content": _canvas_state()}
                ],
            },
        }

        with self.assertRaises(ValueError):
            parse_document(workbook_payload)

    def test_create_document_rejects_unsupported_or_mismatched_versions(self) -> None:
        with self.assertRaises(ValueError):
            create_document(_canvas_state(), version=9)
        with self.assertRaises(ValueError):
            create_document(
                {"active_sheet_index": 0, "sheets": []}, version=CANVAS_FILE_VERSION
            )

    def test_create_document_reports_save_side_error_message(self) -> None:
        # The save path never produced this state from a file, so the failure
        # message must not claim the *file* is invalid.
        with self.assertRaisesRegex(ValueError, "Failed to save"):
            create_document(
                {"active_sheet_index": 0, "sheets": []}, version=CANVAS_FILE_VERSION
            )

    def test_write_and_read_document_round_trip_wrapped_payload(self) -> None:
        state = _canvas_state(
            _model_state(
                {
                    "0": {
                        "element": "C",
                        "x": 0.0,
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    }
                },
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

    def test_read_document_rejects_bond_tombstones(self) -> None:
        state = _canvas_state(
            _model_state(
                {
                    "0": {
                        "element": "C",
                        "x": 0.0,
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    },
                    "1": {
                        "element": "C",
                        "x": 10.0,
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    },
                },
                [
                    None,
                    {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                ],
                2,
            )
        )
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": state,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.chemvas"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                read_document(path)

    def test_write_document_rejects_bond_tombstones_at_current_version(self) -> None:
        state = _canvas_state(
            _model_state(
                {
                    "0": {
                        "element": "C",
                        "x": 0.0,
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    },
                    "1": {
                        "element": "C",
                        "x": 10.0,
                        "y": 0.0,
                        "color": "#000000",
                        "explicit_label": False,
                    },
                },
                [
                    None,
                    {"a": 0, "b": 1, "order": 1, "style": "single", "color": "#000000"},
                ],
                2,
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            with self.assertRaises(ValueError):
                write_document(path, state, version=CANVAS_FILE_VERSION)
            self.assertFalse(path.exists())

    def test_read_document_rejects_deep_json_without_leaking_recursion_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            path.write_text("[" * 20_000 + "0" + "]" * 20_000, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                read_document(path)

    def test_read_document_rejects_invalid_utf8_without_leaking_decode_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            path.write_bytes(b"\xff\xfe\x00")

            with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                read_document(path)

    def test_read_document_rejects_overlong_json_integer_without_leaking_int_guard_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            payload = {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": _canvas_state(
                    _model_state(
                        {
                            "0": {
                                "element": "C",
                                "x": "__HUGE_INT__",
                                "y": 0.0,
                                "color": "#000000",
                                "explicit_label": False,
                            }
                        },
                        [],
                        1,
                    )
                ),
            }
            path.write_text(
                json.dumps(payload).replace('"__HUGE_INT__"', "9" * 5000),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                read_document(path)

    def test_read_document_rejects_unsafe_decimal_float_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            payload = {
                "type": CHEMVAS_FILE_TYPE,
                "version": CANVAS_FILE_VERSION,
                "state": _canvas_state(
                    _model_state(
                        {
                            "0": {
                                "element": "C",
                                "x": "__UNSAFE_FLOAT__",
                                "y": 0.0,
                                "color": "#000000",
                                "explicit_label": False,
                            }
                        },
                        [],
                        1,
                    )
                ),
            }
            path.write_text(
                json.dumps(payload).replace('"__UNSAFE_FLOAT__"', "9007199254740990.5"),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
                read_document(path)

    def test_parse_document_rejects_huge_numeric_coordinate_without_leaking_overflow_error(
        self,
    ) -> None:
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": _canvas_state(
                _model_state(
                    {
                        "0": {
                            "element": "C",
                            "x": int("9" * 4000),
                            "y": 0.0,
                            "color": "#000000",
                            "explicit_label": False,
                        }
                    },
                    [],
                    1,
                )
            ),
        }

        with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
            parse_document(payload)

    def test_parse_document_rejects_overlong_decimal_id_without_leaking_int_guard_error(
        self,
    ) -> None:
        payload = {
            "type": CHEMVAS_FILE_TYPE,
            "version": CANVAS_FILE_VERSION,
            "state": _canvas_state(
                _model_state(
                    {
                        "9" * 5000: {
                            "element": "C",
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
        }

        with self.assertRaisesRegex(ValueError, "Invalid Chemvas file"):
            parse_document(payload)

    def test_write_document_is_atomic_and_preserves_file_on_failure(self) -> None:
        state = _canvas_state()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            path.write_text("ORIGINAL", encoding="utf-8")

            with mock.patch(
                "chemvas.core.document_io.os.fsync", side_effect=OSError("disk full")
            ):
                with self.assertRaises(OSError):
                    write_document(path, state, version=CANVAS_FILE_VERSION)

            self.assertEqual(path.read_text(encoding="utf-8"), "ORIGINAL")
            self.assertEqual(os.listdir(temp_dir), ["sample.chemvas"])

    def test_write_document_does_not_leave_temp_file_on_success(self) -> None:
        state = _canvas_state()

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            write_document(path, state, version=CANVAS_FILE_VERSION)

            siblings = os.listdir(temp_dir)

        self.assertEqual(siblings, ["sample.chemvas"])

    def test_atomic_write_text_preserves_existing_file_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            path.write_text("ORIGINAL", encoding="utf-8")

            with mock.patch(
                "chemvas.core.document_io.os.fsync", side_effect=OSError("disk full")
            ):
                with self.assertRaises(OSError):
                    atomic_write_text(path, "NEW")

            self.assertEqual(path.read_text(encoding="utf-8"), "ORIGINAL")
            self.assertEqual(os.listdir(temp_dir), ["export.xyz"])

    def test_atomic_write_via_temp_uses_unique_sibling_temp_path_per_call(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"
            temp_paths: list[Path] = []

            def writer(tmp: Path) -> None:
                temp_paths.append(tmp)
                tmp.write_text(f"write {len(temp_paths)}", encoding="utf-8")

            atomic_write_via_temp(path, writer)
            atomic_write_via_temp(path, writer)

            self.assertEqual(len(temp_paths), 2)
            self.assertNotEqual(temp_paths[0], temp_paths[1])
            for tmp in temp_paths:
                self.assertEqual(tmp.parent, path.parent)
                self.assertTrue(tmp.name.startswith(f".{path.name}."))
                self.assertTrue(tmp.name.endswith(".tmp"))
                self.assertFalse(tmp.exists())
            self.assertEqual(path.read_text(encoding="utf-8"), "write 2")
            self.assertEqual(os.listdir(temp_dir), ["sample.chemvas"])

    def test_atomic_write_via_temp_fsyncs_write_capable_handle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.chemvas"

            def assert_write_capable(fd: int) -> None:
                self.assertEqual(os.write(fd, b""), 0)

            with mock.patch(
                "chemvas.core.document_io.os.fsync", side_effect=assert_write_capable
            ) as fsync:
                atomic_write_text(path, "NEW")

            fsync.assert_called_once()
            self.assertEqual(path.read_text(encoding="utf-8"), "NEW")

    def test_atomic_write_via_temp_preserves_existing_permission_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shared.chemvas"
            path.write_text("ORIGINAL", encoding="utf-8")
            os.chmod(path, 0o664)
            original_mode = stat.S_IMODE(path.stat().st_mode)

            atomic_write_text(path, "NEW")

            self.assertEqual(stat.S_IMODE(path.stat().st_mode), original_mode)
            self.assertEqual(path.read_text(encoding="utf-8"), "NEW")


if __name__ == "__main__":
    unittest.main()
