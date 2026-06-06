from __future__ import annotations


def main_window_chrome_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QMainWindow {{
                background: {_P["surface_app"]};
            }}
            QToolBar {{
                background: {_P["surface_bar"]};
                border: none;
                border-bottom: 1px solid {_P["border"]};
                spacing: 4px;
                padding: 5px 6px;
            }}
            QToolBar#contextOptionsBar {{
                background: {_P["surface_context"]};
                border-bottom: 1px solid {_P["border"]};
                padding: 3px 8px;
            }}
            QToolBar::separator {{
                background: {_P["border"]};
            }}
            QToolBar::separator:horizontal {{
                width: 1px;
                height: 18px;
                margin: 4px 8px;
            }}
            QToolBar::separator:vertical {{
                width: 20px;
                height: 1px;
                margin: 7px 6px;
            }}
            QToolBar QLabel#toolbarSectionLabel {{
                background: transparent;
                border: none;
                color: {_P["text_faint"]};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.6px;
                margin: 0 2px;
                padding: 2px 4px;
                text-transform: uppercase;
            }}
            QToolButton {{
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 5px;
                color: {_P["text"]};
            }}
            QToolButton:hover {{
                background: {_P["hover"]};
                border-color: transparent;
            }}
            QToolButton:pressed {{
                background: {_P["pressed"]};
                border-color: transparent;
            }}
            QToolButton:checked {{
                background: {_P["checked_bg"]};
                border-color: {_P["checked_border"]};
                color: {_P["checked_text"]};
            }}
            QToolButton:disabled {{
                color: {_P["text_faint"]};
                background: transparent;
                border-color: transparent;
            }}
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {{
                color: {_P["text"]};
            }}
            QDockWidget {{
                background: {_P["surface_panel"]};
                border: 1px solid {_P["border"]};
            }}
            QTabWidget::pane {{
                border: 1px solid {_P["border"]};
                background: {_P["surface_panel"]};
            }}
            QTabBar::tab {{
                background: {_P["surface_app"]};
                padding: 6px 10px;
                border: 1px solid {_P["border"]};
                border-bottom: none;
                margin-right: 2px;
                color: {_P["text"]};
            }}
            QTabBar::tab:selected {{
                background: {_P["surface_canvas"]};
            }}
"""


__all__ = ["main_window_chrome_stylesheet"]
