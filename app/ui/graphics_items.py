from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetricsF, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QStyle,
    QStyleOptionGraphicsItem,
)

from ui.label_layout_logic import SUB_SCALE, LabelLayout, parse_atom_label, place_runs


def _scaled_font(base: QFont, scale: float) -> QFont:
    """Return a copy of ``base`` scaled by ``scale`` for sub/superscript runs."""
    font = QFont(base)
    size_pt = base.pointSizeF()
    if size_pt > 0:
        font.setPointSizeF(max(1.0, size_pt * scale))
    else:
        px = base.pixelSize()
        if px > 0:
            font.setPixelSize(max(1, round(px * scale)))
    return font


class _NoSelectPaintMixin:
    """Paint without the dashed selection rectangle Qt draws for selected items."""

    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)  # type: ignore[misc]


class NoSelectLineItem(_NoSelectPaintMixin, QGraphicsLineItem):
    pass


class NoSelectPathItem(_NoSelectPaintMixin, QGraphicsPathItem):
    pass


class NoSelectPolygonItem(_NoSelectPaintMixin, QGraphicsPolygonItem):
    pass


class NoSelectRectItem(_NoSelectPaintMixin, QGraphicsRectItem):
    pass


class NoSelectEllipseItem(_NoSelectPaintMixin, QGraphicsEllipseItem):
    pass


class AtomDotItem(NoSelectEllipseItem):
    def __init__(self, *args, hit_padding: float = 0.0) -> None:
        super().__init__(*args)
        self._hit_padding = max(0.0, float(hit_padding))

    def boundingRect(self):
        rect = super().boundingRect()
        if self._hit_padding <= 0.0:
            return rect
        return rect.adjusted(
            -self._hit_padding,
            -self._hit_padding,
            self._hit_padding,
            self._hit_padding,
        )

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        rect = self.rect()
        if self._hit_padding > 0.0:
            rect = rect.adjusted(
                -self._hit_padding,
                -self._hit_padding,
                self._hit_padding,
                self._hit_padding,
            )
        path.addEllipse(rect)
        return path

    def export_scene_bounding_rect(self) -> QRectF:
        pen = self.pen()
        brush = self.brush()
        has_pen = pen.style() != Qt.PenStyle.NoPen and pen.color().alpha() > 0
        has_brush = brush.style() != Qt.BrushStyle.NoBrush and brush.color().alpha() > 0
        if not has_pen and not has_brush:
            return QRectF()
        return self.mapRectToScene(super().boundingRect())


class NoSelectTextItem(_NoSelectPaintMixin, QGraphicsTextItem):
    pass


