from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMainWindow

from chemvas.features.session import request_snapshot_on_window_close


class _DocumentActionService(Protocol):
    def confirm_close_window(self, window: object) -> bool: ...


class _WindowServices(Protocol):
    @property
    def document_action_service(self) -> _DocumentActionService: ...


class _PreviewWindow(Protocol):
    def hide(self) -> None: ...


class _UiReferences(Protocol):
    @property
    def preview_window(self) -> _PreviewWindow | None: ...


class MainWindowRuntime(Protocol):
    @property
    def state(self) -> object: ...

    @property
    def ui_refs(self) -> _UiReferences: ...

    @property
    def tab_refs(self) -> object: ...

    @property
    def services(self) -> _WindowServices: ...

    @property
    def preview_3d(self) -> object: ...


WindowFinalizer = Callable[[object], None]


class MainWindow(QMainWindow):
    """Thin Qt shell whose concrete runtime is supplied by bootstrap."""

    def __init__[RuntimeT: MainWindowRuntime](
        self,
        *,
        build_runtime: Callable[[object], RuntimeT],
        bootstrap_window: Callable[[object, RuntimeT], None],
        forget_window: WindowFinalizer,
    ) -> None:
        super().__init__()
        self._forget_window = forget_window
        runtime = build_runtime(self)
        self._state = runtime.state
        self._ui_refs = runtime.ui_refs
        self._tab_refs = runtime.tab_refs
        self._services = runtime.services
        self._preview_3d = runtime.preview_3d
        bootstrap_window(self, runtime)

    @property
    def ui_references(self) -> _UiReferences:
        return self._ui_refs

    @property
    def tab_references(self) -> object:
        return self._tab_refs

    @property
    def runtime_state(self) -> object:
        return self._state

    def closeEvent(self, event: QCloseEvent | None) -> None:
        if event is None:
            super().closeEvent(event)
            return
        if not self._services.document_action_service.confirm_close_window(self):
            event.ignore()
            return
        preview_window = self._ui_refs.preview_window
        if preview_window is not None:
            preview_window.hide()
        shutdown_preview = getattr(self._preview_3d, "shutdown", None)
        if callable(shutdown_preview):
            shutdown_preview()
        self._forget_window(self)
        # Defer a session refresh: it runs only if the app keeps running (a
        # standalone window close drops the closed document from the restore
        # set). During app-wide quit, aboutToQuit sets the quitting flag before
        # this fires, so it no-ops and the full open set is preserved.
        request_snapshot_on_window_close()
        super().closeEvent(event)


__all__ = ["MainWindow", "MainWindowRuntime"]
