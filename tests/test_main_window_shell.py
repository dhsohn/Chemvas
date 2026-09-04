from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QWidget

from chemvas.shell.main_window import MainWindow


class _Signal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self) -> None:
        for slot in tuple(self._slots):
            slot()


class _Preview3D:
    def __init__(self, events: list[str], *, shutdown_ready: bool) -> None:
        self._events = events
        self._shutdown_ready = shutdown_ready
        self.shutdown_finished = _Signal()

    def begin_shutdown(self) -> bool:
        self._events.append("begin_shutdown")
        return self._shutdown_ready

    def finish_shutdown(self) -> None:
        self.shutdown_finished.emit()


def _window(
    *, confirm: bool, events: list[str], shutdown_ready: bool = True
) -> tuple[MainWindow, _Preview3D]:
    class _DocumentActions:
        def confirm_close_window(self, window: object) -> bool:
            events.append("confirm")
            return confirm

    class _PreviewWindow:
        def hide(self) -> None:
            events.append("hide")

    preview = _Preview3D(events, shutdown_ready=shutdown_ready)

    runtime = SimpleNamespace(
        state=object(),
        ui_refs=SimpleNamespace(preview_window=_PreviewWindow()),
        tab_refs=object(),
        services=canvas_runtime_services(document_action_service=_DocumentActions()),
        preview_3d=preview,
    )
    return (
        MainWindow(
            build_runtime=lambda window: runtime,
            bootstrap_window=lambda window, built_runtime: None,
            forget_window=lambda window: events.append("forget"),
        ),
        preview,
    )


def test_rejected_close_performs_no_cleanup() -> None:
    app = QApplication.instance() or QApplication([])
    events: list[str] = []
    window, _preview = _window(confirm=False, events=events)
    close_event = QCloseEvent()

    with mock.patch(
        "chemvas.shell.main_window.QTimer.singleShot",
        side_effect=lambda _delay, _callback: events.append("snapshot"),
    ):
        window.closeEvent(close_event)

    assert close_event.isAccepted() is False
    assert events == ["confirm"]
    window.deleteLater()
    del app


def test_accepted_close_preserves_cleanup_order() -> None:
    app = QApplication.instance() or QApplication([])
    events: list[str] = []
    window, _preview = _window(confirm=True, events=events)
    close_event = QCloseEvent()

    with mock.patch(
        "chemvas.shell.main_window.QTimer.singleShot",
        side_effect=lambda _delay, _callback: events.append("snapshot"),
    ):
        window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert events == [
        "confirm",
        "hide",
        "begin_shutdown",
        "forget",
        "snapshot",
    ]
    assert window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.deleteLater()
    del app


def test_busy_close_waits_without_blocking_or_allowing_new_edits() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    events: list[str] = []
    scheduled: list[object] = []
    window, preview = _window(
        confirm=True,
        events=events,
        shutdown_ready=False,
    )
    window.show()
    app.processEvents()

    def schedule(_delay, callback) -> None:
        if getattr(callback, "__name__", "") == "snapshot_unless_quitting":
            events.append("snapshot")
        else:
            scheduled.append(callback)

    first_close = QCloseEvent()
    repeated_close = QCloseEvent()
    with mock.patch(
        "chemvas.shell.main_window.QTimer.singleShot", side_effect=schedule
    ):
        window.closeEvent(first_close)
        window.closeEvent(repeated_close)

        assert first_close.isAccepted() is False
        assert repeated_close.isAccepted() is False
        assert window.isVisible()
        assert window.isEnabled() is False
        assert events == ["confirm", "hide", "begin_shutdown"]

        preview.finish_shutdown()
        preview.finish_shutdown()
        assert len(scheduled) == 1

        close_again = scheduled.pop()
        assert callable(close_again)
        assert close_again() is True

    assert window.isVisible() is False
    assert events == [
        "confirm",
        "hide",
        "begin_shutdown",
        "forget",
        "snapshot",
    ]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_accepted_close_deletes_main_window_tree_before_application_teardown() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    events: list[str] = []
    window, _preview = _window(confirm=True, events=events)
    child = QWidget(window)
    window.show()
    app.processEvents()

    with mock.patch("chemvas.shell.main_window.QTimer.singleShot"):
        assert window.close() is True
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert sip.isdeleted(window)
    assert sip.isdeleted(child)
