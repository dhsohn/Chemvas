"""Update owned native CDXML by source identity without rebuilding untouched XML."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from typing import Any, cast

from chemvas.domain.atom_aliases import (
    AMBIGUOUS_ELEMENT_LABELS,
    ATOM_ALIAS_DEFINITIONS,
)
from chemvas.domain.document.cdxml_charge_edits import charge_edit_plan
from chemvas.domain.document.cdxml_source import validate_cdxml_source
from chemvas.domain.document.cdxml_stereo_descriptors import (
    ATOM_STEREO_DESCRIPTORS,
    BOND_STEREO_DESCRIPTORS,
    atom_edit_keeps_stereo,
    bond_edit_keeps_stereo,
)
from chemvas.domain.document.inspection import document_annotations, document_model
from chemvas.domain.elements import ATOMIC_NUMBERS
from chemvas.features.cdxml_native_palette import allocate_native_color_index

_GENERIC_NICKNAME = re.compile(r"R[0-9]*|X|A|Q")
_DOUBLE_POSITIONS = {"double_center": "Center", "double_outer": "Right"}


def _is_native_pure_element_label(symbol: str) -> bool:
    """True when ``symbol`` may be written as a native ``Element`` atomic number."""
    return (
        symbol in ATOMIC_NUMBERS
        and symbol not in ATOM_ALIAS_DEFINITIONS
        and symbol not in AMBIGUOUS_ELEMENT_LABELS
    )


def _label_shown(atom: dict[str, Any]) -> bool:
    """True when an atom record draws its element symbol as native text."""
    return atom["element"] != "C" or bool(atom["explicit_label"])


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
    root, _ = native_document_tree(state, note_writer=note_writer)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + cast(
        "bytes", ET.tostring(root, encoding="utf-8")
    )


def native_document_tree(
    state: dict[str, Any], *, note_writer: Any = None
) -> tuple[ET.Element, dict[tuple[str, str | int], str]]:
    """Updated XML and the native IDs of its editable drawing records.

    The document-save boundary uses these bindings to retain scene paint order,
    including objects allocated during this write. The source state is untouched.
    """
    return _NativeWriter(state, note_writer).build()


class _NativeWriter:
    def __init__(self, state: dict[str, Any], note_writer: Any) -> None:
        self.state = state
        self.note_writer = None
        if note_writer is not None:
            # Note HTML omits whatever equals the document's text defaults, so
            # the caption writer must read it with the same defaults the editor
            # used, or omitted fonts become the toolkit's generic family.
            text_defaults = state.get("settings") or {}

            def write_note(
                root: ET.Element, node: ET.Element, note: dict[str, Any]
            ) -> None:
                note_writer(root, node, note, text_defaults)

            self.note_writer = write_note
        self.source = self.state["cdxml_source"]
        self.root = validate_cdxml_source(self.source, self.state)
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
        self.bond_native = dict(self.source["bonds"])
        self.changed_nodes: set[str] = set()
        self.stale_stereo: set[ET.Element] = set()
        self.removed_ids: set[str] = set()
        self.edited_notes: set[str] = set()

    def fresh(self) -> str:
        self.allocated += 1
        return str(self.allocated)

    def delete(self, e: ET.Element) -> None:
        parent = self.parents.get(e)
        if parent is not None and e in list(parent):
            self.removed_ids.update(n.attrib["id"] for n in e.iter() if n.get("id"))
            parent.remove(e)

    def invalidate_stereo(self, e: ET.Element) -> None:
        """Drop CIP descriptors across the outermost fragment holding ``e``."""
        fragment = None
        node: ET.Element | None = e
        while node is not None:
            if node.tag == "fragment":
                fragment = node
            node = self.parents.get(node)
        if fragment is not None:
            self.stale_stereo.add(fragment)

    def color_index(self, color: str) -> str:
        return allocate_native_color_index(self.root, color)

    def pair(self, bond: dict[str, Any]) -> str:
        return f"{min(bond['a'], bond['b'])}:{max(bond['a'], bond['b'])}"

    def update_atoms(self) -> None:
        for key, native in self.source["atoms"].items():
            e = self.byid[native]
            before = self.old_atoms[key]
            after = self.atoms.get(key)
            if after is None:
                self.invalidate_stereo(e)
                self.removed_ids.update(n.attrib["id"] for n in e.iter() if n.get("id"))
                self.delete(e)
                continue
            if after == before:
                continue
            if not atom_edit_keeps_stereo(before, after):
                self.invalidate_stereo(e)
            dx, dy = (after["x"] - before["x"], after["y"] - before["y"])
            if dx or dy:
                transform_native(e, tx=dx, ty=dy)
            if after["element"] != before["element"]:
                symbol = after["element"]
                if not _is_native_pure_element_label(
                    symbol
                ) and not _GENERIC_NICKNAME.fullmatch(symbol):
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
                    "BondOrdering",
                    "Geometry",
                ):
                    e.attrib.pop(prop, None)
                if _is_native_pure_element_label(symbol):
                    e.set("Element", str(ATOMIC_NUMBERS[symbol]))
                else:
                    e.attrib.pop("Element", None)
                    e.set("NodeType", "GenericNickname")
                    e.set("GenericNickname", "R" if symbol.startswith("R") else symbol)
                if _label_shown(after):
                    self.append_label(e, symbol)
                self.changed_nodes.add(native)
            elif _label_shown(after) != _label_shown(before):
                # Same element, only its symbol's visibility changed: a hidden
                # carbon gains or loses its native text without touching any
                # chemical property (charge, isotope, stereo) of the node.
                self.set_label_visibility(e, after)
            if after["color"] != before["color"]:
                color = self.color_index(after["color"])
                e.set("color", color)
                for run in e.findall("./t/s"):
                    run.set("color", color)

    def append_label(self, node: ET.Element, symbol: str) -> None:
        t = ET.SubElement(node, "t", p=node.get("p", ""))
        ET.SubElement(
            t,
            "s",
            font=self.root.get("LabelFont", "3"),
            size=self.root.get("LabelSize", "10"),
            face="96",
        ).text = symbol

    def set_label_visibility(self, e: ET.Element, after: dict[str, Any]) -> None:
        if e.find("fragment") is not None or e.get("NodeType", "Element") != "Element":
            raise ValueError(
                "Showing or hiding a contracted native label is unsupported; the file was not replaced."
            )
        labels = e.findall("t")
        if _label_shown(after):
            if not labels:
                self.append_label(e, after["element"])
                if e.get("color"):
                    for run in e.findall("./t/s"):
                        run.set("color", e.attrib["color"])
            return
        for label in labels:
            self.removed_ids.update(n.attrib["id"] for n in label.iter() if n.get("id"))
            e.remove(label)

    def new_atom_fragments(self) -> dict[str, tuple[str, ET.Element | None]]:
        """Decide each new atom's native fragment from the whole graph.

        New atoms bonded to each other form one component, whatever order the
        model stores them in (Undo re-inserts a deleted atom at the end). A
        component bonded to an existing native fragment joins it; any other
        component maps to ``None`` and gets one fresh fragment. A component
        bridging two existing fragments is left to the bond check, which
        refuses that merge.
        """
        new = [key for key in self.atoms if key not in self.atom_native]
        roots = {key: key for key in new}

        def root(key: str) -> str:
            while roots[key] != key:
                roots[key] = roots[roots[key]]
                key = roots[key]
            return key

        anchors: dict[str, set[str]] = {}
        for bond in self.state["model"]["bonds"]:
            a, b = str(bond["a"]), str(bond["b"])
            if a in roots and b in roots:
                roots[root(a)] = root(b)
            elif a in roots and b in self.atom_native:
                anchors.setdefault(a, set()).add(self.atom_native[b])
            elif b in roots and a in self.atom_native:
                anchors.setdefault(b, set()).add(self.atom_native[a])
        component_natives: dict[str, set[str]] = {}
        for key, natives in anchors.items():
            component_natives.setdefault(root(key), set()).update(natives)
        component_fragment = {
            component: self.parents[self.byid[min(natives, key=int)]]
            for component, natives in component_natives.items()
        }
        return {key: (root(key), component_fragment.get(root(key))) for key in new}

    def add_atoms(self) -> None:
        planned = self.new_atom_fragments()
        fresh_fragments: dict[str, ET.Element] = {}
        for key, after in self.atoms.items():
            if key in self.atom_native:
                continue
            component, fragment = planned[key]
            if fragment is None:
                fragment = fresh_fragments.get(component)
                if fragment is None:
                    fragment = ET.SubElement(self.page, "fragment", id=self.fresh())
                    fresh_fragments[component] = fragment
            symbol = after["element"]
            if not _is_native_pure_element_label(
                symbol
            ) and not _GENERIC_NICKNAME.fullmatch(symbol):
                raise ValueError(
                    f"New native atom '{symbol}' requires an elemental label."
                )
            node = ET.SubElement(
                fragment,
                "n",
                id=self.fresh(),
                p=f"{after['x'] + self.offset[0]:.12g} {after['y'] + self.offset[1]:.12g}",
                Element=(
                    str(ATOMIC_NUMBERS[symbol])
                    if _is_native_pure_element_label(symbol)
                    else "6"
                ),
                color=self.color_index(after["color"]),
            )
            if not _is_native_pure_element_label(symbol):
                node.attrib.pop("Element", None)
                node.set("NodeType", "GenericNickname")
                node.set("GenericNickname", "R" if symbol.startswith("R") else symbol)
            if _label_shown(after):
                self.append_label(node, symbol)
            self.atom_native[key] = node.attrib["id"]
            self.byid[node.attrib["id"]] = node
            self.parents[node] = fragment

    def update_charges(self) -> None:
        for key, charge in self.charge_plan.edits.items():
            native = self.atom_native[key]
            self.invalidate_stereo(self.byid[native])
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
                e = self.byid[native]
                self.invalidate_stereo(e)
                self.removed_ids.add(native)
                self.delete(e)
                # Only ordinary elemental coordination can be discarded here.
                # Fragment/NamedAlternativeGroup ordering maps attachment points
                # and must still pass reference validation before any cleanup.
                for identity in (e.attrib["B"], e.attrib["E"]):
                    node = self.byid[identity]
                    if (
                        identity not in self.removed_ids
                        and node.get("NodeType", "Element") == "Element"
                        and node.find("fragment") is None
                    ):
                        node.attrib.pop("BondOrdering", None)
                        node.attrib.pop("Geometry", None)
        for key, bond in bonds.items():
            native = self.source["bonds"].get(key)
            if native and bond == old_bonds[key]:
                continue
            before = old_bonds.get(key)
            if native and before and bond_edit_keeps_stereo(before, bond):
                e = self.byid[native]
                if bond["color"] != before["color"]:
                    e.set("color", self.color_index(bond["color"]))
                if bond["style"] != before["style"]:
                    e.set(
                        "DoublePosition", _DOUBLE_POSITIONS.get(bond["style"], "Left")
                    )
                continue
            begin, end = (
                self.atom_native[str(bond["a"])],
                self.atom_native[str(bond["b"])],
            )
            if not native:
                for identity in (begin, end):
                    if self.byid[identity].find("fragment") is not None:
                        # Accepted legacy XML may omit or misstate NodeType;
                        # the retained direct fragment is the definition.
                        # The editor has no port selection or unused-port state.
                        # SDK BondOrdering/ConnectionOrder map chemical ports;
                        # BeginAttach/EndAttach only locate label characters.
                        # Missing ordering (including one-port definitions) is
                        # not permission to assign a new bond. update_atoms has
                        # already removed definitions for genuine label retypes.
                        raise ValueError(
                            "Cannot determine the attachment point for a new bond to a defined native contracted structure; undo the new bond before saving. The file was not replaced."
                        )
            if self.parents[self.byid[begin]] is not self.parents[self.byid[end]]:
                raise ValueError(
                    "Connecting two native fragments is not yet supported; saving was cancelled without replacing the file."
                )
            self.invalidate_stereo(self.byid[begin])
            e = (
                self.byid[native]
                if native
                else ET.SubElement(self.parents[self.byid[begin]], "b", id=self.fresh())
            )
            self.bond_native[key] = e.attrib["id"]
            # SDK BeginAttach/EndAttach are label-character offsets, not port
            # numbers. Bind them to the original XML endpoints: importing an
            # End-style wedge/hash may already have reversed the model's a/b.
            attachments = {
                e.get("B"): e.get("BeginAttach"),
                e.get("E"): e.get("EndAttach"),
            }
            for prop in (
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
            for atom_key, identity, prop in (
                (str(bond["a"]), begin, "BeginAttach"),
                (str(bond["b"]), end, "EndAttach"),
            ):
                attachment = attachments.get(identity)
                if (
                    native
                    and attachment is not None
                    and self.old_atoms[atom_key]["element"]
                    == self.atoms[atom_key]["element"]
                ):
                    e.set(prop, attachment)
            if bond["order"] == 2:
                e.set("DoublePosition", _DOUBLE_POSITIONS.get(bond["style"], "Left"))
            else:
                e.attrib.pop("DoublePosition", None)
            for identity in (begin, end):
                node = self.byid[identity]
                if native and (
                    node.get("NodeType") == "Fragment"
                    or (
                        node.get("NodeType") == "Nickname"
                        and node.find("fragment[@ConnectionOrder]") is not None
                    )
                ):
                    # SDK BondOrdering pairs these existing bond IDs with the
                    # definition's ConnectionOrder; a defined Nickname is a
                    # special case of Fragment. Style/order/direction edits do
                    # not change that pairing. Geometry is still stale, and
                    # other edits in changed_nodes retain their invalidation.
                    node.attrib.pop("Geometry", None)
                else:
                    self.changed_nodes.add(identity)

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
                elif collection == "shapes":
                    from chemvas.features.cdxml_editable_rectangles import (
                        update_rectangle,
                    )

                    update_rectangle(e, before, after, self.offset, self.color_index)
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
                        self.edited_notes.add(identity)

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

    def detach_chemical_properties(self) -> None:
        # A ChemDraw chemical property links a caption (formula, weight, ...)
        # to the objects it was computed from. Chemvas treats the caption as
        # plain text. Once the caption is edited or deleted, or the structure
        # loses an object, the link no longer describes that text: drop the
        # link and keep whatever caption remains as ordinary text.
        for e in list(self.root.iter("chemicalproperty")):
            display = e.get("ChemicalPropertyDisplayID", "")
            references = {display, *e.get("BasisObjects", "").split()}
            if display in self.edited_notes or self.removed_ids & references:
                self.delete(e)

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

    def build(self) -> tuple[ET.Element, dict[tuple[str, str | int], str]]:
        self.update_atoms()
        self.add_atoms()
        self.update_charges()
        self.update_bonds()
        self.update_items()
        self.remove_deleted_fallbacks()
        self.detach_chemical_properties()
        self.validate_references()
        for fragment in self.stale_stereo:
            for node in fragment.iter("n"):
                for key in ATOM_STEREO_DESCRIPTORS:
                    node.attrib.pop(key, None)
            for bond_e in fragment.iter("b"):
                for key in BOND_STEREO_DESCRIPTORS:
                    bond_e.attrib.pop(key, None)
        # Other bond, label or charge edits still invalidate node coordination.
        for identity in self.changed_nodes:
            e = self.byid[identity]
            for key in ("BondOrdering", "Geometry"):
                e.attrib.pop(key, None)
        from chemvas.features.cdxml_new_objects import append_new_objects

        items = append_new_objects(
            self.root,
            self.state,
            fresh=self.fresh,
            color_index=self.color_index,
            note_writer=self.note_writer,
            atom_native=self.atom_native,
        )
        objects: dict[tuple[str, str | int], str] = {
            ("atoms", key): identity for key, identity in self.atom_native.items()
        }
        objects.update(
            (("bonds", key), identity) for key, identity in self.bond_native.items()
        )
        objects.update(
            ((kind, index), identity)
            for kind, identities in items.items()
            for index, identity in enumerate(identities)
            if identity is not None
        )
        return self.root, objects
