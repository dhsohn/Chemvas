from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.rdkit_adapter import Molecule3DScene, RDKitAdapter


class Preview3D(QWidget):
    def __init__(self, rdkit_adapter: RDKitAdapter | None = None) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter or RDKitAdapter()
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
        self._disposed = True
        self._update_timer.stop()
        super().closeEvent(event)

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
        painter.fillRect(self.rect(), QColor("#f7f1e8"))

        inner = self.rect().adjusted(10, 10, -10, -10)
        painter.setPen(QPen(QColor("#d8ccbd"), 1.0))
        painter.drawRoundedRect(inner, 10, 10)

        if self._scene is None:
            painter.setPen(QColor("#6f6457"))
            painter.drawText(inner, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._message)
            return

        info_lines = self._info_lines()
        projected_atoms = self._project_scene(self._scene, footer_height=self._footer_height(info_lines))
        if not projected_atoms:
            painter.setPen(QColor("#6f6457"))
            painter.drawText(inner, Qt.AlignmentFlag.AlignCenter, self._message or "3D preview unavailable")
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
            painter.setPen(QPen(QColor("#6d5d4e"), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(*start), QPointF(*end))

        atom_draws = []
        for index, atom in enumerate(self._scene.atoms):
            px, py, pz, radius = projected_atoms[index]
            atom_draws.append((pz, atom.symbol, px, py, radius))
        for _, symbol, px, py, radius in sorted(atom_draws, key=lambda item: item[0]):
            fill = self._element_color(symbol)
            painter.setPen(QPen(QColor("#3d3229"), 1.0))
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(px, py), radius, radius)
            if symbol != "C" or radius >= 9.0:
                painter.save()
                painter.setPen(QColor("#1f1a16"))
                font = painter.font()
                font.setPointSizeF(max(7.0, radius * 0.9))
                painter.setFont(font)
                text_rect = QRectF(px - radius, py - radius, radius * 2.0, radius * 2.0)
                painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignCenter), symbol)
                painter.restore()

        painter.save()
        painter.setPen(QColor("#8a7a68"))
        painter.setFont(self._overlay_font())
        painter.drawText(inner.adjusted(10, 10, -10, -10), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight, "drag: rotate\nwheel: zoom")
        painter.restore()

        if info_lines:
            painter.save()
            painter.setPen(QColor("#6f6457"))
            painter.setFont(self._overlay_font())
            painter.drawText(
                inner.adjusted(10, 10, -10, -10),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                "\n".join(info_lines),
            )
            painter.restore()

    def _project_scene(
        self,
        scene: Molecule3DScene,
        *,
        footer_height: float = 0.0,
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

        content_rect = QRectF(self.rect()).adjusted(18.0, 18.0, -18.0, -18.0)
        if footer_height > 0.0:
            content_rect.setBottom(max(content_rect.top() + 40.0, content_rect.bottom() - footer_height))
        available = max(40.0, min(content_rect.width(), content_rect.height()))
        scale = (available * 0.36 * self._zoom) / max_extent
        center_x = content_rect.center().x()
        center_y = content_rect.top() + content_rect.height() * 0.55
        projected = []
        for atom, (x, y, z) in zip(scene.atoms, rotated):
            depth = 7.0 / max(1.5, 7.0 - z)
            px = center_x + x * scale * depth
            py = center_y - y * scale * depth
            base_radius = 6.0 if atom.symbol == "H" else 9.0
            radius = max(3.0, base_radius * depth)
            projected.append((px, py, z, radius))
        return projected

    def _element_color(self, symbol: str) -> QColor:
        palette = {
            "H": QColor("#f3efe7"),
            "C": QColor("#786b60"),
            "N": QColor("#4b73c4"),
            "O": QColor("#cc584d"),
            "S": QColor("#d0a532"),
            "P": QColor("#d7883d"),
            "F": QColor("#6ea36d"),
            "Cl": QColor("#5f955e"),
            "Br": QColor("#8b5c43"),
            "I": QColor("#7a5ca8"),
        }
        return palette.get(symbol, QColor("#d9d1c6"))

    def _overlay_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(12)
        return font

    def _info_lines(self) -> list[str]:
        lines: list[str] = []
        if self._formula_text:
            lines.append(f"Formula: {self._formula_text}")
        if self._mw_text:
            lines.append(f"MW: {self._mw_text}")
        return lines

    def _footer_height(self, lines: list[str]) -> float:
        if not lines:
            return 0.0
        metrics = QFontMetricsF(self._overlay_font())
        return metrics.lineSpacing() * len(lines) + 12.0
