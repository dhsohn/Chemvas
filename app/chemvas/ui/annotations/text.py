"""Native note typography and boxes shared by editor and scene rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from chemvas.ui.canvas.graphics_items import NoSelectRectItem

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_text_style_state import CanvasTextStyleState


def apply_note_style(item: QGraphicsTextItem, style: CanvasTextStyleState) -> None:
    font = QFont(style.text_font_family, style.text_font_size)
    font.setWeight(style.text_font_weight)
    font.setItalic(style.text_italic)
    item.setFont(font)
    item.setDefaultTextColor(style.text_color)
    doc = item.document()
    if doc is None:
        return
    option = doc.defaultTextOption()
    option.setAlignment(style.text_alignment)
    doc.setDefaultTextOption(option)
    apply_note_appearance(item, style, line_spacing=True)


def apply_note_appearance(
    item: QGraphicsTextItem, style: CanvasTextStyleState, *, line_spacing: bool
) -> None:
    doc = item.document()
    if doc is None:
        return
    if line_spacing:
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        height_type = cast(
            "int", QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
        )
        block_format.setLineHeight(int(style.text_line_spacing * 100), height_type)
        cursor.mergeBlockFormat(block_format)
    update_note_box(item, style)


def update_note_box(item: QGraphicsTextItem, style: CanvasTextStyleState) -> None:
    box = item.data(20)
    rect = item.boundingRect().adjusted(
        -style.note_padding, -style.note_padding, style.note_padding, style.note_padding
    )
    if not (style.note_box_enabled or style.note_border_enabled):
        if isinstance(box, QGraphicsRectItem):
            box.setVisible(False)
        return
    if not isinstance(box, QGraphicsRectItem):
        box = NoSelectRectItem(item)
        box.setData(0, "note_box")
        box.setZValue(-1)
        box.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)
        item.setData(20, box)
    box.setVisible(True)
    box.setRect(rect)
    if style.note_box_enabled:
        fill = QColor(style.note_box_color)
        fill.setAlphaF(style.note_box_alpha)
        box.setBrush(fill)
    else:
        box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    if style.note_border_enabled:
        pen = QPen(style.note_border_color)
        pen.setWidthF(style.note_border_width)
        box.setPen(pen)
    else:
        box.setPen(QPen(Qt.PenStyle.NoPen))
