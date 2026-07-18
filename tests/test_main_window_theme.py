from __future__ import annotations

from pathlib import Path

from chemvas.ui import main_window_stylesheet as main_window_stylesheet_module
from chemvas.ui import main_window_theme
from chemvas.ui.main_window_canvas_tab_styles import main_window_canvas_tab_stylesheet
from chemvas.ui.main_window_chrome_styles import main_window_chrome_stylesheet
from chemvas.ui.main_window_form_styles import main_window_form_stylesheet
from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.main_window_scrollbar_styles import main_window_scrollbar_stylesheet
from chemvas.ui.main_window_status_styles import main_window_status_stylesheet
from chemvas.ui.main_window_stylesheet import (
    MAIN_WINDOW_STYLESHEET,
    build_main_window_stylesheet,
)
from chemvas.ui.main_window_toolbar_styles import (
    CONTEXT_BAR_BUTTON_HEIGHT,
    CONTEXT_BAR_CONTENT_HEIGHT,
    CONTEXT_BAR_ICON_SIZE,
    CONTEXT_SEGMENT_STYLE,
    SMILES_RENDER_BUTTON_STYLE,
    TOOLBAR_BUTTON_SIZE,
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_ICON_SIZE,
    TOOLBAR_MENU_BUTTON_STYLE,
    TOOLBAR_THICKNESS,
)


def test_theme_module_reexports_split_style_contract() -> None:
    assert main_window_theme.PALETTE is PALETTE
    assert main_window_theme.MAIN_WINDOW_STYLESHEET is MAIN_WINDOW_STYLESHEET
    assert main_window_theme.TOOLBAR_BUTTON_STYLE is TOOLBAR_BUTTON_STYLE
    assert main_window_theme.TOOLBAR_MENU_BUTTON_STYLE is TOOLBAR_MENU_BUTTON_STYLE
    assert main_window_theme.CONTEXT_SEGMENT_STYLE is CONTEXT_SEGMENT_STYLE
    assert main_window_theme.SMILES_RENDER_BUTTON_STYLE is SMILES_RENDER_BUTTON_STYLE
    assert main_window_theme.TOOLBAR_THICKNESS == TOOLBAR_THICKNESS
    assert main_window_theme.TOOLBAR_BUTTON_SIZE == TOOLBAR_BUTTON_SIZE
    assert main_window_theme.TOOLBAR_ICON_SIZE == TOOLBAR_ICON_SIZE
    assert main_window_theme.CONTEXT_BAR_BUTTON_HEIGHT == CONTEXT_BAR_BUTTON_HEIGHT
    assert main_window_theme.CONTEXT_BAR_CONTENT_HEIGHT == CONTEXT_BAR_CONTENT_HEIGHT
    assert main_window_theme.CONTEXT_BAR_ICON_SIZE == CONTEXT_BAR_ICON_SIZE


def test_stylesheet_uses_shared_palette_values() -> None:
    assert PALETTE["surface_app"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["surface_canvas"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["accent"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["danger_bg"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["danger_text"] in MAIN_WINDOW_STYLESHEET


def test_palette_exposes_design_system_shell_tokens() -> None:
    assert PALETTE["icon"] == "#2f2f2c"
    assert PALETTE["icon_muted"] == "#8c8c87"
    assert PALETTE["icon_pale_fill"] == "#ededeb"
    assert PALETTE["checked_bg"] == "#d6ece7"
    assert PALETTE["checked_border"] == "#5fb3a6"
    assert PALETTE["checked_text"] == "#0b5750"
    assert PALETTE["danger_bg"] == "#f6eded"
    assert PALETTE["danger_border"] == "#dbbcbc"
    assert PALETTE["danger_text"] == "#8a2020"


def test_main_window_stylesheet_composes_section_modules() -> None:
    expected = "\n".join(
        (
            main_window_chrome_stylesheet(PALETTE),
            main_window_canvas_tab_stylesheet(PALETTE),
            main_window_scrollbar_stylesheet(PALETTE),
            main_window_form_stylesheet(PALETTE),
            main_window_status_stylesheet(PALETTE),
        )
    )
    source = Path(main_window_stylesheet_module.__file__).read_text()

    assert MAIN_WINDOW_STYLESHEET == expected
    assert build_main_window_stylesheet(PALETTE) == expected
    assert "QToolBar {" in main_window_chrome_stylesheet(PALETTE)
    assert "QTabWidget#canvasTabs" in main_window_canvas_tab_stylesheet(PALETTE)
    assert "QScrollBar:horizontal" in main_window_scrollbar_stylesheet(PALETTE)
    assert "QDialog, QMessageBox" in main_window_form_stylesheet(PALETTE)
    assert "QStatusBar {" in main_window_status_stylesheet(PALETTE)
    assert "QToolBar {" not in source
    assert "QStatusBar {" not in source


def test_toolbar_styles_keep_expected_selectors() -> None:
    assert "border-radius: 6px" in main_window_chrome_stylesheet(PALETTE)
    assert "padding: 2px" in main_window_chrome_stylesheet(PALETTE)
    assert "QToolButton:checked" in TOOLBAR_BUTTON_STYLE
    assert "QToolButton::menu-button" in TOOLBAR_MENU_BUTTON_STYLE
    assert "font-size: 13px" in CONTEXT_SEGMENT_STYLE
    assert "QToolButton#smiles_render_button" in SMILES_RENDER_BUTTON_STYLE
    assert PALETTE["checked_bg"] in TOOLBAR_BUTTON_STYLE
    assert PALETTE["accent_pressed"] in SMILES_RENDER_BUTTON_STYLE
