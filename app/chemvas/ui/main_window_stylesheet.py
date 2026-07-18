from __future__ import annotations

from chemvas.ui.main_window_canvas_tab_styles import main_window_canvas_tab_stylesheet
from chemvas.ui.main_window_chrome_styles import main_window_chrome_stylesheet
from chemvas.ui.main_window_form_styles import main_window_form_stylesheet
from chemvas.ui.main_window_palette import PALETTE
from chemvas.ui.main_window_scrollbar_styles import main_window_scrollbar_stylesheet
from chemvas.ui.main_window_status_styles import main_window_status_stylesheet


def build_main_window_stylesheet(palette=PALETTE) -> str:
    return "\n".join(
        (
            main_window_chrome_stylesheet(palette),
            main_window_canvas_tab_stylesheet(palette),
            main_window_scrollbar_stylesheet(palette),
            main_window_form_stylesheet(palette),
            main_window_status_stylesheet(palette),
        )
    )


MAIN_WINDOW_STYLESHEET = build_main_window_stylesheet()


__all__ = ["MAIN_WINDOW_STYLESHEET", "build_main_window_stylesheet"]
