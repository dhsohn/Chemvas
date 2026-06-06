from __future__ import annotations


def main_window_canvas_tab_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QTabWidget#canvasTabs {{
                background: {_P["surface_app"]};
            }}
            QTabWidget#canvasTabs::tab-bar {{
                alignment: left;
                left: 8px;
            }}
            QTabWidget#canvasTabs::pane {{
                border: 1px solid {_P["border"]};
                background: {_P["surface_canvas"]};
            }}
            QTabWidget#canvasTabs QTabBar {{
                background: {_P["surface_app"]};
                padding: 2px 6px 0 6px;
            }}
            QTabWidget#canvasTabs QTabBar::tab {{
                background: transparent;
                color: {_P["text_muted"]};
                border: 1px solid transparent;
                border-top: 2px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                padding: 4px 14px 5px 14px;
                margin: 0 2px 0 0;
            }}
            QTabWidget#canvasTabs QTabBar::tab:last {{
                padding: 4px 8px 5px 8px;
                min-width: 20px;
            }}
            QTabWidget#canvasTabs QTabBar::tab:hover:!selected {{
                background: {_P["hover"]};
            }}
            QTabWidget#canvasTabs QTabBar::tab:selected {{
                background: {_P["surface_canvas"]};
                color: {_P["text"]};
                border-color: {_P["border"]};
                border-top-color: {_P["accent"]};
            }}
            QTabWidget#canvasTabs QTabBar QToolButton {{
                background: transparent;
                border: none;
                border-radius: 8px;
                color: {_P["text_muted"]};
                padding: 4px 6px;
            }}
            QTabWidget#canvasTabs QTabBar QToolButton:hover {{
                background: {_P["hover"]};
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton {{
                background: transparent;
                border: 1px solid transparent;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
                color: {_P["text_muted"]};
                font-size: 18px;
                font-weight: 500;
                margin: 0 4px 0 0;
                min-width: 26px;
                padding: 1px 6px 5px 6px;
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton:hover {{
                background: {_P["hover"]};
                border-color: {_P["border"]};
            }}
            QTabWidget#canvasTabs QToolButton#sheetAddButton:pressed {{
                background: {_P["pressed"]};
            }}
"""


__all__ = ["main_window_canvas_tab_stylesheet"]
