from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.main_window_ui_assembly_service import ArrowButton


class MainWindowDocumentActionService:
    @staticmethod
    def normalize_xyz_export_path(dialog_path: str | None) -> str | None:
        if not dialog_path:
            return None
        path = Path(dialog_path)
        if path.suffix:
            return str(path)
        return str(path.with_suffix(".xyz"))

    def default_xyz_export_path(self, window) -> str:
        if window._current_file_path:
            return str(Path(window._current_file_path).with_suffix(".xyz"))
        return ""

    def default_save_dialog_path(self, window) -> str:
        return window._current_file_path or ""

    def save_canvas_to_path(self, window, path: str, *, message_box) -> bool:
        try:
            window._save_document_state(path)
        except Exception as exc:
            message_box.warning(window, "Save Error", f"Failed to save file:\n{exc}")
            return False
        window._current_file_path = path
        window.statusBar().showMessage(f"Saved: {path}")
        return True

    def save_canvas(self, window, *, resolve_save_path) -> None:
        path = resolve_save_path(current_path=window._current_file_path)
        if path is None:
            window._save_canvas_as()
            return
        window._save_canvas_to_path(path)

    def save_canvas_as(self, window, *, file_dialog, resolve_save_as_path) -> None:
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Save Drawing As",
            window._default_save_dialog_path(),
            "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
        )
        path = resolve_save_as_path(dialog_path)
        if path is None:
            return
        window._save_canvas_to_path(path)

    def export_xyz(self, window, *, file_dialog, message_box) -> None:
        dialog_path, _ = file_dialog.getSaveFileName(
            window,
            "Export 3D XYZ",
            window._default_xyz_export_path(),
            "XYZ (*.xyz);;All Files (*)",
        )
        path = window._normalize_xyz_export_path(dialog_path)
        if path is None:
            return
        try:
            window.canvas.export_xyz(path)
        except Exception as exc:
            message_box.warning(window, "Export Error", f"Failed to export XYZ:\n{exc}")
            return
        window.statusBar().showMessage(f"Exported XYZ: {path}")

    def load_canvas(self, window, *, file_dialog, message_box, read_document, resolve_load_path) -> None:
        dialog_path, _ = file_dialog.getOpenFileName(
            window,
            "Load Drawing",
            "",
            "LiteDraw (*.ldraw);;JSON (*.json);;All Files (*)",
        )
        path = resolve_load_path(dialog_path)
        if path is None:
            return
        try:
            document = read_document(path)
        except Exception as exc:
            message_box.warning(window, "Load Error", f"Failed to load file:\n{exc}")
            return
        state = document.state
        if "sheets" in state:
            window._restore_workbook_document(state)
        else:
            window._restore_single_sheet_document(state)
        window._current_file_path = path
        window.statusBar().showMessage(f"Loaded: {path}")

    def set_bond_length(self, window) -> None:
        current = window.canvas.renderer.style.bond_length_px
        dialog = QDialog(window)
        dialog.setWindowTitle("Bond Length")
        dialog.setStyleSheet(window.styleSheet())
        layout = QVBoxLayout(dialog)

        label = QLabel("Set bond length (px):")
        layout.addWidget(label)

        frame = QFrame()
        frame.setObjectName("spinFrame")
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(2, 2, 2, 2)
        frame_layout.setSpacing(0)

        spin = QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(10.0, 200.0)
        spin.setValue(current)
        spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        spin.setMinimumWidth(90)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        frame_layout.addWidget(spin)

        buttons_col = QVBoxLayout()
        buttons_col.setContentsMargins(0, 0, 0, 0)
        buttons_col.setSpacing(0)
        up_btn = ArrowButton("up")
        up_btn.setObjectName("spinUpButton")
        up_btn.setFixedSize(18, 14)
        down_btn = ArrowButton("down")
        down_btn.setObjectName("spinDownButton")
        down_btn.setFixedSize(18, 14)
        buttons_col.addWidget(up_btn)
        buttons_col.addWidget(down_btn)
        frame_layout.addLayout(buttons_col)

        layout.addWidget(frame)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        action_row.addWidget(ok_btn)
        action_row.addWidget(cancel_btn)
        layout.addLayout(action_row)

        up_btn.clicked.connect(lambda: spin.setValue(min(200.0, spin.value() + 1.0)))
        down_btn.clicked.connect(lambda: spin.setValue(max(10.0, spin.value() - 1.0)))
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            window.canvas.set_bond_length(spin.value())


__all__ = ["MainWindowDocumentActionService"]