class AtomLabelItem(NoSelectTextItem):
    """Atom label that renders subscripts/superscripts via a shared layout.

    Labels with no typographic runs (a single normal run, e.g. ``N`` or a bare
    charge mark ``+``) fall through to the default QGraphicsTextItem rendering so
    their geometry stays byte-identical to before. Only labels that actually need
    typography (``CH3``, ``CO2Me``, ``NH4+``) switch to custom run painting, with
    geometry sourced from :mod:`ui.label_layout_logic`.
    """

    def __init__(self, *args, hit_padding: float = 0.0, hit_radius: float | None = None) -> None:
        super().__init__(*args)
        self._hit_padding = max(0.0, float(hit_padding))
        self._hit_radius = None if hit_radius is None else max(0.0, float(hit_radius))
        self._raw_text = self.toPlainText()
        self._layout: LabelLayout | None = None
        self._typographic = False
        self._outline_mode = False
        self._anchor_element: str | None = None
        self._anchor_at_end = False
        self._relayout()

    def set_outline_mode(self, enabled: bool) -> None:
        """When enabled, paint glyphs as vector outlines (for vector export)."""
        enabled = bool(enabled)
        if enabled == self._outline_mode:
            return
        self._outline_mode = enabled
        self.update()

    def set_hit_padding(self, hit_padding: float) -> None:
        self.prepareGeometryChange()
        self._hit_padding = max(0.0, float(hit_padding))

    def set_hit_radius(self, hit_radius: float | None) -> None:
        self.prepareGeometryChange()
        self._hit_radius = None if hit_radius is None else max(0.0, float(hit_radius))

    def set_anchor(self, element: str | None, *, at_end: bool = False) -> None:
        """Anchor the bond attachment on one element glyph inside the label.

        When set, :meth:`anchor_center` / :meth:`anchor_scene_rect` report that
        glyph so the atom sits on it (not the label's midpoint) and bonds trim to
        it. ``at_end`` picks the last matching glyph, for reversed labels ("HN").
        """
        self._anchor_element = element or None
        self._anchor_at_end = bool(at_end)

    def _anchor_local_rect(self) -> QRectF | None:
        element = self._anchor_element
        if not element:
            return None
        # The element always sits at one extreme of the display text ("N" + H, or
        # H + "N" when reversed), so locate it by position. Matching a parsed run
        # by text would miss it, since parse merges adjacent letters ("NH2" -> a
        # single "NH" run) and the element is only part of that run.
        if self._anchor_at_end:
            if not self._raw_text.endswith(element):
                return None
        elif not self._raw_text.startswith(element):
            return None
        base = self._base_rect()
        margin = self._doc_margin()
        fm = QFontMetricsF(self.font())
        width = fm.horizontalAdvance(element)
        if self._typographic and self._layout is not None:
            total = self._layout.width
        else:
            total = fm.horizontalAdvance(self._raw_text)
        left = margin + (total - width) if self._anchor_at_end else margin
        return QRectF(left, base.top(), width, base.height())

    def anchor_center(self) -> QPointF | None:
        rect = self._anchor_local_rect()
        return rect.center() if rect is not None else None

    def anchor_scene_rect(self) -> QRectF | None:
        rect = self._anchor_local_rect()
        return self.mapRectToScene(rect) if rect is not None else None

    def setPlainText(self, text) -> None:
        self._raw_text = "" if text is None else str(text)
        super().setPlainText(self._raw_text)
        self._anchor_element = None
        self._relayout()

    def setFont(self, font) -> None:
        super().setFont(font)
        self._relayout()

    def _doc_margin(self) -> float:
        doc = self.document()
        return float(doc.documentMargin()) if doc is not None else 0.0

    def _relayout(self) -> None:
        self.prepareGeometryChange()
        runs = parse_atom_label(self._raw_text)
        if not any(run.role != "normal" for run in runs):
            self._layout = None
            self._typographic = False
            return
        font = self.font()
        base_fm = QFontMetricsF(font)
        sub_fm = QFontMetricsF(_scaled_font(font, SUB_SCALE))
        size_pt = font.pointSizeF()
        if size_pt <= 0:
            px = font.pixelSize()
            size_pt = float(px) if px > 0 else 12.0

        def measure(text: str, point_size: float) -> float:
            metrics = sub_fm if point_size < size_pt else base_fm
            return metrics.horizontalAdvance(text)

        self._layout = place_runs(
            runs,
            measure=measure,
            ascent=base_fm.ascent(),
            descent=base_fm.descent(),
            base_point_size=size_pt,
        )
        self._typographic = True

    def _base_rect(self) -> QRectF:
        if self._typographic and self._layout is not None:
            margin = self._doc_margin()
            return QRectF(
                0.0,
                0.0,
                self._layout.width + 2.0 * margin,
                self._layout.height + 2.0 * margin,
            )
        return super().boundingRect()

    def _hit_rect(self) -> QRectF:
        rect = self._base_rect()
        if self._hit_radius is not None and self._hit_radius > 0.0:
            center = rect.center()
            radius = self._hit_radius
            return QRectF(
                center.x() - radius,
                center.y() - radius,
                radius * 2.0,
                radius * 2.0,
            )
        if self._hit_padding > 0.0:
            return rect.adjusted(
                -self._hit_padding,
                -self._hit_padding,
                self._hit_padding,
                self._hit_padding,
            )
        return rect

    def boundingRect(self):
        return self._base_rect().united(self._hit_rect())

    def export_scene_bounding_rect(self) -> QRectF:
        return self.mapRectToScene(self._base_rect())

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        hit_rect = self._hit_rect()
        if self._hit_radius is not None and self._hit_radius > 0.0:
            path.addEllipse(hit_rect)
            path.addRect(self._base_rect())
        else:
            path.addRect(hit_rect)
        return path

    def paint(self, painter, option, widget=None) -> None:
        if self._outline_mode:
            self._paint_outlined(painter)
            return
        if not self._typographic or self._layout is None:
            super().paint(painter, option, widget)
            return
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        painter.save()
        painter.setPen(QPen(self.defaultTextColor()))
        font = self.font()
        sub_font = _scaled_font(font, SUB_SCALE)
        margin = self._doc_margin()
        for run in self._layout.runs:
            painter.setFont(font if run.role == "normal" else sub_font)
            painter.drawText(QPointF(margin + run.x, margin + run.baseline), run.text)
        painter.restore()

    def _paint_outlined(self, painter) -> None:
        text = self._raw_text
        if not text:
            return
        font = self.font()
        margin = self._doc_margin()
        path = QPainterPath()
        if self._typographic and self._layout is not None:
            sub_font = _scaled_font(font, SUB_SCALE)
            for run in self._layout.runs:
                run_font = font if run.role == "normal" else sub_font
                path.addText(QPointF(margin + run.x, margin + run.baseline), run_font, run.text)
        else:
            ascent = QFontMetricsF(font).ascent()
            path.addText(QPointF(margin, margin + ascent), font, text)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.defaultTextColor())
        painter.drawPath(path)
        painter.restore()
