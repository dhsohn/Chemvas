from __future__ import annotations

from chemvas.shell.palette import PALETTE
from chemvas.shell.stylesheet import (
    MAIN_WINDOW_STYLESHEET,
    build_main_window_stylesheet,
    main_window_canvas_tab_stylesheet,
    main_window_chrome_stylesheet,
    main_window_form_stylesheet,
    main_window_scrollbar_stylesheet,
    main_window_status_stylesheet,
)
from chemvas.shell.toolbar_styles import (
    TOOLBAR_BUTTON_STYLE,
    TOOLBAR_MENU_BUTTON_STYLE,
)


def test_stylesheet_uses_shared_palette_values() -> None:
    assert PALETTE["surface_app"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["surface_canvas"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["accent"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["danger_bg"] in MAIN_WINDOW_STYLESHEET
    assert PALETTE["danger_text"] in MAIN_WINDOW_STYLESHEET


def test_main_window_stylesheet_composes_its_sections() -> None:
    expected = "\n".join(
        (
            main_window_chrome_stylesheet(PALETTE),
            main_window_canvas_tab_stylesheet(PALETTE),
            main_window_scrollbar_stylesheet(PALETTE),
            main_window_form_stylesheet(PALETTE),
            main_window_status_stylesheet(PALETTE),
        )
    )

    assert MAIN_WINDOW_STYLESHEET == expected
    assert build_main_window_stylesheet(PALETTE) == expected
    assert "QToolBar {" in main_window_chrome_stylesheet(PALETTE)
    assert "QTabWidget#canvasTabs" in main_window_canvas_tab_stylesheet(PALETTE)
    assert "QScrollBar:horizontal" in main_window_scrollbar_stylesheet(PALETTE)
    assert "QDialog, QMessageBox" in main_window_form_stylesheet(PALETTE)
    assert "QStatusBar {" in main_window_status_stylesheet(PALETTE)


def test_toolbar_styles_keep_expected_selectors() -> None:
    assert "QToolButton:checked" in TOOLBAR_BUTTON_STYLE
    assert "QToolButton::menu-button" in TOOLBAR_MENU_BUTTON_STYLE
    assert PALETTE["checked_bg"] in TOOLBAR_BUTTON_STYLE
