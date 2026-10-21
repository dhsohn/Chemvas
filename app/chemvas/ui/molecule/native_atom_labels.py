"""Source-derived CDXML atom typography shared by live and detached scenes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast, override

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)

from chemvas.domain.document.cdxml_source import parse_native_xml
from chemvas.features.annotations import (
    parse_atom_label,
    reversed_display_text,
    split_hydride_label,
)
from chemvas.ui.canvas.graphics_items import AtomLabelItem


@dataclass(frozen=True)
class NativeAtomLabel:
    text: str
    offset: tuple[float, float]
    runs: tuple[tuple[str, str, float, int], ...]
    alignment: str
    justification: str
    line_height: float | None
    rotation: float = 0.0


def native_atom_labels(state: dict) -> dict[int, NativeAtomLabel]:
    source = state.get("cdxml_source")
    if source is None:
        return {}
    root = parse_native_xml(source["xml"])
    nodes = {e.get("id"): e for e in root.iter("n")}
    fonts = {
        e.get("id"): e.get("name", "Arial") for e in root.findall("./fonttable/font")
    }
    labels = {}
    for atom_id, native_id in source["atoms"].items():
        node = nodes[native_id]
        text = node.find("t")
        if text is None or not text.get("p"):
            continue
        position = [float(v) for v in text.get("p", "").split()]
        atom_position = [float(v) for v in node.get("p", "").split()]
        if (
            len(position) != 2
            or len(atom_position) != 2
            or not all(math.isfinite(v) for v in position + atom_position)
        ):
            raise ValueError("Invalid native atom label position.")
        runs = []
        for run in text.findall("s"):
            size = float(run.get("size", root.get("LabelSize", "10")))
            if not math.isfinite(size) or not 0 < size <= 1000:
                raise ValueError("Invalid native atom label size.")
            family = fonts.get(run.get("font", root.get("LabelFont")), "Arial")
            runs.append(
                (
                    run.text or "",
                    family,
                    size,
                    int(run.get("face", root.get("LabelFace", "96"))),
                )
            )
        labels[int(atom_id)] = NativeAtomLabel(
            "".join(r[0] for r in runs).strip(),
            (position[0] - atom_position[0], position[1] - atom_position[1]),
            tuple(runs),
            text.get("LabelAlignment", "Left"),
            text.get("LabelJustification", "Left"),
            (
                float(text.get("BoundingBox", "").split()[3])
                - float(text.get("BoundingBox", "").split()[1])
            )
            / 2
            if text.get("LabelAlignment") in {"Above", "Below"}
            and len(text.get("BoundingBox", "").split()) == 4
            else None,
            float(text.get("RotationAngle", "0")) / 65536,
        )
    return labels


class NativeAtomLabelItem(AtomLabelItem):
    """Editable atom identity with source text runs and a native baseline anchor."""

    def __init__(
        self, *, hit_padding: float = 0.0, hit_radius: float | None = None
    ) -> None:
        # Shape at 100x resolution so fractional native sizes such as 4.9 pt
        # survive Qt's integer pixel font resolution; map back to scene units.
        super().__init__(
            hit_padding=hit_padding * 100,
            hit_radius=None if hit_radius is None else hit_radius * 100,
        )
        self.setScale(0.01)

    @override
    def set_hit_padding(self, hit_padding: float) -> None:
        super().set_hit_padding(hit_padding * 100)

    @override
    def set_hit_radius(self, hit_radius: float | None) -> None:
        super().set_hit_radius(None if hit_radius is None else hit_radius * 100)

    @override
    def _relayout(self) -> None:
        self.prepareGeometryChange()
        self._layout = None
        self._typographic = False
        self._stack_element_rect = None

    def apply_native(self, label: NativeAtomLabel, color: str) -> None:
        signature = (label, color)
        if getattr(self, "_native_signature", None) == signature:
            return
        self._native_signature = signature
        self._raw_text = label.text
        document = self.document()
        assert document is not None
        document.clear()
        document.setDocumentMargin(0)
        cursor = QTextCursor(document)
        runs = label.runs
        if len(runs) == 1 and runs[0][3] & 0x60 == 0x60:
            text, family, size, face = runs[0]
            if label.alignment == "Right":
                text = reversed_display_text(text) or text
            elif label.alignment in {"Above", "Below"}:
                hydride = split_hydride_label(text)
                if hydride is not None:
                    element, count = hydride
                    hydrogen = "H" + (str(count) if count > 1 else "")
                    text = "\n".join(
                        (element, hydrogen)
                        if label.alignment == "Below"
                        else (hydrogen, element)
                    )
            runs = ((text, family, size, face),)
        for text, family, size, face in runs:
            font = QFont(family, 12)
            # CDXML coordinates and sizes are both points; scene units are
            # device-independent coordinates, so cancel Qt's point-to-pixel factor.
            font.setPointSizeF(size * 100 * 12 / QFontInfo(font).pixelSize())
            font.setKerning(False)
            font.setBold(bool(face & 1))
            font.setItalic(bool(face & 2))
            font.setUnderline(bool(face & 4))
            if cursor.position() == 0:
                self.setFont(font)
            if face & 0x60 == 0x60:
                pieces = [(r.text, r.role) for r in parse_atom_label(text)]
            else:
                role = {0x20: "sub", 0x40: "super"}.get(face & 0x60, "normal")
                pieces = [(text, role)]
            for value, role in pieces:
                fmt = QTextCharFormat()
                fmt.setFont(font)
                fmt.setForeground(QColor(color))
                fmt.setVerticalAlignment(
                    {
                        "normal": QTextCharFormat.VerticalAlignment.AlignNormal,
                        "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
                        "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
                    }[role]
                )
                cursor.insertText(value, fmt)
        if label.line_height is not None and label.line_height > 0:
            cursor.select(QTextCursor.SelectionType.Document)
            block = QTextBlockFormat()
            block.setLineHeight(
                label.line_height * 100,
                cast("int", QTextBlockFormat.LineHeightTypes.FixedHeight.value),
            )
            cursor.mergeBlockFormat(block)
        self.update()

    def position_native(self, label: NativeAtomLabel, x: float, y: float) -> None:
        self.boundingRect()
        document = self.document()
        assert document is not None
        layout = document.begin().layout()
        assert layout is not None and layout.lineCount()
        line = layout.lineAt(0)
        baseline = layout.position().y() + line.y() + line.ascent()
        horizontal = 0.0
        if label.justification == "Right":
            horizontal = line.naturalTextWidth()
        elif label.justification == "Center":
            horizontal = line.naturalTextWidth() / 2
        radians = math.radians(label.rotation)
        anchor_x = horizontal * math.cos(radians) - baseline * math.sin(radians)
        anchor_y = horizontal * math.sin(radians) + baseline * math.cos(radians)
        self.setPos(
            QPointF(
                x + label.offset[0] - anchor_x * self.scale(),
                y + label.offset[1] - anchor_y * self.scale(),
            )
        )
        self.setRotation(label.rotation)
