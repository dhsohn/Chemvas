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


class NoSelectTextItem(QGraphicsTextItem):
    def paint(self, painter, option, widget=None) -> None:
        option = QStyleOptionGraphicsItem(option)
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
