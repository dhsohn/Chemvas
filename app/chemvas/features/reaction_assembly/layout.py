"""Place reaction participants using local ink bounds and step references."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.features.reaction_assembly.geometry import (
    Size,
    format_bbox,
    format_point,
    format_point3,
    fragment_drawable_size,
    fragment_local_origin,
    translate_coordinates,
    unattached_text_size,
)
from chemvas.features.reaction_assembly.validate import (
    is_plus_text,
    resolve_arrow_identity,
)

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from chemvas.features.reaction_assembly.validate import NormalizedReaction


@dataclass(frozen=True)
class Placement:
    element: ET.Element
    x: float
    y: float
    size: Size


@dataclass(frozen=True)
class ReactionLayoutContext:
    body: list[ET.Element]
    counterion: ET.Element | None
    first_reactant: ET.Element
    arrow: ET.Element
    above_arrow: list[ET.Element]
    below_arrow: list[ET.Element]


def _size(e: ET.Element) -> Size:
    if e.tag == "fragment":
        return fragment_drawable_size(e)
    if e.tag == "t":
        return unattached_text_size(e)
    raise ValueError(f"unsupported reaction component {e.tag}")


def _net_charge(fragment: ET.Element) -> int:
    return sum(int(n.get("Charge", "0")) for n in fragment.findall("n"))


def _molecules(refs: list[str], reaction: NormalizedReaction) -> list[ET.Element]:
    mols = [reaction.by_id[i] for i in refs if not is_plus_text(reaction.by_id[i])]
    if not mols or any(m.tag != "fragment" for m in mols):
        raise ValueError("reaction side must reference molecular fragments")
    return mols


def reaction_layout_context(reaction: NormalizedReaction) -> ReactionLayoutContext:
    arrow = resolve_arrow_identity(reaction.by_id, reaction.arrow_refs[0])
    reactants = _molecules(reaction.reactant_ids, reaction)
    products = _molecules(reaction.product_ids, reaction)
    counterion = None
    if (
        len(reactants) == 2
        and not any(is_plus_text(reaction.by_id[i]) for i in reaction.reactant_ids)
        and _net_charge(reactants[0]) * _net_charge(reactants[1]) < 0
    ):
        single = [m for m in reactants if len(m.findall("n")) == 1]
        if len(single) == 1:
            counterion = single[0]
            reactants.remove(counterion)
    pluses = [
        e
        for e in reaction.page
        if is_plus_text(e)
        and e
        not in [reaction.by_id[i] for i in reaction.above_arrow + reaction.below_arrow]
    ]
    if len(pluses) != len(reactants) + len(products) - 2:
        raise ValueError("reaction requires one plus note between adjacent molecules")
    named = set(reaction.reactant_ids + reaction.product_ids)
    free = iter(
        sorted(
            (e for e in pluses if e.get("id") not in named),
            key=lambda e: e.attrib["id"],
        )
    )

    def separated(side: list[ET.Element], refs: list[str]) -> list[ET.Element]:
        explicit = [reaction.by_id[i] for i in refs if is_plus_text(reaction.by_id[i])]
        if explicit and len(explicit) != len(side) - 1:
            raise ValueError("reaction separator count does not match participants")
        separators = iter(explicit) if explicit else free
        row = []
        for index, molecule in enumerate(side):
            if index:
                separator = next(separators, None)
                if separator is None:
                    raise ValueError("missing reaction separator")
                row.append(separator)
            row.append(molecule)
        return row

    body = (
        separated(reactants, reaction.reactant_ids)
        + [arrow]
        + separated(products, reaction.product_ids)
    )
    return ReactionLayoutContext(
        body=body,
        counterion=counterion,
        first_reactant=reactants[0],
        arrow=arrow,
        above_arrow=[reaction.by_id[i] for i in reaction.above_arrow],
        below_arrow=[reaction.by_id[i] for i in reaction.below_arrow],
    )


def compute_placements(reaction: NormalizedReaction) -> list[Placement]:
    unit = float(reaction.root.get("BondLength", "14.4"))
    if not math.isfinite(unit) or unit <= 0:
        raise ValueError("invalid reaction bond length")
    layout = reaction_layout_context(reaction)
    body = layout.body
    counterion = layout.counterion
    above = layout.above_arrow
    below = layout.below_arrow
    arrow = layout.arrow
    gap = 0.58 * unit
    width = max([3 * unit] + [_size(e).width + 0.35 * unit for e in above + below])
    placements = []
    x = 2 * unit
    for e in body:
        size = Size(width, 0) if e is arrow else _size(e)
        placements.append(Placement(e, x, -size.height / 2, size))
        if e is arrow:
            for sign, items in ((-1, list(reversed(above))), (1, below)):
                distance = 0.62 * unit
                for item in items:
                    box = _size(item)
                    y = distance if sign == 1 else -distance - box.height
                    placements.append(
                        Placement(item, x + (width - box.width) / 2, y, box)
                    )
                    distance += box.height + 0.28 * unit
        if counterion is not None and e is layout.first_reactant:
            ion = _size(counterion)
            placements.append(
                Placement(
                    counterion, x, -size.height / 2 - ion.height - 0.2 * unit, ion
                )
            )
        x += size.width + gap
    return placements


def apply_layout(reaction: NormalizedReaction, placements: list[Placement]) -> None:
    present = {p.element for p in placements}
    for child in reaction.page:
        if child.tag in {"fragment", "t", "arrow"} and child not in present:
            raise ValueError("unassigned reaction object")
    shift = 24 - min(p.y for p in placements)
    for placement in placements:
        e = placement.element
        x, y = placement.x, placement.y + shift
        w, h = placement.size.width, placement.size.height
        if e.tag == "fragment":
            left, top = fragment_local_origin(e)
            translate_coordinates(e, x - left, y - top)
        elif e.tag == "t":
            align = e.get(
                "Justification", reaction.root.get("CaptionJustification", "Left")
            )
            anchor = {"Left": x, "Center": x + w / 2, "Right": x + w}.get(align, x)
            e.set("p", format_point((anchor, y + 0.82 * h)))
            e.set("BoundingBox", format_bbox((x, y, x + w, y + h)))
        else:
            e.set("Tail3D", format_point3((x, y)))
            e.set("Head3D", format_point3((x + w, y)))
            e.set("BoundingBox", format_bbox((x, y - 2, x + w, y + 2)))
            for g in reaction.page.findall("graphic"):
                if resolve_arrow_identity(reaction.by_id, g.attrib["id"]) is not e:
                    raise ValueError("unassigned reaction graphic")
                g.set("BoundingBox", format_bbox((x + w, y, x, y)))
    bounds = (
        0,
        0,
        max(p.x + p.size.width for p in placements) + 24,
        max(p.y + p.size.height for p in placements) + shift + 24,
    )
    reaction.page.set("BoundingBox", format_bbox(bounds))
