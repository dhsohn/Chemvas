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
from chemvas.ui.canvas.canvas_background_painter import draw_canvas_background_for
from chemvas.ui.canvas.canvas_callback_state import (
    run_scene_selection_group_callback_for,
    run_scene_selection_outline_callback_for,
)
from chemvas.ui.canvas.canvas_feedback_renderer import draw_canvas_feedback_for
from chemvas.ui.canvas.canvas_view_ports import (
    input_controller_for_view,
    pointer_controller_for_view,
)
from chemvas.ui.canvas.canvas_view_setup import initialize_canvas_view
from chemvas.ui.canvas.canvas_window_access import notify_error_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import (
        QPainter,
    )

    from chemvas.adapters.qt.renderer import Renderer
    from chemvas.core.rdkit_adapter import RDKitAdapter
    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.canvas.canvas_runtime_services import CanvasRuntimeServices
    from chemvas.ui.canvas.canvas_runtime_state import CanvasRuntimeState
    from chemvas.ui.molecule.bond_renderer import BondRenderer
    from chemvas.ui.scene.scene_render_context import SceneRenderContext

logger = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    """The Qt view. Its event overrides hand each event to the input services.

    Qt can deliver events while the view is still being set up, before the
    services are attached; every override then falls back to the base
    handler. Mouse and key-press overrides contain editing exceptions: an
    exception escaping a Python override of a Qt virtual is fatal. Mutation
    services retain ownership of rollback and history policy.
    """

    FILE_FORMAT_VERSION = CANVAS_FILE_VERSION
    # Created once by ``initialize_canvas_view``; read directly by editor code.
    model: MoleculeModel
    renderer: Renderer
    rdkit: RDKitAdapter
    runtime_state: CanvasRuntimeState
    render_context: SceneRenderContext
    bond_renderer: BondRenderer
    services: CanvasRuntimeServices
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
    def drawForeground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is not None:
            draw_canvas_feedback_for(self, painter, rect)

    @override
    def keyPressEvent(self, event) -> None:
        try:
            base_key_press_event = super().keyPressEvent
            input_controller = input_controller_for_view(self)
            if input_controller is None:
                base_key_press_event(event)
                return
            input_controller.key_press_event(event)
        except Exception:
            self._report_input_event_failure(event, "key-press")

    def _report_input_event_failure(self, event, phase: str) -> None:
        # PyQt6 treats an exception escaping a Python virtual-method override
        # as fatal (qFatal/SIGABRT). Editing services own their transactions;
        # contain and report the exception only at this outer Qt boundary.
        with contextlib.suppress(Exception):
            logger.exception("Canvas %s handling failed", phase)
        try:
            notify_error_for(
                self,
                "The current interaction could not be completed. Try again.",
            )
        except Exception:
            with contextlib.suppress(Exception):
                logger.exception("Canvas input-event error notification failed")
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
            self._report_input_event_failure(event, "mouse-press")

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
            self._report_input_event_failure(event, "mouse-double-click")

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
            self._report_input_event_failure(event, "mouse-move")

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
            self._report_input_event_failure(event, "mouse-release")

    @override
    def viewportEvent(self, event) -> bool:
        base_viewport_event = super().viewportEvent
        pointer_controller = pointer_controller_for_view(self)
        if pointer_controller is None:
            return base_viewport_event(event)
        return pointer_controller.viewport_event(
            event,
            single_shot=self._single_shot,
            base_viewport_event=base_viewport_event,
        )

    def _single_shot(self, delay: int, callback: Callable[[], None]) -> None:
        # A static singleShot retains a Python service callback after its canvas
        # is deleted. A child timer cancels that callback with the Qt view.
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(callback)
        timer.timeout.connect(timer.deleteLater)
        timer.start(delay)

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
