"""A queued Color callback never dereferences a destroyed Qt window."""

import sys

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.mark.parametrize("drain_deletes_first", [False, True])
def test_queued_color_callback_survives_window_close(
    app, monkeypatch, drain_deletes_first
):
    window = build_main_window()
    window.show()
    app.processEvents()
    canvas = active_canvas_for_window(window)
    services = services_for_window(window)
    errors = []
    monkeypatch.setattr(
        sys, "excepthook", lambda _type, error, _trace: errors.append(str(error))
    )
    try:
        # Keep the real zero-QTimer, including its ordinary event-loop ordering.
        services.tool_routing_service.apply_color_preset(window, "#e12345")
        services.canvas_document_service.mark_clean(canvas)
        assert window.close()
        if drain_deletes_first:
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert sip.isdeleted(window)
        QTest.qWait(2)
        assert errors == []
    finally:
        if not sip.isdeleted(window):
            services.canvas_document_service.mark_clean(canvas)
            window.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
