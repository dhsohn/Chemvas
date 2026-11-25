"""Contour-aware horizontal packing for reaction assembly."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.features.reaction_assembly.contours import (
    READABLE_CLEARANCE_PT,
    ContourBand,
    arrow_contour_bands_in_placement_coords,
    fragment_contour_bands_in_placement_coords,
    line_width_half,
    painted_horizontal_extent,
    text_contour_bands_in_placement_coords,
)
from chemvas.features.reaction_assembly.layout import (
    Placement,
    reaction_layout_context,
)

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from chemvas.features.reaction_assembly.validate import NormalizedReaction


@dataclass(frozen=True, slots=True)
class _BodyGroup:
    anchor: ET.Element
    local_bands: tuple[ContourBand, ...]


def _placement_index(placements: list[Placement]) -> dict[ET.Element, Placement]:
    return {placement.element: placement for placement in placements}


def _local_bands_for(
    element: ET.Element,
    *,
    half_bond_width: float,
    arrow_width: float,
) -> list[ContourBand]:
    if element.tag == "fragment":
        return fragment_contour_bands_in_placement_coords(
            element, half_bond_width=half_bond_width
        )
    if element.tag == "t":
        return text_contour_bands_in_placement_coords(element)
    if element.tag == "arrow":
        return arrow_contour_bands_in_placement_coords(width=arrow_width)
    raise ValueError(f"unsupported reaction component {element.tag}")


def _body_groups(
    reaction: NormalizedReaction,
    placements: list[Placement],
) -> list[_BodyGroup]:
    layout = reaction_layout_context(reaction)
    body = layout.body
    by_element = _placement_index(placements)
    half_bond = line_width_half(reaction.root)
    arrow_placement = by_element[layout.arrow]
    arrow_width = arrow_placement.size.width
    groups: list[_BodyGroup] = []
    for element in body:
        attached: list[ET.Element] = []
        if layout.counterion is not None and element is layout.first_reactant:
            attached.append(layout.counterion)
        if element is layout.arrow:
            attached.extend(layout.above_arrow)
            attached.extend(layout.below_arrow)
        local: list[ContourBand] = []
        anchor_placement = by_element[element]
        for item in (element, *attached):
            item_placement = by_element[item]
            dx = item_placement.x - anchor_placement.x
            dy = item_placement.y
            for band in _local_bands_for(
                item,
                half_bond_width=half_bond,
                arrow_width=arrow_width,
            ):
                local.append(band.shifted(dx=dx, dy=dy))
        groups.append(
            _BodyGroup(
                anchor=element,
                local_bands=tuple(local),
            )
        )
    return groups


def _minimum_origin(
    *,
    local_bands: tuple[ContourBand, ...],
    prior_world_bands: list[ContourBand],
    clearance: float,
) -> float:
    required = -math.inf
    for old in prior_world_bands:
        for new in local_bands:
            vertical = max(0.0, new.y_bottom - old.y_top, old.y_bottom - new.y_top)
            if vertical < clearance:
                required = max(
                    required,
                    old.right + math.sqrt(clearance**2 - vertical**2) - new.left,
                )
    if not math.isfinite(required):
        return 0.0
    return required


def _world_bands_for_origins(
    groups: list[_BodyGroup], origins: list[float]
) -> list[ContourBand]:
    world: list[ContourBand] = []
    for group, origin in zip(groups, origins, strict=True):
        world.extend(band.shifted(dx=origin) for band in group.local_bands)
    return world


def _painted_width_for_origins(groups: list[_BodyGroup], origins: list[float]) -> float:
    left, right = painted_horizontal_extent(_world_bands_for_origins(groups, origins))
    return right - left


def _minimum_origins(
    groups: list[_BodyGroup], default_origins: list[float]
) -> list[float]:
    origins = [default_origins[0]]
    world_bands: list[ContourBand] = []
    for index, group in enumerate(groups):
        if index:
            origins.append(
                _minimum_origin(
                    local_bands=group.local_bands,
                    prior_world_bands=world_bands,
                    clearance=READABLE_CLEARANCE_PT + 1.2,
                )
            )
        world_bands.extend(band.shifted(dx=origins[-1]) for band in group.local_bands)
    return origins


def packed_body_origins(
    reaction: NormalizedReaction,
    placements: list[Placement],
    *,
    max_width_pt: float,
) -> tuple[list[float], float]:
    if not math.isfinite(max_width_pt) or max_width_pt <= 0:
        raise ValueError("max_width_pt must be a positive finite number")
    # Leave space for the publication renderer's crop and stroke margins.
    ink_budget = max_width_pt - 6.0
    groups = _body_groups(reaction, placements)
    by_element = _placement_index(placements)
    default_origins = [by_element[group.anchor].x for group in groups]
    default_width = _painted_width_for_origins(groups, default_origins)
    if default_width <= ink_budget + 1e-6:
        return default_origins, default_width
    minimum_origins = _minimum_origins(groups, default_origins)
    minimum_width = _painted_width_for_origins(groups, minimum_origins)
    if minimum_width > ink_budget + 1e-6:
        raise ValueError(
            f"reaction row needs an estimated {minimum_width + 6:.3f} pt with export margins, exceeding "
            f"max_width_pt {max_width_pt:.3f}; increase the limit or edit the source "
            "layout"
        )
    low, high = 0.0, 1.0
    for _ in range(48):
        mid = (low + high) * 0.5
        trial = [
            default + mid * (minimum - default)
            for default, minimum in zip(default_origins, minimum_origins, strict=True)
        ]
        if _painted_width_for_origins(groups, trial) <= ink_budget + 1e-6:
            high = mid
        else:
            low = mid
    origins = [
        default + high * (minimum - default)
        for default, minimum in zip(default_origins, minimum_origins, strict=True)
    ]
    painted_width = _painted_width_for_origins(groups, origins)
    return origins, painted_width


def apply_packed_origins(
    reaction: NormalizedReaction,
    placements: list[Placement],
    *,
    origins: list[float],
) -> list[Placement]:
    layout = reaction_layout_context(reaction)
    by_element = _placement_index(placements)
    shifts = {
        anchor: x - by_element[anchor].x
        for anchor, x in zip(layout.body, origins, strict=True)
    }
    for condition in layout.above_arrow + layout.below_arrow:
        shifts[condition] = shifts[layout.arrow]
    if layout.counterion is not None:
        shifts[layout.counterion] = shifts[layout.first_reactant]
    adjusted: list[Placement] = []
    for placement in placements:
        dx = shifts[placement.element]
        adjusted.append(
            Placement(
                placement.element,
                placement.x + dx,
                placement.y,
                placement.size,
            )
        )
    return adjusted


def pack_placements(
    reaction: NormalizedReaction,
    placements: list[Placement],
    *,
    max_width_pt: float,
) -> tuple[list[Placement], float]:
    origins, painted_width = packed_body_origins(
        reaction, placements, max_width_pt=max_width_pt
    )
    packed = apply_packed_origins(reaction, placements, origins=origins)
    return packed, painted_width


__all__ = ("pack_placements", "packed_body_origins")
