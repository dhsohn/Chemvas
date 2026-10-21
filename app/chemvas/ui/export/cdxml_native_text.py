"""Write edited Qt rich text into an existing native CDXML caption."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCharFormat, QTextDocument


def write_native_caption(root: ET.Element, node: ET.Element, state: dict) -> None:
    document = QTextDocument()
    document.setHtml(state.get("html", ""))
    if not state.get("html"):
        document.setPlainText(state["text"])
    fonts = root.find("fonttable")
    if fonts is None:
        fonts = ET.SubElement(root, "fonttable")
    colors = root.find("colortable")
    if colors is None:
        colors = ET.SubElement(root, "colortable")

    def font_id(name: str) -> str:
        for font in fonts:
            if font.get("name") == name:
                return font.attrib["id"]
        identity = str(max((int(f.get("id", "0")) for f in fonts), default=0) + 1)
        ET.SubElement(fonts, "font", id=identity, name=name, charset="utf-8")
        return identity

    def color_id(value: str) -> str:
        if value == "#000000":
            return "0"
        if value == "#ffffff":
            return "1"
        rgb = [int(value[i : i + 2], 16) for i in (1, 3, 5)]
        for i, color in enumerate(colors):
            if [round(float(color.get(k, "0")) * 255) for k in ("r", "g", "b")] == rgb:
                return str(i + 2)
        ET.SubElement(
            colors,
            "color",
            {k: str(v / 255) for k, v in zip(("r", "g", "b"), rgb, strict=True)},
        )
        return str(len(colors) + 1)

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
                    color=color_id(fmt.foreground().color().name()),
                ).text = fragment.text()
            it += 1
        first = False
        block = block.next()
    # Bounds and wrap metrics are derived by the native consumer after an edit.
    for key in ("BoundingBox", "LineStarts", "WordWrapWidth"):
        node.attrib.pop(key, None)
