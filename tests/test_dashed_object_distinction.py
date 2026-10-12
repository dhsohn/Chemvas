"""Existing dotted chemical bonds versus independent dashed drawing lines."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.ui.export.export_cdxml import (
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService
from tests.test_cdxml_export import _top_bonds, _top_nodes

pytestmark = pytest.mark.usefixtures("qt_application")


def state(style="dotted", order=1):
    return dict(
        model=serialize_model_state(
            MoleculeModel(
                atoms={0: Atom("C", 0.0, 0.0), 1: Atom("C", 40.0, 0.0)},
                bonds=[Bond(0, 1, order, style, "#123456")],
            )
        ),
        ring_fills=[],
        notes=[],
        marks=[],
        arrows=[
            dict(
                kind="line_dashed",
                start=(0.0, 70.0),
                end=(40.0, 70.0),
                control=None,
                double=False,
            )
        ],
        ts_brackets=[],
        shapes=[],
        orbitals=[],
        settings=serialize_settings(
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
        last_smiles_input=None,
    )


@pytest.mark.parametrize("operation", [preflight_cdxml, serialize_cdxml])
@pytest.mark.parametrize(
    "order",
    [True, 1.0, 2, 3, 1],
    ids=["bool", "float", "double", "triple", "int-single"],
)
def test_existing_dotted_direct_boundary(order, operation):
    with offscreen_document_scene(state(), command="existing-dotted-direct") as context:
        context.model.bonds[0].order = order
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=60.0
        )
        if type(order) is int and order == 1:
            operation(context, items, plan)
        else:
            with pytest.raises(CdxmlUnsupportedObjectError, match="exact integer"):
                operation(context, items, plan)


def test_existing_dotted_native_v9_and_two_xml_objects(tmp_path):
    assert CANVAS_FILE_VERSION == 9
    native = tmp_path / "unchanged-generation.chemvas"
    write_document(native, state(), CANVAS_FILE_VERSION)
    assert read_document(native).state["model"]["bonds"][0]["style"] == "dotted"
    with offscreen_document_scene(
        state(), command="existing-dotted-service"
    ) as context:
        output = tmp_path / "two.cdxml"
        FigureExportService(context).export_figure(
            str(output), fmt="cdxml", sizing="custom", target_width_mm=60.0
        )
    root = ET.fromstring(output.read_bytes())
    bonds = root.findall(".//fragment/b")
    assert len(bonds) == 1
    assert bonds[0].get("Display") == "Dash" and bonds[0].get("Order") == "1"
    assert bonds[0].get("B") != bonds[0].get("E")
    lines = root.findall("./page/arrow")
    assert len(lines) == 1 and lines[0].get("LineType") == "Dashed"
    assert len(root.findall(".//fragment/n")) == 2


def test_explicit_documentary_and_unlisted_chemical_dotted_can_coexist():
    from chemvas.features.export.cdxml_label_bindings import CdxmlDocumentaryContact
    from chemvas.ui.export.export_cdxml import CdxmlLabelBinding

    value = state()
    model = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 40.0, 0.0),
            2: Atom("P", 0.0, 100.0),
            3: Atom("Ar", 40.0, 100.0),
        },
        bonds=[Bond(0, 1, 1, "dotted"), Bond(2, 3, 1, "dotted")],
    )
    value["model"] = serialize_model_state(model)
    value["arrows"] = []
    with offscreen_document_scene(value, command="mixed-dotted") as context:
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=60.0
        )
        kwargs = dict(
            label_bindings={3: CdxmlLabelBinding.aryl_label("explicit caption")},
            documentary_contacts=(
                CdxmlDocumentaryContact(1, 2, 3, 1, "dotted", "ts_contact"),
            ),
        )
        preflight_cdxml(context, items, plan, **kwargs)
        root = ET.fromstring(serialize_cdxml(context, items, plan, **kwargs))
    assert len(root.findall(".//fragment/b")) == 1
    assert root.find(".//fragment/b").get("Display") == "Dash"
    assert len(root.findall("./page/arrow")) == 1


@pytest.mark.parametrize(
    "use_binding", [True, False], ids=["explicit-generic", "literal-Ar"]
)
@pytest.mark.parametrize("style", ["single", "wedge", "hash", "dotted", "multi"])
def test_generic_aryl_existing_attachment_intersection(style, use_binding):
    from chemvas.ui.export.export_cdxml import CdxmlLabelBinding

    value = state("single")
    model = MoleculeModel(
        atoms={0: Atom("P", 0.0, 0.0), 1: Atom("Ar", 40.0, 0.0)},
        bonds=[Bond(0, 1, 1, "single" if style == "multi" else style)],
    )
    if style == "multi":
        model.atoms[2] = Atom("H", 40.0, 40.0)
        model.bonds.append(Bond(2, 1, 1, "dotted"))
    value["model"] = serialize_model_state(model)
    value["arrows"] = []
    with offscreen_document_scene(value, command="generic-intersection") as context:
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=60.0
        )
        kwargs = dict(
            label_bindings={1: CdxmlLabelBinding.generic_aryl()}
            if use_binding
            else None
        )
        if not use_binding:
            # Ar is also argon: drawn text alone cannot authorize an aryl query.
            for operation in (preflight_cdxml, serialize_cdxml):
                with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
                    operation(context, items, plan, **kwargs)
            assert context.model.atoms[1].element == "Ar"
            return
        preflight_cdxml(context, items, plan, **kwargs)
        root = ET.fromstring(serialize_cdxml(context, items, plan, **kwargs))
        node = next(n for n in _top_nodes(root) if n.get("NodeType") == "Nickname")
        query = node.find('./fragment/n[@GenericNickname="ARY"]')
        assert query is not None and query.get("NodeType") == "GenericNickname"
        assert "".join(query.find("t").itertext()) == "ARY"
        assert "".join(node.find("t").itertext()) == "Ar"
        assert node.get("Element") is None and query.get("Element") is None
        assert not any(n.get("Element") == "18" for n in root.iter("n"))
        assert node.find("t").get("InterpretChemically") == "yes"
        bonds = _top_bonds(root)
        assert len(bonds) == (2 if style == "multi" else 1)
        assert all(bond.get("E") == node.get("id") for bond in bonds)
        display = {
            "single": None,
            "wedge": "WedgeBegin",
            "hash": "WedgedHashBegin",
            "dotted": "Dash",
            "multi": None,
        }[style]
        assert bonds[0].get("Display") == display
        if style == "multi":
            assert bonds[1].get("Display") == "Dash"
            assert bonds[1].get("Order") == "1"


@pytest.mark.parametrize(
    "use_binding", [False, True], ids=["literal-Ar", "explicit-generic"]
)
def test_isolated_aryl_drawing_label_without_invented_connections(use_binding):
    from chemvas.ui.export.export_cdxml import CdxmlLabelBinding

    value = state("single")
    value["model"] = serialize_model_state(
        MoleculeModel(atoms={0: Atom("Ar", 20.0, 20.0, explicit_label=True)}, bonds=[])
    )
    value["arrows"] = []
    with offscreen_document_scene(value, command="isolated-Ar-drawing") as context:
        items, plan = FigureExportService(context)._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=60.0
        )
        kwargs = dict(
            label_bindings={0: CdxmlLabelBinding.generic_aryl()}
            if use_binding
            else None
        )
        if not use_binding:
            for operation in (preflight_cdxml, serialize_cdxml):
                with pytest.raises(CdxmlUnsupportedObjectError, match="ambiguous"):
                    operation(context, items, plan, **kwargs)
            assert context.model.atoms[0].element == "Ar"
            return
        preflight_cdxml(context, items, plan, **kwargs)
        root = ET.fromstring(serialize_cdxml(context, items, plan, **kwargs))
    nodes = _top_nodes(root)
    assert len(nodes) == 1
    node = nodes[0]
    assert node.get("NodeType") == "Nickname" and node.get("Element") is None
    query = node.find('./fragment/n[@GenericNickname="ARY"]')
    assert query is not None and query.get("Element") is None
    assert node.findall('./fragment/n[@NodeType="ExternalConnectionPoint"]') == []
    assert "".join(node.find("t").itertext()) == "Ar"
    assert node.find("t").get("InterpretChemically") == "yes"
    assert root.findall(".//b") == []
