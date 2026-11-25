"""Standard CDXML graph-only depiction and phenolic OH import."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_render_preprocessing import maybe_preprocess_external_cdxml
from chemvas.features.cdxml_standard_depiction import depict_standard_cdxml
from chemvas.features.document_files import read_exact_document

_FONT = '<fonttable><font id="3" name="Arial" charset="iso-8859-1" /></fonttable>'
_ROOT_ATTRS = 'BondLength="14.4" LineWidth="1.08" LabelSize="11.52" LabelFont="3"'


def _phenol(positioned: bool = False, explicit: bool = False) -> str:
    root = ET.fromstring(
        f'<CDXML {_ROOT_ATTRS}>{_FONT}<page id="1"><fragment id="2"/></page></CDXML>'
    )
    fragment = root.find(".//fragment")
    assert fragment is not None
    for i in range(6):
        angle = i * math.pi / 3
        n = ET.SubElement(fragment, "n", id=str(10 + i), Element="6")
        if positioned:
            n.set("p", f"{20 + 14.4 * math.cos(angle)} {20 + 14.4 * math.sin(angle)}")
        ET.SubElement(
            fragment,
            "b",
            id=str(30 + i),
            B=str(10 + i),
            E=str(10 + (i + 1) % 6),
            Order=str(1 + i % 2),
        )
    oxygen = ET.SubElement(fragment, "n", id="18", Element="8")
    if positioned:
        oxygen.set("p", "48.8 20")
    if explicit:
        oxygen.set("NumHydrogens", "1")
    ET.SubElement(fragment, "b", id="40", B="10", E="18", Order="1")
    return ET.tostring(root, encoding="unicode")


GRAPH_ONLY = _phenol()
POSITIONED_GRAPH = _phenol(True)
EXPLICIT_OH_GRAPH = _phenol(True, True)


def _bond_lengths(root: ET.Element) -> list[float]:
    nodes = {node.get("id"): node for node in root.findall(".//n") if node.get("p")}
    lengths: list[float] = []
    for bond in root.findall(".//b"):
        begin = bond.get("B")
        end = bond.get("E")
        if begin not in nodes or end not in nodes:
            continue
        x1, y1 = map(float, nodes[begin].get("p").split())
        x2, y2 = map(float, nodes[end].get("p").split())
        lengths.append(math.hypot(x2 - x1, y2 - y1))
    return lengths


def test_fixed_document_preserves_existing_coordinates() -> None:
    depicted, report = depict_standard_cdxml(POSITIONED_GRAPH)
    assert report["mode"] == "preserved"
    root = ET.fromstring(depicted)
    oxygen = root.find('.//n[@id="18"]')
    assert oxygen is not None
    assert oxygen.get("p") == "48.8 20"
    assert oxygen.findtext(".//s") == "OH"


def test_explicit_oh_preserves_coordinates_and_hydrogen_count() -> None:
    depicted, report = depict_standard_cdxml(EXPLICIT_OH_GRAPH)
    assert report["mode"] == "preserved"
    root = ET.fromstring(depicted)
    oxygen = root.find('.//n[@id="18"]')
    assert oxygen is not None
    assert oxygen.get("NumHydrogens") == "1"
    assert oxygen.get("p") == "48.8 20"


@pytest.mark.parametrize("fixture", [POSITIONED_GRAPH, EXPLICIT_OH_GRAPH])
def test_rejects_partial_geometry(fixture: str) -> None:
    root = ET.fromstring(fixture)
    node = root.find('.//n[@id="18"]')
    assert node is not None
    node.attrib.pop("p", None)
    broken = ET.tostring(root, encoding="unicode")
    with pytest.raises(ValueError, match="partial geometry"):
        depict_standard_cdxml(broken)


def test_graph_only_sample_receives_coordinates_at_reference_bond_length() -> None:
    depicted, report = depict_standard_cdxml(GRAPH_ONLY)
    assert report["mode"] == "depicted"
    assert report["backend"] == "rdkit"
    root = ET.fromstring(depicted)
    assert all(node.get("p") for node in root.findall(".//n"))
    lengths = sorted(_bond_lengths(root))
    assert lengths
    bond_length = float(root.get("BondLength", "14.4"))
    assert lengths[0] == pytest.approx(bond_length, rel=1e-5, abs=1e-3)
    assert min(lengths) == pytest.approx(max(lengths), rel=0.1, abs=0.5)


def test_graph_depiction_adds_neutral_phenolic_oh_label() -> None:
    depicted, _ = depict_standard_cdxml(GRAPH_ONLY)
    root = ET.fromstring(depicted)
    oxygen = root.find('.//n[@id="18"]')
    assert oxygen is not None
    assert oxygen.get("NumHydrogens") == "1"
    text = oxygen.find("t")
    assert text is not None
    assert text.findtext("s") == "OH"


def test_depicted_samples_import_with_explicit_oh_display() -> None:
    for raw in (GRAPH_ONLY, EXPLICIT_OH_GRAPH):
        depicted, _ = depict_standard_cdxml(raw)
        document = parse_cdxml_document(depicted.encode("utf-8"))
        atoms = document.state["model"]["atoms"]
        oxygen = next(atom for atom in atoms.values() if atom["element"] == "OH")
        assert oxygen["explicit_label"] is True


def test_headless_depiction_module_imports_neither_qt_nor_rdkit() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import chemvas.features.cdxml_standard_depiction; "
                "import chemvas.features.cdxml_render_preprocessing; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules); "
                "assert not any(name == 'rdkit' or name.startswith('rdkit.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "app", **os.environ},
    )
    assert result.returncode == 0, result.stderr


def test_render_document_graph_only_without_prepass(tmp_path: Path) -> None:
    source = tmp_path / "graph.cdxml"
    output = tmp_path / "out.svg"
    source.write_text(GRAPH_ONLY, encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "render-document",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "app", **os.environ},
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert (
        json.loads(result.stdout)["source_sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )
    assert "<svg" in output.read_text(encoding="utf-8")


def test_render_document_preserves_coordinates_and_shows_oh(tmp_path: Path) -> None:
    source = tmp_path / "fixed.cdxml"
    output = tmp_path / "fixed.svg"
    source.write_text(POSITIONED_GRAPH, encoding="utf-8")
    document = read_exact_document(source, preprocess_for_render=True).document
    oxygen = next(
        atom
        for atom in document.state["model"]["atoms"].values()
        if atom["element"] == "OH"
    )
    assert oxygen["explicit_label"] is True
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "render-document",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "app", **os.environ},
    )
    assert result.returncode == 0, result.stderr
    assert output.is_file()


def test_single_atom_without_bonds_depicts() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><fragment id="2">'
        '<n id="1" Element="6" />'
        "</fragment></page></CDXML>"
    )
    depicted, report = depict_standard_cdxml(raw)
    assert report["mode"] == "depicted"
    root = ET.fromstring(depicted)
    assert root.find('.//n[@id="1"]').get("p")


def test_rejects_duplicate_atom_ids() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><fragment id="2">'
        '<n id="1" Element="6" /><n id="1" Element="8" />'
        '<b id="10" B="1" E="1" Order="1" />'
        "</fragment></page></CDXML>"
    )
    with pytest.raises(ValueError, match="duplicate atom id"):
        depict_standard_cdxml(raw)


def test_rejects_dangling_bond_reference() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><fragment id="2">'
        '<n id="1" Element="6" /><n id="2" Element="6" />'
        '<b id="10" B="1" E="99" Order="1" />'
        "</fragment></page></CDXML>"
    )
    with pytest.raises(ValueError, match="missing atom id"):
        depict_standard_cdxml(raw)


def test_wedge_bond_requires_supplied_coordinates() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><fragment id="2">'
        '<n id="1" Element="6" /><n id="2" Element="6" /><n id="3" Element="8" />'
        '<b id="10" B="1" E="2" Order="1" Display="WedgeBegin" />'
        '<b id="11" B="2" E="3" Order="1" />'
        "</fragment></page></CDXML>"
    )
    with pytest.raises(ValueError, match="bond display"):
        depict_standard_cdxml(raw)


def test_rejects_stereo_atom_attribute() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><fragment id="2">'
        '<n id="1" Element="6" ABS="Absolute" /><n id="2" Element="6" />'
        '<b id="10" B="1" E="2" Order="1" />'
        "</fragment></page></CDXML>"
    )
    with pytest.raises(ValueError, match="stereochemistry"):
        depict_standard_cdxml(raw)


def test_preprocessing_skips_page_with_graphic() -> None:
    raw = (
        f'<CDXML {_ROOT_ATTRS}><page id="1"><graphic GraphicType="Line" />'
        f"<fragment id='2'><n id='1' Element='6' /></fragment></page></CDXML>"
    )
    assert maybe_preprocess_external_cdxml(raw, ET.fromstring(raw)) == raw


def test_preprocessing_applies_to_eligible_graph_only() -> None:
    processed = maybe_preprocess_external_cdxml(GRAPH_ONLY, ET.fromstring(GRAPH_ONLY))
    assert processed != GRAPH_ONLY
    assert 'p="' in processed


@pytest.mark.parametrize(
    "attrs", [{"Charge": "-1"}, {"NumHydrogens": "0"}, {"Radical": "Doublet"}]
)
def test_positioned_oxygen_with_explicit_chemistry_keeps_its_label(
    attrs: dict[str, str],
) -> None:
    root = ET.fromstring(POSITIONED_GRAPH)
    oxygen = root.find('.//n[@id="18"]')
    assert oxygen is not None
    oxygen.attrib.update(attrs)
    depicted, _ = depict_standard_cdxml(ET.tostring(root, encoding="unicode"))
    assert ET.fromstring(depicted).find('.//n[@id="18"]/t') is None
