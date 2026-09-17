from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QRectF, QTimer, pyqtSlot
from PyQt6.QtGui import QNativeGestureEvent
from PyQt6.QtWidgets import (
    QGraphicsView,
)

from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document import (
    CLIPBOARD_SELECTION_VERSION as CURRENT_CLIPBOARD_SELECTION_VERSION,
)
from chemvas.ui.canvas_background_painter import draw_canvas_background_for
from chemvas.ui.canvas_callback_state import (
    run_scene_selection_group_callback_for,
    run_scene_selection_outline_callback_for,
)
from chemvas.ui.canvas_view_ports import (
    input_controller_for_view,
    pointer_controller_for_view,
)
from chemvas.ui.canvas_view_setup import initialize_canvas_view
from chemvas.ui.canvas_window_access import notify_error_for

if TYPE_CHECKING:
    from PyQt6.QtGui import (
        QPainter,
    )

logger = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    """The Qt view. Its event overrides hand each event to the input services.

    Qt can deliver events while the view is still being set up, before the
    services are attached; every override then falls back to the base
    handler. Only the four mouse overrides contain exceptions: an exception
    escaping a Python override of a Qt virtual is fatal, and a failed
    pointer gesture is the one the user can simply retry.
    """

    FILE_FORMAT_VERSION = CANVAS_FILE_VERSION
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = CURRENT_CLIPBOARD_SELECTION_VERSION

    def __init__(self, *, renderer: object) -> None:
        super().__init__()
        initialize_canvas_view(self, renderer=renderer)

    @pyqtSlot()
    def handle_scene_selection_group_changed(self) -> None:
        """Route group expansion through this QObject receiver.

        QGraphicsScene is owned by the view and is destroyed after the view has
        begun tearing down.  Keeping the signal receiver on the view lets Qt
        disconnect it before child graphics items emit selection changes from
        their destructors.
        """
        run_scene_selection_group_callback_for(self)

    @pyqtSlot()
    def handle_scene_selection_outline_changed(self) -> None:
        run_scene_selection_outline_callback_for(self)

    @override
    def drawBackground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is None:
            return
        draw_canvas_background_for(self, painter, rect)

    @override
    def keyPressEvent(self, event) -> None:
        base_key_press_event = super().keyPressEvent
        input_controller = input_controller_for_view(self)
        if input_controller is None:
            base_key_press_event(event)
            return
        input_controller.key_press_event(event)

    def _report_mouse_event_failure(self, event, phase: str) -> None:
        # PyQt6 treats an exception escaping a Python virtual-method override
        # as fatal (qFatal/SIGABRT). Perspective preserves its transaction and
        # local cursor on failure so a later pointer event can retry it; contain
        # the exception only at this outer Qt boundary.
        with contextlib.suppress(Exception):
            logger.exception("Canvas mouse-%s handling failed", phase)
        try:
            notify_error_for(
                self,
                "The current interaction could not be completed. Try again.",
            )
        except Exception:
            with contextlib.suppress(Exception):
                logger.exception("Canvas mouse-event error notification failed")
        with contextlib.suppress(Exception):
            accept = getattr(event, "accept", None)
            if callable(accept):
                accept()

    @override
    def mousePressEvent(self, event) -> None:
        try:
            base_mouse_press_event = super().mousePressEvent
            pointer_controller = pointer_controller_for_view(self)
            if pointer_controller is None:
                base_mouse_press_event(event)
                return
            pointer_controller.mouse_press_event(
                event, base_mouse_press_event=base_mouse_press_event
            )
        except Exception:
            self._report_mouse_event_failure(event, "press")

    @override
    def mouseDoubleClickEvent(self, event) -> None:
        try:
            base_mouse_double_click_event = super().mouseDoubleClickEvent
            pointer_controller = pointer_controller_for_view(self)
            if pointer_controller is None:
                base_mouse_double_click_event(event)
                return
            pointer_controller.mouse_double_click_event(
                event,
                base_mouse_double_click_event=base_mouse_double_click_event,
            )
        except Exception:
            self._report_mouse_event_failure(event, "double-click")

    @override
    def mouseMoveEvent(self, event) -> None:
        try:
            base_mouse_move_event = super().mouseMoveEvent
            pointer_controller = pointer_controller_for_view(self)
            if pointer_controller is None:
                base_mouse_move_event(event)
                return
            pointer_controller.mouse_move_event(
                event, base_mouse_move_event=base_mouse_move_event
            )
        except Exception:
            self._report_mouse_event_failure(event, "move")

    @override
    def mouseReleaseEvent(self, event) -> None:
        try:
            base_mouse_release_event = super().mouseReleaseEvent
            pointer_controller = pointer_controller_for_view(self)
            if pointer_controller is None:
                base_mouse_release_event(event)
                return
            pointer_controller.mouse_release_event(
                event, base_mouse_release_event=base_mouse_release_event
            )
        except Exception:
            self._report_mouse_event_failure(event, "release")

    @override
    def viewportEvent(self, event) -> bool:
        base_viewport_event = super().viewportEvent
        pointer_controller = pointer_controller_for_view(self)
        if pointer_controller is None:
            return base_viewport_event(event)
        return pointer_controller.viewport_event(
            event,
            single_shot=QTimer.singleShot,
            base_viewport_event=base_viewport_event,
        )

    @override
    def wheelEvent(self, event) -> None:
        base_wheel_event = super().wheelEvent
        pointer_controller = pointer_controller_for_view(self)
        if pointer_controller is None:
            base_wheel_event(event)
            return
        pointer_controller.wheel_event(event, base_wheel_event=base_wheel_event)

    @override
    def event(self, event) -> bool:
        base_event = super().event
        input_controller = input_controller_for_view(self)
        if input_controller is None:
            return base_event(event)
        return input_controller.event(
            event, native_gesture_event_type=QNativeGestureEvent
        )

    @override
    def scrollContentsBy(self, dx: int, dy: int) -> None:
        base_scroll_contents_by = super().scrollContentsBy
        pointer_controller = pointer_controller_for_view(self)
        if pointer_controller is None:
            base_scroll_contents_by(dx, dy)
            return
        pointer_controller.scroll_contents_by(
            dx, dy, base_scroll_contents_by=base_scroll_contents_by
        )
