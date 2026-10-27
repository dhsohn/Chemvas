"""Update owned native CDXML by source identity without rebuilding untouched XML."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any, cast

from chemvas.domain.document.cdxml_charge_edits import charge_edit_plan
from chemvas.domain.document.cdxml_source import parse_native_xml, validate_cdxml_source
from chemvas.domain.document.inspection import document_annotations, document_model
from chemvas.features.cdxml_document import _ELEMENTS


def transform_native(
    e: ET.Element, *, sx: float = 1, sy: float = 1, tx: float = 0, ty: float = 0
) -> None:
    for node in e.iter():
        for key in (
            "p",
            "BoundingBox",
            "Head3D",
            "Tail3D",
            "Center3D",
            "MajorAxisEnd3D",
            "MinorAxisEnd3D",
            "CurvePoints",
        ):
            if key not in node.attrib:
                continue
            values = [float(v) for v in node.attrib[key].split()]
            if key.endswith("3D"):
                values[0] = values[0] * sx + tx
                values[1] = values[1] * sy + ty
            else:
                if len(values) % 2:
                    raise ValueError("Invalid native coordinate array.")
                values = [
                    v * (sx if i % 2 == 0 else sy) + (tx if i % 2 == 0 else ty)
                    for i, v in enumerate(values)
                ]
            if any(not math.isfinite(v) or abs(v) > 1000000 for v in values):
                raise ValueError("Native coordinate transform exceeds limits.")
            node.set(key, " ".join(f"{v:.12g}" for v in values))


def update_native_document(state: dict[str, Any], *, note_writer: Any = None) -> bytes:
    return _NativeWriter(state, note_writer).build()


class _NativeWriter:
    def __init__(self, state: dict[str, Any], note_writer: Any) -> None:
        self.state = state
        self.note_writer = note_writer
        self.source = self.state["cdxml_source"]
        validate_cdxml_source(self.source, self.state)
        self.root = parse_native_xml(self.source["xml"])
        self.charge_plan = charge_edit_plan(self.state, self.root, for_write=True)
        # Model-only charge/radical edits have no native form; the shared
        # resolver rejects any that marks and native Charge do not match.
        document_annotations(self.state, document_model(self.state))
        page = self.root.find("page")
        assert page is not None
        self.page = page
        self.byid = {
            e.get("id"): e
            for e in self.root.iter()
            if e.tag not in {"font", "objecttag"}
        }
        self.parents = {
            child: parent for parent in self.root.iter() for child in parent
        }
        self.original = self.source["baseline"]
        self.offset = self.source["offset"]
        self.allocated = max(
            (int(k) for k in self.byid if k and k.isdigit()), default=0
        )
        self.old_atoms = {str(k): v for k, v in self.original["model"]["atoms"].items()}
        self.atoms = {str(k): v for k, v in self.state["model"]["atoms"].items()}
        self.atom_native = dict(self.source["atoms"])
        self.changed_nodes: set[str] = set()
        self.removed_ids: set[str] = set()

    def fresh(self) -> str:
        self.allocated += 1
        return str(self.allocated)

    def delete(self, e: ET.Element) -> None:
        parent = self.parents.get(e)
        if parent is not None and e in list(parent):
            self.removed_ids.update(n.attrib["id"] for n in e.iter() if n.get("id"))
            parent.remove(e)

    def color_index(self, color: str) -> str:
        if color.lower() == "#000000" and self.root.get("fgcolor", "0") == "0":
            return "0"
        if color.lower() == "#ffffff":
            return "1"
        table = self.root.find("colortable")
        if table is None:
            table = ET.SubElement(self.root, "colortable")
        target = tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))
        for i, c in enumerate(table):
            if (
                tuple(round(float(c.get(k, "0")) * 255) for k in ("r", "g", "b"))
                == target
            ):
                return str(i + 2)
        ET.SubElement(
            table,
            "color",
            {
                k: f"{v / 255:.12g}"
                for k, v in zip(("r", "g", "b"), target, strict=True)
            },
        )
        return str(len(table) + 1)

    def pair(self, bond: dict[str, Any]) -> str:
        return f"{min(bond['a'], bond['b'])}:{max(bond['a'], bond['b'])}"

    def update_atoms(self) -> None:
        for key, native in self.source["atoms"].items():
            e = self.byid[native]
            before = self.old_atoms[key]
            after = self.atoms.get(key)
            if after is None:
                self.removed_ids.update(n.attrib["id"] for n in e.iter() if n.get("id"))
                self.delete(e)
                continue
            if after == before:
                continue
            dx, dy = (after["x"] - before["x"], after["y"] - before["y"])
            if dx or dy:
                transform_native(e, tx=dx, ty=dy)
                for node in self.parents[e].iter("n"):
                    node.attrib.pop("AS", None)
                    node.attrib.pop("CIP", None)
            if after["element"] != before["element"]:
                symbol = after["element"]
                if symbol not in _ELEMENTS and not re.fullmatch(
                    r"R[0-9]*|X|A|Q", symbol
                ):
                    raise ValueError(
                        f"Changing a native atom to '{symbol}' requires an elemental label; existing contracted labels are preserved."
                    )
                if e.get("Charge", "0") != "0" or e.get("Radical"):
                    raise ValueError(
                        "Replacing a native charged or radical atom label requires explicit annotation handling; the file was not replaced."
                    )
                for child in list(e):
                    if child.tag in {"fragment", "t"}:
                        self.removed_ids.update(
                            n.attrib["id"] for n in child.iter() if n.get("id")
                        )
                        e.remove(child)
                for prop in (
                    "NodeType",
                    "GenericNickname",
                    "NumHydrogens",
                    "Charge",
                    "Radical",
                    "Isotope",
                    "AS",
                    "BondOrdering",
                    "Geometry",
                ):
                    e.attrib.pop(prop, None)
                if symbol in _ELEMENTS:
                    e.set("Element", str(_ELEMENTS.index(symbol)))
                else:
                    e.attrib.pop("Element", None)
                    e.set("NodeType", "GenericNickname")
                    e.set("GenericNickname", "R" if symbol.startswith("R") else symbol)
                if symbol != "C" or after["explicit_label"]:
                    t = ET.SubElement(e, "t", p=e.get("p", ""))
                    ET.SubElement(
                        t,
                        "s",
                        font=self.root.get("LabelFont", "3"),
                        size=self.root.get("LabelSize", "10"),
                        face="96",
                    ).text = symbol
                self.changed_nodes.add(native)
            if after["color"] != before["color"]:
                color = self.color_index(after["color"])
                e.set("color", color)
                for run in e.findall("./t/s"):
                    run.set("color", color)

    def add_atoms(self) -> None:
        for key, after in self.atoms.items():
            if key in self.atom_native:
                continue
            fragment = None
            for bond in self.state["model"]["bonds"]:
                ends = [str(bond["a"]), str(bond["b"])]
                if key not in ends:
                    continue
                other = ends[1] if ends[0] == key else ends[0]
                if other in self.atom_native:
                    fragment = self.parents.get(self.byid[self.atom_native[other]])
                    break
            if fragment is None:
                fragment = ET.SubElement(self.page, "fragment", id=self.fresh())
            symbol = after["element"]
            if symbol not in _ELEMENTS and not re.fullmatch(r"R[0-9]*|X|A|Q", symbol):
                raise ValueError(
                    f"New native atom '{symbol}' requires an elemental label."
                )
            node = ET.SubElement(
                fragment,
                "n",
                id=self.fresh(),
                p=f"{after['x'] + self.offset[0]:.12g} {after['y'] + self.offset[1]:.12g}",
                Element=str(_ELEMENTS.index(symbol)) if symbol in _ELEMENTS else "6",
                color=self.color_index(after["color"]),
            )
            if symbol not in _ELEMENTS:
                node.attrib.pop("Element", None)
                node.set("NodeType", "GenericNickname")
                node.set("GenericNickname", "R" if symbol.startswith("R") else symbol)
            if symbol != "C" or after["explicit_label"]:
                t = ET.SubElement(node, "t", p=node.get("p", ""))
                ET.SubElement(
                    t,
                    "s",
                    font=self.root.get("LabelFont", "3"),
                    size=self.root.get("LabelSize", "10"),
                    face="96",
                ).text = symbol
            self.atom_native[key] = node.attrib["id"]
            self.byid[node.attrib["id"]] = node
            self.parents[node] = fragment

    def update_charges(self) -> None:
        for key, charge in self.charge_plan.edits.items():
            native = self.atom_native[key]
            if charge:
                self.byid[native].set("Charge", str(charge))
            else:
                self.byid[native].attrib.pop("Charge", None)
            self.changed_nodes.add(native)

    def update_bonds(self) -> None:
        old_bonds = {self.pair(b): b for b in self.original["model"]["bonds"]}
        bonds = {self.pair(b): b for b in self.state["model"]["bonds"]}
        displays = {
            "single": "Solid",
            "double": "Solid",
            "double_center": "Solid",
            "double_outer": "Solid",
            "triple": "Solid",
            "wedge": "WedgeBegin",
            "hash": "WedgedHashBegin",
            "hash_plain": "Hash",
            "wavy": "Wavy",
            "double_either": "Wavy",
            "dotted": "Dash",
            "dotted_double": "Dash",
            "dotted_double_outer": "Dash",
            "bold_in": "Bold",
            "bold_center": "Bold",
            "bold_out": "Bold",
        }
        for key, native in self.source["bonds"].items():
            if key not in bonds:
                self.removed_ids.add(native)
                self.delete(self.byid[native])
        for key, bond in bonds.items():
            native = self.source["bonds"].get(key)
            if native and bond == old_bonds[key]:
                continue
            begin, end = (
                self.atom_native[str(bond["a"])],
                self.atom_native[str(bond["b"])],
            )
            if self.parents[self.byid[begin]] is not self.parents[self.byid[end]]:
                raise ValueError(
                    "Connecting two native fragments is not yet supported; saving was cancelled without replacing the file."
                )
            e = (
                self.byid[native]
                if native
                else ET.SubElement(self.parents[self.byid[begin]], "b", id=self.fresh())
            )
            for prop in (
                "BS",
                "CIP",
                "BondCircularOrdering",
                "Display2",
                "BeginAttach",
                "EndAttach",
            ):
                e.attrib.pop(prop, None)
            e.set("B", begin)
            e.set("E", end)
            e.set("Order", str(bond["order"]))
            e.set("Display", displays[bond["style"]])
            e.set("color", self.color_index(bond["color"]))
            if bond["order"] == 2:
                e.set(
                    "DoublePosition",
                    {"double_center": "Center", "double_outer": "Right"}.get(
                        bond["style"], "Left"
                    ),
                )
            else:
                e.attrib.pop("DoublePosition", None)
            self.changed_nodes.update((begin, end))

    def update_items(self) -> None:
        for collection, original_bindings in self.source["baseline_items"].items():
            active_bindings = self.source["items"].get(
                collection, [None] * len(self.state.get(collection, []))
            )
            current = {
                identity: item
                for identity, item in zip(
                    active_bindings, self.state.get(collection, []), strict=True
                )
                if identity is not None
            }
            for identity, before in zip(
                original_bindings, self.original.get(collection, []), strict=True
            ):
                if identity is None:
                    continue
                e = self.byid[identity]
                after = current.get(identity)
                if after is None:
                    if (
                        e.find("represent") is not None
                        and identity not in self.charge_plan.deleted_graphics
                    ):
                        raise ValueError(
                            "Deleting a native chemical annotation requires updating its atom property; the file was not replaced."
                        )
                    self.removed_ids.add(identity)
                    self.delete(e)
                    continue
                if after == before:
                    continue
                if collection == "images":
                    if after["data_base64"] != before["data_base64"] or after.get(
                        "opacity", 1
                    ) != before.get("opacity", 1):
                        raise ValueError(
                            "Native CDXML graphics retain their vector artwork; replacing their raster projection or opacity is unsupported."
                        )
                    sx, sy = (
                        after["width"] / before["width"],
                        after["height"] / before["height"],
                    )
                    tx = (
                        after["x"]
                        + self.offset[0]
                        - sx * (before["x"] + self.offset[0])
                    )
                    ty = (
                        after["y"]
                        + self.offset[1]
                        - sy * (before["y"] + self.offset[1])
                    )
                    transform_native(e, sx=sx, sy=sy, tx=tx, ty=ty)
                    superseded = [
                        g
                        for g in self.root.iter("graphic")
                        if g.get("SupersededBy") == identity
                    ]
                    for graphic in superseded:
                        transform_native(graphic, sx=sx, sy=sy, tx=tx, ty=ty)
                elif collection == "arrows":
                    from chemvas.features.cdxml_editable_arrows import update_arrow

                    update_arrow(e, before, after, self.offset, self.color_index)
                    # Update transitive legacy line copies as well. Their IDs may
                    # themselves be used by reaction metadata.
                    pending = {identity}
                    remaining = list(self.root.iter("graphic"))
                    while pending:
                        targets, pending = pending, set()
                        for graphic in remaining[:]:
                            if graphic.get("SupersededBy") not in targets:
                                continue
                            if graphic.find(".//represent") is not None:
                                raise ValueError(
                                    "Editing a native chemical annotation requires updating its atom property."
                                )
                            pending.add(graphic.get("id"))
                            remaining.remove(graphic)
                            if graphic.get("GraphicType", "Line") != "Line":
                                raise ValueError("Native arrow fallback is not a line.")
                            coordinates = [
                                after[key][axis] + self.offset[axis]
                                for key in ("end", "start")
                                for axis in (0, 1)
                            ]
                            graphic.set(
                                "BoundingBox",
                                " ".join(f"{v:.12g}" for v in coordinates),
                            )
                            if after.get("color") != before.get("color"):
                                graphic.set(
                                    "color",
                                    self.color_index(after.get("color") or "#000000"),
                                )
                elif collection == "notes":
                    transform_native(
                        e, tx=after["x"] - before["x"], ty=after["y"] - before["y"]
                    )
                    if after.get("rotation", 0) != before.get("rotation", 0):
                        raise ValueError(
                            "Rotation of native captions is not yet supported."
                        )
                    if after["text"] != before["text"] or after.get(
                        "html"
                    ) != before.get("html"):
                        if self.note_writer is None:
                            raise ValueError(
                                "Native rich-text writer is required for caption edits."
                            )
                        self.note_writer(self.root, e, after)

    def remove_deleted_fallbacks(self) -> None:
        # Superseded graphics are hidden alternate representations of their target,
        # not independent artwork. Remove the fallback too, never reactivate it.
        fallbacks: dict[str, list[ET.Element]] = {}
        for graphic in self.root.iter("graphic"):
            target = graphic.get("SupersededBy")
            if target:
                fallbacks.setdefault(target, []).append(graphic)
        pending = list(self.removed_ids)
        while pending:
            for graphic in fallbacks.pop(pending.pop(), []):
                if graphic.find(".//represent") is not None:
                    raise ValueError(
                        "Deleting a native chemical annotation requires updating its atom property; the file was not replaced."
                    )
                pending.extend(
                    n.attrib["id"]
                    for n in graphic.iter()
                    if n.get("id") and n.attrib["id"] not in self.removed_ids
                )
                self.delete(graphic)

    def validate_references(self) -> None:
        reference_keys = {
            "ReactionStepReactants",
            "ReactionStepProducts",
            "ReactionStepArrows",
            "ReactionStepObjectsAboveArrow",
            "ReactionStepObjectsBelowArrow",
            "BracketedObjectIDs",
            "GraphicID",
            "BondID",
            "InnerAtomID",
            "BasisObjects",
            "object",
            "SupersededBy",
            "BondOrdering",
            "BondCircularOrdering",
        }
        for e in self.root.iter():
            if e.tag == "step":
                for key in (
                    "ReactionStepArrows",
                    "ReactionStepObjectsAboveArrow",
                    "ReactionStepObjectsBelowArrow",
                ):
                    references = e.get(key, "").split()
                    if self.removed_ids.intersection(references):
                        remaining = [r for r in references if r not in self.removed_ids]
                        if remaining:
                            e.set(key, " ".join(remaining))
                        else:
                            e.attrib.pop(key)
            for key in reference_keys:
                if self.removed_ids.intersection(e.get(key, "").split()):
                    raise ValueError(
                        f"Deleting this object would break native {e.tag}.{key} references; undo the deletion before saving."
                    )

    def build(self) -> bytes:
        self.update_atoms()
        self.add_atoms()
        self.update_charges()
        self.update_bonds()
        self.update_items()
        self.remove_deleted_fallbacks()
        self.validate_references()
        for identity in self.changed_nodes:
            e = self.byid[identity]
            for key in ("AS", "CIP", "BondOrdering", "Geometry"):
                e.attrib.pop(key, None)
        from chemvas.features.cdxml_new_objects import append_new_objects

        append_new_objects(
            self.root,
            self.state,
            fresh=self.fresh,
            color_index=self.color_index,
            note_writer=self.note_writer,
            atom_native=self.atom_native,
        )
        return b'<?xml version="1.0" encoding="UTF-8"?>\n' + cast(
            "bytes", ET.tostring(self.root, encoding="utf-8")
        )
