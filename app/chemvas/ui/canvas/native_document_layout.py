"""Transient layout derived from retained CDXML, without rewriting edit state."""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import replace
from itertools import pairwise
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform

from chemvas.domain.document.cdxml_source import parse_native_xml

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


def native_object_projections(
    context: SceneRenderContext,
) -> dict[tuple[str, str | int], list[QGraphicsItem]]:
    """Graphics keyed by the existing native writer's stable record bindings."""
    from chemvas.ui.canvas.canvas_document_state import GROUP_COLLECTION_STATES
    from chemvas.ui.export.export_scope import export_item_closure

    projections: dict[tuple[str, str | int], list[QGraphicsItem]] = {}
    atoms = context.state.atom_graphics_state
    for collection in (atoms.atom_items, atoms.atom_dots):
        for aid, item in collection.items():
            projections.setdefault(("atoms", str(aid)), []).append(item)
    for bid, bond in enumerate(context.model.bonds):
        if bond is not None:
            key = f"{min(bond.a, bond.b)}:{max(bond.a, bond.b)}"
            projections["bonds", key] = list(
                context.state.bond_graphics_state.bond_items.get(bid, ())
            )
    for kind, name in GROUP_COLLECTION_STATES.items():
        for index, item in enumerate(context.state.scene_items(name)):
            if item is not None:
                projections[kind, index] = [item]
    return {key: export_item_closure(items) for key, items in projections.items()}


def restore_native_paint_order(context: SceneRenderContext, state: dict) -> None:
    """Restore retained native order within the editor's existing paint layers.

    Graph IDs and model array order are unchanged. Missing/tied source ranks
    retain the renderer's stable insertion order. Cross-layer orders still use
    the established native presentation; save verifies their reconstruction.
    """
    source = state.get("cdxml_source")
    if source is None:
        return
    root = parse_native_xml(source["xml"])
    byid = {
        e.get("id"): float(e.get("Z", "0"))
        for e in root.iter()
        if e.tag not in {"font", "objecttag"} and e.get("id") is not None
    }
    bindings = {
        (kind, key): identity
        for kind in ("atoms", "bonds")
        for key, identity in source[kind].items()
    }
    bindings.update(
        ((kind, index), identity)
        for kind, identities in source["items"].items()
        for index, identity in enumerate(identities)
        if identity is not None
    )
    native_z = {
        item: byid[bindings[key]]
        for key, items in native_object_projections(context).items()
        if key in bindings
        for item in items
    }
    bands: dict[tuple[QGraphicsItem | None, float], list[QGraphicsItem]] = {}
    for item in context.scene.items(Qt.SortOrder.AscendingOrder):
        bands.setdefault((item.parentItem(), item.zValue()), []).append(item)
    for items in bands.values():
        bound = iter(
            sorted((i for i in items if i in native_z), key=native_z.__getitem__)
        )
        ordered = [next(bound) if i in native_z else i for i in items]
        for above, below in pairwise(reversed(ordered)):
            below.stackBefore(above)


def native_bond_metrics(state: dict) -> dict[tuple[int, int], dict[str, float]]:
    source = state.get("cdxml_source")
    if source is None:
        return {}
    root = parse_native_xml(source["xml"])
    parents = {child: parent for parent in root.iter() for child in parent}
    nodes = {e.get("id"): e for e in root.iter("b")}

    def number(node, key, default):
        current = node
        while current is not None and key not in current.attrib:
            current = parents.get(current)
        value = float(current.get(key) if current is not None else default)
        if not math.isfinite(value) or not 0 < value <= 1000:
            raise ValueError(f"Invalid native bond {key}.")
        return value

    result = {}
    for key, native_id in source["bonds"].items():
        node = nodes[native_id]
        a, b = (int(v) for v in key.split(":"))
        result[a, b] = dict(
            bond_line_width=number(node, "LineWidth", 0.6),
            bold_bond_width=number(node, "BoldWidth", 2.0),
            # Plain/ring double geometry applies a 1.1 display factor.
            bond_spacing_px=number(node, "BondSpacing", 18)
            * number(node, "BondLength", 14.4)
            / 100
            / 1.1,
            hash_spacing_px=number(node, "HashSpacing", 2.5),
        )
    return result


@contextmanager
def native_bond_style(context, bond_id):
    if not context.state.bond_graphics_state.native_metrics:
        yield
        return
    bond = context.model.bond_for_id(bond_id)
    metrics = (
        None
        if bond is None
        else context.state.bond_graphics_state.native_metrics.get(
            (min(bond.a, bond.b), max(bond.a, bond.b))
        )
    )
    previous = context.renderer.style
    if metrics:
        scale = context.renderer.metric_scale()
        context.renderer.style = replace(
            previous, **{key: value / scale for key, value in metrics.items()}
        )
    try:
        yield
    finally:
        context.renderer.style = previous


def native_caption_layouts(state: dict) -> dict[int, tuple[float, float, str, float]]:
    source = state.get("cdxml_source")
    if source is None:
        return {}
    root = parse_native_xml(source["xml"])
    nodes = {e.get("id"): e for e in root.iter("t")}
    originals = dict(
        zip(source["baseline_items"]["notes"], source["baseline"]["notes"], strict=True)
    )
    layouts = {}
    for index, native_id in enumerate(source["items"]["notes"]):
        node = nodes.get(native_id)
        original = originals.get(native_id)
        if node is None or not node.get("p") or original is None:
            continue
        px, py = (float(v) for v in node.get("p", "").split())
        layouts[index] = (
            px - source["offset"][0] - original["x"],
            py - source["offset"][1] - original["y"],
            node.get("Justification", root.get("CaptionJustification", "Left")),
            float(node.get("RotationAngle", "0")) / 65536,
        )
    return layouts


def place_native_caption(
    item, placement: tuple[float, float, str, float] | None
) -> None:
    if placement is None:
        return
    set_derived_layout = getattr(item, "set_derived_layout", None)
    if set_derived_layout is not None:
        # Editable captions re-anchor whenever their text or format changes;
        # the installer applies the placement once immediately.
        set_derived_layout(lambda note: _place_caption(note, placement))
    else:
        _place_caption(item, placement)
    # Captions are annotations above the retained graphic projections.
    item.setZValue(2)


def _place_caption(item, placement: tuple[float, float, str, float]) -> None:
    px, py, alignment, rotation = placement
    item.boundingRect()  # Materialize QTextLayout before reading its baseline.
    layout = item.document().begin().layout()
    line = layout.lineAt(0)
    anchor = line.naturalTextRect().left()
    if alignment == "Center":
        anchor += line.naturalTextWidth() / 2
    elif alignment == "Right":
        anchor += line.naturalTextWidth()
    item.setTransform(
        QTransform()
        .translate(px, py)
        .rotate(rotation)
        .translate(
            -layout.position().x() - anchor,
            -layout.position().y() - line.y() - line.ascent(),
        )
    )


def apply_native_presentation(context: SceneRenderContext, item) -> None:
    """Give an annotation projection its retained CDXML presentation.

    Document load and history re-creation both call this once the item
    carries its final record ID. The native styles and caption placements are
    keyed by that ID, so a projection materialized under a temporary ID was
    drawn without them.
    """
    record_id = item.data(3)
    state = context.state
    if record_id in state.native_arrow_styles:
        context.arrows.render_record(item, context.arrows.record(item))
    placement = state.native_caption_placements.get(record_id)
    if placement is not None:
        place_native_caption(item, placement)
    elif hasattr(item, "set_derived_layout"):
        # A projection without a retained caption anchor keeps Qt's layout.
        item.set_derived_layout(None)
