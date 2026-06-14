from __future__ import annotations

import math
from typing import Any

from core.rdkit_adapter import Molecule3DScene, RDKitAdapter
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QWidget

from ui.preview_3d_interaction import (
    preview_drag_rotation,
    preview_zoom_for_wheel_delta,
)
from ui.preview_3d_painter import Preview3DPaintState, paint_preview_3d_panel
from ui.preview_3d_state import preview_payload_signature
from ui.preview_3d_worker import Preview3DWorker
from ui.structure_payload_access import build_3d_conversion_payload_for


class Preview3D(QWidget):
    def __init__(self, rdkit_adapter: RDKitAdapter | None = None) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter or RDKitAdapter()
        self._async_enabled = rdkit_adapter is None
        self._preview_request_id = 0
        self._preview_jobs: dict[int, tuple[QThread, Preview3DWorker]] = {}
        self._disposed = False
        self._pending_model: Any | None = None
        self._pending_annotations: Any | None = None
        self._current_signature: tuple[Any, ...] | None = None
        self._scene: Molecule3DScene | None = None
        self._message = "3D preview unavailable"
        self._formula_text = ""
        self._mw_text = ""
        self._rotation_x = math.radians(-18.0)
        self._rotation_y = math.radians(22.0)
        self._zoom = 1.0
        self._last_pos: QPointF | None = None
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

    def refresh_from_canvas(self, canvas) -> None:
        try:
            model, atom_annotations = build_3d_conversion_payload_for(canvas)
        except Exception as exc:
            self.clear_preview(str(exc))
            return
        if not self._async_enabled:
            formula, mw, _ = self._rdkit.compute_props(model)
            self.set_info(formula or "", "" if mw is None else f"{mw:.2f}")
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
        self._pending_model = None
        self._pending_annotations = None
        self._current_signature = None
        self._scene = None
        self._message = message
        self._formula_text = ""
        self._mw_text = ""
        self._safe_update()

    def set_info(self, formula: str, mw: str) -> None:
        if formula == self._formula_text and mw == self._mw_text:
            return
        self._formula_text = formula
        self._mw_text = mw
        self._safe_update()

    def _payload_signature(self, model, atom_annotations) -> tuple:
        return preview_payload_signature(model, atom_annotations)

    def _rebuild_scene(self) -> None:
        if self._disposed:
            return
        if self._pending_model is None:
            self._scene = None
            self._message = "3D preview unavailable"
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
        self._safe_update()

    def _ensure_rdkit_loaded_for_worker(self) -> bool:
        if self._rdkit.is_loaded():
            return True
        if self._rdkit.preload():
            return True
        self.clear_preview(self._rdkit.last_error or "RDKit is not available in this environment.")
        return False

    def _start_preview_worker(self) -> None:
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
        thread.finished.connect(lambda request_id=request_id: self._preview_jobs.pop(request_id, None))
        thread.start()

    def _handle_preview_worker_finished(
        self,
        request_id: int,
        formula: str | None,
        mw: float | None,
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
            self._message = error or "Failed to build 3D preview."
            self._safe_update()
            return
        self._formula_text = formula or ""
        self._mw_text = "" if mw is None else f"{mw:.2f}"
        self._scene = scene
        self._message = ""
        self._safe_update()

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
