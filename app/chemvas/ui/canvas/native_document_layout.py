"""Transient layout derived from retained CDXML, without rewriting edit state."""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import replace

from PyQt6.QtGui import QTransform

from chemvas.domain.document.cdxml_source import parse_native_xml


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
    # Captions are annotations above the retained graphic projections.
    item.setZValue(2)
