from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextOption

from chemvas.domain.document import is_document_number, is_hex_color
from chemvas.ui.canvas_scene_items_state import arrow_items_for, note_items_for
from chemvas.ui.canvas_text_style_state import set_text_style_for, text_style_state_for
from chemvas.ui.history_commands import SetAnnotationStyleCommand
from chemvas.ui.note_item_access import set_committed_note_html_for
from chemvas.ui.note_selection_box import update_note_selection_box_for
from chemvas.ui.renderer_style_access import atom_color_for, font_size_pt_for
from chemvas.ui.scene_decoration_build_access import apply_arrow_labels_for
from chemvas.ui.selection_service_access import refresh_selection_outline_for
from chemvas.ui.selection_style_state import selection_style_state_for
from chemvas.ui.transactions.document import document_transaction

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsTextItem

NOTE_APPEARANCE_FIELDS = frozenset(
    {
        "note_box_enabled",
        "note_box_color",
        "note_box_alpha",
        "note_border_enabled",
        "note_border_color",
        "note_border_width",
        "note_padding",
        "text_line_spacing",
    }
)

_ARROW_LABEL_STYLE_FIELDS = frozenset(
    {
        "text_font_family",
        "text_font_size",
        "text_font_weight",
        "text_italic",
        "text_color",
    }
)


@dataclass(frozen=True)
class _NoteStyle:
    item: QGraphicsTextItem
    html: str
    font: QFont
    color: QColor
    text_option: QTextOption


@dataclass(frozen=True)
class _TextStyleChange:
    settings: dict[str, object]
    notes: tuple[_NoteStyle, ...]


