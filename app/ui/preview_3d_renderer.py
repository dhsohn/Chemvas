from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen

from ui.preview_3d_molecule_renderer import draw_projected_scene, preview_element_color


def draw_card_shadow(painter: QPainter, rect: QRectF, radius: float, *, layers=None) -> None:
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


def draw_panel(painter: QPainter, rect: QRectF) -> None:
    painter.save()
    draw_card_shadow(painter, rect, 9.0)

    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, QColor("#ffffff"))
    gradient.setColorAt(1.0, QColor("#f4f4f3"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
    painter.drawRoundedRect(rect, 9.0, 9.0)
    painter.restore()


def draw_header(
    painter: QPainter,
    rect: QRectF,
    *,
    title_font: QFont,
    caption_font: QFont,
    status_badge: tuple[str, QColor, QColor, QColor],
    subtitle: str,
) -> None:
    painter.save()
    status_text, status_fill, status_border, status_pen = status_badge
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

    subtitle_rect = QRectF(rect.left(), title_rect.bottom() + 1.0, rect.width(), 17.0)
    painter.setPen(QColor("#6f6f6c"))
    painter.setFont(caption_font)
    painter.drawText(subtitle_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), subtitle)
    painter.restore()


def draw_viewport(painter: QPainter, rect: QRectF) -> None:
    painter.save()
    draw_card_shadow(painter, rect, 7.0, layers=((4.0, 4), (2.0, 7)))
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


def draw_empty_state(
    painter: QPainter,
    rect: QRectF,
    *,
    title: str,
    detail: str,
    title_font: QFont,
    detail_font: QFont,
) -> None:
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


def draw_interaction_hints(painter: QPainter, viewport: QRectF, *, font: QFont) -> None:
    painter.save()
    labels = ("Drag rotate", "Wheel zoom")
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


def draw_footer(
    painter: QPainter,
    rect: QRectF,
    *,
    items: list[tuple[str, str]],
    item_rects: list[QRectF],
    label_font: QFont,
    value_font: QFont,
) -> None:
    if rect.isNull():
        return
    painter.save()
    painter.setPen(QPen(QColor("#e0e0dd"), 1.0))
    painter.setBrush(QColor("#f4f4f3"))
    painter.drawRoundedRect(rect, 7.0, 7.0)

    if not items:
        painter.restore()
        return
    for item_rect, (label, value) in zip(item_rects, items, strict=False):
        draw_info_chip(painter, item_rect, label, value, label_font=label_font, value_font=value_font)
    painter.restore()


def draw_info_chip(
    painter: QPainter,
    rect: QRectF,
    label: str,
    value: str,
    *,
    label_font: QFont,
    value_font: QFont,
) -> None:
    painter.save()
    painter.setPen(QPen(QColor("#e4e4e1"), 1.0))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(rect, 6.0, 6.0)

    value_font = QFont(value_font)
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


__all__ = [
    "draw_card_shadow",
    "draw_empty_state",
    "draw_footer",
    "draw_header",
    "draw_info_chip",
    "draw_interaction_hints",
    "draw_panel",
    "draw_projected_scene",
    "draw_viewport",
    "preview_element_color",
]
