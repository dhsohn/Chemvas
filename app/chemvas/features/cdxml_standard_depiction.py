"""Headless standard CDXML graph-only 2D coordinate assignment.

Coordinates are preserved when every visible atom already carries ``p``. Mixed
presence is refused. Graph-only inputs call RDKit at import time of the backend
helper only; the product declares RDKit as a runtime dependency.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from chemvas.domain.document.cdxml_source import (
    parse_native_xml,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_STEREO_NODE_ATTRS = frozenset(
    {"ABS", "Racemic", "AS", "EnhancedStereoGroup", "EnhancedStereoType"}
)
_QUERY_BOND_ATTRS = frozenset({"BondQuery", "BS", "Rxn"})


def depict_standard_cdxml(text: str) -> tuple[str, dict[str, Any]]:
    """Return depicted CDXML text and a short JSON report."""
    root = parse_native_xml(text)
    page = root.find("page")
    if page is None:
        raise ValueError("standard CDXML depiction requires a single page element")
    nodes = page.findall("./fragment/n")
    bonds = page.findall("./fragment/b")
    if not nodes:
        raise ValueError("standard CDXML depiction requires at least one atom node")
    positioned = [_node_has_position(node) for node in nodes]
    if all(positioned):
        _apply_neutral_phenolic_oh_labels(root, nodes, bonds)
        return ET.tostring(root, encoding="unicode"), {
            "mode": "preserved",
            "backend": None,
            "atom_count": len(nodes),
            "bond_count": len(bonds),
        }
    if any(positioned):
        raise ValueError(
            "unsupported partial geometry: every atom must either have coordinates "
            "or omit them"
        )
    if len(nodes) > 1000 or len(bonds) > 2000:
        raise ValueError("graph-only depiction exceeds the molecular layout limit")
    _validate_graph_only_inputs(nodes, bonds)
    placement = _depict_coordinates(root, nodes, bonds)
    _apply_coordinates(nodes, placement)
    _apply_neutral_phenolic_oh_labels(root, nodes, bonds)
    return ET.tostring(root, encoding="unicode"), {
        "mode": "depicted",
        "backend": placement["backend"],
        "atom_count": len(nodes),
        "bond_count": len(bonds),
    }


def neutral_phenolic_oh_label(
    node: ET.Element,
    incident: list[ET.Element],
    *,
    node_by_id: Mapping[str, ET.Element],
) -> str | None:
    """Return ``OH`` when the node is a neutral single-bonded phenolic oxygen."""
    if (
        node.get("Element") != "8"
        or node.get("Radical")
        or node.get("NodeType", "Element") != "Element"
    ):
        return None
    charge = int(node.get("Charge", "0"))
    if charge != 0:
        return None
    hydrogen_count = node.get("NumHydrogens")
    if hydrogen_count is not None and int(hydrogen_count) != 1:
        return None
    node_id = node.get("id")
    if node_id is None:
        return None
    if len(incident) != 1:
        return None
    bond = incident[0]
    if bond.get("Order", "1") != "1" or bond.get("BS") or bond.get("BondQuery"):
        return None
    if bond.get("Display", "Solid") not in {"Solid", "WedgeBegin", "WedgeEnd"}:
        return None
    other_id = bond.get("E") if bond.get("B") == node_id else bond.get("B")
    if other_id is None:
        return None
    neighbor = node_by_id.get(other_id)
    if (
        neighbor is None
        or neighbor.get("NodeType", "Element") != "Element"
        or neighbor.get("Element", "6") != "6"
    ):
        return None
    label_node = node.find("t")
    if label_node is not None and "".join(label_node.itertext()).strip():
        return None
    return "OH"


def _validate_graph_only_inputs(
    nodes: list[ET.Element], bonds: list[ET.Element]
) -> None:
    seen: set[str] = set()
    for node in nodes:
        node_id = node.get("id")
        if node_id is None:
            raise ValueError("every atom node requires an id attribute")
        if node_id in seen:
            raise ValueError(f"duplicate atom id {node_id!r}")
        seen.add(node_id)
        kind = node.get("NodeType", "Element")
        if kind != "Element":
            raise ValueError(f"unsupported graph-only node type {kind!r}")
        if node.get("Radical"):
            raise ValueError("graph-only depiction does not support explicit radicals")
        if _STEREO_NODE_ATTRS.intersection(node.attrib):
            matched = min(_STEREO_NODE_ATTRS.intersection(node.attrib))
            raise ValueError(f"unsupported stereochemistry attribute {matched}")
        if node.get("GenericNickname") or node.get("AtomID"):
            raise ValueError("unsupported query or ambiguous atom node")
    bond_ids: set[str] = set()
    for bond in bonds:
        begin = bond.get("B")
        end = bond.get("E")
        if begin not in seen or end not in seen:
            raise ValueError("bond references a missing atom id")
        bond_id = bond.get("id")
        if bond_id is not None:
            if bond_id in bond_ids:
                raise ValueError(f"duplicate bond id {bond_id!r}")
            bond_ids.add(bond_id)
        if _QUERY_BOND_ATTRS.intersection(bond.attrib):
            matched = min(_QUERY_BOND_ATTRS.intersection(bond.attrib))
            raise ValueError(f"unsupported query bond attribute {matched}")
        display = bond.get("Display", "Solid")
        if display != "Solid":
            raise ValueError(f"unsupported ambiguous bond display {display!r}")


def _node_has_position(node: ET.Element) -> bool:
    value = node.get("p", "").strip()
    if not value:
        return False
    parts = value.split()
    if len(parts) != 2:
        raise ValueError(f"atom #{node.get('id', '?')}: invalid coordinate pair")
    for part in parts:
        number = float(part)
        if not math.isfinite(number):
            raise ValueError(f"atom #{node.get('id', '?')}: non-finite coordinate")
    return True


def _bond_length(root: ET.Element) -> float:
    value = float(root.get("BondLength", "14.4"))
    if value <= 0 or not math.isfinite(value):
        raise ValueError("CDXML BondLength must be a positive finite number")
    return value


def _depict_coordinates(
    root: ET.Element,
    nodes: list[ET.Element],
    bonds: list[ET.Element],
) -> dict[str, Any]:
    from rdkit import Chem
    from rdkit.Chem import rdDepictor

    id_to_index: dict[str, int] = {}
    mol = Chem.RWMol()
    for node in sorted(nodes, key=lambda element: int(element.get("id", "0"))):
        node_id = node.get("id")
        assert node_id is not None
        atomic_number = int(node.get("Element", "6"))
        if not 1 <= atomic_number <= 118:
            raise ValueError(f"unsupported atomic number {atomic_number}")
        atom = Chem.Atom(atomic_number)
        charge = int(node.get("Charge", "0"))
        if charge != 0:
            atom.SetFormalCharge(charge)
        mol.AddAtom(atom)
        id_to_index[node_id] = mol.GetNumAtoms() - 1

    for bond in bonds:
        begin = bond.get("B")
        end = bond.get("E")
        assert begin in id_to_index and end in id_to_index
        order = bond.get("Order", "1")
        bond_type = {
            "1": Chem.BondType.SINGLE,
            "2": Chem.BondType.DOUBLE,
            "3": Chem.BondType.TRIPLE,
            "1.5": Chem.BondType.AROMATIC,
        }.get(order)
        if bond_type is None:
            raise ValueError(f"unsupported bond order {order!r}")
        if (
            begin == end
            or mol.GetBondBetweenAtoms(id_to_index[begin], id_to_index[end]) is not None
        ):
            raise ValueError(
                "graph-only depiction requires distinct endpoints and one bond per atom pair"
            )
        mol.AddBond(id_to_index[begin], id_to_index[end], bond_type)
    molecule = mol.GetMol()
    Chem.SanitizeMol(molecule)
    rdDepictor.Compute2DCoords(molecule, forceRDKit=True)
    conf = molecule.GetConformer()

    target_length = _bond_length(root)
    if bonds:
        first_bond = bonds[0]
        begin = first_bond.get("B")
        end = first_bond.get("E")
        if begin is None or end is None:
            raise ValueError("bond requires B and E atom ids")
        begin_pos = conf.GetAtomPosition(id_to_index[begin])
        end_pos = conf.GetAtomPosition(id_to_index[end])
        reference_length = math.hypot(begin_pos.x - end_pos.x, begin_pos.y - end_pos.y)
    else:
        reference_length = 1.0
    if reference_length <= 0:
        raise ValueError("depiction backend returned a zero bond length")
    scale = target_length / reference_length

    raw_points: dict[str, tuple[float, float]] = {}
    for node_id, index in id_to_index.items():
        pos = conf.GetAtomPosition(index)
        raw_points[node_id] = (pos.x * scale, -pos.y * scale)

    min_x = min(point[0] for point in raw_points.values())
    min_y = min(point[1] for point in raw_points.values())
    margin = 70.0
    shift_x = margin - min_x
    shift_y = margin - min_y
    coordinates = {
        node_id: (x + shift_x, y + shift_y) for node_id, (x, y) in raw_points.items()
    }
    return {"backend": "rdkit", "coordinates": coordinates}


def _apply_coordinates(nodes: list[ET.Element], placement: Mapping[str, Any]) -> None:
    coordinates = placement["coordinates"]
    for node in nodes:
        node_id = node.get("id")
        if node_id not in coordinates:
            raise ValueError(f"missing depicted coordinates for atom #{node_id}")
        x, y = coordinates[node_id]
        node.set("p", f"{x:.6f} {y:.6f}")


def _apply_neutral_phenolic_oh_labels(
    root: ET.Element,
    nodes: list[ET.Element],
    bonds: list[ET.Element],
) -> None:
    by_id = {node_id: node for node in nodes if (node_id := node.get("id")) is not None}
    incident: dict[str, list[ET.Element]] = {key: [] for key in by_id}
    for bond in bonds:
        for endpoint in ("B", "E"):
            key = bond.get(endpoint)
            if key in incident:
                incident[key].append(bond)
    label_font = root.get("LabelFont", "3")
    label_size = root.get("LabelSize", "11.52")
    for key, node in by_id.items():
        if neutral_phenolic_oh_label(node, incident[key], node_by_id=by_id) != "OH":
            continue
        node.set("NumHydrogens", "1")
        text = node.find("t")
        if text is None:
            text = ET.SubElement(node, "t")
        text.clear()
        text.set("InterpretChemically", "yes")
        run = ET.SubElement(text, "s")
        run.set("font", label_font)
        run.set("size", label_size)
        run.set("color", "0")
        run.text = "OH"
