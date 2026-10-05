from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication

from chemvas.shell.main_window import MainWindow


def _window(*, confirm: bool, events: list[str]) -> MainWindow:
    class _DocumentActions:
        def confirm_close_window(self, window: object) -> bool:
            events.append("confirm")
            return confirm

    runtime = SimpleNamespace(
        state=object(),
        ui_refs=object(),
        tab_refs=object(),
        services=SimpleNamespace(document_action_service=_DocumentActions()),
    )
    return MainWindow(
        build_runtime=lambda window: runtime,
        bootstrap_window=lambda window, built_runtime: None,
        forget_window=lambda window: events.append("forget"),
    )


def test_rejected_close_performs_no_cleanup() -> None:
    app = QApplication.instance() or QApplication([])
    events: list[str] = []
    window = _window(confirm=False, events=events)
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


def test_failed_close_confirmation_keeps_the_window_open(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    events: list[str] = []
    reported: list[BaseException] = []
    # The desktop exception boundary replaces sys.excepthook. PyQt then reports
    # a handler exception to it and lets Qt act on the close event as it stands.
    monkeypatch.setattr(
        sys, "excepthook", lambda _type, error, _tb: reported.append(error)
    )
    window = _window(confirm=True, events=events)
    actions = window.services.document_action_service
    window.show()
    app.processEvents()

    def fail(_window: object) -> bool:
        events.append("confirm")
        raise RuntimeError("close prompt failure")

    actions.confirm_close_window = fail
    with mock.patch(
        "chemvas.shell.main_window.QTimer.singleShot",
        side_effect=lambda _delay, _callback: events.append("snapshot"),
    ):
        assert window.close() is False
        assert [str(error) for error in reported] == ["close prompt failure"]
        assert window.isVisible()
        assert window.is_closing is False
        assert events == ["confirm"]

        del actions.confirm_close_window
        assert window.close() is True

    assert events == [
        "confirm",
        "confirm",
        "forget",
        "snapshot",
    ]
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(window)
