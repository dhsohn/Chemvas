from __future__ import annotations

from dataclasses import dataclass

from core.rdkit_adapter import Molecule3DScene
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter

from ui.preview_3d_layout import (
    preview_footer_height,
    preview_footer_item_rects,
    preview_layout_rects,
)
from ui.preview_3d_molecule_renderer import draw_projected_scene
from ui.preview_3d_projection import project_preview_scene
from ui.preview_3d_renderer import (
    draw_empty_state,
    draw_footer,
    draw_header,
    draw_interaction_hints,
    draw_panel,
    draw_viewport,
)
from ui.preview_3d_state import (
    preview_empty_state_text,
    preview_info_items,
    preview_info_lines,
    preview_metadata_summary,
    preview_status_badge,
)


@dataclass(frozen=True, slots=True)
class Preview3DPaintState:
    scene: Molecule3DScene | None
    message: str
    formula_text: str
    mw_text: str
    rotation_x: float
    rotation_y: float
    zoom: float


def preview_overlay_font(base_font: QFont) -> QFont:
    font = QFont(base_font)
    font.setPixelSize(12)
    return font


def preview_caption_font(base_font: QFont) -> QFont:
    font = QFont(base_font)
    font.setPixelSize(11)
    return font


def preview_title_font(base_font: QFont) -> QFont:
    font = QFont(base_font)
    font.setPixelSize(13)
    font.setWeight(QFont.Weight.DemiBold)
    return font


def preview_footer_height_for_lines(lines: list[str], base_font: QFont) -> float:
    metrics = QFontMetricsF(preview_overlay_font(base_font))
    return preview_footer_height(len(lines), metrics.lineSpacing())


def preview_layout_for_widget(
    widget_rect: QRectF,
    info_lines: list[str],
    base_font: QFont,
) -> dict[str, QRectF]:
    return preview_layout_rects(
        widget_rect,
        footer_height=preview_footer_height_for_lines(info_lines, base_font),
    )


def project_preview_paint_scene(
    scene: Molecule3DScene,
    *,
    rotation_x: float,
    rotation_y: float,
    zoom: float,
    widget_rect: QRectF,
    footer_height: float = 0.0,
    viewport_rect: QRectF | None = None,
) -> list[tuple[float, float, float, float]]:
    return project_preview_scene(
        scene,
        rotation_x=rotation_x,
        rotation_y=rotation_y,
        zoom=zoom,
        widget_rect=widget_rect,
        footer_height=footer_height,
        viewport_rect=viewport_rect,
    )


def paint_preview_3d_panel(
    painter: QPainter,
    widget_rect: QRectF,
    base_font: QFont,
    state: Preview3DPaintState,
) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.fillRect(widget_rect, QColor("#f1f1f0"))

    info_lines = preview_info_lines(state.formula_text, state.mw_text)
    layout = preview_layout_for_widget(widget_rect, info_lines, base_font)
    caption_font = preview_caption_font(base_font)
    overlay_font = preview_overlay_font(base_font)

    draw_panel(painter, layout["panel"])
    draw_header(
        painter,
        layout["header"],
        title_font=preview_title_font(base_font),
        caption_font=caption_font,
        status_badge=preview_status_badge(state.scene, state.message),
        subtitle=preview_metadata_summary(state.scene, state.message),
    )
    draw_viewport(painter, layout["viewport"])

    if state.scene is None:
        title, detail = preview_empty_state_text(state.message)
        draw_empty_state(
            painter,
            layout["viewport"],
            title=title,
            detail=detail,
            title_font=preview_title_font(base_font),
            detail_font=overlay_font,
        )
        return

    projected_atoms = project_preview_paint_scene(
        state.scene,
        rotation_x=state.rotation_x,
        rotation_y=state.rotation_y,
        zoom=state.zoom,
        widget_rect=widget_rect,
        viewport_rect=layout["molecule"],
    )
    if not projected_atoms:
        title, detail = preview_empty_state_text(state.message)
        draw_empty_state(
            painter,
            layout["viewport"],
            title=title,
            detail=detail,
            title_font=preview_title_font(base_font),
            detail_font=overlay_font,
        )
        return

    draw_projected_scene(painter, state.scene, projected_atoms)
    draw_interaction_hints(painter, layout["viewport"], font=caption_font)
    if info_lines:
        items = preview_info_items(state.formula_text, state.mw_text)
        draw_footer(
            painter,
            layout["footer"],
            items=items,
            item_rects=preview_footer_item_rects(layout["footer"], len(items)),
            label_font=caption_font,
            value_font=overlay_font,
        )


__all__ = [
    "Preview3DPaintState",
    "paint_preview_3d_panel",
    "preview_caption_font",
    "preview_footer_height_for_lines",
    "preview_layout_for_widget",
    "preview_overlay_font",
    "preview_title_font",
    "project_preview_paint_scene",
]
