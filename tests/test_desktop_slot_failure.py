"""A Python slot failure must not abort the desktop event loop."""

import subprocess
import sys

import pytest

from chemvas.shell.window_registry import failures_reported_in, take_failed_window
from tests.subprocess_support import source_subprocess_env


def test_desktop_action_failure_is_reported_and_event_loop_continues():
    script = r"""
import sys
from types import SimpleNamespace
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication
from chemvas.bootstrap import application, window_registry
from chemvas.core import rdkit_adapter
from chemvas.ui.session import session_recovery_service

if sys.platform != "win32":
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

original_open = window_registry.open_new_window
original_hook = sys.excepthook
observed = []
def open_window():
    window = original_open()
    action = QAction(window)
    def fail():
        raise RuntimeError("menu failure regression")
    action.triggered.connect(fail)
    def exercise():
        action.trigger()
        observed.append(window.statusBar().currentMessage())
        QApplication.instance().quit()
    QTimer.singleShot(0, exercise)
    return window
window_registry.open_new_window = open_window
session_recovery_service.create_session_recovery_service = (
    lambda **kwargs: SimpleNamespace(start=lambda app: None)
)
rdkit_adapter.warm_rdkit_in_background = lambda: None
sys.argv = ["chemvas"]
application.main()
assert sys.excepthook is original_hook
assert observed == ["The current command could not be completed. Try again."]
print("desktop survived slot failure")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=source_subprocess_env({"QT_QPA_PLATFORM": "offscreen"}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "desktop survived slot failure" in result.stdout
    assert "menu failure regression" in result.stderr


def test_desktop_close_failure_keeps_the_unsaved_window_open():
    script = r"""
import sys
from types import SimpleNamespace
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from chemvas.bootstrap import application, window_registry
from chemvas.core import rdkit_adapter
from chemvas.shell.window_registry import open_windows
from chemvas.ui.session import session_recovery_service
from chemvas.ui.window.main_window_ports import active_canvas_for_window

if sys.platform != "win32":
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

original_open = window_registry.open_new_window
observed = {}
def open_window():
    window = original_open()
    def exercise():
        canvas = active_canvas_for_window(window)
        documents = window.services.canvas_document_service
        documents.mark_dirty(canvas)
        actions = window.services.document_action_service
        def fail(_window):
            raise RuntimeError("close prompt failure regression")
        actions.confirm_close_window = fail
        observed["closed"] = window.close()
        observed["message"] = window.statusBar().currentMessage()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        observed["alive"] = not sip.isdeleted(window) and window.isVisible()
        observed["registered"] = open_windows() == (window,)
        try:
            observed["autosave"] = [
                document.dirty
                for document in session_recovery_service.collect_open_documents()
            ]
        except RuntimeError as error:
            observed["autosave"] = str(error)
        # Leave through the ordinary prompt, discarding the test drawing.
        del actions.confirm_close_window
        QMessageBox.question = staticmethod(
            lambda *args, **kwargs: QMessageBox.StandardButton.Discard
        )
        QApplication.instance().quit()
    QTimer.singleShot(0, exercise)
    return window
window_registry.open_new_window = open_window
session_recovery_service.create_session_recovery_service = (
    lambda **kwargs: SimpleNamespace(start=lambda app: None)
)
rdkit_adapter.warm_rdkit_in_background = lambda: None
sys.argv = ["chemvas"]
application.main()
assert observed == {
    "closed": False,
    "message": "The current command could not be completed. Try again.",
    "alive": True,
    "registered": True,
    "autosave": [True],
}, observed
assert open_windows() == ()
print("unsaved window survived close failure")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=source_subprocess_env({"QT_QPA_PLATFORM": "offscreen"}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unsaved window survived close failure" in result.stdout
    assert "close prompt failure regression" in result.stderr


def test_background_close_failure_is_reported_in_the_closing_window():
    script = r"""
import sys
from types import SimpleNamespace
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication
from chemvas.bootstrap import application, window_registry
from chemvas.core import rdkit_adapter
from chemvas.ui.session import session_recovery_service

if sys.platform != "win32":
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

original_open = window_registry.open_new_window
message = "The current command could not be completed. Try again."
observed = {}
def open_window():
    active = original_open()
    def exercise():
        closing = original_open()
        active.activateWindow()
        QApplication.processEvents()
        observed["active"] = QApplication.activeWindow() is active
        actions = closing.services.document_action_service
        def fail(_window):
            raise RuntimeError("background close failure regression")
        actions.confirm_close_window = fail
        def reported():
            return tuple(
                window.statusBar().currentMessage() == message
                for window in (closing, active)
            )
        observed["closed"] = closing.close()
        observed["after close"] = reported()
        # A later failure that no window handler claims goes to the active window,
        # even from an action of the window whose close failed.
        closing.statusBar().clearMessage()
        action = QAction(closing)
        def fail_slot():
            raise RuntimeError("later slot failure regression")
        action.triggered.connect(fail_slot)
        action.trigger()
        observed["after slot"] = reported()
        del actions.confirm_close_window
        QApplication.instance().quit()
    QTimer.singleShot(0, exercise)
    return active
window_registry.open_new_window = open_window
session_recovery_service.create_session_recovery_service = (
    lambda **kwargs: SimpleNamespace(start=lambda app: None)
)
rdkit_adapter.warm_rdkit_in_background = lambda: None
sys.argv = ["chemvas"]
application.main()
assert observed == {
    "active": True,
    "closed": False,
    "after close": (True, False),
    "after slot": (False, True),
}, observed
print("close failure reported in the closing window")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=source_subprocess_env({"QT_QPA_PLATFORM": "offscreen"}),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "close failure reported in the closing window" in result.stdout
    assert "background close failure regression" in result.stderr
    assert "later slot failure regression" in result.stderr


def test_a_kept_failure_window_belongs_to_its_own_exception():
    window = object()
    with pytest.raises(RuntimeError) as escaped, failures_reported_in(window):
        raise RuntimeError("handler failure")

    # Caught before the boundary saw it: another report finds no window and
    # releases the kept one.
    assert take_failed_window(RuntimeError("slot failure")) is None
    assert take_failed_window(escaped.value) is None
