from __future__ import annotations


def main_window_status_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QStatusBar {{
                background: {_P["surface_bar"]};
                border-top: 1px solid {_P["border"]};
                color: {_P["text_muted"]};
                padding: 2px 8px;
            }}
            QStatusBar[statusState="error"] {{
                background: {_P["danger_bg"]};
                border-top: 1px solid {_P["danger_border"]};
                color: {_P["danger_text"]};
            }}
            QStatusBar QLabel {{
                color: {_P["text_muted"]};
            }}
            QStatusBar QLabel#statusContextLabel {{
                border-left: 1px solid {_P["border"]};
                padding: 0 8px;
            }}
            QStatusBar QToolButton#statusZoomButton {{
                color: {_P["text_muted"]};
                background: transparent;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                min-width: 18px;
                padding: 1px 5px;
                margin: 0;
            }}
            QStatusBar QToolButton#statusZoomButton:hover {{
                background: {_P["hover"]};
                color: {_P["text"]};
            }}
            QStatusBar QToolButton#statusZoomButton:pressed {{
                background: {_P["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomLabel {{
                color: {_P["text"]};
                font-weight: 500;
            }}
            QStatusBar QToolButton#statusZoomLabel:hover {{
                background: {_P["hover"]};
            }}
            QStatusBar QToolButton#statusZoomLabel:pressed {{
                background: {_P["pressed"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton {{
                color: {_P["text_muted"]};
                background: transparent;
                border: 1px solid {_P["border_strong"]};
                border-radius: 4px;
                font-size: 12px;
                font-weight: 500;
                min-width: 18px;
                padding: 1px 7px;
                margin: 0 0 0 3px;
            }}
            QStatusBar QToolButton#statusZoomFitButton:hover {{
                background: {_P["hover"]};
                color: {_P["text"]};
                border-color: {_P["scrollbar_hover"]};
            }}
            QStatusBar QToolButton#statusZoomFitButton:pressed {{
                background: {_P["pressed"]};
            }}
"""


__all__ = ["main_window_status_stylesheet"]
