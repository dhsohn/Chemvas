from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.features.reaction_assembly.geometry import (
    plain_text,
)

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

_KNOWN_TAGS = frozenset(
    {
        "CDXML",
        "page",
        "fonttable",
        "font",
        "colortable",
        "color",
        "group",
        "fragment",
        "n",
        "b",
        "t",
        "s",
        "graphic",
        "arrow",
        "curve",
        "scheme",
        "step",
        "represent",
        "objecttag",
        "bracketedgroup",
        "bracketattachment",
        "crossingbond",
        "ColoredMolecularArea",
        "embeddedobject",
        "annotation",
        "chemicalproperty",
    }
)
_UNSUPPORTED_DECORATIONS = frozenset(
    {
        "bracketedgroup",
        "bracketattachment",
        "crossingbond",
        "ColoredMolecularArea",
        "embeddedobject",
        "annotation",
        "chemicalproperty",
        "curve",
    }
)
_ROLE_REFERENCE_KEYS = frozenset(
    {
        "ReactionStepReactants",
        "ReactionStepProducts",
        "ReactionStepArrows",
        "ReactionStepObjectsAboveArrow",
        "ReactionStepObjectsBelowArrow",
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedReaction:
    root: ET.Element
    page: ET.Element
    step: ET.Element
    by_id: dict[str, ET.Element]
    reactant_ids: list[str]
    product_ids: list[str]
    arrow_refs: list[str]
    above_arrow: list[str]
    below_arrow: list[str]


def validate_normalized_reaction(root: ET.Element) -> NormalizedReaction:
    _validate_root_tree(root)
    page, step = _single_page_and_step(root)
    by_id = _object_index(root)
    role_ids = _validate_step_roles(step, by_id)
    referenced = [identity for ids in role_ids.values() for identity in ids]
    if len(set(referenced)) != len(referenced) or any(
        by_id[identity] not in list(page) for identity in referenced
    ):
        raise ValueError("reaction roles require distinct page-level objects")
    _validate_normalized_geometry(page, by_id, role_ids["arrow_refs"][0])
    return NormalizedReaction(
        root,
        page,
        step,
        by_id,
        role_ids["reactant_ids"],
        role_ids["product_ids"],
        role_ids["arrow_refs"],
        role_ids["above_arrow"],
        role_ids["below_arrow"],
    )


def _validate_root_tree(root: ET.Element) -> None:
    if root.tag != "CDXML":
        raise ValueError("input root must be CDXML")
    for element in root.iter():
        if element.tag not in _KNOWN_TAGS:
            raise ValueError(f"unsupported native object {element.tag}")
        if element.tag in _UNSUPPORTED_DECORATIONS:
            raise ValueError(f"unsupported decoration {element.tag}")
    if root.get("BoundingBox") or root.get("Position"):
        raise ValueError("document position bounds must be absent")


def _single_page_and_step(root: ET.Element) -> tuple[ET.Element, ET.Element]:
    page = root.find("page")
    if page is None:
        raise ValueError("normalized reaction must contain exactly one page")
    if page.get("BoundingBox") or page.get("Width") or page.get("Height"):
        raise ValueError("page position bounds must be absent")
    steps = list(root.iter("step"))
    if len(steps) != 1:
        raise ValueError("normalized reaction must contain exactly one step")
    schemes = list(root.iter("scheme"))
    if len(schemes) != 1:
        raise ValueError("normalized reaction must contain exactly one scheme")
    return page, steps[0]


def _object_index(root: ET.Element) -> dict[str, ET.Element]:
    by_id: dict[str, ET.Element] = {}
    for element in root.iter():
        identity = element.get("id")
        if identity and element.tag not in {"font", "objecttag", "s"}:
            if identity in by_id:
                raise ValueError(f"duplicate object ID {identity}")
            by_id[identity] = element
    return by_id


def _validate_step_roles(
    step: ET.Element, by_id: dict[str, ET.Element]
) -> dict[str, list[str]]:
    reactant_ids = _reference_list(step, "ReactionStepReactants")
    product_ids = _reference_list(step, "ReactionStepProducts")
    arrow_refs = _reference_list(step, "ReactionStepArrows")
    above_arrow = _reference_list(step, "ReactionStepObjectsAboveArrow")
    below_arrow = _reference_list(step, "ReactionStepObjectsBelowArrow")
    if not reactant_ids:
        raise ValueError("reaction step must name reactants")
    if not product_ids:
        raise ValueError("reaction step must name products")
    if not arrow_refs:
        raise ValueError("reaction step must name an arrow")
    if len(arrow_refs) != 1:
        raise ValueError("only one arrow is supported in assemble-reaction")
    for key in _ROLE_REFERENCE_KEYS:
        for identity in _reference_list(step, key):
            if identity not in by_id:
                raise ValueError(f"unknown role reference {identity}")
    return {
        "reactant_ids": reactant_ids,
        "product_ids": product_ids,
        "arrow_refs": arrow_refs,
        "above_arrow": above_arrow,
        "below_arrow": below_arrow,
    }


def _validate_normalized_geometry(
    page: ET.Element, by_id: dict[str, ET.Element], arrow_ref: str
) -> None:
    if any(
        e.tag not in {"fragment", "scheme", "t", "arrow", "graphic"} or not e.get("id")
        for e in page
    ):
        raise ValueError("unsupported or unidentified page-level reaction object")
    for fragment in page.findall("fragment"):
        _validate_fragment_local(fragment)
    for text in page.findall("t"):
        if text.get("p") or text.get("BoundingBox"):
            raise ValueError("page text must omit p and BoundingBox")
    for arrow in page.iter("arrow"):
        for key in ("Head3D", "Tail3D", "BoundingBox"):
            if arrow.get(key):
                raise ValueError(f"arrow must omit {key} before assembly")
    for graphic in page.iter("graphic"):
        if graphic.get("BoundingBox"):
            raise ValueError("legacy graphic must omit BoundingBox before assembly")
        if graphic.get("SupersededBy"):
            continue
        if graphic.get("GraphicType") not in {None, "Line"} and not _is_plus_graphic(
            graphic
        ):
            raise ValueError("unsupported visible graphic decoration")
    resolved_arrow = resolve_arrow_identity(by_id, arrow_ref)
    if resolved_arrow.tag != "arrow":
        raise ValueError("arrow reference must resolve to a native arrow")


def resolve_arrow_identity(by_id: dict[str, ET.Element], identity: str) -> ET.Element:
    current = by_id[identity]
    seen: set[str] = set()
    while current.tag == "graphic" and (target := current.get("SupersededBy")):
        if target in seen:
            raise ValueError("arrow alias chain contains a cycle")
        seen.add(current.get("id", identity))
        if target not in by_id:
            raise ValueError(f"unknown arrow alias target {target}")
        current = by_id[target]
    return current


def is_plus_text(element: ET.Element) -> bool:
    return element.tag == "t" and plain_text(element) == "+"


def _reference_list(step: ET.Element, key: str) -> list[str]:
    raw = step.get(key, "")
    return [value for value in raw.split() if value]


def _validate_fragment_local(fragment: ET.Element) -> None:
    atoms = fragment.findall("n")
    if not atoms or any(not atom.get("p") for atom in atoms):
        raise ValueError("each fragment must contain positioned atoms")


def _is_plus_graphic(graphic: ET.Element) -> bool:
    return graphic.get("GraphicType") == "Line" and graphic.get("ArrowType") in {
        None,
        "NoHead",
    }
