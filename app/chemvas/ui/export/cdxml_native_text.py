"""Write edited Qt rich text into an existing native CDXML caption."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCharFormat, QTextDocument

from chemvas.features.cdxml_native_palette import allocate_native_color_index

if TYPE_CHECKING:
    from collections.abc import Mapping


def write_native_caption(
    root: ET.Element,
    node: ET.Element,
    state: dict,
    text_defaults: Mapping[str, Any] | None = None,
) -> None:
    """Rewrite ``node``'s runs from the note record ``state``.

    ``text_defaults`` are the document's text settings. The record's HTML is
    exported relative to them (Qt drops a run's family, weight or italic when
    it equals the editor's default font), so they are the base the runs are
    resolved against; without them an omitted family would be saved as the
    toolkit's generic default instead of the font the caption shows.
    """
    document = QTextDocument()
    document.setDefaultFont(_default_font(document.defaultFont(), text_defaults))
    document.setHtml(state.get("html", ""))
    if not state.get("html"):
        document.setPlainText(state["text"])
    fonts = root.find("fonttable")
    if fonts is None:
        fonts = ET.SubElement(root, "fonttable")

    def font_id(name: str) -> str:
        for font in fonts:
            if font.get("name") == name:
                return font.attrib["id"]
        identity = str(max((int(f.get("id", "0")) for f in fonts), default=0) + 1)
        ET.SubElement(fonts, "font", id=identity, name=name, charset="utf-8")
        return identity

    for child in list(node):
        if child.tag == "s":
            node.remove(child)
    block = document.begin()
    first = True
    while block.isValid():
        alignment = block.blockFormat().alignment()
        if first:
            node.set(
                "Justification",
                "Center"
                if alignment & Qt.AlignmentFlag.AlignHCenter
                else "Right"
                if alignment & Qt.AlignmentFlag.AlignRight
                else "Left",
            )
        elif len(node):
            previous = node.findall("s")[-1]
            previous.text = (previous.text or "") + "\n"
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                font = fmt.font().resolve(document.defaultFont())
                size = font.pointSizeF()
                if font.pixelSize() > 0:
                    # Imported native captions use scene units, equal to CDXML points.
                    size = float(font.pixelSize())
                if size <= 0:
                    size = float(root.get("CaptionSize", "12"))
                face = (
                    (1 if font.weight() >= QFont.Weight.Bold else 0)
                    | (2 if font.italic() else 0)
                    | (4 if font.underline() else 0)
                )
                if (
                    fmt.verticalAlignment()
                    == QTextCharFormat.VerticalAlignment.AlignSubScript
                ):
                    face |= 32
                elif (
                    fmt.verticalAlignment()
                    == QTextCharFormat.VerticalAlignment.AlignSuperScript
                ):
                    face |= 64
                ET.SubElement(
                    node,
                    "s",
                    font=font_id(font.family()),
                    size=f"{size:.12g}",
                    face=str(face),
                    color=allocate_native_color_index(
                        root, fmt.foreground().color().name()
                    ),
                ).text = fragment.text()
            it += 1
        first = False
        block = block.next()
    # Bounds and wrap metrics are derived by the native consumer after an edit.
    for key in ("BoundingBox", "LineStarts", "WordWrapWidth"):
        node.attrib.pop(key, None)


def _default_font(base: QFont, text_defaults: Mapping[str, Any] | None) -> QFont:
    font = QFont(base)
    if not text_defaults:
        return font
    family = text_defaults.get("text_font_family")
    if isinstance(family, str) and family:
        font.setFamilies([family])
    weight = text_defaults.get("text_font_weight")
    if type(weight) is int and 1 <= weight <= 1000:
        font.setWeight(QFont.Weight(weight))
    italic = text_defaults.get("text_italic")
    if type(italic) is bool:
        font.setItalic(italic)
    return font
