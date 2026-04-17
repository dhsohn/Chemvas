from __future__ import annotations


MAIN_WINDOW_STYLESHEET = """
            QMainWindow {
                background: #f0ebe4;
            }
            QToolBar {
                background: #f7f3ee;
                border: none;
                border-bottom: 1px solid #ddd5ca;
                spacing: 4px;
                padding: 3px;
            }
            QToolBar::separator {
                background: #ddd5ca;
                width: 1px;
                height: 20px;
                margin: 4px 6px;
            }
            QToolButton {
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 5px;
                color: #3d3229;
            }
            QToolButton:hover {
                background: #ebe4da;
                border-color: #d4c9bb;
            }
            QToolButton:pressed {
                background: #ddd3c5;
                border-color: #c4b6a4;
            }
            QToolButton:checked {
                background: #e8ddd0;
                border-color: #b8a48e;
            }
            QLabel, QCheckBox, QGroupBox, QTabBar, QDockWidget, QToolButton {
                color: #3d3229;
            }
            QDockWidget {
                background: #f7f3ee;
                border: 1px solid #ddd5ca;
            }
            QTabWidget::pane {
                border: 1px solid #ddd5ca;
                background: #f7f3ee;
            }
            QTabBar::tab {
                background: #f0ebe4;
                padding: 6px 10px;
                border: 1px solid #ddd5ca;
                border-bottom: none;
                margin-right: 2px;
                color: #3d3229;
            }
            QTabBar::tab:selected {
                background: #faf8f5;
            }
            QTabWidget#canvasTabs {
                background: #f0ebe4;
            }
            QTabWidget#canvasTabs::tab-bar {
                alignment: left;
                left: 8px;
            }
            QTabWidget#canvasTabs::pane {
                border: 1px solid #ddd5ca;
                background: #f7f3ee;
            }
            QTabWidget#canvasTabs QTabBar {
                background: #f0ebe4;
                padding: 3px 6px 0 6px;
            }
            QTabWidget#canvasTabs QTabBar::tab {
                background: transparent;
                color: #5b5045;
                border: 1px solid transparent;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                padding: 4px 12px 5px 12px;
                margin: 0 2px 0 0;
            }
            QTabWidget#canvasTabs QTabBar::tab:last {
                padding: 4px 8px 5px 8px;
                min-width: 18px;
            }
            QTabWidget#canvasTabs QTabBar::tab:hover:!selected {
                background: #e7dfd4;
            }
            QTabWidget#canvasTabs QTabBar::tab:selected {
                background: #faf8f5;
                color: #312a24;
                border-color: #d8d0c5;
            }
            QTabWidget#canvasTabs QTabBar QToolButton {
                background: transparent;
                border: none;
                border-radius: 5px;
                color: #5b5045;
                padding: 4px 6px;
            }
            QTabWidget#canvasTabs QTabBar QToolButton:hover {
                background: #e7dfd4;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton {
                background: transparent;
                border: 1px solid transparent;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                color: #5b5045;
                font-size: 18px;
                font-weight: 500;
                margin: 0 4px 0 0;
                min-width: 26px;
                padding: 1px 6px 5px 6px;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton:hover {
                background: #e7dfd4;
                border-color: #ddd5ca;
            }
            QTabWidget#canvasTabs QToolButton#sheetAddButton:pressed {
                background: #ddd3c5;
            }
            QScrollBar:horizontal {
                background: #efe8de;
                height: 16px;
                margin: 0 16px 0 16px;
                border-top: 1px solid #ddd5ca;
            }
            QScrollBar::handle:horizontal {
                background: #f8f4ee;
                border: 1px solid #cfc3b3;
                border-radius: 8px;
                min-width: 36px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: #efe8de;
                border: none;
                width: 16px;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:horizontal {
                subcontrol-position: left;
            }
            QScrollBar::add-line:horizontal {
                subcontrol-position: right;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: #efe8de;
            }
            QScrollBar:vertical {
                background: #efe8de;
                width: 16px;
                margin: 16px 0 16px 0;
                border-left: 1px solid #ddd5ca;
            }
            QScrollBar::handle:vertical {
                background: #f8f4ee;
                border: 1px solid #cfc3b3;
                border-radius: 8px;
                min-height: 36px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: #efe8de;
                border: none;
                height: 16px;
                subcontrol-origin: margin;
            }
            QScrollBar::sub-line:vertical {
                subcontrol-position: top;
            }
            QScrollBar::add-line:vertical {
                subcontrol-position: bottom;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: #efe8de;
            }
            QAbstractScrollArea::corner {
                background: #efe8de;
                border-top: 1px solid #ddd5ca;
                border-left: 1px solid #ddd5ca;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 3px 6px;
                color: #3d3229;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #b8a48e;
            }
            QSpinBox, QDoubleSpinBox {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 2px 6px;
                color: #3d3229;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
                width: 14px;
            }
            QFrame#spinFrame {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
            }
            QFrame#spinFrame QDoubleSpinBox {
                background: transparent;
                border: none;
                padding: 2px 6px;
                color: #3d3229;
            }
            QToolButton#spinUpButton {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
                border-bottom: 1px solid #d4c9bb;
            }
            QToolButton#spinDownButton {
                background: #f7f3ee;
                border-left: 1px solid #d4c9bb;
            }
            QComboBox QAbstractItemView {
                background: #faf8f5;
                color: #3d3229;
                border: 1px solid #d4c9bb;
                selection-background-color: #e8ddd0;
                selection-color: #3d3229;
            }
            QAbstractItemView {
                background: #faf8f5;
                color: #3d3229;
                border: 1px solid #d4c9bb;
            }
            QAbstractItemView::item {
                background: #faf8f5;
                color: #3d3229;
            }
            QPushButton {
                color: #3d3229;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 4px 12px;
                background: #faf8f5;
            }
            QPushButton:hover {
                background: #ebe4da;
                border-color: #c4b6a4;
            }
            QPushButton:pressed {
                background: #ddd3c5;
            }
            QMenu {
                background: #faf8f5;
                border: 1px solid #ddd5ca;
                border-radius: 6px;
                padding: 4px 0;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                color: #3d3229;
            }
            QMenu::item:selected {
                background: #ebe4da;
                border-radius: 4px;
            }
            QMenu::separator {
                height: 1px;
                background: #ddd5ca;
                margin: 4px 8px;
            }
            QDialog, QMessageBox {
                background: #f4f0ea;
            }
            QDialog QLabel, QMessageBox QLabel {
                color: #3d3229;
            }
            QDialog QLineEdit, QMessageBox QLineEdit {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 3px 6px;
                color: #3d3229;
            }
            QDialog QPushButton, QMessageBox QPushButton {
                background: #faf8f5;
                border: 1px solid #d4c9bb;
                border-radius: 4px;
                padding: 5px 14px;
                color: #3d3229;
            }
            QDialog QPushButton:hover, QMessageBox QPushButton:hover {
                background: #ebe4da;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #ddd3c5;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                background: #b8a48e;
                border-radius: 6px;
                margin: -4px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #a6917a;
            }
            QStatusBar {
                background: #f7f3ee;
                border-top: 1px solid #ddd5ca;
                color: #7a6e61;
                padding: 2px 8px;
            }
            QStatusBar QLabel {
                color: #7a6e61;
            }
"""

