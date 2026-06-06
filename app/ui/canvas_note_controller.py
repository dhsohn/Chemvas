from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from ui.canvas_scene_items_state import remove_selected_note_for, selected_notes_for
from ui.canvas_text_style_state import text_style_state_for
from ui.graphics_items import NoSelectRectItem
from ui.history_commands import (
    AddSceneItemsCommand,
    DeleteSceneItemsCommand,
    UpdateSceneItemCommand,
)
from ui.input_view_access import focus_canvas_for, set_focused_scene_item_for
from ui.note_item_access import (
    committed_note_text_for,
    new_note_item_for,
    set_committed_note_text_for,
)
from ui.note_selection_box import update_note_selection_box_for
from ui.scene_item_access import attach_scene_item, remove_scene_item
from ui.scene_item_state import note_state_dict_for
from ui.selection_service_access import selection_service_from_canvas


class CanvasNoteController:
    def __init__(self, canvas, *, selection_controller=None, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service
        self.selection_controller = selection_controller

    def _selection_controller(self):
        if self.selection_controller is not None:
            return self.selection_controller
        try:
            return selection_service_from_canvas(self.canvas)
        except AttributeError:
            return None

    def create_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        item = new_note_item_for(self.canvas)
        item.setPlainText(text)
        set_committed_note_text_for(item, text)
        item.setData(0, "note")
        item.setPos(pos)
        attach_scene_item(self.canvas, item)
        self.apply_note_style(item)
        return item

    def handle_note_focus_out(self, item: QGraphicsTextItem) -> None:
        text = item.toPlainText().strip()
        committed_text = committed_note_text_for(item)
        if text:
            if text != committed_text:
                before_state = note_state_dict_for(self.canvas, item)
                before_state["text"] = committed_text
                after_state = note_state_dict_for(self.canvas, item)
                if not committed_text:
                    command = AddSceneItemsCommand(item_states=[after_state], items=[item])
                    self.history.push(command)
                else:
                    command = UpdateSceneItemCommand(item, before_state, after_state)
                    self.history.push(command)
                set_committed_note_text_for(item, text)
            return
        if committed_text:
            before_state = note_state_dict_for(self.canvas, item)
            command = DeleteSceneItemsCommand(item_states=[before_state], items=[item])
            remove_scene_item(self.canvas, item)
            self.history.push(command)
            set_committed_note_text_for(item, "")
            return
        if item in selected_notes_for(self.canvas):
            remove_selected_note_for(self.canvas, item)
            update_note_selection_box_for(self.canvas, item)
        remove_scene_item(self.canvas, item)

    def update_text_note(self, item: QGraphicsTextItem, text: str) -> None:
        item.setPlainText(text)
        self.apply_note_style(item)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        if item not in selected_notes_for(self.canvas):
            selection_controller = self._selection_controller()
            if selection_controller is not None:
                selection_controller.select_note(item, additive=False)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        focus_canvas_for(self.canvas, Qt.FocusReason.MouseFocusReason)
        item.setFocus(Qt.FocusReason.MouseFocusReason)
        set_focused_scene_item_for(self.canvas, item)
        cursor = item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def apply_text_style_to_selected(self) -> None:
        for item in selected_notes_for(self.canvas):
            self.apply_note_style(item)

    def apply_note_style(self, item: QGraphicsTextItem) -> None:
        style = text_style_state_for(self.canvas)
        font = QFont(style.text_font_family, style.text_font_size)
        font.setWeight(style.text_font_weight)
        font.setItalic(style.text_italic)
        item.setFont(font)
        item.setDefaultTextColor(style.text_color)
        doc = item.document()
        option = doc.defaultTextOption()
        option.setAlignment(style.text_alignment)
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
        block_format.setLineHeight(int(style.text_line_spacing * 100), height_type)
        cursor.mergeBlockFormat(block_format)
        self.update_note_box(item)
        update_note_selection_box_for(self.canvas, item)

    def update_note_box(self, item: QGraphicsTextItem) -> None:
        style = text_style_state_for(self.canvas)
        box = item.data(20)
        rect = item.boundingRect().adjusted(
            -style.note_padding,
            -style.note_padding,
            style.note_padding,
            style.note_padding,
        )
        if not (style.note_box_enabled or style.note_border_enabled):
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


__all__ = ["CanvasNoteController"]
