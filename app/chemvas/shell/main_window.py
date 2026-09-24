from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, override

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QMainWindow

from chemvas.features.session import snapshot_unless_quitting

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent


# The shell cannot name the ``ui`` classes bootstrap supplies. Each runtime
# object it touches is described by the members the shell itself relies on;
# the state and tab references it only carries are bounded by ``object``.
# ``chemvas.ui.window.main_window_like`` holds the ``ui`` side of the contract.


class _DocumentActionService(Protocol):
    # The window argument is this shell window; ``ui`` types it concretely.
    def confirm_close_window(self, window: Any) -> bool: ...


class _WindowServices(Protocol):
    @property
    def document_action_service(self) -> _DocumentActionService: ...


class _PreviewWindow(Protocol):
    def hide(self) -> None: ...


class _Preview3D(Protocol):
    # A class-level ``pyqtSignal`` seen through an instance. mypy checks a
    # type-variable bound against the declared descriptor, not its ``__get__``
    # result, so ``pyqtBoundSignal`` fails the bound and ``pyqtSignal`` has no
    # ``connect``; ``Any`` is the one spelling that admits ``Preview3D`` here.
    shutdown_finished: Any

    def begin_shutdown(self) -> bool: ...


class _UiReferences(Protocol):
    @property
    def preview_window(self) -> _PreviewWindow | None: ...


class MainWindowRuntime[
    ServicesT: _WindowServices,
    StateT,
    TabsT,
    UiRefsT: _UiReferences,
    PreviewT: _Preview3D,
](Protocol):
    @property
    def state(self) -> StateT: ...

    @property
    def ui_refs(self) -> UiRefsT: ...

    @property
    def tab_refs(self) -> TabsT: ...

    @property
    def services(self) -> ServicesT: ...

    @property
    def preview_3d(self) -> PreviewT: ...


WindowFinalizer = Callable[[object], None]


class MainWindow[
    ServicesT: _WindowServices,
    StateT,
    TabsT,
    UiRefsT: _UiReferences,
    PreviewT: _Preview3D,
](QMainWindow):
    """Thin Qt shell whose concrete runtime is supplied by bootstrap.

    The type parameters are the runtime's concrete classes, which live in
    ``ui`` where the shell cannot name them: the shell relies only on the
    bounds above (and merely carries the state and tab references), bootstrap
    instantiates the window with the classes it builds, and
    ``chemvas.ui.window.main_window_like`` spells the resulting type once for
    ``ui`` code.
    """

    def __init__(
        self,
        *,
        build_runtime: Callable[
            [object], MainWindowRuntime[ServicesT, StateT, TabsT, UiRefsT, PreviewT]
        ],
        bootstrap_window: Callable[
            [object, MainWindowRuntime[ServicesT, StateT, TabsT, UiRefsT, PreviewT]],
            None,
        ],
        forget_window: WindowFinalizer,
    ) -> None:
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._forget_window = forget_window
        self._close_state = "open"
        runtime = build_runtime(self)
        self._state = runtime.state
        self._ui_refs = runtime.ui_refs
        self._tab_refs = runtime.tab_refs
        self._services = runtime.services
        self._preview_3d = runtime.preview_3d
        self._preview_3d.shutdown_finished.connect(
            self._resume_close_after_preview_shutdown
        )
        bootstrap_window(self, runtime)

    @property
    def ui_references(self) -> UiRefsT:
        return self._ui_refs

    @property
    def tab_references(self) -> TabsT:
        return self._tab_refs

    @property
    def runtime_state(self) -> StateT:
        return self._state

    @property
    def services(self) -> ServicesT:
        return self._services

    @property
    def preview_3d(self) -> PreviewT:
        return self._preview_3d

    @property
    def is_closing(self) -> bool:
        return self._close_state != "open"

    def close_after_confirmation(self) -> None:
        """Finish a close already confirmed by the application Quit coordinator."""
        if self._close_state == "open":
            self._close_state = "confirmed"
        self.close()

    @override
    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            super().closeEvent(event)
            return
        if self._close_state == "waiting":
            event.ignore()
            return
        if self._close_state == "ready":
            self._finalize_close(event)
            return
        if self._close_state not in {"open", "confirmed"}:
            event.ignore()
            return
        if (
            self._close_state == "open"
            and not self._services.document_action_service.confirm_close_window(self)
        ):
            event.ignore()
            return
        preview_window = self._ui_refs.preview_window
        if preview_window is not None:
            preview_window.hide()
        self._close_state = "waiting"
        if not self._preview_3d.begin_shutdown():
            # Confirmation has completed, so freeze editing until the pending
            # worker drains. Keep the window visible: hiding an ignored primary
            # close prevents Qt from emitting lastWindowClosed on the retry.
            self.setEnabled(False)
            event.ignore()
            return
        self._close_state = "ready"
        self._finalize_close(event)

    def _resume_close_after_preview_shutdown(self) -> None:
        if self._close_state != "waiting":
            return
        self._close_state = "ready"
        QTimer.singleShot(0, self.close)

    def _finalize_close(self, event: QCloseEvent) -> None:
        if self._close_state != "ready":
            event.ignore()
            return
        self._close_state = "finalizing"
        self._forget_window(self)
        # Defer a session refresh: it runs only if the app keeps running (a
        # standalone window close drops the closed document from the restore
        # set). The app-wide Quit coordinator freezes the full set before it
        # starts closing windows, so these callbacks no-op during that shutdown.
        QTimer.singleShot(0, snapshot_unless_quitting)
        super().closeEvent(event)
        self._close_state = "closed"


__all__ = ["MainWindow", "MainWindowRuntime"]
