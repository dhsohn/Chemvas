"""Read-only figure preview using the same scope and geometry as export."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from chemvas.features.export import svg_viewport_size_points
from chemvas.shell.palette import PALETTE
from chemvas.ui.export.export_guard_service import validate_export_budget
from chemvas.ui.export.export_vector import pdf_page_size
from chemvas.ui.export.figure_export_service import FigureExportService
from chemvas.ui.selection.selection_queries import selection_items_for_copy_for

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView


class FigureExportPreview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.addWidget(QLabel("Figure preview"))
        self.image = QLabel()
        self.image.setObjectName("exportPreview")
        self.image.setAccessibleName("Figure preview")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setFixedSize(380, 280)
        self.image.setWordWrap(True)
        self.image.setStyleSheet(
            f"background: {PALETTE['surface_canvas']}; color: {PALETTE['text']}; "
            f"border: 1px solid {PALETTE['border_strong']};"
        )
        layout.addWidget(self.image)
        self.dimensions = QLabel()
        self.dimensions.setObjectName("exportDimensions")
        self.dimensions.setWordWrap(True)
        layout.addWidget(self.dimensions)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)

    def update_options(
        self,
        canvas: CanvasView | None,
        *,
        fmt: str,
        sizing: str,
        scope: str,
        background: str,
        dpi: int,
        target_width_mm: float | None,
        max_height_mm: float | None,
        min_font_check: bool,
    ) -> bool:
        self.image.clear()
        self.dimensions.clear()
        self.note.setText("Adjust the options to preview and export.")
        if canvas is None:
            self.image.setText("Open a drawing to preview and export.")
            return False
        try:
            image, plan = FigureExportService(
                canvas.render_context
            ).preview_figure_export(
                scope=scope,
                selection=selection_items_for_copy_for(canvas)
                if scope == "selection"
                else None,
                sizing=sizing,
                target_width_mm=target_width_mm,
                background=background,
            )
            pixels_w, pixels_h = validate_export_budget(
                plan,
                output_format=fmt,
                dpi=dpi,
                max_height_mm=max_height_mm,
            )
            width_pt, height_pt = plan.out_w_pt, plan.out_h_pt
            if fmt == "svg":
                width_pt, height_pt = svg_viewport_size_points(plan)
            elif fmt == "pdf":
                size = pdf_page_size(plan).sizePoints()
                width_pt, height_pt = size.width(), size.height()
            elif pixels_w is not None and pixels_h is not None:
                width_pt, height_pt = pixels_w * 72 / dpi, pixels_h * 72 / dpi
            self.dimensions.setText(
                f"Output: {width_pt * 25.4 / 72:.2f} × {height_pt * 25.4 / 72:.2f} mm"
                + (f" · {pixels_w} × {pixels_h} px" if pixels_w is not None else "")
                + f"\nBackground: {background}"
            )
            ratio = self.devicePixelRatioF()
            pixmap = QPixmap.fromImage(image).scaled(
                round(360 * ratio),
                round(260 * ratio),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            pixmap.setDevicePixelRatio(ratio)
            self.image.setPixmap(pixmap)
            self.note.setText(
                "Minimum font size checked on export." if min_font_check else ""
            )
            return True
        except ValueError as error:
            self.image.setText(str(error))
            return False
