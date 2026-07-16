from __future__ import annotations

import logging

from PyQt6.QtCore import QRectF, pyqtSlot
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
    route_scene_selection_group_changed,
    route_scene_selection_outline_changed,
    route_scroll_contents_by,
    route_viewport_event,
    route_wheel_event,
)
from ui.canvas_view_setup import initialize_canvas_view
from ui.canvas_window_access import notify_error_for

logger = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    FILE_FORMAT_VERSION = 4
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 2

    def __init__(self) -> None:
        super().__init__()
        initialize_canvas_view(self)

    @pyqtSlot()
    def handle_scene_selection_group_changed(self) -> None:
        """Route group expansion through this QObject receiver.

        QGraphicsScene is owned by the view and is destroyed after the view has
        begun tearing down.  Keeping the signal receiver on the view lets Qt
        disconnect it before child graphics items emit selection changes from
        their destructors.
        """
        route_scene_selection_group_changed(self)

    @pyqtSlot()
    def handle_scene_selection_outline_changed(self) -> None:
        route_scene_selection_outline_changed(self)

    def drawBackground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is None:
            return
        draw_canvas_background_for(self, painter, rect)

    def keyPressEvent(self, event) -> None:
        route_key_press_event(self, event, base_key_press_event=super().keyPressEvent)

    def _report_mouse_event_failure(self, event, phase: str) -> None:
        # PyQt6 treats an exception escaping a Python virtual-method override
        # as fatal (qFatal/SIGABRT). Perspective preserves its transaction and
        # local cursor on failure so a later pointer event can retry it; contain
        # the exception only at this outer Qt boundary.
        try:
            logger.exception("Canvas mouse-%s handling failed", phase)
        except BaseException:
            pass
        try:
            notify_error_for(
                self,
                "The current interaction could not be completed. Try again.",
            )
        except BaseException:
            try:
                logger.exception("Canvas mouse-event error notification failed")
            except BaseException:
                pass
        try:
            accept = getattr(event, "accept", None)
            if callable(accept):
                accept()
        except BaseException:
            pass

    def mousePressEvent(self, event) -> None:
        try:
            route_mouse_press_event(self, event, base_mouse_press_event=super().mousePressEvent)
        except BaseException:
            self._report_mouse_event_failure(event, "press")

    def mouseDoubleClickEvent(self, event) -> None:
        try:
            route_mouse_double_click_event(
                self,
                event,
                base_mouse_double_click_event=super().mouseDoubleClickEvent,
            )
        except BaseException:
            self._report_mouse_event_failure(event, "double-click")

    def mouseMoveEvent(self, event) -> None:
        try:
            route_mouse_move_event(self, event, base_mouse_move_event=super().mouseMoveEvent)
        except BaseException:
            self._report_mouse_event_failure(event, "move")

    def mouseReleaseEvent(self, event) -> None:
        try:
            route_mouse_release_event(self, event, base_mouse_release_event=super().mouseReleaseEvent)
        except BaseException:
            self._report_mouse_event_failure(event, "release")

    def viewportEvent(self, event) -> bool:
        return route_viewport_event(self, event, base_viewport_event=super().viewportEvent)

    def wheelEvent(self, event) -> None:
        route_wheel_event(self, event, base_wheel_event=super().wheelEvent)

    def event(self, event) -> bool:
        return route_event(self, event, base_event=super().event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        route_scroll_contents_by(self, dx, dy, base_scroll_contents_by=super().scrollContentsBy)
