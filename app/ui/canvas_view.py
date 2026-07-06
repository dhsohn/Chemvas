from __future__ import annotations

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import (
    QPainter,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
)

from ui.canvas_background_painter import draw_canvas_background_for
from ui.canvas_view_event_router import (
    route_event,
    route_key_press_event,
    route_mouse_double_click_event,
    route_mouse_move_event,
    route_mouse_press_event,
    route_mouse_release_event,
    route_scroll_contents_by,
    route_viewport_event,
    route_wheel_event,
)
from ui.canvas_view_setup import initialize_canvas_view


class CanvasView(QGraphicsView):
    FILE_FORMAT_VERSION = 4
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        initialize_canvas_view(self)

    def drawBackground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is None:
            return
        draw_canvas_background_for(self, painter, rect)

    def keyPressEvent(self, event) -> None:
        route_key_press_event(self, event, base_key_press_event=super().keyPressEvent)

    def mousePressEvent(self, event) -> None:
        route_mouse_press_event(self, event, base_mouse_press_event=super().mousePressEvent)

    def mouseDoubleClickEvent(self, event) -> None:
        route_mouse_double_click_event(
            self,
            event,
            base_mouse_double_click_event=super().mouseDoubleClickEvent,
        )

    def mouseMoveEvent(self, event) -> None:
        route_mouse_move_event(self, event, base_mouse_move_event=super().mouseMoveEvent)

    def mouseReleaseEvent(self, event) -> None:
        route_mouse_release_event(self, event, base_mouse_release_event=super().mouseReleaseEvent)

    def viewportEvent(self, event) -> bool:
        return route_viewport_event(self, event, base_viewport_event=super().viewportEvent)

    def wheelEvent(self, event) -> None:
        route_wheel_event(self, event, base_wheel_event=super().wheelEvent)

    def event(self, event) -> bool:
        return route_event(self, event, base_event=super().event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        route_scroll_contents_by(self, dx, dy, base_scroll_contents_by=super().scrollContentsBy)
