"""Consistent native charge edits for inspection and saving.

Native Charge attributes own the electronic value of imported atoms; their
Symbol graphics are image projections. Only two edits are understood: deleting
one supported +/- glyph that alone represents its atom's Charge, and adding one
new Chemvas charge mark to a plain atom. Untouched native records are not
checked here and stay exactly as they are. Inspection (``for_write=False``)
only derives effective native charges; constraints that exist because the
native writer cannot serialize a form are applied when ``for_write`` is set.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

MARK_SYMBOLS = {
    "plus": ("Plus", 1),
    "circled_plus": ("CirclePlus", 1),
    "minus": ("Minus", -1),
    "circled_minus": ("CircleMinus", -1),
}
_SYMBOL_CHARGES = dict(MARK_SYMBOLS.values())
_GENERIC = re.compile(r"R[0-9]*|X|A|Q")


@dataclass(frozen=True)
class ChargeEditPlan:
    # Model atom key -> effective native Charge, as the attribute would read.
    charges: dict[str, int]
    # Model atom key -> new Charge for real changes only; 0 removes the attribute.
    edits: dict[str, int]
    # Removed native glyphs whose Charge the edits above account for.
    deleted_graphics: frozenset[str]


def charge_edit_plan(
    state: Mapping[str, Any], root: ET.Element, *, for_write: bool = True
) -> ChargeEditPlan:
    """Resolve charge edits against the unmodified source XML in ``root``."""
    source = state["cdxml_source"]
    byid = {
        e.attrib["id"]: e
        for e in root.iter()
        if "id" in e.attrib and e.tag not in {"font", "objecttag"}
    }
    native_atoms: Mapping[str, str] = source["atoms"]
    atom_keys = {native: str(key) for key, native in native_atoms.items()}
    atoms = {str(k): v for k, v in state["model"]["atoms"].items()}
    annotations = {
        str(k): v for k, v in (state["model"].get("atom_annotations") or {}).items()
    }
    represents: dict[str, int] = {}
    for reference in root.iter("represent"):
        target = reference.get("object")
        if target is not None:
            represents[target] = represents.get(target, 0) + 1
    charges = {
        str(key): int(byid[native].attrib["Charge"])
        for key, native in native_atoms.items()
        if "Charge" in byid[native].attrib
    }

    images = state.get("images", [])
    bindings = source.get("items", {}).get("images", [None] * len(images))
    current = {
        identity
        for identity, _ in zip(bindings, images, strict=True)
        if identity is not None
    }
    deleted: dict[str, str] = {}
    for identity in source.get("baseline_items", {}).get("images", []):
        if identity is None or identity in current:
            continue
        graphic = byid[identity]
        if graphic.find(".//represent") is None:
            continue
        represent = graphic.find("represent")
        target = represent.get("object", "") if represent is not None else ""
        key = atom_keys.get(target)
        node = byid.get(target)
        if (
            represent is None
            or graphic.tag != "graphic"
            or graphic.get("GraphicType") != "Symbol"
            or graphic.get("SymbolType") not in _SYMBOL_CHARGES
            or list(graphic.iter()) != [graphic, represent]
            or represent.get("attribute") != "Charge"
            or key is None
            or node is None
            or represents[target] != 1
            or not _plain_atom(node)
            or "Radical" in node.attrib
            or int(node.get("Charge", "0"))
            != _SYMBOL_CHARGES[graphic.attrib["SymbolType"]]
        ):
            raise ValueError(
                "Deleting a native chemical annotation requires updating its atom property; the file was not replaced."
            )
        deleted[identity] = key

    marks = state.get("marks", [])
    marked: dict[str, list[int]] = {}
    for identity, mark in zip(
        source.get("items", {}).get("marks", [None] * len(marks)), marks, strict=True
    ):
        if identity is not None or not isinstance(mark, Mapping):
            continue
        kind = mark.get("kind")
        if not isinstance(kind, str) or kind not in MARK_SYMBOLS:
            continue
        if mark.get("atom_id") is None:
            continue
        key = str(mark["atom_id"])
        if key not in atoms:
            raise ValueError("Invalid Chemvas document state: mark atom is invalid.")
        marked.setdefault(key, []).append(MARK_SYMBOLS[kind][1])

    cleared = set(deleted.values())
    edits: dict[str, int] = {}
    for key in sorted(cleared | set(marked)):
        if key not in atoms:
            continue  # The native atom was deleted together with its glyph.
        deltas = marked.get(key, [])
        charge = sum(deltas)
        native = native_atoms.get(key)
        node = byid[native] if native is not None else None
        before = int(node.get("Charge", "0")) if node is not None else 0
        retained = node is not None and key not in cleared
        if not for_write:
            if retained and before:
                # The resolver compares the undeleted native Charge with marks.
                continue
        elif len(deltas) > 1:
            raise ValueError(
                f"Chemvas atom {key} has several new charge marks; a native save supports one per atom."
            )
        elif charge and _GENERIC.fullmatch(atoms[key]["element"]):
            # Checked on the current label: a native atom may have been renamed.
            raise ValueError(
                "Charge marks on generic atoms are unsupported; the file was not replaced."
            )
        elif (
            node is not None
            and retained
            and (
                before
                or "Radical" in node.attrib
                or native in represents
                or not _plain_atom(node)
            )
        ):
            raise ValueError(
                f"Chemvas atom {key} keeps native charge, radical or label data; delete its native charge glyph before adding a charge mark."
            )
        else:
            annotation = annotations.get(key) or {}
            if (
                annotation.get("radical_electrons")
                or annotation.get("formal_charge", charge) != charge
            ):
                raise ValueError(
                    f"Conflicting charge annotation and marks for Chemvas atom {key}; the file was not replaced."
                )
        if charge != before:
            edits[key] = charge
        if charge:
            charges[key] = charge
        else:
            charges.pop(key, None)
    return ChargeEditPlan(charges, edits, frozenset(deleted))


def _plain_atom(node: ET.Element) -> bool:
    return (
        node.tag == "n"
        and node.get("NodeType", "Element") == "Element"
        and node.find(".//n") is None
    )
