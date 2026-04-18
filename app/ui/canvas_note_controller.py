from __future__ import annotations

from core.history import AddSceneItemsCommand, DeleteSceneItemsCommand, UpdateSceneItemCommand
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from ui.graphics_items import NoSelectRectItem
from ui.scene_item_access import attach_scene_item, remove_scene_item


class CanvasNoteController:
    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def create_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        item = self.canvas._new_note_item()
        item.setPlainText(text)
        item._last_text = text
        item.setData(0, "note")
        item.setPos(pos)
        attach_scene_item(self.canvas, item)
        self.apply_note_style(item)
        return item

    def handle_note_focus_out(self, item: QGraphicsTextItem) -> None:
        text = item.toPlainText().strip()
        if text:
            if text != item._last_text:
                before_state = self.canvas._note_state_dict(item)
                before_state["text"] = item._last_text
                after_state = self.canvas._note_state_dict(item)
                if not item._last_text:
                    command = AddSceneItemsCommand(item_states=[after_state], items=[item])
                    self.canvas._push_command(command)
                else:
                    command = UpdateSceneItemCommand(item, before_state, after_state)
                    self.canvas._push_command(command)
                item._last_text = text
            return
        if item._last_text:
            before_state = self.canvas._note_state_dict(item)
            command = DeleteSceneItemsCommand(item_states=[before_state], items=[item])
            remove_scene_item(self.canvas, item)
            self.canvas._push_command(command)
            item._last_text = ""
            return
        if item in self.canvas.selected_notes:
            self.canvas.selected_notes.remove(item)
            self.canvas._update_note_selection_box(item)
        remove_scene_item(self.canvas, item)

    def update_text_note(self, item: QGraphicsTextItem, text: str) -> None:
        item.setPlainText(text)
        self.apply_note_style(item)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        if item not in self.canvas.selected_notes:
            self.canvas.select_note(item, additive=False)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
        item.setFocus(Qt.FocusReason.MouseFocusReason)
        self.canvas.scene().setFocusItem(item)
        cursor = item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def apply_text_style_to_selected(self) -> None:
        for item in self.canvas.selected_notes:
            self.apply_note_style(item)

    def apply_note_style(self, item: QGraphicsTextItem) -> None:
        font = QFont(self.canvas.text_font_family, self.canvas.text_font_size)
        font.setWeight(self.canvas.text_font_weight)
        font.setItalic(self.canvas.text_italic)
        item.setFont(font)
        item.setDefaultTextColor(self.canvas.text_color)
        doc = item.document()
        option = doc.defaultTextOption()
        option.setAlignment(self.canvas.text_alignment)
        doc.setDefaultTextOption(option)
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        if hasattr(QTextBlockFormat, "LineHeightType") and hasattr(
            QTextBlockFormat.LineHeightType,
            "ProportionalHeight",
        ):
            height_type = QTextBlockFormat.LineHeightType.ProportionalHeight
        else:
            height_type = QTextBlockFormat.LineHeightTypes.ProportionalHeight
            if hasattr(height_type, "value"):
                height_type = height_type.value
        block_format.setLineHeight(int(self.canvas.text_line_spacing * 100), height_type)
        cursor.mergeBlockFormat(block_format)
        self.update_note_box(item)
        self.canvas._update_note_selection_box(item)

    def update_note_box(self, item: QGraphicsTextItem) -> None:
        box = item.data(20)
        rect = item.boundingRect().adjusted(
            -self.canvas.note_padding,
            -self.canvas.note_padding,
            self.canvas.note_padding,
            self.canvas.note_padding,
        )
        if not (self.canvas.note_box_enabled or self.canvas.note_border_enabled):
            if isinstance(box, QGraphicsRectItem):
                box.setVisible(False)
            return
        if not isinstance(box, QGraphicsRectItem):
            box = NoSelectRectItem(item)
            box.setData(0, "note_box")
            box.setZValue(-1)
            item.setData(20, box)
        box.setVisible(True)
        box.setRect(rect)
        if self.canvas.note_box_enabled:
            fill = QColor(self.canvas.note_box_color)
            fill.setAlphaF(self.canvas.note_box_alpha)
            box.setBrush(fill)
        else:
            box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if self.canvas.note_border_enabled:
            pen = QPen(self.canvas.note_border_color)
            pen.setWidthF(self.canvas.note_border_width)
            box.setPen(pen)
        else:
            box.setPen(Qt.PenStyle.NoPen)
