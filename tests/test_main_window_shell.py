from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.shell.main_window import MainWindow
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication


def _window(*, confirm: bool, events: list[str]) -> MainWindow:
    class _DocumentActions:
        def confirm_close_window(self, window: object) -> bool:
            events.append("confirm")
            return confirm

    class _PreviewWindow:
        def hide(self) -> None:
            events.append("hide")

    class _Preview3D:
        def shutdown(self) -> None:
            events.append("shutdown")

    runtime = SimpleNamespace(
        state=object(),
        ui_refs=SimpleNamespace(preview_window=_PreviewWindow()),
        tab_refs=object(),
        services=canvas_runtime_services(document_action_service=_DocumentActions()),
        preview_3d=_Preview3D(),
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
        "chemvas.shell.main_window.request_snapshot_on_window_close",
        side_effect=lambda: events.append("snapshot"),
    ):
        window.closeEvent(close_event)

    assert close_event.isAccepted() is False
    assert events == ["confirm"]
    window.deleteLater()
    del app


def test_accepted_close_preserves_cleanup_order() -> None:
    app = QApplication.instance() or QApplication([])
    events: list[str] = []
    window = _window(confirm=True, events=events)
    close_event = QCloseEvent()

    with mock.patch(
        "chemvas.shell.main_window.request_snapshot_on_window_close",
        side_effect=lambda: events.append("snapshot"),
    ):
        window.closeEvent(close_event)

    assert close_event.isAccepted() is True
    assert events == ["confirm", "hide", "shutdown", "forget", "snapshot"]
    window.deleteLater()
    del app
