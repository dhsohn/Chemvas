from types import SimpleNamespace

from chemvas.ui.canvas_text_style_state import (
    CanvasTextStyleState,
    set_text_style_for,
    text_style_state_for,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


def test_text_style_state_for_uses_runtime_state() -> None:
    runtime_state = SimpleNamespace(
        text_style_state=CanvasTextStyleState(text_font_size=18)
    )
    canvas = SimpleNamespace(runtime_state=runtime_state)

    assert text_style_state_for(canvas) is runtime_state.text_style_state
    assert text_style_state_for(canvas).text_font_size == 18


def test_text_style_state_for_does_not_read_legacy_fake_canvas_attrs() -> None:
    color = QColor("#abcdef")
    canvas = SimpleNamespace(
        text_font_family="Courier",
        text_font_size=11,
        text_font_weight=500,
        text_italic=True,
        text_color=color,
        text_alignment=Qt.AlignmentFlag.AlignRight,
        text_line_spacing=1.25,
        note_box_enabled=True,
        note_box_alpha=0.5,
        note_padding=9.0,
    )

    state = text_style_state_for(canvas)

    assert state.text_font_family == "Arial"
    assert state.text_font_size == 12
    assert state.text_font_weight == 400
    assert state.text_italic is False
    assert state.text_color is not color
    assert state.text_color.name() == "#222222"
    assert state.text_alignment == Qt.AlignmentFlag.AlignLeft
    assert state.text_line_spacing == 1.0
    assert state.note_box_enabled is False
    assert state.note_box_alpha == 1.0
    assert state.note_padding == 6.0


def test_set_text_style_for_updates_state_without_canvas_attr_mirror() -> None:
    canvas = SimpleNamespace()

    set_text_style_for(canvas, "text_font_size", 15)
    set_text_style_for(canvas, "text_italic", True)
    set_text_style_for(canvas, "note_padding", 7.5)

    state = text_style_state_for(canvas)
    assert state.text_font_size == 15
    assert state.text_italic is True
    assert state.note_padding == 7.5
    assert not hasattr(canvas, "text_font_size")
    assert not hasattr(canvas, "text_italic")
    assert not hasattr(canvas, "note_padding")
