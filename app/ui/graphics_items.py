from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath
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


class NoSelectLineItem(QGraphicsLineItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectPathItem(QGraphicsPathItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectPolygonItem(QGraphicsPolygonItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectRectItem(QGraphicsRectItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class NoSelectEllipseItem(QGraphicsEllipseItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


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


class NoSelectTextItem(QGraphicsTextItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class AtomLabelItem(NoSelectTextItem):
    def __init__(self, *args, hit_padding: float = 0.0, hit_radius: float | None = None) -> None:
        super().__init__(*args)
        self._hit_padding = max(0.0, float(hit_padding))
        self._hit_radius = None if hit_radius is None else max(0.0, float(hit_radius))

    def set_hit_padding(self, hit_padding: float) -> None:
        self.prepareGeometryChange()
        self._hit_padding = max(0.0, float(hit_padding))

    def set_hit_radius(self, hit_radius: float | None) -> None:
        self.prepareGeometryChange()
        self._hit_radius = None if hit_radius is None else max(0.0, float(hit_radius))

    def _hit_rect(self) -> QRectF:
        rect = super().boundingRect()
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
        rect = super().boundingRect()
        return rect.united(self._hit_rect())

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        hit_rect = self._hit_rect()
        if self._hit_radius is not None and self._hit_radius > 0.0:
            path.addEllipse(hit_rect)
        else:
            path.addRect(hit_rect)
        return path
