from __future__ import annotations

import math

from core.rdkit_adapter import Molecule3DScene, RDKitAdapter
from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class _Preview3DWorker(QObject):
    finished = pyqtSignal(int, object, object, object, object)

    def __init__(self, request_id: int, rdkit_adapter, model, atom_annotations) -> None:
        super().__init__()
        self._request_id = request_id
        self._rdkit = rdkit_adapter
        self._model = model
        self._atom_annotations = atom_annotations

    def run(self) -> None:
        formula = None
        mw = None
        scene = None
        error = None
        try:
            formula, mw, _ = self._rdkit.compute_props(self._model)
            scene = self._rdkit.model_to_3d_scene(
                self._model,
                atom_annotations=self._atom_annotations,
            )
            if scene is None:
                error = self._rdkit.last_error or "Failed to build 3D preview."
        except Exception as exc:
            error = str(exc) or "Failed to build 3D preview."
        self.finished.emit(self._request_id, formula, mw, scene, error)


class Preview3D(QWidget):
    def __init__(self, rdkit_adapter: RDKitAdapter | None = None) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter or RDKitAdapter()
        self._async_enabled = rdkit_adapter is None
        self._preview_request_id = 0
        self._preview_jobs = {}
        self._disposed = False
        self._pending_model = None
        self._pending_annotations = None
        self._current_signature = None
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

    def refresh_from_canvas(self, canvas) -> None:
        try:
            model, atom_annotations = canvas.build_3d_conversion_payload()
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
        atom_sig = tuple(
            (
                atom_id,
                atom.element,
                round(atom.x, 3),
                round(atom.y, 3),
            )
            for atom_id, atom in sorted(model.atoms.items())
        )
        bond_sig = tuple(
            (
                bond.a,
                bond.b,
                bond.order,
                bond.style,
            )
            for bond in model.bonds
            if bond is not None
        )
        annotation_sig = tuple(
            (
                atom_id,
                int(values.get("formal_charge", 0)),
                int(values.get("radical_electrons", 0)),
            )
            for atom_id, values in sorted((atom_annotations or {}).items())
        )
        return atom_sig, bond_sig, annotation_sig

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
        scene = self._rdkit.model_to_3d_scene(
            self._pending_model,
            atom_annotations=self._pending_annotations,
        )
        if scene is None:
            self.clear_preview(self._rdkit.last_error or "Failed to build 3D preview.")
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
        worker = _Preview3DWorker(
            request_id,
            self._rdkit,
            self._pending_model,
            self._pending_annotations,
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
            delta = current - self._last_pos
            self._rotation_y += delta.x() * 0.01
            self._rotation_x += delta.y() * 0.01
            self._last_pos = current
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_pos = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta:
            factor = 1.0 + (0.1 if delta > 0 else -0.1)
            self._zoom = max(0.3, min(3.0, self._zoom * factor))
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f1f1f0"))

        info_lines = self._info_lines()
        layout = self._layout_rects(info_lines)
        self._draw_panel(painter, layout["panel"])
        self._draw_header(painter, layout["header"])
        self._draw_viewport(painter, layout["viewport"])

        if self._scene is None:
            self._draw_empty_state(painter, layout["viewport"])
            return

        projected_atoms = self._project_scene(self._scene, viewport_rect=layout["molecule"])
        if not projected_atoms:
            self._draw_empty_state(painter, layout["viewport"])
            return

        bond_depths = []
        for bond in self._scene.bonds:
            if bond.a >= len(projected_atoms) or bond.b >= len(projected_atoms):
                continue
            ax, ay, az, _ = projected_atoms[bond.a]
            bx, by, bz, _ = projected_atoms[bond.b]
            bond_depths.append((az + bz, bond, (ax, ay), (bx, by)))
        for _, bond, start, end in sorted(bond_depths, key=lambda item: item[0]):
            width = 1.4 + max(0, bond.order - 1) * 1.0
            painter.setPen(QPen(QColor(60, 60, 58, 70), width + 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(start[0] + 1.0, start[1] + 1.2), QPointF(end[0] + 1.0, end[1] + 1.2))
            painter.setPen(QPen(QColor("#4a4a48"), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(*start), QPointF(*end))

        atom_draws = []
        for index, atom in enumerate(self._scene.atoms):
            px, py, pz, radius = projected_atoms[index]
            atom_draws.append((pz, atom.symbol, px, py, radius))
        for _, symbol, px, py, radius in sorted(atom_draws, key=lambda item: item[0]):
            fill = self._element_color(symbol)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(40, 40, 38, 35))
            painter.drawEllipse(QPointF(px + 1.1, py + 1.8), radius * 1.04, radius * 1.04)
            painter.setPen(QPen(QColor("#2a2a28"), 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(px, py), radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 72))
            painter.drawEllipse(QPointF(px - radius * 0.28, py - radius * 0.32), radius * 0.33, radius * 0.24)
            if symbol != "C" or radius >= 9.0:
                painter.save()
                painter.setPen(QColor("#1c1c1a"))
                font = painter.font()
                font.setPointSizeF(max(7.0, radius * 0.9))
                painter.setFont(font)
                text_rect = QRectF(px - radius, py - radius, radius * 2.0, radius * 2.0)
                painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), symbol)
                painter.restore()

        self._draw_interaction_hints(painter, layout["viewport"])
        if info_lines:
            self._draw_footer(painter, layout["footer"])

    def _layout_rects(self, info_lines: list[str] | None = None) -> dict[str, QRectF]:
        info_lines = info_lines or []
        panel = QRectF(self.rect()).adjusted(8.0, 8.0, -8.0, -8.0)
        if panel.width() <= 0.0 or panel.height() <= 0.0:
            panel = QRectF(self.rect())

        pad = 12.0
        header_height = 42.0
        footer_height = self._footer_height(info_lines)
        footer_gap = 8.0 if footer_height > 0.0 else 0.0

        header = QRectF(panel.left() + pad, panel.top() + 10.0, max(20.0, panel.width() - pad * 2.0), header_height)
        footer = QRectF()
        viewport_bottom = panel.bottom() - pad - footer_height - footer_gap
        viewport_top = header.bottom() + 8.0
        viewport_height = max(48.0, viewport_bottom - viewport_top)
        viewport = QRectF(panel.left() + pad, viewport_top, max(20.0, panel.width() - pad * 2.0), viewport_height)
        if footer_height > 0.0:
            footer_top = min(panel.bottom() - pad - footer_height, viewport.bottom() + footer_gap)
            footer = QRectF(panel.left() + pad, footer_top, max(20.0, panel.width() - pad * 2.0), footer_height)

        molecule = viewport.adjusted(18.0, 22.0, -18.0, -14.0)
        if molecule.width() < 36.0 or molecule.height() < 36.0:
            molecule = viewport.adjusted(10.0, 16.0, -10.0, -10.0)

        return {
            "panel": panel,
            "header": header,
            "viewport": viewport,
            "molecule": molecule,
            "footer": footer,
        }

    @staticmethod
    def _draw_card_shadow(painter: QPainter, rect: QRectF, radius: float, *, layers=None) -> None:
        # Layered translucent rounded rects offset downward fake a soft drop
        # shadow so cards read as floating rather than outlined-and-flat.
        layers = layers if layers is not None else ((6.0, 7), (3.5, 11), (1.5, 18))
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        for spread, alpha in layers:
            painter.setBrush(QColor(38, 38, 36, alpha))
            painter.drawRoundedRect(
                rect.adjusted(-spread * 0.3, spread * 0.25, spread * 0.3, spread + 1.0),
                radius + spread * 0.3,
                radius + spread * 0.3,
            )
        painter.restore()

    def _draw_panel(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        self._draw_card_shadow(painter, rect, 9.0)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(1.0, QColor("#f4f4f3"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
        painter.drawRoundedRect(rect, 9.0, 9.0)
        painter.restore()

    def _draw_header(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        caption_font = self._caption_font()

        status_text, status_fill, status_border, status_pen = self._status_badge()
        metrics = QFontMetricsF(caption_font)
        badge_width = max(50.0, metrics.horizontalAdvance(status_text) + 20.0)
        badge = QRectF(rect.right() - badge_width, rect.top() + 4.0, badge_width, 22.0)
        painter.setPen(QPen(status_border, 1.0))
        painter.setBrush(status_fill)
        painter.drawRoundedRect(badge, 11.0, 11.0)
        painter.setPen(status_pen)
        painter.setFont(caption_font)
        painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), status_text)

        title_rect = QRectF(rect.left(), rect.top() + 1.0, max(20.0, rect.width() - badge_width - 10.0), 20.0)
        painter.setPen(QColor("#232322"))
        painter.setFont(title_font)
        painter.drawText(title_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), "3D Preview")

        subtitle = self._metadata_summary()
        subtitle_rect = QRectF(rect.left(), title_rect.bottom() + 1.0, rect.width(), 17.0)
        painter.setPen(QColor("#6f6f6c"))
        painter.setFont(caption_font)
        painter.drawText(subtitle_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), subtitle)
        painter.restore()

    def _draw_viewport(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        self._draw_card_shadow(painter, rect, 7.0, layers=((4.0, 4), (2.0, 7)))
        painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
        painter.setBrush(QColor("#fbfbfa"))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        inner = rect.adjusted(6.0, 6.0, -6.0, -6.0)
        painter.setPen(QPen(QColor(210, 210, 206, 90), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(inner, 5.0, 5.0)

        tick_pen = QPen(QColor(160, 160, 154, 80), 1.0)
        painter.setPen(tick_pen)
        tick = 12.0
        corners = (
            (inner.left(), inner.top(), 1.0, 1.0),
            (inner.right(), inner.top(), -1.0, 1.0),
            (inner.left(), inner.bottom(), 1.0, -1.0),
            (inner.right(), inner.bottom(), -1.0, -1.0),
        )
        for x, y, dx, dy in corners:
            painter.drawLine(QPointF(x, y), QPointF(x + tick * dx, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + tick * dy))
        painter.restore()

    def _draw_empty_state(self, painter: QPainter, rect: QRectF) -> None:
        title, detail = self._empty_state_text()
        painter.save()
        center = rect.center()
        icon_center = QPointF(center.x(), center.y() - 24.0)
        line_pen = QPen(QColor("#b0b0ab"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(line_pen)
        painter.drawLine(icon_center + QPointF(-18.0, 3.0), icon_center + QPointF(0.0, -9.0))
        painter.drawLine(icon_center + QPointF(0.0, -9.0), icon_center + QPointF(19.0, 5.0))
        painter.drawLine(icon_center + QPointF(-18.0, 3.0), icon_center + QPointF(14.0, 18.0))

        for point, radius, color in (
            (icon_center + QPointF(-18.0, 3.0), 5.0, QColor("#5a5a56")),
            (icon_center + QPointF(0.0, -9.0), 6.0, QColor("#cc584d")),
            (icon_center + QPointF(19.0, 5.0), 4.5, QColor("#4b73c4")),
            (icon_center + QPointF(14.0, 18.0), 4.0, QColor("#ededeb")),
        ):
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#4a4a48"), 1.0))
            painter.drawEllipse(point, radius, radius)

        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        detail_font = self._overlay_font()
        title_rect = QRectF(rect.left() + 18.0, center.y() + 6.0, rect.width() - 36.0, 18.0)
        detail_rect = QRectF(rect.left() + 22.0, title_rect.bottom() + 3.0, rect.width() - 44.0, 34.0)

        painter.setPen(QColor("#232322"))
        painter.setFont(title_font)
        painter.drawText(title_rect, int(Qt.AlignmentFlag.AlignCenter), title)
        painter.setPen(QColor("#6f6f6c"))
        painter.setFont(detail_font)
        painter.drawText(
            detail_rect,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            detail,
        )
        painter.restore()

    def _draw_interaction_hints(self, painter: QPainter, viewport: QRectF) -> None:
        painter.save()
        labels = ("Drag rotate", "Wheel zoom")
        font = self._caption_font()
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        gap = 5.0
        widths = [metrics.horizontalAdvance(label) + 18.0 for label in labels]
        total_width = sum(widths) + gap
        x = viewport.right() - total_width - 10.0
        y = viewport.top() + 10.0
        for label, width in zip(labels, widths, strict=False):
            pill = QRectF(x, y, width, 22.0)
            painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
            painter.setBrush(QColor("#ffffff"))
            painter.drawRoundedRect(pill, 11.0, 11.0)
            painter.setPen(QColor("#6f6f6c"))
            painter.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), label)
            x += width + gap
        painter.restore()

    def _draw_footer(self, painter: QPainter, rect: QRectF) -> None:
        if rect.isNull():
            return
        painter.save()
        painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
        painter.setBrush(QColor("#f4f4f3"))
        painter.drawRoundedRect(rect, 7.0, 7.0)

        items = self._info_items()
        if not items:
            painter.restore()
            return
        for item_rect, (label, value) in zip(self._footer_item_rects(rect, len(items)), items, strict=False):
            self._draw_info_chip(painter, item_rect, label, value)
        painter.restore()

    def _footer_item_rects(self, rect: QRectF, item_count: int) -> list[QRectF]:
        if rect.isNull() or item_count <= 0:
            return []
        gap = 6.0
        available_height = max(18.0, rect.height() - gap * (item_count + 1))
        item_height = available_height / item_count
        item_width = max(18.0, rect.width() - gap * 2.0)
        x = rect.left() + gap
        y = rect.top() + gap
        return [
            QRectF(x, y + index * (item_height + gap), item_width, item_height)
            for index in range(item_count)
        ]

    def _draw_info_chip(self, painter: QPainter, rect: QRectF, label: str, value: str) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#e4e4e1"), 1.0))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 6.0, 6.0)

        label_font = self._caption_font()
        value_font = self._overlay_font()
        value_font.setWeight(QFont.Weight.DemiBold)
        label_metrics = QFontMetricsF(label_font)
        value_metrics = QFontMetricsF(value_font)
        label_width = label_metrics.horizontalAdvance(label) + 10.0
        label_rect = QRectF(rect.left() + 7.0, rect.top(), label_width, rect.height())
        value_rect = QRectF(
            label_rect.right() + 3.0,
            rect.top(),
            max(8.0, rect.right() - label_rect.right() - 10.0),
            rect.height(),
        )

        painter.setFont(label_font)
        painter.setPen(QColor("#8c8c87"))
        painter.drawText(label_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
        painter.setFont(value_font)
        painter.setPen(QColor("#232322"))
        painter.drawText(
            value_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            value_metrics.elidedText(value, Qt.TextElideMode.ElideRight, value_rect.width()),
        )
        painter.restore()

    def _project_scene(
        self,
        scene: Molecule3DScene,
        *,
        footer_height: float = 0.0,
        viewport_rect: QRectF | None = None,
    ) -> list[tuple[float, float, float, float]]:
        if not scene.atoms:
            return []
        cx = sum(atom.x for atom in scene.atoms) / len(scene.atoms)
        cy = sum(atom.y for atom in scene.atoms) / len(scene.atoms)
        cz = sum(atom.z for atom in scene.atoms) / len(scene.atoms)

        rotated: list[tuple[float, float, float]] = []
        max_extent = 1.0
        cos_y = math.cos(self._rotation_y)
        sin_y = math.sin(self._rotation_y)
        cos_x = math.cos(self._rotation_x)
        sin_x = math.sin(self._rotation_x)
        for atom in scene.atoms:
            x = atom.x - cx
            y = atom.y - cy
            z = atom.z - cz
            x1 = x * cos_y + z * sin_y
            z1 = -x * sin_y + z * cos_y
            y1 = y * cos_x - z1 * sin_x
            z2 = y * sin_x + z1 * cos_x
            rotated.append((x1, y1, z2))
            max_extent = max(max_extent, math.sqrt(x1 * x1 + y1 * y1 + z2 * z2))

        if viewport_rect is not None:
            content_rect = QRectF(viewport_rect)
        else:
            content_rect = QRectF(self.rect()).adjusted(18.0, 18.0, -18.0, -18.0)
        if viewport_rect is None and footer_height > 0.0:
            content_rect.setBottom(max(content_rect.top() + 40.0, content_rect.bottom() - footer_height))
        available = max(40.0, min(content_rect.width(), content_rect.height()))
        scale = (available * 0.36 * self._zoom) / max_extent
        center_x = content_rect.center().x()
        center_y = content_rect.top() + content_rect.height() * 0.55
        projected = []
        for atom, (x, y, z) in zip(scene.atoms, rotated, strict=False):
            depth = 7.0 / max(1.5, 7.0 - z)
            px = center_x + x * scale * depth
            py = center_y - y * scale * depth
            base_radius = 6.0 if atom.symbol == "H" else 9.0
            radius = max(3.0, base_radius * depth)
            projected.append((px, py, z, radius))
        return projected

    def _element_color(self, symbol: str) -> QColor:
        palette = {
            "H": QColor("#ededeb"),
            "C": QColor("#4a4a48"),
            "N": QColor("#4b73c4"),
            "O": QColor("#cc584d"),
            "S": QColor("#d0a532"),
            "P": QColor("#d7883d"),
            "F": QColor("#6ea36d"),
            "Cl": QColor("#5f955e"),
            "Br": QColor("#8b5c43"),
            "I": QColor("#7a5ca8"),
        }
        return palette.get(symbol, QColor("#cfcfca"))

    def _overlay_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        return font

    def _caption_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(11)
        return font

    def _info_lines(self) -> list[str]:
        lines: list[str] = []
        if self._formula_text:
            lines.append(f"Formula: {self._formula_text}")
        if self._mw_text:
            lines.append(f"MW: {self._mw_text}")
        return lines

    def _info_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self._formula_text:
            items.append(("FORMULA", self._formula_text))
        if self._mw_text:
            items.append(("MW", self._mw_text))
        return items

    def _footer_height(self, lines: list[str]) -> float:
        if not lines:
            return 0.0
        metrics = QFontMetricsF(self._overlay_font())
        row_height = max(28.0, metrics.lineSpacing() + 10.0)
        gap = 6.0
        return row_height * len(lines) + gap * (len(lines) + 1)

    def _metadata_summary(self) -> str:
        if self._scene is not None:
            atom_count = len(self._scene.atoms)
            bond_count = len(self._scene.bonds)
            atom_label = "atom" if atom_count == 1 else "atoms"
            bond_label = "bond" if bond_count == 1 else "bonds"
            return f"{atom_count} {atom_label} / {bond_count} {bond_label}"
        if self._message.startswith("Updating"):
            return "Preparing coordinates"
        if self._is_empty_message():
            return ""
        return "Preview needs attention"

    def _status_badge(self) -> tuple[str, QColor, QColor, QColor]:
        if self._scene is not None:
            return "Ready", QColor("#eef0ee"), QColor("#c3c9c2"), QColor("#41514a")
        if self._message.startswith("Updating"):
            return "Building", QColor("#eeeeec"), QColor("#cfcfca"), QColor("#55555a")
        if self._is_empty_message():
            return "Empty", QColor("#ededeb"), QColor("#cfcfca"), QColor("#6f6f6c")
        return "Issue", QColor("#f6eded"), QColor("#dbbcbc"), QColor("#8a2020")

    def _empty_state_text(self) -> tuple[str, str]:
        message = " ".join((self._message or "3D preview unavailable").split())
        if message.startswith("Updating"):
            return "Building preview", "Preparing coordinates"
        if self._is_empty_message(message):
            return "No molecule yet", "Draw or paste a structure to preview it in 3D."
        if len(message) > 96:
            message = f"{message[:93]}..."
        return "Preview unavailable", message

    def _is_empty_message(self, message: str | None = None) -> bool:
        message = " ".join((self._message if message is None else message or "").split()).lower()
        return message in {"", "3d preview unavailable"} or "no chemical structure" in message
