"""Resolve retained native Z ties from the actual document scene at save time."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt

from chemvas.ui.canvas.native_document_layout import native_object_projections
from chemvas.ui.export.export_scope import item_export_bounds

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext

_Z_TAGS = frozenset({"n", "b", "t", "graphic", "arrow", "curve", "embeddedobject"})
_Z_MAX = 32767


@dataclass
class _PaintObject:
    element: ET.Element
    items: list[QGraphicsItem]
    low: int
    high: int
    block: ET.Element
    leaves: list[ET.Element] = field(default_factory=list)
    visible_z: list[int] = field(default_factory=list)


def _painted_bounds(item: QGraphicsItem) -> QRectF:
    if not item.isVisible() or item.effectiveOpacity() <= 0:
        return QRectF()
    return item_export_bounds(item)


def normalize_document_paint_order(
    root: ET.Element,
    objects: dict[tuple[str, str | int], str],
    context: SceneRenderContext,
    source_xml: str,
) -> None:
    """Assign positive unique INT16 Z without changing native chemistry/artwork.

    Already unambiguous retained native ordering is kept. New objects' ranks
    are provisional even when unique. A repair uses actual scene stacking,
    never XML sibling order for visible ties. It refuses overlapping fragment
    interleaving, split painters, missing projections and reversals of an
    explicit native order. Hidden definitions/fallbacks only reserve numbers.
    """
    leaves = [e for e in root.iter() if e.tag in _Z_TAGS]
    try:
        old_z = {e: int(e.get("Z", "0")) for e in leaves}
    except ValueError as exc:
        raise ValueError("Native CDXML paint order must use integer Z values.") from exc
    if len(leaves) > _Z_MAX:
        raise ValueError("Too many drawable objects for CDXML INT16 paint order.")
    import xml.etree.ElementTree as ET

    original_z = {
        e.get("id"): int(e.get("Z", "0"))
        for e in ET.fromstring(source_xml).iter()
        if e.tag in _Z_TAGS and e.get("id") is not None
    }
    # New marks get _top_z + 1 from the headless writer on every save. That
    # provisional number says nothing about their position in this scene and
    # must not bypass resolution after the retained source has unique ranks.
    if (
        len(set(old_z.values())) == len(leaves)
        and all(0 < z <= _Z_MAX for z in old_z.values())
        and all(e.get("id") in original_z for e in leaves)
    ):
        return

    parents = {c: p for p in root.iter() for c in p}
    byid = {e.get("id"): e for e in root.iter() if e.tag not in {"font", "objecttag"}}
    scene = list(context.scene.items(Qt.SortOrder.AscendingOrder))
    ranks = {item: rank for rank, item in enumerate(scene)}
    projections = native_object_projections(context)

    def ancestors(e: ET.Element):
        while e in parents:
            e = parents[e]
            yield e

    painters: dict[ET.Element, _PaintObject] = {}
    for key, identity in objects.items():
        element = byid.get(identity)
        if element is None:
            continue  # Deleted native objects keep no paint slot.
        items = projections.get(key, [])
        items = [item for item in items if item in ranks]
        if not items:
            continue
        # Implicit-carbon dots reserve native node slots but paint no ink.
        # Neither their hit halos nor other empty projections constrain stacking.
        ink = [item for item in items if not _painted_bounds(item).isEmpty()]
        fragments = [e for e in ancestors(element) if e.tag == "fragment"]
        painters[element] = _PaintObject(
            element,
            ink,
            min(ranks[i] for i in ink or items),
            max(ranks[i] for i in ink or items),
            fragments[-1] if fragments else element,
        )

    hidden: list[ET.Element] = []
    for leaf in leaves:
        chain = [leaf, *ancestors(leaf)]
        if any(e.get("Visible") == "no" for e in chain) or (
            leaf.tag == "curve" and not leaf.get("CurvePoints", "").strip()
        ):
            hidden.append(leaf)
            continue
        owner = next((painters[e] for e in chain if e in painters), None)
        superseded = leaf.get("SupersededBy")
        if superseded:
            seen = {leaf.get("id")}
            while superseded and superseded not in seen:
                seen.add(superseded)
                target = byid.get(superseded)
                if target is None:
                    break
                owner = painters.get(target)
                superseded = target.get("SupersededBy")
            if superseded or owner is None:
                raise ValueError("Cannot resolve native fallback paint order.")
        if owner is None:
            raise ValueError(
                f"No scene item establishes native {leaf.tag} #{leaf.get('id', '?')} paint order; the file was not replaced."
            )
        owner.leaves.append(leaf)
        # A contracted definition and a superseded graphic have no independent
        # visible ink; their old numbers cannot constrain the label/active arrow.
        if not leaf.get("SupersededBy") and not any(
            e.tag == "fragment" for e in chain[: chain.index(owner.element)]
        ):
            if leaf.get("id") in original_z:
                owner.visible_z.append(original_z[leaf.get("id")])

    ordered = _order_painters(painters, context)
    ordered_leaves = [e for p in ordered for e in p.leaves] + hidden
    for z, leaf in enumerate(ordered_leaves, 1):
        leaf.set("Z", str(z))


def _order_painters(
    painters: dict[ET.Element, _PaintObject], context: SceneRenderContext
) -> list[_PaintObject]:
    blocks: dict[ET.Element, list[_PaintObject]] = {}
    for painter in painters.values():
        if painter.leaves:
            blocks.setdefault(painter.block, []).append(painter)
    block_ranges = {}
    for block, members in blocks.items():
        members.sort(key=lambda p: p.low)
        visible = [p for p in members if p.items]
        if any(a.high >= b.low for a, b in pairwise(visible)):
            raise ValueError(
                "A native object's painters interleave; cannot assign one Z."
            )
        limits = visible or members
        block_ranges[block] = (limits[0].low, max(p.high for p in limits))
    ordered = [
        p
        for block in sorted(blocks, key=lambda b: block_ranges[b][1])
        for p in blocks[block]
    ]
    positions = {p.element: index for index, p in enumerate(ordered)}
    item_owners = {item: p for p in ordered for item in p.items}
    bounds = {item: _painted_bounds(item) for item in item_owners}
    # Use the scene's spatial index; a large, mostly disjoint page does not
    # require comparing every object with every other object.
    for painter in ordered:
        peers = {
            item_owners[item].element
            for own_item in painter.items
            for item in context.scene.items(
                bounds[own_item],
                Qt.ItemSelectionMode.IntersectsItemBoundingRect,
            )
            if item in item_owners and bounds[own_item].intersects(bounds[item])
        }
        for peer in peers:
            other = painters[peer]
            if positions[peer] <= positions[painter.element]:
                continue
            if painter.block is not other.block:
                low, high = block_ranges[painter.block]
                other_low, other_high = block_ranges[other.block]
                if low < other_high and other_low < high:
                    raise ValueError(
                        "Native fragment paint order interleaves with overlapping artwork."
                    )
            if (
                painter.visible_z
                and other.visible_z
                and max(painter.visible_z) > min(other.visible_z)
            ):
                raise ValueError(
                    "Native paint order conflicts with overlapping scene artwork; the file was not replaced."
                )
    return ordered


def retain_resolved_paint_order(
    root: ET.Element, state: dict, context: SceneRenderContext
) -> dict:
    """Retain the resolved order without rebasing edit baselines.

    Source IDs bind the persisted ranks to graph and annotation identities.
    New/unbound objects deliberately gain no invented baseline or ordinal;
    their order must pass reconstruction before the atomic write. Keep the
    original provenance byte-for-byte when it already restores the same order.
    """
    import xml.etree.ElementTree as ET

    if _replays_paint_order(context, state):
        return state
    source = state["cdxml_source"]
    original = ET.fromstring(source["xml"])
    z_by_id = {
        e.get("id"): e.get("Z")
        for e in root.iter()
        if e.tag in _Z_TAGS and e.get("id") is not None
    }
    changed = False
    for element in original.iter():
        if element.tag not in _Z_TAGS:
            continue
        z = z_by_id.get(element.get("id"))
        if z is not None and element.get("Z") != z:
            element.set("Z", z)
            changed = True
    retained = {
        **state,
        "cdxml_source": {**source, "xml": ET.tostring(original, encoding="unicode")},
    }
    if not changed or not _replays_paint_order(context, retained):
        raise ValueError(
            "The document snapshot cannot restore this overlapping paint order; the file was not replaced."
        )
    return retained


def _replays_paint_order(context: SceneRenderContext, state: dict) -> bool:
    """Whether the existing snapshot reconstructs observable stacking.

    In particular, unbound additions and arbitrary cross-layer restacking have
    no persistent scene-order field. Check their overlapping ink before the
    atomic write instead of silently reopening a different drawing.
    """
    from chemvas.ui.canvas.document_scene import detached_document_scene

    projections = native_object_projections(context)
    bounds = {
        item: _painted_bounds(item) for items in projections.values() for item in items
    }
    owners = {
        item: key
        for key, items in projections.items()
        for item in items
        if not bounds[item].isEmpty()
    }
    ranks = {item: n for n, item in enumerate(context.scene.items())}
    pairs = {
        (owners[a], owners[b])
        for a in owners
        for b in context.scene.items(
            bounds[a], Qt.ItemSelectionMode.IntersectsItemBoundingRect
        )
        if b in owners
        and owners[a] != owners[b]
        and ranks[a] < ranks[b]
        and bounds[a].intersects(bounds[b])
    }
    if not pairs:
        return True
    with detached_document_scene(state) as replay:
        replay_ranks = {item: n for n, item in enumerate(replay.scene.items())}
        restored = {
            key: [replay_ranks[i] for i in items if not _painted_bounds(i).isEmpty()]
            for key, items in native_object_projections(replay).items()
        }
        for above, below in pairs:
            a, b = restored.get(above, []), restored.get(below, [])
            if not a or not b or max(a) >= min(b):
                return False
    return True
