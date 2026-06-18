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
                background: #f6eded;
                border-top: 1px solid {_P["border_strong"]};
                color: #8a2020;
            }}
            QStatusBar QLabel {{
                color: {_P["text_muted"]};
            }}
            QStatusBar QLabel#statusContextLabel {{
                border-left: 1px solid {_P["border"]};
                padding: 0 8px;
            }}
            QStatusBar QLabel#statusZoomLabel {{
                color: {_P["text"]};
                font-weight: 500;
                padding: 0 8px 0 4px;
            }}
"""


__all__ = ["main_window_status_stylesheet"]