class CanvasStyleController:
    def __init__(self, canvas: Any, *, note_controller, history_service) -> None:
        self.canvas = canvas
        self.note_controller = note_controller
        self.history = history_service

    @property
    def text_style(self):
        return text_style_state_for(self.canvas)

    def note_appearance(self) -> dict[str, object]:
        return {name: self._text_value(name) for name in NOTE_APPEARANCE_FIELDS}

    def _text_value(self, name: str) -> object:
        value = getattr(self.text_style, name)
        return value.name() if isinstance(value, QColor) else value

    def _apply_text_settings(
        self, canvas, values: dict[str, object], *, restyle_text: bool
    ) -> None:
        for name, value in values.items():
            set_text_style_for(
                canvas,
                name,
                QColor(str(value)) if name.endswith("color") else value,
            )
        restyle_notes = restyle_text or bool(
            NOTE_APPEARANCE_FIELDS.intersection(values)
        )
        if restyle_notes:
            for item in note_items_for(canvas):
                if restyle_text:
                    self.note_controller.apply_note_style(item)
                else:
                    self.note_controller.apply_note_appearance(
                        item, line_spacing="text_line_spacing" in values
                    )
                set_committed_note_html_for(item, item.toHtml())
        restyled_labels = self._restyle_arrow_labels(canvas, values)
        if restyle_notes or restyled_labels:
            refresh_selection_outline_for(canvas)

    @staticmethod
    def _restyle_arrow_labels(canvas, values: dict[str, object]) -> bool:
        if not _ARROW_LABEL_STYLE_FIELDS.intersection(values):
            return False
        changed = False
        for item in arrow_items_for(canvas):
            labels = (item.data(2) or {}).get("labels")
            if labels:
                # Use the same layout and explicit arrow-color precedence as
                # document restore, without rebuilding the arrow's own path.
                apply_arrow_labels_for(canvas, item, labels)
                changed = True
        return changed

    @staticmethod
    def _capture_notes(items) -> tuple[_NoteStyle, ...]:
        return tuple(
            _NoteStyle(
                item,
                item.toHtml(),
                QFont(item.font()),
                QColor(item.defaultTextColor()),
                QTextOption(item.document().defaultTextOption()),
            )
            for item in items
        )

    def _restore_text_style(self, canvas, state: _TextStyleChange) -> None:
        for name, value in state.settings.items():
            set_text_style_for(
                canvas, name, QColor(str(value)) if name.endswith("color") else value
            )
        for note in state.notes:
            note.item.setFont(note.font)
            note.item.setDefaultTextColor(note.color)
            note.item.setHtml(note.html)
            document = note.item.document()
            assert document is not None
            document.setDefaultTextOption(note.text_option)
            self.note_controller.update_note_box(note.item)
            update_note_selection_box_for(canvas, note.item)
            set_committed_note_html_for(note.item, note.item.toHtml())
        restyled_labels = self._restyle_arrow_labels(canvas, state.settings)
        if state.notes or restyled_labels:
            refresh_selection_outline_for(canvas)

    def _change_text_settings(
        self, values: dict[str, object], *, restyle_text: bool = False
    ) -> None:
        changed = {
            name: value
            for name, value in values.items()
            if self._text_value(name) != value
        }
        if not changed:
            return
        items = (
            note_items_for(self.canvas)
            if restyle_text or NOTE_APPEARANCE_FIELDS.intersection(changed)
            else []
        )
        before = _TextStyleChange(
            {name: self._text_value(name) for name in changed},
            self._capture_notes(items),
        )
        with document_transaction(self.canvas, history_service=self.history):
            self._apply_text_settings(self.canvas, changed, restyle_text=restyle_text)
            after = _TextStyleChange(dict(changed), self._capture_notes(items))
            if (
                self.history.push(
                    SetAnnotationStyleCommand(before, after, self._restore_text_style)
                )
                is False
            ):
                raise RuntimeError("Text style history push did not commit")

    def set_note_appearance(self, values: dict[str, object]) -> None:
        if not values.keys() <= NOTE_APPEARANCE_FIELDS:
            raise ValueError("Unknown note appearance setting.")
        for name, value in values.items():
            if name.endswith("enabled"):
                if type(value) is not bool:
                    raise ValueError(f"{name} must be boolean.")
            elif name.endswith("color"):
                if not is_hex_color(value):
                    raise ValueError(f"{name} must be a #RRGGBB color.")
            else:
                minimum = {
                    "note_box_alpha": 0.0,
                    "note_border_width": 0.5,
                    "note_padding": 2.0,
                    "text_line_spacing": 0.8,
                }[name]
                if (
                    not is_document_number(value)
                    or float(cast("float", value)) < minimum
                ):
                    raise ValueError(f"{name} must be finite and at least {minimum}.")
                if name == "note_box_alpha" and float(cast("float", value)) > 1.0:
                    raise ValueError("note_box_alpha must not exceed 1.")
        self._change_text_settings(values)

    def set_text_font_family_default(self, family: str) -> None:
        if not family.strip():
            raise ValueError("Text font family must not be empty.")
        family.encode("utf-8")
        self._change_text_settings({"text_font_family": family})

    def suspend_selection_outline(self, suspend: bool) -> None:
        selection_style_state_for(self.canvas).suspend_outline = bool(suspend)

    def set_text_color(self, color: QColor) -> None:
        if color.isValid():
            self._change_text_settings({"text_color": color.name()}, restyle_text=True)

    def apply_text_preset_acs(self) -> None:
        self._change_text_settings(
            {
                "text_font_family": "Arial",
                "text_font_size": font_size_pt_for(self.canvas),
                "text_font_weight": QFont.Weight.Normal,
                "text_italic": False,
                "text_color": QColor(atom_color_for(self.canvas)).name(),
                "text_alignment": Qt.AlignmentFlag.AlignLeft,
                "text_line_spacing": 1.0,
                "note_box_enabled": False,
                "note_border_enabled": False,
            },
            restyle_text=True,
        )

    def apply_text_preset_paper_thin(self) -> None:
        self._change_text_settings(
            {
                "text_font_family": "Arial",
                "text_font_size": max(9, font_size_pt_for(self.canvas) - 1),
                "text_font_weight": QFont.Weight.Normal,
                "text_italic": False,
                "text_color": "#222222",
                "text_alignment": Qt.AlignmentFlag.AlignLeft,
                "text_line_spacing": 1.05,
                "note_box_enabled": False,
                "note_border_enabled": False,
            },
            restyle_text=True,
        )

    def apply_text_preset_paper_bold(self) -> None:
        self._change_text_settings(
            {
                "text_font_family": "Arial",
                "text_font_size": font_size_pt_for(self.canvas) + 2,
                "text_font_weight": QFont.Weight.DemiBold,
                "text_italic": False,
                "text_color": "#111111",
                "text_alignment": Qt.AlignmentFlag.AlignLeft,
                "text_line_spacing": 1.1,
                "note_box_enabled": True,
                "note_box_color": "#ffffff",
                "note_box_alpha": 1.0,
                "note_border_enabled": True,
                "note_border_color": "#111111",
                "note_border_width": 1.2,
                "note_padding": 8.0,
            },
            restyle_text=True,
        )

    def set_note_box_color(self, color: QColor) -> None:
        if color.isValid():
            self.set_note_appearance({"note_box_color": color.name()})

    def set_note_border_color(self, color: QColor) -> None:
        if color.isValid():
            self.set_note_appearance({"note_border_color": color.name()})


__all__ = ["CanvasStyleController"]
