from __future__ import annotations


def main_window_scrollbar_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QScrollBar:horizontal {{
                background: {_P["surface_app"]};
                height: 10px;
                margin: 0;
                border-top: 1px solid {_P["border"]};
            }}
            QScrollBar::handle:horizontal {{
                background: {_P["scrollbar"]};
                border: 2px solid {_P["surface_app"]};
                border-radius: 8px;
                min-width: 36px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {_P["scrollbar_hover"]};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                background: transparent;
                border: none;
                width: 0px;
                subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:horizontal {{
                subcontrol-position: left;
            }}
            QScrollBar::add-line:horizontal {{
                subcontrol-position: right;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: {_P["surface_app"]};
            }}
            QScrollBar:vertical {{
                background: {_P["surface_app"]};
                width: 10px;
                margin: 0;
                border-left: 1px solid {_P["border"]};
            }}
            QScrollBar::handle:vertical {{
                background: {_P["scrollbar"]};
                border: 2px solid {_P["surface_app"]};
                border-radius: 8px;
                min-height: 36px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_P["scrollbar_hover"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                background: transparent;
                border: none;
                height: 0px;
                subcontrol-origin: margin;
            }}
            QScrollBar::sub-line:vertical {{
                subcontrol-position: top;
            }}
            QScrollBar::add-line:vertical {{
                subcontrol-position: bottom;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: {_P["surface_app"]};
            }}
            QAbstractScrollArea::corner {{
                background: {_P["surface_app"]};
                border-top: 1px solid {_P["border"]};
                border-left: 1px solid {_P["border"]};
            }}
"""


__all__ = ["main_window_scrollbar_stylesheet"]
