from __future__ import annotations


def main_window_form_stylesheet(palette) -> str:
    _P = palette
    return f"""
            QLineEdit, QComboBox, QSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 4px 7px;
                color: {_P["text"]};
                selection-background-color: {_P["checked_bg"]};
                selection-color: {_P["checked_text"]};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {_P["accent"]};
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 2px 6px;
                color: {_P["text"]};
            }}
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
                width: 14px;
            }}
            QFrame#spinFrame {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
            }}
            QFrame#spinFrame QDoubleSpinBox {{
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: {_P["text"]};
            }}
            QToolButton#spinUpButton {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
                border-bottom: 1px solid {_P["border_strong"]};
            }}
            QToolButton#spinDownButton {{
                background: {_P["surface_bar"]};
                border-left: 1px solid {_P["border_strong"]};
            }}
            QComboBox QAbstractItemView {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
                selection-background-color: {_P["checked_bg"]};
                selection-color: {_P["checked_text"]};
            }}
            QAbstractItemView {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
            }}
            QAbstractItemView::item {{
                background: {_P["surface_input"]};
                color: {_P["text"]};
            }}
            QPushButton {{
                color: {_P["text"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 5px 12px;
                background: {_P["surface_input"]};
            }}
            QPushButton:hover {{
                background: {_P["hover"]};
                border-color: {_P["checked_border"]};
            }}
            QPushButton:pressed {{
                background: {_P["pressed"]};
            }}
            QMenu {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border"]};
                border-radius: 8px;
                padding: 5px 0;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                color: {_P["text"]};
            }}
            QMenu::item:selected {{
                background: {_P["hover"]};
                border-radius: 4px;
            }}
            QMenu::separator {{
                height: 1px;
                background: {_P["border"]};
                margin: 4px 8px;
            }}
            QDialog, QMessageBox {{
                background: {_P["surface_bar"]};
            }}
            QDialog QLabel, QMessageBox QLabel {{
                color: {_P["text"]};
            }}
            QDialog QLineEdit, QMessageBox QLineEdit {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 3px 6px;
                color: {_P["text"]};
            }}
            QDialog QPushButton, QMessageBox QPushButton {{
                background: {_P["surface_input"]};
                border: 1px solid {_P["border_strong"]};
                border-radius: 8px;
                padding: 5px 14px;
                color: {_P["text"]};
            }}
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {{
                background: {_P["hover"]};
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {_P["border_strong"]};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 12px;
                height: 12px;
                background: {_P["accent"]};
                border-radius: 8px;
                margin: -5px 0;
            }}
            QSlider::handle:horizontal:hover {{
                background: {_P["checked_text"]};
            }}
"""


__all__ = ["main_window_form_stylesheet"]
