"""CDXML export: opt-in v2 documentary TS contacts (synthetic fixtures only).

These tests describe an explicit sidecar contract for turning selected native
order-1 dotted contacts into non-chemical dashed ``graphic`` lines while the
drawn ``Ar`` label exports as a non-chemical page caption (no ``<n>``) with a
caller-supplied author note. They exercise ``parse_cdxml_label_bindings`` and the figure
export service path only; they are not ChemDraw visual or roundtrip evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    deserialize_model_state,
    serialize_model_state,
    serialize_settings,
)
from chemvas.domain.json_io import strict_json_loads
from chemvas.features.export.cdxml_label_bindings import (
    CDXML_LABEL_BINDINGS_FORMAT,
    CDXML_LABEL_BINDINGS_VERSION,
    CdxmlDocumentaryContact,
    CdxmlLabelBindings,
    authorize_documentary_contact_for_export,
    parse_cdxml_label_bindings,
)

if TYPE_CHECKING:
    from chemvas.features.export.plan import ExportPlan
    from chemvas.ui.scene.scene_render_context import SceneRenderContext

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap.document_cli_shared import offscreen_document_scene
from chemvas.ui.export.export_cdxml import (
    CdxmlLabelBinding,
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.figure_export_service import FigureExportService

pytestmark = pytest.mark.usefixtures("qt_application")

H_A = "H\u1d43"
_AUTHOR_NOTE = "ortho-OH/tBu substituted aryl"
_TS_CLASS = "ts_contact"
_Z_LEAF_TAGS = ("n", "b", "t", "graphic", "arrow")
_Z_MAX = 32767
_COORD_TOLERANCE = 1e-6

# Regression endpoint ids from the approved FPh TS inventory (synthetic layout only).
_OH_P = 111
_OH_H = 114
_OH_AR = 115
_OH_BOND_P_AR = 113
_OH_BOND_H_AR = 118

_OME_P = 201
_OME_H = 209
_OME_AR = 205
_OME_BOND_P_AR = 203
_OME_BOND_H_AR = 208

# Filler bonds only occupy distant bond slots 0..max_id (excluding documentary
# slots). Each is an isolated C–C single with normal 20px length and ≥50px gap
# between consecutive filler fragments so atom/bond paint bounds do not overlap
# and the CDXML fragment interleaving guard stays a real check.
_FILLER_BOND_LENGTH_PX = 20.0
_FILLER_FRAGMENT_SPACING_PX = 50.0
_FILLER_SLOT_PITCH_PX = _FILLER_BOND_LENGTH_PX + _FILLER_FRAGMENT_SPACING_PX


def _line_endpoints(line):
    assert line.tag == "arrow"
    assert line.get("ArrowheadHead", "None") == "None"
    assert line.get("ArrowheadTail", "None") == "None"
    tail, head = line.get("Tail3D").split(), line.get("Head3D").split()
    assert tail[2] == head[2] == "0"
    return " ".join((*tail[:2], *head[:2]))


def _settings() -> dict[str, object]:
    return serialize_settings(
        bond_length_px=20.0,
        arrow_line_width=1.5,
        arrow_head_scale=0.4,
        orbital_phase_enabled=True,
        text_font_size=12,
        text_font_weight=400,
        text_italic=False,
        sheet_size="A4",
        sheet_orientation="portrait",
    )


def _state_from_model(model: MoleculeModel) -> dict[str, object]:
    return {
        "model": serialize_model_state(model),
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


def _document_digest(state: dict[str, object]) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.chemvas"
        write_document(path, state, CANVAS_FILE_VERSION)
        data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def _binding_entry(
    atom_id: int,
    expected_label: str,
    meaning: str,
    **fields: object,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "atom_id": atom_id,
        "expected_label": expected_label,
        "meaning": meaning,
        **fields,
    }
    return entry


def _contact_entry(
    bond_id: int,
    a: int,
    b: int,
    *,
    contact_id: str | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "bond_id": bond_id,
        "a": a,
        "b": b,
        "native_order": 1,
        "native_style": "dotted",
        "classification": _TS_CLASS,
    }
    if contact_id is not None:
        entry["contact_id"] = contact_id
    return entry


def _v2_payload(
    source_sha256: str,
    *,
    bindings: list[dict[str, object]],
    documentary_contacts: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "format": CDXML_LABEL_BINDINGS_FORMAT,
        "version": 2,
        "source_sha256": source_sha256,
        "bindings": bindings,
        "documentary_contacts": documentary_contacts,
    }


def _parse_sidecar(
    payload: dict[str, object], source_sha256: str
) -> CdxmlLabelBindings:
    text = json.dumps(payload, ensure_ascii=False)
    raw = text.encode("utf-8")
    return parse_cdxml_label_bindings(
        strict_json_loads(raw),
        sidecar_sha256=hashlib.sha256(raw).hexdigest(),
        source_sha256=source_sha256,
    )


def _fph_bindings(ar_id: int, h_id: int) -> list[dict[str, object]]:
    return [
        _binding_entry(
            ar_id,
            "Ar",
            "aryl_label",
            author_note=_AUTHOR_NOTE,
        ),
        _binding_entry(h_id, H_A, "element", element="H"),
    ]


def _fill_bond_slots(
    model: MoleculeModel,
    max_bond_id: int,
    documentary: dict[int, Bond],
    *,
    filler_y: float,
) -> None:
    next_atom = 10_000
    for slot in range(max_bond_id + 1):
        if slot in documentary:
            model.set_bond(slot, documentary[slot])
            continue
        a_id = next_atom
        b_id = next_atom + 1
        next_atom += 2
        x0 = float(slot) * _FILLER_SLOT_PITCH_PX
        model.atoms[a_id] = Atom("C", x0, filler_y)
        model.atoms[b_id] = Atom("C", x0 + _FILLER_BOND_LENGTH_PX, filler_y)
        model.set_bond(slot, Bond(a_id, b_id))


def _oh_fph_state() -> dict[str, object]:
    model = MoleculeModel(
        atoms={
            _OH_P: Atom("P", 0.0, 0.0, explicit_label=True),
            _OH_H: Atom(H_A, -30.0, 35.0, explicit_label=True),
            _OH_AR: Atom("Ar", 55.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    _fill_bond_slots(
        model,
        _OH_BOND_H_AR,
        {
            _OH_BOND_P_AR: Bond(_OH_P, _OH_AR, style="dotted"),
            _OH_BOND_H_AR: Bond(_OH_H, _OH_AR, style="dotted"),
        },
        filler_y=-400.0,
    )
    return _state_from_model(model)


def _ome_fph_state() -> dict[str, object]:
    model = MoleculeModel(
        atoms={
            _OME_P: Atom("P", 0.0, 0.0, explicit_label=True),
            _OME_H: Atom(H_A, -30.0, 35.0, explicit_label=True),
            _OME_AR: Atom("Ar", 55.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    _fill_bond_slots(
        model,
        _OME_BOND_H_AR,
        {
            _OME_BOND_P_AR: Bond(_OME_P, _OME_AR, style="dotted"),
            _OME_BOND_H_AR: Bond(_OME_H, _OME_AR, style="dotted"),
        },
        filler_y=-500.0,
    )
    return _state_from_model(model)


def _generic_ph_to_ar_state() -> dict[str, object]:
    p_id, h_id, ar_id = 31, 32, 33
    model = MoleculeModel(
        atoms={
            p_id: Atom("P", 0.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, -25.0, 30.0, explicit_label=True),
            ar_id: Atom("Ar", 50.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(p_id, ar_id, style="dotted"))
    model.set_bond(1, Bond(h_id, ar_id, style="dotted"))
    return _state_from_model(model), p_id, h_id, ar_id


def _choices_for_fph_state(
    state: dict[str, object],
    *,
    ar_id: int,
    h_id: int,
    contacts: list[dict[str, object]],
) -> CdxmlLabelBindings:
    _, source_sha = _document_digest(state)
    payload = _v2_payload(
        source_sha,
        bindings=_fph_bindings(ar_id, h_id),
        documentary_contacts=contacts,
    )
    return _parse_sidecar(payload, source_sha)


def _export_with_choices(
    state: dict[str, object],
    choices: CdxmlLabelBindings,
    *,
    documentary_contacts: tuple[CdxmlDocumentaryContact, ...] | None = None,
    scope: str = "sheet",
    selection: list[object] | None = None,
) -> tuple[bytes, ExportPlan, dict[int, tuple[float, float]]]:
    with offscreen_document_scene(state, command="test-cdxml-documentary") as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing="custom",
            target_width_mm=170.0,
        )
        typed = service._typed_label_bindings(items, choices)
        documentary = documentary_contacts
        if documentary is None:
            documentary = choices.documentary_contacts or None
        anchors = _aryl_label_anchors(context, plan, typed)
        preflight_cdxml(
            context,
            items,
            plan,
            label_bindings=typed,
            documentary_contacts=documentary,
        )
        xml_bytes = serialize_cdxml(
            context,
            items,
            plan,
            label_bindings=typed,
            documentary_contacts=documentary,
        )
        return xml_bytes, plan, anchors


def _export_with_direct_bindings(
    state: dict[str, object],
    label_bindings: dict[int, CdxmlLabelBinding],
    *,
    documentary_contacts: tuple[CdxmlDocumentaryContact, ...] | None = None,
    scope: str = "sheet",
    selection: list[object] | None = None,
) -> tuple[bytes, ExportPlan, dict[int, tuple[float, float]]]:
    with offscreen_document_scene(state, command="test-cdxml-documentary") as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope=scope,
            selection=selection,
            sizing="custom",
            target_width_mm=170.0,
        )
        anchors = _aryl_label_anchors(context, plan, label_bindings)
        preflight_cdxml(
            context,
            items,
            plan,
            label_bindings=label_bindings,
            documentary_contacts=documentary_contacts,
        )
        xml_bytes = serialize_cdxml(
            context,
            items,
            plan,
            label_bindings=label_bindings,
            documentary_contacts=documentary_contacts,
        )
        return xml_bytes, plan, anchors


def _page_fragments(root: ET.Element) -> list[ET.Element]:
    page = root.find("page")
    assert page is not None
    return page.findall("fragment")


def _top_nodes(root: ET.Element) -> list[ET.Element]:
    return [n for frag in _page_fragments(root) for n in frag.findall("n")]


def _top_bonds(root: ET.Element) -> list[ET.Element]:
    return [b for frag in _page_fragments(root) for b in frag.findall("b")]


def _page_line_graphics(root: ET.Element) -> list[ET.Element]:
    page = root.find("page")
    assert page is not None
    return [g for g in page if g.tag == "arrow"]


def _label_text(node: ET.Element) -> str:
    text = node.find("t")
    if text is None:
        return ""
    return "".join(run.text or "" for run in text.findall("s"))


def _point(node: ET.Element) -> tuple[float, float]:
    return tuple(float(value) for value in node.get("p").split())


def _expected_point(plan: ExportPlan, atom: Atom) -> tuple[float, float]:
    scale = plan.out_w_pt / plan.source_w
    return (
        (atom.x - plan.source_x) * scale,
        (atom.y - plan.source_y) * scale,
    )


def _scene_label_left_baseline_pt(
    context: SceneRenderContext,
    atom_id: int,
    plan: ExportPlan,
) -> tuple[float, float]:
    """Left baseline anchor of the drawn atom label in CDXML page coordinates."""
    from PyQt6.QtWidgets import QGraphicsTextItem

    item = context.state.atom_graphics_state.atom_items.get(atom_id)
    assert item is not None and item.isVisible()
    assert isinstance(item, QGraphicsTextItem)
    document = item.document()
    assert document is not None
    block = document.begin()
    assert block.isValid()
    layout = block.layout()
    assert layout is not None and layout.lineCount() > 0
    line = layout.lineAt(0)
    local_x = layout.position().x() + line.x()
    local_baseline_y = layout.position().y() + line.y() + line.ascent()
    transform = item.sceneTransform()
    scene_label_x = (
        transform.m11() * local_x + transform.m21() * local_baseline_y + transform.dx()
    )
    scene_baseline_y = (
        transform.m12() * local_x + transform.m22() * local_baseline_y + transform.dy()
    )
    scale = plan.out_w_pt / plan.source_w
    return (
        (scene_label_x - plan.source_x) * scale,
        (scene_baseline_y - plan.source_y) * scale,
    )


def _aryl_label_anchors(
    context: SceneRenderContext,
    plan: ExportPlan,
    label_bindings: dict[int, CdxmlLabelBinding],
) -> dict[int, tuple[float, float]]:
    return {
        atom_id: _scene_label_left_baseline_pt(context, atom_id, plan)
        for atom_id, binding in label_bindings.items()
        if binding.meaning == "aryl_label"
    }


def _node_ids_by_atom(
    root: ET.Element,
    plan: ExportPlan,
    atoms: dict[int, Atom],
    *,
    exclude_atom_ids: frozenset[int] = frozenset(),
) -> dict[int, str]:
    expected = {
        atom_id: _expected_point(plan, atom)
        for atom_id, atom in atoms.items()
        if atom_id not in exclude_atom_ids
    }
    found: dict[int, str] = {}
    for node in _top_nodes(root):
        position = _point(node)
        for atom_id, target in expected.items():
            if math.dist(position, target) < _COORD_TOLERANCE:
                found[atom_id] = node.get("id")
    assert len(found) == len(expected)
    return found


def _page_text_elements(root: ET.Element) -> list[ET.Element]:
    page = root.find("page")
    assert page is not None
    return [el for el in page if el.tag == "t"]


def _caption_text(t_el: ET.Element) -> str:
    return "".join(run.text or "" for run in t_el.findall("s"))


def _objecttag_values(parent: ET.Element) -> list[str]:
    return [tag.get("Value") or "" for tag in parent.findall("objecttag")]


def _caption_metadata(values: list[str]) -> dict[str, str]:
    for value in values:
        if "meaning=aryl_label" in value and "atom_id=" in value:
            meta: dict[str, str] = {}
            for line in value.splitlines():
                key, sep, val = line.partition("=")
                if sep:
                    meta[key] = val
            return meta
    return {}


def _assert_aryl_label_caption(
    root: ET.Element,
    plan: ExportPlan,
    ar_id: int,
    atom: Atom,
    *,
    expected_anchor_pt: tuple[float, float],
) -> ET.Element:
    captions = [
        t
        for t in _page_text_elements(root)
        if t.get("InterpretChemically") == "no" and _caption_text(t) == "Ar"
    ]
    assert len(captions) == 1
    caption = captions[0]
    tags = caption.findall("objecttag")
    _assert_objecttags_are_opaque_metadata(tags)
    values = _objecttag_values(caption)
    assert _AUTHOR_NOTE in values
    meta = _caption_metadata(values)
    assert meta["atom_id"] == str(ar_id)
    assert meta["expected_label"] == "Ar"
    assert meta["meaning"] == "aryl_label"
    assert meta["unexpanded_aryl_label"] == "yes"
    assert meta["chemical_atom_identity"] == "none"
    assert meta["automatic_tracking"] == "no"
    assert caption.get("Justification") == "Left"
    assert math.dist(_point(caption), expected_anchor_pt) < _COORD_TOLERANCE
    for node in _top_nodes(root):
        if math.dist(_point(node), _expected_point(plan, atom)) < _COORD_TOLERANCE:
            pytest.fail("aryl_label must not emit a chemical atom node at Ar")
    return caption


def _assert_unique_positive_z(root: ET.Element) -> None:
    values: list[int] = []
    for element in root.iter():
        if element.tag not in _Z_LEAF_TAGS:
            continue
        z_attr = element.get("Z")
        assert z_attr is not None, f"drawable leaf <{element.tag}> is missing Z"
        z = int(z_attr)
        values.append(z)
    assert values
    assert all(0 < z <= _Z_MAX for z in values)
    assert len(values) == len(set(values))


def _assert_objecttags_are_opaque_metadata(tags: list[ET.Element]) -> None:
    for tag in tags:
        name = tag.get("Name") or ""
        assert name.startswith("Chemvas.")
        assert not name.startswith("CS")
        assert not name.startswith("CD")
        assert tag.get("TagType") == "String"
        assert tag.get("Persistent") == "yes"
        assert tag.get("Tracking") == "no"
        value = tag.get("Value") or ""
        assert not value.startswith("CS")
        assert not value.startswith("CD")


def _assert_no_chemical_b_between(
    bonds: list[ET.Element],
    node_a: str,
    node_b: str,
) -> None:
    pair = {node_a, node_b}
    for bond in bonds:
        ends = {bond.get("B"), bond.get("E")}
        assert ends != pair


def _documentary_contact_metadata(graphic: ET.Element) -> dict[str, str]:
    meta: dict[str, str] = {}
    for tag in graphic.findall("objecttag"):
        for line in (tag.get("Value") or "").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                meta[key] = value
    return meta


def _bbox_endpoint_pair(bbox: str) -> tuple[tuple[float, float], tuple[float, float]]:
    x1, y1, x2, y2 = (float(part) for part in bbox.split())
    return (x1, y1), (x2, y2)


def _unordered_points_match(
    actual: tuple[tuple[float, float], tuple[float, float]],
    expected_a: tuple[float, float],
    expected_b: tuple[float, float],
) -> bool:
    p1, p2 = actual
    forward = (
        math.dist(p1, expected_a) < _COORD_TOLERANCE
        and math.dist(p2, expected_b) < _COORD_TOLERANCE
    )
    reverse = (
        math.dist(p1, expected_b) < _COORD_TOLERANCE
        and math.dist(p2, expected_a) < _COORD_TOLERANCE
    )
    return forward or reverse


def _assert_documentary_contact_graphics(
    root: ET.Element,
    plan: ExportPlan,
    state: dict[str, object],
    *,
    contact_pairs: list[tuple[int, int]],
    bond_ids: list[int],
    aryl_label_anchors: dict[int, tuple[float, float]],
) -> None:
    model = deserialize_model_state(state["model"])
    ar_id = next(
        atom_id for atom_id, atom in model.atoms.items() if atom.element == "Ar"
    )
    nodes = _node_ids_by_atom(
        root,
        plan,
        model.atoms,
        exclude_atom_ids=frozenset({ar_id}),
    )
    _assert_aryl_label_caption(
        root,
        plan,
        ar_id,
        model.atoms[ar_id],
        expected_anchor_pt=aryl_label_anchors[ar_id],
    )
    dashed = [g for g in _page_line_graphics(root) if g.get("LineType") == "Dashed"]
    assert len(dashed) == len(contact_pairs)
    expected_by_bond = dict(zip(bond_ids, contact_pairs, strict=True))
    metadata_by_bond: dict[int, ET.Element] = {}
    for graphic in dashed:
        meta = _documentary_contact_metadata(graphic)
        bond_key = meta.get("bond_id")
        assert bond_key is not None, (
            "documentary graphic metadata must include bond_id="
        )
        assert bond_key.isdigit(), (
            f"bond_id metadata must be an integer, got {bond_key!r}"
        )
        bond_id = int(bond_key)
        assert bond_id not in metadata_by_bond, (
            f"duplicate documentary graphic for bond {bond_id}"
        )
        metadata_by_bond[bond_id] = graphic
    assert set(metadata_by_bond) == set(expected_by_bond)
    bonds = _top_bonds(root)
    for left, right in contact_pairs:
        if left in nodes and right in nodes:
            _assert_no_chemical_b_between(bonds, nodes[left], nodes[right])
    for bond in bonds:
        assert bond.get("Order") != "0.5"
    for node in _top_nodes(root):
        if node.get("Element") == "18":
            pytest.fail("drawn Ar must not export as argon Element 18")
        if node.get("NodeType") == "Nickname" and _label_text(node) == "Ar":
            pytest.fail("aryl_label must not expand to a bound aryl graph")
        if node.get("NodeType") in ("GenericNickname", "Unspecified") and (
            node.get("GenericNickname") == "Ar" or _label_text(node) == "Ar"
        ):
            pytest.fail("aryl_label must not export as a chemical Ar node")
    for bond_id, (atom_a, atom_b) in expected_by_bond.items():
        graphic = metadata_by_bond[bond_id]
        tags = graphic.findall("objecttag")
        _assert_objecttags_are_opaque_metadata(tags)
        meta = _documentary_contact_metadata(graphic)
        assert meta["classification"] == _TS_CLASS
        assert meta["a"] == str(atom_a)
        assert meta["b"] == str(atom_b)
        assert meta["native_order"] == "1"
        assert meta["native_style"] == "dotted"
        assert meta["chemical_meaning"] == "unspecified"
        bbox = _line_endpoints(graphic)
        assert bbox is not None
        endpoints = _bbox_endpoint_pair(bbox)
        assert _unordered_points_match(
            endpoints,
            _expected_point(plan, model.atoms[atom_a]),
            _expected_point(plan, model.atoms[atom_b]),
        )
    _assert_unique_positive_z(root)


# ── v1 sidecar remains strict (parser-only) ─────────────────────────


def test_v1_parse_still_accepts_existing_meanings() -> None:
    payload = {
        "format": CDXML_LABEL_BINDINGS_FORMAT,
        "version": CDXML_LABEL_BINDINGS_VERSION,
        "source_sha256": "a" * 64,
        "bindings": [
            _binding_entry(1, "Ar", "generic_aryl"),
            _binding_entry(2, H_A, "element", element="H"),
        ],
    }
    parsed = parse_cdxml_label_bindings(
        payload,
        sidecar_sha256="b" * 64,
        source_sha256="a" * 64,
    )
    assert parsed.entries[0].meaning == "generic_aryl"
    assert parsed.entries[1].meaning == "element"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        (
            {
                "format": CDXML_LABEL_BINDINGS_FORMAT,
                "version": 1,
                "source_sha256": "c" * 64,
                "bindings": [_binding_entry(1, "Ar", "generic_aryl")],
                "documentary_contacts": [],
            },
            r"unknown keys \['documentary_contacts'\]",
        ),
        (
            {
                "format": CDXML_LABEL_BINDINGS_FORMAT,
                "version": 1,
                "source_sha256": "c" * 64,
                "bindings": [
                    _binding_entry(1, "Ar", "aryl_label", author_note="note"),
                ],
            },
            "meaning must be one of",
        ),
    ],
)
def test_v1_refuses_v2_only_fields(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_cdxml_label_bindings(
            payload,
            sidecar_sha256="d" * 64,
            source_sha256="c" * 64,
        )


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda sha: _v2_payload(sha, bindings=[], documentary_contacts=[]),
            "bindings must be a non-empty JSON array",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[_binding_entry(1, "Ar", "aryl_label")],
                documentary_contacts=[_contact_entry(0, 1, 2)],
            ),
            r"missing keys \['author_note'\]",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[
                    _binding_entry(1, "Ar", "aryl_label", author_note=""),
                ],
                documentary_contacts=[_contact_entry(0, 1, 2)],
            ),
            "author_note must be a non-empty string",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[
                    _binding_entry(1, "Ph", "aryl_label", author_note="note"),
                ],
                documentary_contacts=[_contact_entry(0, 1, 2)],
            ),
            "expected_label",
        ),
        (
            lambda sha: {
                "format": CDXML_LABEL_BINDINGS_FORMAT,
                "version": 2,
                "source_sha256": sha,
                "bindings": [
                    _binding_entry(1, "Ar", "aryl_label", author_note="note"),
                ],
            },
            r"missing keys \['documentary_contacts'\]",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[
                    _binding_entry(1, "Ar", "aryl_label", author_note="note"),
                    _binding_entry(1, "Ar", "element", element="Ar"),
                ],
                documentary_contacts=[_contact_entry(0, 1, 2)],
            ),
            "repeats atom_id 1",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[_binding_entry(1, "Ar", "aryl_label", author_note="note")],
                documentary_contacts=[
                    _contact_entry(0, 1, 2),
                    _contact_entry(0, 3, 4),
                ],
            ),
            "repeats bond_id 0",
        ),
        (
            lambda sha: _v2_payload(
                sha,
                bindings=[_binding_entry(1, "Ar", "aryl_label", author_note="note")],
                documentary_contacts=[_contact_entry(0, 1, 2, contact_id="")],
            ),
            "contact_id must be a non-empty string",
        ),
    ],
    ids=[
        "empty-bindings",
        "missing-author-note-key",
        "empty-author-note",
        "wrong-aryl-label-text",
        "missing-documentary-contacts",
        "duplicate-atom-binding",
        "duplicate-bond-contact",
        "empty-contact-id",
    ],
)
def test_v2_malformed_sidecars_are_refused(mutator, match: str) -> None:
    source_sha = "e" * 64
    payload = mutator(source_sha)
    with pytest.raises(ValueError, match=match):
        _parse_sidecar(payload, source_sha)


def test_v2_source_sha_mismatch_is_refused() -> None:
    payload = _v2_payload(
        "f" * 64,
        bindings=[_binding_entry(1, "Ar", "aryl_label", author_note="note")],
        documentary_contacts=[_contact_entry(0, 1, 2)],
    )
    with pytest.raises(ValueError, match="different document"):
        _parse_sidecar(payload, "0" * 64)


# ── Positive documentary export (RED until v2 parse + exporter land) ──


def test_oh_fph_ts_contacts_export_two_documentary_dashed_lines() -> None:
    state = _oh_fph_state()
    choices = _choices_for_fph_state(
        state,
        ar_id=_OH_AR,
        h_id=_OH_H,
        contacts=[
            _contact_entry(_OH_BOND_P_AR, _OH_P, _OH_AR, contact_id="oh-p-ar"),
            _contact_entry(_OH_BOND_H_AR, _OH_H, _OH_AR, contact_id="oh-h-ar"),
        ],
    )
    xml_bytes, plan, anchors = _export_with_choices(state, choices)
    root = ET.fromstring(xml_bytes)
    _assert_documentary_contact_graphics(
        root,
        plan,
        state,
        contact_pairs=[(_OH_P, _OH_AR), (_OH_H, _OH_AR)],
        bond_ids=[_OH_BOND_P_AR, _OH_BOND_H_AR],
        aryl_label_anchors=anchors,
    )
    (hydrogen,) = [n for n in _top_nodes(root) if _label_text(n) == H_A]
    assert hydrogen.get("Element") == "1"
    assert hydrogen.get("NodeType") is None


def test_ome_fph_ts_contacts_preserve_bond_slots_203_and_208() -> None:
    state = _ome_fph_state()
    choices = _choices_for_fph_state(
        state,
        ar_id=_OME_AR,
        h_id=_OME_H,
        contacts=[
            _contact_entry(_OME_BOND_P_AR, _OME_P, _OME_AR, contact_id="ome-p-ar"),
            _contact_entry(_OME_BOND_H_AR, _OME_H, _OME_AR, contact_id="ome-h-ar"),
        ],
    )
    xml_bytes, plan, anchors = _export_with_choices(state, choices)
    root = ET.fromstring(xml_bytes)
    _assert_documentary_contact_graphics(
        root,
        plan,
        state,
        contact_pairs=[(_OME_P, _OME_AR), (_OME_H, _OME_AR)],
        bond_ids=[_OME_BOND_P_AR, _OME_BOND_H_AR],
        aryl_label_anchors=anchors,
    )


def test_generic_ph_to_ar_documentary_contacts() -> None:
    state, p_id, h_id, ar_id = _generic_ph_to_ar_state()
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(0, p_id, ar_id, contact_id="gen-p-ar"),
                _contact_entry(1, h_id, ar_id, contact_id="gen-h-ar"),
            ],
        ),
        source_sha,
    )
    xml_bytes, plan, anchors = _export_with_choices(state, choices)
    root = ET.fromstring(xml_bytes)
    _assert_documentary_contact_graphics(
        root,
        plan,
        state,
        contact_pairs=[(p_id, ar_id), (h_id, ar_id)],
        bond_ids=[0, 1],
        aryl_label_anchors=anchors,
    )


def _documentary_aryl_two_contact_state(
    *,
    center_id: int,
    h_id: int,
    ar_id: int,
    chemical_bond: Bond,
    h_ar_bond_id: int = 1,
) -> dict[str, object]:
    model = MoleculeModel(
        atoms={
            center_id: Atom("C", 0.0, 0.0),
            h_id: Atom(H_A, -25.0, 30.0, explicit_label=True),
            ar_id: Atom("Ar", 50.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, chemical_bond)
    model.set_bond(h_ar_bond_id, Bond(h_id, ar_id, style="dotted"))
    return _state_from_model(model)


@pytest.mark.parametrize(
    ("style", "display", "reverse"),
    [
        ("single", None, False),
        ("wedge", "WedgeBegin", False),
        ("hash", "WedgedHashBegin", False),
        ("wedge", "WedgeBegin", True),
    ],
)
def test_native_chemical_edge_to_documentary_aryl_refuses_caption_export(
    style: str,
    display: str | None,
    reverse: bool,
) -> None:
    center_id, h_id, ar_id = 70, 71, 72
    chemical = (
        Bond(ar_id, center_id, style=style)
        if reverse
        else Bond(center_id, ar_id, style=style)
    )
    state = _documentary_aryl_two_contact_state(
        center_id=center_id,
        h_id=h_id,
        ar_id=ar_id,
        chemical_bond=chemical,
    )
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[_contact_entry(1, h_id, ar_id)],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="non-documentary bond on Ar"):
        _export_with_choices(state, choices)


def test_wedge_neighbor_stays_native_b_display_while_contacts_are_documentary() -> None:
    c_id, p_id, h_id, ar_id = 40, 41, 42, 43
    model = MoleculeModel(
        atoms={
            c_id: Atom("C", 0.0, 0.0),
            p_id: Atom("P", 25.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, 50.0, 35.0, explicit_label=True),
            ar_id: Atom("Ar", 80.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(c_id, p_id, style="wedge"))
    model.set_bond(1, Bond(p_id, ar_id, style="dotted"))
    model.set_bond(2, Bond(h_id, ar_id, style="dotted"))
    state = _state_from_model(model)
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(1, p_id, ar_id),
                _contact_entry(2, h_id, ar_id),
            ],
        ),
        source_sha,
    )
    from PyQt6.QtCore import Qt

    with offscreen_document_scene(state, command="test-wedge-documentary") as context:
        # These overlapping contacts must paint outside the chemical fragment's
        # rank range: a CDXML fragment cannot contain a page graphic between
        # its native wedge and atom objects. Change only the scene stacking.
        chemical_items = [
            item
            for item in context.scene.items()
            if (item.data(0) == "atom" and item.data(1) in (c_id, p_id))
            or (item.data(0) == "bond" and item.data(1) == 0)
        ]
        contact_items = [
            item
            for item in context.scene.items()
            if item.data(0) == "bond" and item.data(1) in (1, 2)
        ]
        assert chemical_items and len(contact_items) == 2
        top_z = max(item.zValue() for item in context.scene.items())
        for item in contact_items:
            item.setZValue(top_z + 1.0)
        order = list(context.scene.items(Qt.SortOrder.AscendingOrder))
        assert min(order.index(item) for item in contact_items) > max(
            order.index(item) for item in chemical_items
        )
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        typed = service._typed_label_bindings(items, choices)
        anchors = _aryl_label_anchors(context, plan, typed)
        preflight_cdxml(
            context,
            items,
            plan,
            label_bindings=typed,
            documentary_contacts=choices.documentary_contacts,
        )
        xml_bytes = serialize_cdxml(
            context,
            items,
            plan,
            label_bindings=typed,
            documentary_contacts=choices.documentary_contacts,
        )
    root = ET.fromstring(xml_bytes)
    model_atoms = deserialize_model_state(state["model"]).atoms
    nodes = _node_ids_by_atom(
        root,
        plan,
        model_atoms,
        exclude_atom_ids=frozenset({ar_id}),
    )
    _assert_aryl_label_caption(
        root,
        plan,
        ar_id,
        model_atoms[ar_id],
        expected_anchor_pt=anchors[ar_id],
    )
    stereo = next(
        b
        for b in _top_bonds(root)
        if {b.get("B"), b.get("E")} == {nodes[c_id], nodes[p_id]}
    )
    assert len(_top_bonds(root)) == 1
    assert stereo.get("B") == nodes[c_id]
    assert stereo.get("E") == nodes[p_id]
    assert stereo.get("Display") == "WedgeBegin"
    assert stereo.get("Order") is None
    dashed = [g for g in _page_line_graphics(root) if g.get("LineType") == "Dashed"]
    assert len(dashed) == 2


# ── Direct API aryl_label captions (no documentary_contacts) ─────────


def test_direct_api_isolated_aryl_label_exports_page_caption() -> None:
    ar_id = 801
    state = _state_from_model(
        MoleculeModel(
            atoms={ar_id: Atom("Ar", 12.0, -8.0, explicit_label=True)},
            bonds=[],
        )
    )
    bindings = {ar_id: CdxmlLabelBinding.aryl_label(_AUTHOR_NOTE)}
    xml_bytes, plan, anchors = _export_with_direct_bindings(state, bindings)
    root = ET.fromstring(xml_bytes)
    model = deserialize_model_state(state["model"])
    _assert_aryl_label_caption(
        root,
        plan,
        ar_id,
        model.atoms[ar_id],
        expected_anchor_pt=anchors[ar_id],
    )
    assert _top_bonds(root) == []
    assert _top_nodes(root) == []


@pytest.mark.parametrize("style", ["single", "wedge", "hash"])
def test_direct_api_bonded_aryl_label_refuses_without_documentary_permission(
    style: str,
) -> None:
    center_id, ar_id = 802, 803
    state = _state_from_model(
        MoleculeModel(
            atoms={
                center_id: Atom("C", 0.0, 0.0),
                ar_id: Atom("Ar", 50.0, 0.0, explicit_label=True),
            },
            bonds=[],
        )
    )
    model = deserialize_model_state(state["model"])
    model.set_bond(0, Bond(center_id, ar_id, style=style))
    state["model"] = serialize_model_state(model)
    bindings = {ar_id: CdxmlLabelBinding.aryl_label(_AUTHOR_NOTE)}
    with pytest.raises(CdxmlUnsupportedObjectError, match="non-documentary bond on Ar"):
        _export_with_direct_bindings(state, bindings)


def test_caption_aryl_refuses_bond_when_neighbor_outside_export_selection() -> None:
    center_id, ar_id = 810, 811
    state = _state_from_model(
        MoleculeModel(
            atoms={
                center_id: Atom("C", 0.0, 0.0),
                ar_id: Atom("Ar", 50.0, 0.0, explicit_label=True),
            },
            bonds=[],
        )
    )
    model = deserialize_model_state(state["model"])
    model.set_bond(0, Bond(center_id, ar_id, style="single"))
    state["model"] = serialize_model_state(model)
    bindings = {ar_id: CdxmlLabelBinding.aryl_label(_AUTHOR_NOTE)}
    with offscreen_document_scene(state, command="test-cdxml-documentary") as context:
        ar_item = next(
            item
            for item in context.scene.items()
            if item.data(0) == "atom" and item.data(1) == ar_id
        )
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="selection",
            selection=[ar_item],
            sizing="custom",
            target_width_mm=170.0,
        )
        with pytest.raises(
            CdxmlUnsupportedObjectError, match="non-documentary bond on Ar"
        ):
            preflight_cdxml(context, items, plan, label_bindings=bindings)
        with pytest.raises(
            CdxmlUnsupportedObjectError, match="non-documentary bond on Ar"
        ):
            serialize_cdxml(context, items, plan, label_bindings=bindings)


# ── Export refuses without explicit permission ───────────────────────


def test_dotted_pair_with_explicit_element_binding_exports_chemical_bonds() -> None:
    state = _oh_fph_state()
    _, source_sha = _document_digest(state)
    v1_only = parse_cdxml_label_bindings(
        {
            "format": CDXML_LABEL_BINDINGS_FORMAT,
            "version": CDXML_LABEL_BINDINGS_VERSION,
            "source_sha256": source_sha,
            "bindings": [
                _binding_entry(_OH_H, H_A, "element", element="H"),
                _binding_entry(_OH_AR, "Ar", "element", element="Ar"),
            ],
        },
        sidecar_sha256="a" * 64,
        source_sha256=source_sha,
    )
    xml_bytes, _, _ = _export_with_choices(state, v1_only)
    root = ET.fromstring(xml_bytes)
    dotted_bonds = [
        bond for bond in root.findall(".//fragment/b") if bond.get("Display") == "Dash"
    ]
    assert len(dotted_bonds) == 2
    assert all(bond.get("Order") == "1" for bond in dotted_bonds)
    assert root.findall("./page/arrow") == []


def test_unlisted_third_dotted_contact_refuses_even_with_two_permissions() -> None:
    p_id, h_id, ar_id, extra_id = 51, 52, 53, 54
    model = MoleculeModel(
        atoms={
            p_id: Atom("P", 0.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, -20.0, 25.0, explicit_label=True),
            ar_id: Atom("Ar", 40.0, 0.0, explicit_label=True),
            extra_id: Atom("O", 80.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(p_id, ar_id, style="dotted"))
    model.set_bond(1, Bond(h_id, ar_id, style="dotted"))
    model.set_bond(2, Bond(extra_id, ar_id, style="dotted"))
    state = _state_from_model(model)
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(0, p_id, ar_id),
                _contact_entry(1, h_id, ar_id),
            ],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="non-documentary bond"):
        _export_with_choices(state, choices)


def test_v2_parser_refuses_single_native_style_in_contact_record() -> None:
    source_sha = "e" * 64
    with pytest.raises(ValueError, match="native_style"):
        _parse_sidecar(
            _v2_payload(
                source_sha,
                bindings=[
                    _binding_entry(1, "Ar", "aryl_label", author_note="note"),
                ],
                documentary_contacts=[
                    {
                        "bond_id": 0,
                        "a": 1,
                        "b": 2,
                        "native_order": 1,
                        "native_style": "single",
                        "classification": _TS_CLASS,
                    }
                ],
            ),
            source_sha,
        )


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda contacts: [
                contacts[0],
                _contact_entry(9, _OH_P, _OH_AR),
            ],
            "endpoints",
        ),
        (
            lambda contacts: [
                _contact_entry(_OH_BOND_P_AR, _OH_P, _OH_AR),
                {
                    "bond_id": _OH_BOND_H_AR,
                    "a": _OH_H,
                    "b": _OH_P,
                    "native_order": 1,
                    "native_style": "dotted",
                    "classification": _TS_CLASS,
                },
            ],
            "endpoints",
        ),
    ],
    ids=["filler-bond-slot", "mismatched-endpoints"],
)
def test_documentary_contact_permission_must_match_native_bond(
    mutator,
    match: str,
) -> None:
    state = _oh_fph_state()
    contacts = mutator(
        [
            _contact_entry(_OH_BOND_P_AR, _OH_P, _OH_AR),
            _contact_entry(_OH_BOND_H_AR, _OH_H, _OH_AR),
        ]
    )
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(_OH_AR, _OH_H),
            documentary_contacts=contacts,
        ),
        source_sha,
    )
    with pytest.raises((ValueError, CdxmlUnsupportedObjectError), match=match):
        _export_with_choices(state, choices)


def test_charged_aryl_label_refuses_fail_closed() -> None:
    ar_id, h_id, p_id = 61, 62, 63
    model = MoleculeModel(
        atoms={
            p_id: Atom("P", 0.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, -20.0, 25.0, explicit_label=True),
            ar_id: Atom("Ar", 40.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(p_id, ar_id, style="dotted"))
    model.set_bond(1, Bond(h_id, ar_id, style="dotted"))
    model.set_atom_annotation(ar_id, {"formal_charge": 1})
    state = _state_from_model(model)
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(0, p_id, ar_id),
                _contact_entry(1, h_id, ar_id),
            ],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="charge"):
        _export_with_choices(state, choices)


def test_radical_aryl_label_refuses_fail_closed() -> None:
    ar_id, h_id, p_id = 64, 65, 66
    model = MoleculeModel(
        atoms={
            p_id: Atom("P", 0.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, -20.0, 25.0, explicit_label=True),
            ar_id: Atom("Ar", 40.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(p_id, ar_id, style="dotted"))
    model.set_bond(1, Bond(h_id, ar_id, style="dotted"))
    model.set_atom_annotation(ar_id, {"radical_electrons": 1})
    state = _state_from_model(model)
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(0, p_id, ar_id),
                _contact_entry(1, h_id, ar_id),
            ],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="radical"):
        _export_with_choices(state, choices)


def test_aryl_label_without_documentary_contacts_refuses_dotted() -> None:
    state, _, h_id, ar_id = _generic_ph_to_ar_state()
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[_contact_entry(0, 31, ar_id)],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="non-documentary bond on Ar"):
        _export_with_choices(state, choices, documentary_contacts=())


def test_hidden_aryl_endpoint_refuses_documentary_export() -> None:
    state, p_id, h_id, ar_id = _generic_ph_to_ar_state()
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[
                _contact_entry(0, p_id, ar_id),
                _contact_entry(1, h_id, ar_id),
            ],
        ),
        source_sha,
    )
    with offscreen_document_scene(state, command="test-cdxml-documentary") as context:
        for item in context.scene.items():
            if item.data(0) == "atom" and item.data(1) == ar_id:
                item.setVisible(False)
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        with pytest.raises(ValueError, match="hidden or outside the export scope"):
            service._typed_label_bindings(items, choices)


def test_coincident_documentary_contact_endpoints_refuse() -> None:
    ar_id, h_id = 90, 91
    model = MoleculeModel(
        atoms={
            ar_id: Atom("Ar", 0.0, 0.0, explicit_label=True),
            h_id: Atom(H_A, 0.0, 0.0, explicit_label=True),
        },
        bonds=[],
    )
    model.set_bond(0, Bond(h_id, ar_id, style="dotted"))
    state = _state_from_model(model)
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[_contact_entry(0, h_id, ar_id)],
        ),
        source_sha,
    )
    with pytest.raises(CdxmlUnsupportedObjectError, match="zero-length"):
        _export_with_choices(state, choices)


def test_preflight_and_serialize_refuse_forged_documentary_contact_record() -> None:
    center_id, h_id, ar_id = 93, 94, 95
    state = _documentary_aryl_two_contact_state(
        center_id=center_id,
        h_id=h_id,
        ar_id=ar_id,
        chemical_bond=Bond(center_id, ar_id, style="single"),
    )
    _, source_sha = _document_digest(state)
    choices = _parse_sidecar(
        _v2_payload(
            source_sha,
            bindings=_fph_bindings(ar_id, h_id),
            documentary_contacts=[_contact_entry(1, h_id, ar_id)],
        ),
        source_sha,
    )
    forged = (
        CdxmlDocumentaryContact(
            bond_id=0,
            a=center_id,
            b=ar_id,
            native_order=1,
            native_style="dotted",
            classification=_TS_CLASS,
        ),
    )
    with offscreen_document_scene(state, command="test-cdxml-documentary") as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet",
            selection=None,
            sizing="custom",
            target_width_mm=170.0,
        )
        typed = service._typed_label_bindings(items, choices)
        with pytest.raises(CdxmlUnsupportedObjectError, match="document bond"):
            preflight_cdxml(
                context,
                items,
                plan,
                label_bindings=typed,
                documentary_contacts=forged,
            )
        with pytest.raises(CdxmlUnsupportedObjectError, match="document bond"):
            serialize_cdxml(
                context,
                items,
                plan,
                label_bindings=typed,
                documentary_contacts=forged,
            )


def test_authorize_documentary_contact_for_export_rejects_forged_classification() -> (
    None
):
    contact = CdxmlDocumentaryContact(
        bond_id=0,
        a=1,
        b=2,
        native_order=1,
        native_style="dotted",
        classification="note",
    )
    with pytest.raises(ValueError, match="classification"):
        authorize_documentary_contact_for_export(contact)


@pytest.mark.parametrize("overlap", [True, False])
@pytest.mark.parametrize("operation", [preflight_cdxml, serialize_cdxml])
def test_documentary_bond_fragment_interleave_geometry(overlap, operation) -> None:
    from PyQt6.QtCore import Qt

    y = 0.0 if overlap else 100.0
    model = MoleculeModel(
        atoms={
            1: Atom("P", 0.0, 0.0, explicit_label=True),
            2: Atom("Ar", 80.0, 0.0, explicit_label=True),
            3: Atom("C", 30.0, y),
            4: Atom("C", 50.0, y),
        },
        bonds=[Bond(1, 2, style="dotted"), Bond(3, 4)],
    )
    state = _state_from_model(model)
    contact = CdxmlDocumentaryContact(0, 1, 2, 1, "dotted", _TS_CLASS)
    with offscreen_document_scene(state, command="test-contact-interleave") as context:
        by_role_id = {
            (it.data(0), it.data(1)): it
            for it in context.scene.items()
            if it.data(0) in ("atom", "bond")
        }
        for it in by_role_id.values():
            it.setZValue(10.0)
        chemical = [
            by_role_id[("bond", 1)],
            by_role_id[("atom", 3)],
            by_role_id[("atom", 4)],
        ]
        chemical[0].setZValue(0.0)
        chemical[1].setZValue(2.0)
        chemical[2].setZValue(2.0)
        documentary = by_role_id[("bond", 0)]
        documentary.setZValue(1.0)
        order = list(context.scene.items(Qt.SortOrder.AscendingOrder))
        assert (
            min(order.index(it) for it in chemical)
            < order.index(documentary)
            < max(order.index(it) for it in chemical)
        )
        assert (
            any(
                documentary.sceneBoundingRect().intersects(it.sceneBoundingRect())
                for it in chemical
            )
            == overlap
        )
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        kwargs = dict(
            label_bindings={2: CdxmlLabelBinding.aryl_label("note")},
            documentary_contacts=(contact,),
        )
        if overlap:
            with pytest.raises(CdxmlUnsupportedObjectError, match="interleaves"):
                operation(context, items, plan, **kwargs)
        else:
            operation(context, items, plan, **kwargs)


@pytest.mark.parametrize("field", ["author_note", "contact_id"])
@pytest.mark.parametrize("illegal", ["\x00", "\x0b", "\ufffe", "\uffff", "\ud800"])
@pytest.mark.parametrize("operation", [preflight_cdxml, serialize_cdxml])
def test_direct_metadata_illegal_xml_refused(field, illegal, operation) -> None:
    model = MoleculeModel(
        atoms={
            1: Atom("P", 0.0, 0.0, explicit_label=True),
            2: Atom("Ar", 60.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(1, 2, style="dotted")],
    )
    with offscreen_document_scene(
        _state_from_model(model), command="test-metadata"
    ) as context:
        service = FigureExportService(context)
        items, plan = service._resolve_figure_export(
            scope="sheet", selection=None, sizing="custom", target_width_mm=170.0
        )
        note = illegal if field == "author_note" else "note"
        contact = CdxmlDocumentaryContact(
            0, 1, 2, 1, "dotted", _TS_CLASS, illegal if field == "contact_id" else "id"
        )
        with pytest.raises(CdxmlUnsupportedObjectError, match="illegal in XML 1.0"):
            operation(
                context,
                items,
                plan,
                label_bindings={2: CdxmlLabelBinding.aryl_label(note)},
                documentary_contacts=(contact,),
            )


@pytest.mark.parametrize("field", ["author_note", "contact_id"])
def test_invalid_metadata_export_preserves_destination(field, tmp_path) -> None:
    from chemvas.features.export.cdxml_label_bindings import CdxmlLabelBindingEntry

    model = MoleculeModel(
        atoms={
            1: Atom("P", 0.0, 0.0, explicit_label=True),
            2: Atom("Ar", 60.0, 0.0, explicit_label=True),
        },
        bonds=[Bond(1, 2, style="dotted")],
    )
    state = _state_from_model(model)
    _, digest = _document_digest(state)
    choices = CdxmlLabelBindings(
        digest,
        "a" * 64,
        (
            CdxmlLabelBindingEntry(
                2,
                "Ar",
                "aryl_label",
                author_note="\x00" if field == "author_note" else "note",
            ),
        ),
        version=2,
        documentary_contacts=(
            CdxmlDocumentaryContact(
                0,
                1,
                2,
                1,
                "dotted",
                _TS_CLASS,
                "\x00" if field == "contact_id" else "id",
            ),
        ),
    )
    destination = tmp_path / "existing.cdxml"
    sentinel = b"existing destination sentinel\n"
    destination.write_bytes(sentinel)
    before = hashlib.sha256(sentinel).hexdigest()
    with offscreen_document_scene(state, command="test-metadata-atomic") as context:
        with pytest.raises(ValueError, match="illegal in XML 1.0"):
            FigureExportService(context).export_figure(
                str(destination),
                fmt="cdxml",
                sizing="custom",
                target_width_mm=170.0,
                label_bindings=choices,
            )
    assert destination.read_bytes() == sentinel
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == before


def test_valid_metadata_xml_exact_preservation() -> None:
    value = ' \t\n\r한글 α 😀 & < > " '
    state, p, h, ar = _generic_ph_to_ar_state()
    contacts = (
        CdxmlDocumentaryContact(0, p, ar, 1, "dotted", _TS_CLASS, value),
        CdxmlDocumentaryContact(1, h, ar, 1, "dotted", _TS_CLASS),
    )
    data, _, _ = _export_with_direct_bindings(
        state,
        {
            ar: CdxmlLabelBinding.aryl_label(value),
            h: CdxmlLabelBinding.element_identity("H"),
        },
        documentary_contacts=contacts,
    )
    tags = ET.fromstring(data).findall(".//objecttag")
    assert any(
        tag.get("Name", "").endswith("ArylLabelAuthorNote")
        and tag.get("Value") == value
        for tag in tags
    )
    assert any("contact_id=" + value in tag.get("Value", "") for tag in tags)
