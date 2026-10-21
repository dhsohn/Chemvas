"""CDXML label-binding sidecar through ``render-document`` and the service.

Synthetic O-LABEL documents and explicit synthetic bindings only. They are
serializer-path fixtures, not statements about any real figure, and the XML
checks here are not ChemDraw (or any consumer) visual or roundtrip evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap import document_render as cli
from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.features.export.cdxml_label_bindings import (
    CDXML_LABEL_BINDINGS_FORMAT,
    CdxmlLabelBindingEntry,
    CdxmlLabelBindings,
)
from chemvas.ui.export.export_cdxml import (
    CdxmlLabelBinding,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService
from tests.document_file_helpers import write_document

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

pytestmark = pytest.mark.usefixtures("qt_application")

H_A = "H\u1d43"


def _state(atoms: dict[int, Atom], bonds: list[Bond]) -> dict[str, object]:
    return {
        "model": serialize_model_state(MoleculeModel(atoms=atoms, bonds=bonds)),
        "ring_fills": [],
        "notes": [],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=20.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=12,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _label_state(label: str = "Ar") -> dict[str, object]:
    return _state(
        {
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom(label, 25.0, 0.0, explicit_label=True),
        },
        [Bond(0, 1)],
    )


def _mixed_state() -> dict[str, object]:
    """O bonded to Ar and to H-identifier, plus a second O-Ar for a phenyl."""
    return _state(
        {
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
            2: Atom(H_A, -12.5, 21.65, explicit_label=True),
            3: Atom("O", 0.0, 80.0, explicit_label=True),
            4: Atom("Ar", 25.0, 80.0, explicit_label=True),
        },
        [Bond(0, 1), Bond(0, 2), Bond(3, 4)],
    )


def _write_source(path: Path, state: dict[str, object]) -> bytes:
    write_document(path, state, CANVAS_FILE_VERSION)
    return path.read_bytes()


def _sidecar(source_bytes: bytes, *entries: dict[str, object]) -> dict[str, object]:
    return {
        "format": CDXML_LABEL_BINDINGS_FORMAT,
        "version": 1,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "bindings": list(entries) or [_entry()],
    }


def _write_sidecar(path: Path, payload: object) -> bytes:
    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    path.write_bytes(content)
    return content


def _render(source: Path, output: Path, sidecar: Path) -> int:
    return cli.run(
        [
            "render-document",
            str(source),
            "--output",
            str(output),
            "--cdxml-label-bindings",
            str(sidecar),
        ]
    )


def _top_nodes(root: ET.Element) -> list[ET.Element]:
    page = root.find("page")
    assert page is not None
    return [n for frag in page.findall("fragment") for n in frag.findall("n")]


def _label_text(node: ET.Element) -> str:
    (text,) = node.findall("t")
    return "".join(run.text or "" for run in text.findall("s"))


def _assert_refused(
    capsys: pytest.CaptureFixture[str],
    source: Path,
    output: Path,
    sidecar: Path,
    source_bytes: bytes,
    match: str,
) -> None:
    with pytest.raises(SystemExit) as error:
        _render(source, output, sidecar)
    assert error.value.code == 2
    assert match in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == source_bytes
    assert not list(output.parent.glob(".chemvas-*"))


# 1. The CLI hands typed bindings to the exporter unchanged.


def test_generic_aryl_sidecar_exports_typed_nickname_and_reports_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())
    sidecar = tmp_path / "labels.json"
    sidecar_bytes = _write_sidecar(sidecar, _sidecar(source_bytes))
    output = tmp_path / "out.cdxml"

    assert _render(source, output, sidecar) == 0
    report = json.loads(capsys.readouterr().out)

    root = ET.fromstring(output.read_bytes())
    (group,) = [n for n in _top_nodes(root) if n.get("NodeType") is not None]
    assert group.get("NodeType") == "Nickname"
    assert group.find('./fragment/n[@GenericNickname="ARY"]') is not None
    assert _label_text(group) == "Ar"
    assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert report["cdxml_label_bindings"] == {
        "sidecar": str(sidecar),
        "sidecar_sha256": hashlib.sha256(sidecar_bytes).hexdigest(),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "bindings": [{"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"}],
    }
    assert source.read_bytes() == source_bytes


def test_cli_output_equals_direct_exporter_call_with_the_same_typed_bindings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    state = _mixed_state()
    source = tmp_path / "mixed-source.cdxml"
    source_bytes = _write_source(source, state)
    sidecar = tmp_path / "labels.json"
    entries = [
        {"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"},
        {"atom_id": 2, "expected_label": H_A, "meaning": "element", "element": "H"},
        {
            "atom_id": 4,
            "expected_label": "Ar",
            "meaning": "aryl_fragment",
            "fragment": "Ph",
        },
    ]
    _write_sidecar(sidecar, _sidecar(source_bytes, *entries))
    output = tmp_path / "mixed.cdxml"

    assert _render(source, output, sidecar) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["cdxml_label_bindings"]["bindings"] == entries

    typed = {
        1: CdxmlLabelBinding.generic_aryl(),
        2: CdxmlLabelBinding.element_identity("H"),
        4: CdxmlLabelBinding.aryl_fragment("Ph"),
    }
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context, groups={})
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="bond", target_width_mm=None
        )
        preflight_cdxml(
            context, items, plan, background="white", groups={}, label_bindings=typed
        )
        expected = serialize_cdxml(
            context, items, plan, background="white", groups={}, label_bindings=typed
        )
    assert output.read_bytes() == expected

    root = ET.fromstring(output.read_bytes())
    labelled = [n for n in _top_nodes(root) if n.find("t") is not None]
    (hydrogen,) = [n for n in labelled if _label_text(n) == H_A]
    assert hydrogen.get("Element") == "1"
    assert hydrogen.get("Isotope") is None
    node_types = sorted(n.get("NodeType") or "" for n in labelled)
    assert node_types.count("GenericNickname") == 0
    assert node_types.count("Nickname") == 2


# 2. Every malformed, unbound or mismatched sidecar is refused before output.


def _bad_sidecar(case: str, source_bytes: bytes) -> str:
    digest = hashlib.sha256(source_bytes).hexdigest()
    head = f'"format": "{CDXML_LABEL_BINDINGS_FORMAT}", "version": 1'
    good = '{"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"}'
    texts = {
        "duplicate-top-level-key": (
            f'{{{head}, "source_sha256": "{digest}", '
            f'"source_sha256": "{digest}", "bindings": [{good}]}}'
        ),
        "duplicate-binding-key": (
            f'{{{head}, "source_sha256": "{digest}", "bindings": [{{"atom_id": 1, '
            '"atom_id": 1, "expected_label": "Ar", "meaning": "generic_aryl"}]}'
        ),
        "nan": f'{{{head}, "source_sha256": "{digest}", "bindings": [NaN]}}',
        "trailing-data": (
            f'{{{head}, "source_sha256": "{digest}", "bindings": [{good}]}} {{}}'
        ),
    }
    return texts[case]


@pytest.mark.parametrize(
    "case",
    ["duplicate-top-level-key", "duplicate-binding-key", "nan", "trailing-data"],
)
def test_non_strict_sidecar_json_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())
    sidecar = tmp_path / "labels.json"
    sidecar.write_text(_bad_sidecar(case, source_bytes), encoding="utf-8")

    _assert_refused(
        capsys,
        source,
        tmp_path / "out.cdxml",
        sidecar,
        source_bytes,
        "not strict JSON",
    )


def _entry(**fields: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "atom_id": 1,
        "expected_label": "Ar",
        "meaning": "generic_aryl",
    }
    entry.update(fields)
    return entry


@pytest.mark.parametrize(
    ("label", "overrides", "entry", "match"),
    [
        ("Ar", {"extra": 1}, _entry(), "unknown keys ['extra']"),
        ("Ar", {"version": True}, _entry(), "version must be the integer 1"),
        ("Ar", {"bindings": []}, None, "non-empty JSON array"),
        ("Ar", {}, _entry(meaning="argon"), "meaning must be one of"),
        ("Ar", {}, _entry(colour="red"), "unknown keys ['colour']"),
        ("Ar", {}, _entry(fragment="Ph"), "unknown keys ['fragment']"),
        ("Ar", {}, _entry(atom_id="1"), "atom_id must be a non-negative integer"),
        ("Ar", {}, _entry(atom_id=1.0), "atom_id must be a non-negative integer"),
        ("Ar", {}, _entry(expected_label=["Ar"]), "expected_label must be"),
        ("Ar", {}, _entry(meaning="element", element=18), "element must be"),
        ("Ar", {}, _entry(atom_id=9), "the atom is not in the document"),
        ("Ar", {}, _entry(expected_label="AR"), "is not the expected label 'AR'"),
        ("Ar", {}, _entry(expected_label="Ar "), "is not the expected label 'Ar '"),
        (H_A, {}, _entry(expected_label="Ha"), "is not the expected label 'Ha'"),
        (
            "Ar",
            {},
            _entry(meaning="aryl_fragment", fragment="Me"),
            "no verified aryl fragment definition",
        ),
        (
            H_A,
            {},
            _entry(expected_label=H_A, meaning="element", element="He"),
            "does not match bound element 'He'",
        ),
        ("N", {}, _entry(expected_label="N"), "applies only to the label 'Ar'"),
    ],
)
def test_invalid_or_mismatched_sidecars_publish_nothing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    label: str,
    overrides: dict[str, object],
    entry: dict[str, object] | None,
    match: str,
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state(label))
    payload = _sidecar(source_bytes, *([] if entry is None else [entry]))
    payload.update(overrides)
    sidecar = tmp_path / "labels.json"
    _write_sidecar(sidecar, payload)

    _assert_refused(
        capsys, source, tmp_path / "out.cdxml", sidecar, source_bytes, match
    )


@pytest.mark.parametrize(
    ("digest", "match"),
    [
        (hashlib.sha256(b"other document").hexdigest(), "different document"),
        ("A" * 64, "64 lowercase hexadecimal"),
    ],
)
def test_sidecar_bound_to_other_bytes_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], digest: str, match: str
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())
    payload = _sidecar(source_bytes)
    payload["source_sha256"] = digest
    sidecar = tmp_path / "labels.json"
    _write_sidecar(sidecar, payload)

    _assert_refused(
        capsys, source, tmp_path / "out.cdxml", sidecar, source_bytes, match
    )


@pytest.mark.parametrize("output_format", ["svg", "png", "pdf"])
def test_option_is_refused_for_non_cdxml_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], output_format: str
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())
    sidecar = tmp_path / "labels.json"
    _write_sidecar(sidecar, _sidecar(source_bytes))

    _assert_refused(
        capsys,
        source,
        tmp_path / f"out.{output_format}",
        sidecar,
        source_bytes,
        "supports CDXML output only",
    )


def test_missing_sidecar_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())

    _assert_refused(
        capsys,
        source,
        tmp_path / "out.cdxml",
        tmp_path / "missing.json",
        source_bytes,
        "sidecar does not exist",
    )


def test_existing_destination_is_preserved_when_a_binding_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state())
    sidecar = tmp_path / "labels.json"
    _write_sidecar(sidecar, _sidecar(source_bytes, _entry(expected_label="Ph")))
    output = tmp_path / "keep.cdxml"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        _render(source, output, sidecar)

    assert error.value.code == 2
    assert output.read_text(encoding="utf-8") == "keep"


# 3. One read of the source: a file replaced after it was read is not re-read.


def test_validation_and_export_use_the_same_source_bytes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source-source.cdxml"
    source_bytes = _write_source(source, _label_state("Ar"))
    replacement = tmp_path / "replacement.cdxml"
    replacement_bytes = _write_source(replacement, _label_state("N"))
    assert replacement_bytes != source_bytes
    original_read = cli.read_exact_document

    def read_then_replace(path, **kwargs):
        result = original_read(path, **kwargs)
        Path(path).write_bytes(replacement_bytes)
        return result

    monkeypatch.setattr(cli, "read_exact_document", read_then_replace)

    # Bound to the bytes that were read: exported from those bytes.
    sidecar = tmp_path / "labels.json"
    _write_sidecar(sidecar, _sidecar(source_bytes))
    output = tmp_path / "out.cdxml"
    assert _render(source, output, sidecar) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    root = ET.fromstring(output.read_bytes())
    assert len(root.findall('.//n[@GenericNickname="ARY"]')) == 1

    # Bound to the replacement bytes: the read bytes do not match, so refused.
    source.write_bytes(source_bytes)
    _write_sidecar(sidecar, _sidecar(replacement_bytes, _entry(expected_label="N")))
    refused = tmp_path / "refused.cdxml"
    with pytest.raises(SystemExit) as error:
        _render(source, refused, sidecar)
    assert error.value.code == 2
    assert "different document" in capsys.readouterr().err
    assert not refused.exists()


# 4. Service-level scope, visibility and format checks.


def _bindings(*entries: CdxmlLabelBindingEntry) -> CdxmlLabelBindings:
    return CdxmlLabelBindings(
        source_sha256="0" * 64, sidecar_sha256="1" * 64, entries=entries
    )


def _is(item: QGraphicsItem, role: str, ids: tuple[int, ...]) -> bool:
    return item.data(0) == role and item.data(1) in ids


GENERIC_AR = _bindings(CdxmlLabelBindingEntry(1, "Ar", "generic_aryl"))


def test_service_refuses_a_binding_on_a_hidden_atom(tmp_path: Path) -> None:
    output = tmp_path / "keep.cdxml"
    output.write_text("keep", encoding="utf-8")
    with offscreen_document_scene(_label_state(), command="test-cdxml") as context:
        hidden = [item for item in context.scene.items() if _is(item, "atom", (1,))]
        assert hidden
        for item in hidden:
            item.setVisible(False)
        with pytest.raises(ValueError, match="hidden or outside the export scope"):
            FigureExportService(context).export_figure(
                str(output), fmt="cdxml", label_bindings=GENERIC_AR
            )
    assert output.read_text(encoding="utf-8") == "keep"


def test_service_refuses_a_binding_outside_the_selection(tmp_path: Path) -> None:
    state = _state(
        {
            0: Atom("O", 0.0, 0.0, explicit_label=True),
            1: Atom("Ar", 25.0, 0.0, explicit_label=True),
            2: Atom("N", 0.0, 80.0, explicit_label=True),
            3: Atom("O", 25.0, 80.0, explicit_label=True),
        },
        [Bond(0, 1), Bond(2, 3)],
    )
    output = tmp_path / "keep.cdxml"
    output.write_text("keep", encoding="utf-8")
    with offscreen_document_scene(state, command="test-cdxml") as context:
        selection = [
            item
            for item in context.scene.items()
            if _is(item, "atom", (2, 3)) or _is(item, "bond", (1,))
        ]
        service = FigureExportService(context)
        with pytest.raises(ValueError, match="hidden or outside the export scope"):
            service.export_figure(
                str(output),
                fmt="cdxml",
                scope="selection",
                selection=selection,
                label_bindings=GENERIC_AR,
            )
        # The same selection without the binding exports the N-O fragment.
        service.export_figure(
            str(tmp_path / "selection.cdxml"),
            fmt="cdxml",
            scope="selection",
            selection=selection,
        )
    assert output.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("fmt", ["svg", "png", "pdf"])
def test_service_refuses_bindings_for_non_cdxml_formats(
    tmp_path: Path, fmt: str
) -> None:
    output = tmp_path / f"keep.{fmt}"
    output.write_text("keep", encoding="utf-8")
    with offscreen_document_scene(_label_state(), command="test-cdxml") as context:
        with pytest.raises(ValueError, match="CDXML export only"):
            FigureExportService(context).export_figure(
                str(output), fmt=fmt, label_bindings=GENERIC_AR
            )
    assert output.read_text(encoding="utf-8") == "keep"


def test_service_without_bindings_keeps_the_existing_cdxml_bytes(
    tmp_path: Path,
) -> None:
    state = _label_state("N")
    output = tmp_path / "plain.cdxml"
    with offscreen_document_scene(state, command="test-cdxml") as context:
        service = FigureExportService(context)
        service.export_figure(str(output), fmt="cdxml")
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="bond", target_width_mm=None
        )
        preflight_cdxml(context, items, plan, background="transparent")
        expected = serialize_cdxml(context, items, plan, background="transparent")
    assert output.read_bytes() == expected
