"""Native CDXML objects with visual projections for unsupported drawing styles.

The integrity-bound document snapshot owns Chemvas editing state. Projections
keep unsupported objects visible in other readers without inventing chemistry.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import TYPE_CHECKING

from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from chemvas.domain.document import connected_atom_components
from chemvas.features.export import ExportPlan
from chemvas.ui.export.export_cdxml import (
    CdxmlUnsupportedObjectError,
    preflight_cdxml,
    serialize_cdxml,
)
from chemvas.ui.export.export_scope import (
    collect_export_items,
    content_bounds,
    exported_scene,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.scene.scene_render_context import SceneRenderContext


def serialize_working_document(context: SceneRenderContext, rect: QRectF) -> bytes:
    plan = ExportPlan(
        source_x=rect.x(),
        source_y=rect.y(),
        source_w=rect.width(),
        source_h=rect.height(),
        out_w_pt=rect.width(),
        out_h_pt=rect.height(),
    )
    items = collect_export_items(context.scene)
    root = ET.Element("CDXML", CreationProgram="Chemvas", InterpretChemically="yes")
    colors = ET.SubElement(root, "colortable")
    fonts = ET.SubElement(root, "fonttable")
    page = ET.SubElement(
        root,
        "page",
        id="1",
        Width=f"{rect.width():.12g}",
        Height=f"{rect.height():.12g}",
        BoundingBox=f"0 0 {rect.width():.12g} {rect.height():.12g}",
    )
    if not items:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    try:
        preflight_cdxml(context, items, plan)
        return serialize_cdxml(context, items, plan)
    except CdxmlUnsupportedObjectError:
        pass

    # Keep each molecule whole. Other records and their children form one
    # visual unit, so a styled note or orbital is never partially dropped.
    components = connected_atom_components(
        context.model.atoms, ((b.a, b.b) for b in context.model.bonds if b is not None)
    )
    atom_groups = {
        aid: index for index, component in enumerate(components) for aid in component
    }
    parts: dict[tuple[str, int], list[QGraphicsItem]] = defaultdict(list)
    for item in reversed(items):
        owner = item
        while (parent := owner.parentItem()) is not None:
            owner = parent
        role, identity = owner.data(0), owner.data(1)
        if role == "atom" and identity in atom_groups:
            part_key = ("molecule", atom_groups[identity])
        elif (
            role == "bond"
            and isinstance(identity, int)
            and context.model.bonds[identity] is not None
        ):
            bond = context.model.bonds[identity]
            assert bond is not None
            part_key = ("molecule", atom_groups[bond.a])
        else:
            part_key = ("item", id(owner))
        parts[part_key].append(item)

    next_id = 2
    z = 1
    for part in parts.values():
        try:
            preflight_cdxml(context, part, plan)
            fragment = ET.fromstring(serialize_cdxml(context, part, plan))
        except CdxmlUnsupportedObjectError:
            image = _projection(context, part, rect)
            if image is None:
                continue
            image.set("id", str(next_id))
            next_id += 1
            image.set("Z", str(z))
            z += 1
            page.append(image)
            continue
        for key, value in fragment.attrib.items():
            if key != "bgcolor":
                root.set(key, value)
        color_map = {"0": "0", "1": "1"}
        for index, color in enumerate(fragment.findall("./colortable/color"), 2):
            color_map[str(index)] = str(len(colors) + 2)
            colors.append(color)
        font_map = {}
        for font in fragment.findall("./fonttable/font"):
            old = font.attrib["id"]
            font_map[old] = str(len(fonts) + 3)
            font.set("id", font_map[old])
            fonts.append(font)
        source_page = fragment.find("page")
        assert source_page is not None
        identities = {}
        for element in source_page.iter():
            if element is source_page or "id" not in element.attrib:
                continue
            identities[element.attrib["id"]] = str(next_id)
            next_id += 1
        # XML traversal order differs from the native serializer's paint order.
        # Shift its Z values as a block instead of reordering bonds and labels.
        source_z = sorted(
            {int(e.attrib["Z"]) for e in source_page.iter() if "Z" in e.attrib}
        )
        z_map = {old: str(z + index) for index, old in enumerate(source_z)}
        z += len(source_z)
        if z > 32768:
            raise ValueError("Too many drawable objects for CDXML paint order.")
        for element in source_page.iter():
            if element is source_page:
                continue
            for key in ("id", "B", "E", "SupersededBy"):
                if key in element.attrib:
                    element.set(key, identities[element.attrib[key]])
            for key in ("BondOrdering", "ConnectionOrder"):
                if key in element.attrib:
                    element.set(
                        key,
                        " ".join(identities[v] for v in element.attrib[key].split()),
                    )
            if "font" in element.attrib:
                element.set("font", font_map[element.attrib["font"]])
            if "color" in element.attrib:
                element.set("color", color_map[element.attrib["color"]])
            if "Z" in element.attrib:
                element.set("Z", z_map[int(element.attrib["Z"])])
        page.extend(list(source_page))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _projection(
    context: SceneRenderContext, items: list[QGraphicsItem], rect: QRectF
) -> ET.Element | None:
    bounds = content_bounds(items)
    if bounds is None:
        return None
    bounds = bounds.adjusted(-1, -1, 1, 1)
    scale = min(4.0, 4096 / max(bounds.width(), bounds.height()))
    width, height = (
        max(1, math.ceil(bounds.width() * scale)),
        max(1, math.ceil(bounds.height() * scale)),
    )
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        with exported_scene(context.scene, items):
            context.scene.render(painter, QRectF(0, 0, width, height), bounds)
    finally:
        painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise ValueError(
            "Could not preserve the drawing preview; document was not saved."
        )
    return ET.Element(
        "embeddedobject",
        BoundingBox=(
            f"{bounds.left() - rect.x():.12g} {bounds.top() - rect.y():.12g} "
            f"{bounds.right() - rect.x():.12g} {bounds.bottom() - rect.y():.12g}"
        ),
        PNG=buffer.data().data().hex(),
    )