TOOLBAR_BUTTON_STYLE = (
    "QToolButton {"
    " border: 1px solid transparent;"
    " border-radius: 5px;"
    " padding: 4px;"
    "}"
    "QToolButton:hover {"
    " background-color: #ebe4da;"
    " border-color: #d4c9bb;"
    "}"
    "QToolButton:pressed {"
    " background-color: #ddd3c5;"
    " border-color: #c4b6a4;"
    "}"
    "QToolButton:checked {"
    " background-color: #e8ddd0;"
    " border-color: #b8a48e;"
    "}"
)

TOOLBAR_MENU_BUTTON_STYLE = (
    "QToolButton {"
    " border: 1px solid transparent;"
    " border-radius: 5px;"
    " padding: 4px;"
    " padding-right: 8px;"
    "}"
    "QToolButton:hover {"
    " background-color: #ebe4da;"
    " border-color: #d4c9bb;"
    "}"
    "QToolButton:pressed {"
    " background-color: #ddd3c5;"
    " border-color: #c4b6a4;"
    "}"
    "QToolButton:checked {"
    " background-color: #e8ddd0;"
    " border-color: #b8a48e;"
    "}"
    "QToolButton::menu-button {"
    " subcontrol-origin: padding;"
    " subcontrol-position: top right;"
    " width: 14px;"
    " border: none;"
    " background: transparent;"
    "}"
    "QToolButton::menu-button:hover { background: transparent; }"
    "QToolButton::menu-button:pressed { background: transparent; }"
    "QToolButton::menu-indicator { image: none; width: 0px; height: 0px; }"
    "QToolButton::menu-arrow { image: none; width: 0px; height: 0px; border: none; background: transparent; }"
)

SMILES_RENDER_BUTTON_STYLE = (
    "QToolButton#smiles_render_button {"
    " border: 1px solid #d4c9bb;"
    " border-radius: 5px;"
    " padding: 3px 10px;"
    " background-color: #faf8f5;"
    " color: #3d3229;"
    "}"
    "QToolButton#smiles_render_button:hover {"
    " background-color: #ebe4da;"
    " border-color: #c4b6a4;"
    "}"
    "QToolButton#smiles_render_button:pressed {"
    " background-color: #ddd3c5;"
    " border-color: #b8a48e;"
    "}"
)


__all__ = ["MAIN_WINDOW_STYLESHEET"]
