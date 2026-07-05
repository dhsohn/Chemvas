from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from core.rdkit_adapter import Molecule3DScene, RDKitAdapter
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer
from PyQt6.QtGui import QFont, QFontMetricsF, QIcon, QPainter
from PyQt6.QtWidgets import QApplication, QToolButton, QWidget

from ui.main_window_palette import PALETTE
from ui.preview_3d_interaction import (
    preview_drag_rotation,
    preview_zoom_for_wheel_delta,
)
from ui.preview_3d_painter import (
    Preview3DPaintState,
    paint_preview_3d_panel,
    preview_caption_font,
    preview_layout_for_widget,
)
from ui.preview_3d_renderer import status_badge_width
from ui.preview_3d_state import preview_payload_signature, preview_status_badge
from ui.preview_3d_worker import Preview3DWorker
from ui.structure_payload_access import build_selected_3d_conversion_payload_for
from ui.structure_payload_logic import model_with_atom_annotations


class Preview3D(QWidget):
    def __init__(self, rdkit_adapter: RDKitAdapter | None = None) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter or RDKitAdapter()
        self._async_enabled = rdkit_adapter is None
        self._preview_request_id = 0
        self._preview_jobs: dict[int, tuple[QThread, Preview3DWorker]] = {}
        # Single-flight guard: at most one preview worker runs at a time. If a
        # newer structure arrives while one is in flight, we remember to rebuild
        # once it finishes instead of spawning parallel RDKit embeddings.
        self._preview_restart_pending = False
        self._disposed = False
        self._pending_model: Any | None = None
        self._pending_annotations: Any | None = None
        self._current_signature: tuple[Any, ...] | None = None
        self._scene: Molecule3DScene | None = None
        self._message = "3D preview unavailable"
        self._formula_text = ""
        self._mw_text = ""
        self._smiles_text = ""
        self._inchikey_text = ""
        self._copy_smiles_button: QToolButton | None = None
        self._copy_inchikey_button: QToolButton | None = None
        self._rotation_x = math.radians(-18.0)
        self._rotation_y = math.radians(22.0)
        self._zoom = 1.0
        self._last_pos: QPointF | None = None
        self._export_xyz_callback: Callable[[], None] | None = None
        self._export_xyz_button: QToolButton | None = None
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(120)
        self._update_timer.timeout.connect(self._rebuild_scene)
        self.setMinimumSize(260, 220)
        self.setMouseTracking(True)

    @property
    def rdkit_adapter(self) -> Any:
        return self._rdkit

    def set_rdkit_adapter(self, rdkit_adapter: Any) -> None:
        self._rdkit = rdkit_adapter

    @property
    def export_xyz_button(self) -> QToolButton | None:
        return self._export_xyz_button

    def set_export_xyz_action(
        self,
        callback: Callable[[], None],
    ) -> None:
        self._export_xyz_callback = callback
        button = self._ensure_export_xyz_button()
        button.setIcon(QIcon())
        self._sync_export_xyz_button()

    def refresh_selected_from_canvas(self, canvas) -> None:
        try:
            model, atom_annotations = build_selected_3d_conversion_payload_for(canvas)
        except Exception as exc:
            self.clear_preview(str(exc))
            return
        self._set_canvas_structure(model, atom_annotations)

    def _set_canvas_structure(self, model, atom_annotations) -> None:
        if not self._async_enabled:
            identifier_model = model_with_atom_annotations(model, atom_annotations)
            identifiers = self._rdkit.compute_identifiers(identifier_model)
            self.set_info(
                identifiers.formula or "",
                "" if identifiers.mw is None else f"{identifiers.mw:.2f}",
                identifiers.smiles or "",
                identifiers.inchikey or "",
            )
        self.set_structure(model, atom_annotations)

    def set_structure(self, model, atom_annotations=None) -> None:
        signature = self._payload_signature(model, atom_annotations)
        if signature == self._current_signature:
            return
        self._current_signature = signature
        self._pending_model = model
        self._pending_annotations = atom_annotations
        self._message = "Updating 3D preview..."
        self._safe_update()
        self._update_timer.start()

    def clear_preview(self, message: str = "3D preview unavailable") -> None:
        self._update_timer.stop()
        self._preview_request_id += 1
        self._preview_restart_pending = False
        self._pending_model = None
        self._pending_annotations = None
        self._current_signature = None
        self._scene = None
        self._message = message
        self._formula_text = ""
        self._mw_text = ""
        self._smiles_text = ""
        self._inchikey_text = ""
        self._sync_export_xyz_button()
        self._safe_update()

    def set_info(self, formula: str, mw: str, smiles: str = "", inchikey: str = "") -> None:
        if (
            formula == self._formula_text
            and mw == self._mw_text
            and smiles == self._smiles_text
            and inchikey == self._inchikey_text
        ):
            return
        self._formula_text = formula
        self._mw_text = mw
        self._smiles_text = smiles
        self._inchikey_text = inchikey
        self._sync_export_xyz_button()
        self._safe_update()

    def _payload_signature(self, model, atom_annotations) -> tuple:
        return preview_payload_signature(model, atom_annotations)

    def _rebuild_scene(self) -> None:
        if self._disposed:
            return
        if self._pending_model is None:
            self._scene = None
            self._message = "3D preview unavailable"
            self._sync_export_xyz_button()
            self._safe_update()
            return
        if self._async_enabled:
            if not self._ensure_rdkit_loaded_for_worker():
                return
            self._start_preview_worker()
            return
        result_method = getattr(self._rdkit, "model_to_3d_scene_result", None)
        if callable(result_method):
            result = result_method(self._pending_model, atom_annotations=self._pending_annotations)
            scene = result.value
            error = result.error
        else:
            scene = self._rdkit.model_to_3d_scene(
                self._pending_model,
                atom_annotations=self._pending_annotations,
            )
            error = getattr(self._rdkit, "last_error", None)
        if scene is None:
            self.clear_preview(error or "Failed to build 3D preview.")
            return
        self._scene = scene
        self._message = ""
        self._sync_export_xyz_button()
        self._safe_update()

    def _ensure_rdkit_loaded_for_worker(self) -> bool:
        if self._rdkit.is_loaded():
            return True
        if self._rdkit.preload():
            return True
        self.clear_preview(self._rdkit.last_error or "RDKit is not available in this environment.")
        return False

    def _start_preview_worker(self) -> None:
        if self._preview_jobs:
            # A worker is already running. Defer: rebuild with the latest pending
            # payload once it finishes, keeping at most one job alive.
            self._preview_restart_pending = True
            return
        self._preview_restart_pending = False
        self._preview_request_id += 1
        request_id = self._preview_request_id
        thread = QThread(self)
        worker = Preview3DWorker(
            request_id,
            None,
            self._pending_model,
            self._pending_annotations,
            rdkit_adapter_factory=RDKitAdapter,
        )
        worker.moveToThread(thread)
        self._preview_jobs[request_id] = (thread, worker)
        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_preview_worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda request_id=request_id: self._on_preview_thread_finished(request_id))
        thread.start()

    def _on_preview_thread_finished(self, request_id: int) -> None:
        self._preview_jobs.pop(request_id, None)
        if self._disposed or self._preview_jobs:
            return
        if self._preview_restart_pending and self._pending_model is not None:
            self._preview_restart_pending = False
            self._rebuild_scene()

    def _handle_preview_worker_finished(
        self,
        request_id: int,
        formula: str | None,
        mw: float | None,
        smiles: str | None,
        inchikey: str | None,
        scene: Molecule3DScene | None,
        error: str | None,
    ) -> None:
        if self._disposed or request_id != self._preview_request_id:
            return
        if error or scene is None:
            self._scene = None
            self._current_signature = None
            self._formula_text = ""
            self._mw_text = ""
            self._smiles_text = ""
            self._inchikey_text = ""
            self._message = error or "Failed to build 3D preview."
            self._sync_export_xyz_button()
            self._safe_update()
            return
        self._formula_text = formula or ""
        self._mw_text = "" if mw is None else f"{mw:.2f}"
        self._smiles_text = smiles or ""
        self._inchikey_text = inchikey or ""
        self._scene = scene
        self._message = ""
        self._sync_export_xyz_button()
        self._safe_update()

    def resizeEvent(self, event) -> None:
        self._sync_export_xyz_button()
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = QPointF(event.position())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._last_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = QPointF(event.position())
            self._rotation_x, self._rotation_y, self._last_pos = preview_drag_rotation(
                self._rotation_x,
                self._rotation_y,
                self._last_pos,
                current,
            )
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            self._zoom = preview_zoom_for_wheel_delta(self._zoom, delta)
            self.update()
        super().wheelEvent(event)

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._disposed = True
        self._preview_request_id += 1
        self._preview_restart_pending = False
        self._update_timer.stop()
        self._stop_preview_jobs()

    def _stop_preview_jobs(self) -> None:
        for thread, _worker in list(self._preview_jobs.values()):
            thread.quit()
            if thread.isRunning():
                thread.wait()
        self._preview_jobs.clear()

    def _safe_update(self) -> None:
        if self._disposed:
            return
        try:
            self.update()
        except RuntimeError:
            self._disposed = True

    def _ensure_export_xyz_button(self) -> QToolButton:
        if self._export_xyz_button is not None:
            return self._export_xyz_button
        button = QToolButton(self)
        button.setObjectName("preview_export_xyz_button")
        button.setText("Export 3D")
        button.setToolTip("Export 3D XYZ")
        button.setStatusTip("Export the selected molecule as 3D XYZ")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.clicked.connect(lambda _checked=False: self._handle_export_xyz_clicked())
        button.setStyleSheet(self._header_button_style("preview_export_xyz_button"))
        self._export_xyz_button = button
        return button

    def _handle_export_xyz_clicked(self) -> None:
        if self._export_xyz_callback is not None:
            self._export_xyz_callback()

    def _sync_export_xyz_button(self) -> None:
        button = self._export_xyz_button
        if button is not None:
            self._apply_export_xyz_button_font()
            button.setVisible(self._scene is not None)
            button.setEnabled(self._scene is not None)
            if self._scene is not None:
                self._position_export_xyz_button()
        self._sync_copy_buttons()

    def _apply_export_xyz_button_font(self) -> None:
        button = self._export_xyz_button
        if button is None:
            return
        font = preview_caption_font(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        button.setFont(font)

    def _position_export_xyz_button(self) -> None:
        button = self._export_xyz_button
        if button is None:
            return
        layout = preview_layout_for_widget(QRectF(self.rect()), [], self.font())
        header = layout["header"]
        metrics = QFontMetricsF(button.font())
        width = max(112.0, metrics.horizontalAdvance(button.text()) + 36.0)
        height = 22.0
        # The status badge (e.g. "Ready") is painted at the header's right edge.
        # Anchor the Export button to the left of it so they never overlap.
        badge_text = preview_status_badge(self._scene, self._message)[0]
        badge_width = status_badge_width(badge_text, QFontMetricsF(preview_caption_font(self.font())))
        badge_gap = 8.0
        x = header.right() - badge_width - badge_gap - width
        y = header.top() + 4.0
        button.setGeometry(round(x), round(y), round(width), round(height))

    def _header_button_style(self, object_name: str) -> str:
        return (
            f"QToolButton#{object_name} {{"
            f"  background: {PALETTE['surface_input']};"
            f"  border: 1px solid {PALETTE['border_strong']};"
            f"  border-radius: 8px;"
            f"  color: {PALETTE['text']};"
            f"  padding: 0;"
            f"  text-align: center;"
            f"}}"
            f"QToolButton#{object_name}:hover {{"
            f"  background: {PALETTE['surface_input']};"
            f"  border-color: {PALETTE['checked_border']};"
            f"}}"
            f"QToolButton#{object_name}:pressed {{"
            f"  background: {PALETTE['pressed']};"
            f"  border-color: {PALETTE['accent_pressed']};"
            f"}}"
        )

    def _build_copy_button(self, object_name: str, text: str, value_getter) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setText(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setStyleSheet(self._header_button_style(object_name))
        button.clicked.connect(
            lambda _checked=False, b=button, g=value_getter, t=text: self._handle_copy_clicked(g(), b, t)
        )
        return button

    def _ensure_copy_buttons(self) -> None:
        if self._copy_smiles_button is None:
            self._copy_smiles_button = self._build_copy_button(
                "preview_copy_smiles_button", "SMILES", lambda: self._smiles_text
            )
        if self._copy_inchikey_button is None:
            self._copy_inchikey_button = self._build_copy_button(
                "preview_copy_inchikey_button", "InChIKey", lambda: self._inchikey_text
            )

    def _sync_copy_buttons(self) -> None:
        self._ensure_copy_buttons()
        export = self._export_xyz_button
        # Lay out [SMILES] [InChIKey] [Export] right-aligned: each copy button is
        # anchored to the left edge of the one to its right. They only appear when
        # a structure is present and the identifier value exists.
        specs = [
            (self._copy_inchikey_button, "Copy InChIKey", self._inchikey_text),
            (self._copy_smiles_button, "Copy canonical SMILES", self._smiles_text),
        ]
        # Gate on scene presence (mirroring the Export button's own visibility
        # flag), NOT on export.isVisible(): the preview can be refreshed while
        # the Molecule Info window is still closed, and isVisible() is False
        # then. The Export button's geometry is set even while hidden, so the
        # copy buttons can still be positioned and will appear with it on show.
        if self._scene is None or export is None:
            for button, _tooltip, _value in specs:
                if button is not None:
                    button.setVisible(False)
                    button.setEnabled(False)
            return
        geometry = export.geometry()
        right_edge = float(geometry.x())
        gap = 6
        for button, base_tooltip, value in specs:
            if button is None:
                continue
            has_value = bool(value)
            button.setVisible(has_value)
            button.setEnabled(has_value)
            if not has_value:
                continue
            button.setFont(export.font())
            button.setToolTip(f"{base_tooltip}\n{value}")
            metrics = QFontMetricsF(button.font())
            width = max(96.0, metrics.horizontalAdvance(button.text()) + 28.0)
            x = right_edge - gap - width
            button.setGeometry(round(x), geometry.y(), round(width), geometry.height())
            right_edge = x

    def _handle_copy_clicked(self, value: str, button: QToolButton, label: str) -> None:
        if not value:
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(value)
        button.setText("Copied")
        QTimer.singleShot(1200, lambda b=button, t=label: b.setText(t))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_preview_3d_panel(
            painter,
            QRectF(self.rect()),
            self.font(),
            Preview3DPaintState(
                scene=self._scene,
                message=self._message,
                formula_text=self._formula_text,
                mw_text=self._mw_text,
                rotation_x=self._rotation_x,
                rotation_y=self._rotation_y,
                zoom=self._zoom,
            ),
        )
