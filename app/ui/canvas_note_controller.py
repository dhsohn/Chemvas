from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPen,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from ui.canvas_scene_items_state import remove_selected_note_for, selected_notes_for
from ui.canvas_text_style_state import text_style_state_for
from ui.graphics_items import NoSelectRectItem
from ui.history_commands import (
    AddSceneItemsCommand,
    DeleteSceneItemsCommand,
    UpdateSceneItemCommand,
)
from ui.input_view_access import (
    focus_canvas_for,
    focused_scene_item_for,
    set_focused_scene_item_for,
)
from ui.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
    new_note_item_for,
    set_committed_note_html_for,
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
        set_committed_note_html_for(item, item.toHtml())
        return item

    def handle_note_focus_out(self, item: QGraphicsTextItem) -> None:
        text = item.toPlainText().strip()
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        current_html = item.toHtml()
        html_changed = bool(committed_html) and current_html != committed_html
        if text:
            if text != committed_text or html_changed:
                after_state = note_state_dict_for(self.canvas, item)
                if not committed_text:
                    self.history.push(AddSceneItemsCommand(item_states=[after_state], items=[item]))
                else:
                    before_state = note_state_dict_for(self.canvas, item)
                    before_state["text"] = committed_text
                    before_state["html"] = committed_html
                    self.history.push(UpdateSceneItemCommand(item, before_state, after_state))
                set_committed_note_text_for(item, text)
                set_committed_note_html_for(item, current_html)
            return
        if committed_text:
            before_state = note_state_dict_for(self.canvas, item)
            before_state["text"] = committed_text
            before_state["html"] = committed_html
            remove_scene_item(self.canvas, item)
            self.history.push(DeleteSceneItemsCommand(item_states=[before_state], items=[item]))
            set_committed_note_text_for(item, "")
            set_committed_note_html_for(item, "")
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

    def _editing_note(self) -> QGraphicsTextItem | None:
        item = focused_scene_item_for(self.canvas)
        if isinstance(item, QGraphicsTextItem) and item.data(0) == "note":
            return item
        return None

    def _merge_editing_char_format(self, mutate) -> None:
        item = self._editing_note()
        if item is None:
            return
        cursor = item.textCursor()
        fmt = QTextCharFormat()
        mutate(cursor.charFormat(), fmt)
        cursor.mergeCharFormat(fmt)
        item.setTextCursor(cursor)
        self.update_note_box(item)
        update_note_selection_box_for(self.canvas, item)

    def toggle_text_bold(self) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            is_bold = current.fontWeight() > QFont.Weight.Normal
            fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)

        self._merge_editing_char_format(mutate)

    def toggle_text_italic(self) -> None:
        self._merge_editing_char_format(
            lambda current, fmt: fmt.setFontItalic(not current.fontItalic())
        )

    def toggle_text_superscript(self) -> None:
        self._toggle_vertical_alignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)

    def toggle_text_subscript(self) -> None:
        self._toggle_vertical_alignment(QTextCharFormat.VerticalAlignment.AlignSubScript)

    def _toggle_vertical_alignment(self, alignment: QTextCharFormat.VerticalAlignment) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            if current.verticalAlignment() == alignment:
                fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
            else:
                fmt.setVerticalAlignment(alignment)

        self._merge_editing_char_format(mutate)

    def adjust_text_size(self, delta: int) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            size = current.fontPointSize()
            if size <= 0:
                size = float(text_style_state_for(self.canvas).text_font_size)
            fmt.setFontPointSize(max(6.0, min(96.0, size + delta)))

        self._merge_editing_char_format(mutate)

    def set_text_font_family(self, family: str) -> None:
        def mutate(item: QGraphicsTextItem) -> None:
            cursor = QTextCursor(item.document())
            cursor.select(QTextCursor.SelectionType.Document)
            char_format = QTextCharFormat()
            char_format.setFontFamilies([family])
            cursor.mergeCharFormat(char_format)

        self._apply_to_target_notes(mutate)

    def set_text_alignment(self, alignment: str) -> None:
        qt_alignment = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(alignment, Qt.AlignmentFlag.AlignLeft)

        def mutate(item: QGraphicsTextItem) -> None:
            cursor = QTextCursor(item.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            block_format.setAlignment(qt_alignment)
            cursor.mergeBlockFormat(block_format)

        self._apply_to_target_notes(mutate)

    def _apply_to_target_notes(self, mutate) -> None:
        editing = self._editing_note()
        if editing is not None:
            mutate(editing)
            self.update_note_box(editing)
            update_note_selection_box_for(self.canvas, editing)
            return
        for item in selected_notes_for(self.canvas):
            before_state = note_state_dict_for(self.canvas, item)
            mutate(item)
            self.update_note_box(item)
            update_note_selection_box_for(self.canvas, item)
            after_state = note_state_dict_for(self.canvas, item)
            if before_state != after_state and self.history is not None:
                self.history.push(UpdateSceneItemCommand(item, before_state, after_state))
                set_committed_note_html_for(item, item.toHtml())

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
        if doc is None:
            return
        option = doc.defaultTextOption()
        option.setAlignment(style.text_alignment)
        doc.setDefaultTextOption(option)
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        line_height_type = getattr(QTextBlockFormat, "LineHeightType", None)
        if line_height_type is not None and hasattr(line_height_type, "ProportionalHeight"):
            height_type = line_height_type.ProportionalHeight
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
