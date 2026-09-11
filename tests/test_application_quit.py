from __future__ import annotations

import os
import subprocess
import sys

import pytest

SCRIPT = r"""
import json
import os
from pathlib import Path
import sys

from PyQt6.QtCore import QEvent, QObject, QPointF, QTimer
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from chemvas.adapters.qt.file_open_events import FileOpenEventFilter
from chemvas.bootstrap.file_open import open_document
from chemvas.bootstrap.window_registry import open_new_window, open_windows
from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.features.session import is_quitting
from chemvas.ui.app_data_paths import sessions_dir
from chemvas.ui.main_window_ports import active_canvas_for_window, preview_for_window, services_for_window
from chemvas.ui.session_recovery_service import SessionRecoveryService
from chemvas.ui.session_snapshot_store import new_session_store
from chemvas.ui.structure_mutation_access import add_bond_between_points_for

root, mode = Path(sys.argv[1]), sys.argv[2]
app = QApplication([])
app.setApplicationName("Chemvas")
app.setOrganizationName("Chemvas")
if mode == "keep-alive":
    app.setQuitOnLastWindowClosed(False)
windows = []
for name in "abc":
    window = open_new_window(windows[-1] if windows else None)
    canvas = active_canvas_for_window(window)
    add_bond_between_points_for(canvas, QPointF(0, 0), QPointF(40, 0))
    assert services_for_window(window).document_action_service.save_canvas_to_path(window, str(root / (name + ".chemvas")))
    windows.append(window)
for window in (() if mode == "clean" else (windows[0], windows[2])):
    add_bond_between_points_for(active_canvas_for_window(window), QPointF(0, 80), QPointF(40, 80))
if mode in {"save-as", "save-as-cancel"}:
    window = open_new_window(windows[-1])
    add_bond_between_points_for(active_canvas_for_window(window), QPointF(0, 0), QPointF(40, 0))
    windows.append(window)
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(root / "new.chemvas") if mode == "save-as" else "", ""))

store = new_session_store(sessions_dir())
service = SessionRecoveryService(store, interval_ms=20)
service.start(app)
incoming = root / "incoming.chemvas"
write_document(incoming, read_document(root / "b.chemvas").state, CANVAS_FILE_VERSION)
file_filter = FileOpenEventFilter(open_document, parent=app)
app.installEventFilter(file_filter)
class SyntheticFileOpen(QEvent):
    # PyQt cannot construct QFileOpenEvent; dispatch its actual filter protocol.
    def __init__(self):
        super().__init__(QEvent.Type.FileOpen)
    def file(self):
        return str(incoming)
def incoming_event():
    before = open_windows()
    QApplication.sendEvent(app, SyntheticFileOpen())
    assert open_windows() == before, "Quit must refuse OS Open before creating a window"
    assert any(str(incoming) in window.statusBar().currentMessage() for window in before)
prompts = []
class Answer(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QMessageBox):
            if not obj.property("answered"):
                obj.setProperty("answered", True)
                assert obj.windowTitle() == "Save Changes", obj.text()
                prompts.append(obj.text())
                choice = QMessageBox.StandardButton.Discard if mode == "discard" else QMessageBox.StandardButton.Save
                if mode in {"cancel", "file-open-cancel"} and len(prompts) == 2:
                    choice = QMessageBox.StandardButton.Cancel
                if mode in {"file-open-modal", "file-open-cancel"} and len(prompts) == 1:
                    QTimer.singleShot(10, incoming_event)
                if mode == "nested-quit":
                    QTimer.singleShot(20, app.quit)
                QTimer.singleShot(70, lambda: obj.button(choice).click())
        return False
answer = Answer(app)
app.installEventFilter(answer)
if mode in {"worker", "file-open-worker"}:
    preview = preview_for_window(windows[0])
    def delayed_shutdown():
        if mode == "file-open-worker":
            QTimer.singleShot(10, incoming_event)
        QTimer.singleShot(100, preview.shutdown_finished.emit)
        QTimer.singleShot(20, app.quit)
        return False
    preview.begin_shutdown = delayed_shutdown

cancelled_modes = {"cancel", "failed-save", "failed-snapshot", "save-as-cancel", "file-open-cancel"}
if mode in cancelled_modes:
    if mode == "failed-save":
        services_for_window(windows[0]).document_action_service.save_canvas = lambda *a, **k: False
    if mode == "failed-snapshot":
        def fail_save(docs):
            raise OSError("injected full disk")
        store.save_documents = fail_save
    def check_cancel():
        assert len(open_windows()) == len(windows)
        assert all(window.isVisible() and window.isEnabled() for window in windows)
        assert not is_quitting()
        manifest = json.loads((store.session_dir / "session.json").read_text())
        assert not manifest["clean_exit"]
        if mode == "failed-snapshot":
            label = services_for_window(windows[0]).status_service.autosave_error_label
            assert label.isVisible() and "injected full disk" in label.toolTip()
        if mode == "file-open-cancel":
            QApplication.sendEvent(app, SyntheticFileOpen())
            assert len(open_windows()) == 4
            canvas = active_canvas_for_window(open_windows()[-1])
            assert services_for_window(open_windows()[-1]).canvas_document_service.file_path(canvas) == str(incoming)
        print("cancelled safely", flush=True)
        os._exit(0)
    QTimer.singleShot(500, check_cancel)

QTimer.singleShot(0, app.quit)
QTimer.singleShot(4000, lambda: os._exit(91))
assert app.exec() == 0
assert mode not in cancelled_modes, "Quit should have been cancelled"
manifest = json.loads((store.session_dir / "session.json").read_text())
expected = {"a.chemvas", "b.chemvas", "c.chemvas"}
if mode == "save-as":
    expected.add("new.chemvas")
assert {entry["display_name"] for entry in manifest["docs"]} == expected, manifest
assert manifest["clean_exit"]
assert not open_windows()
for name in "abc":
    bonds = read_document(root / (name + ".chemvas")).state["model"]["bonds"]
    assert len(bonds) == (1 if name == "b" or mode in {"discard", "clean"} else 2)
if mode == "save-as":
    assert len(read_document(root / "new.chemvas").state["model"]["bonds"]) == 1
assert len(prompts) == (0 if mode == "clean" else 3 if mode == "save-as" else 2), prompts
print("quit preserved all documents", flush=True)
"""


@pytest.mark.parametrize(
    "mode",
    [
        "save",
        "discard",
        "cancel",
        "save-as",
        "worker",
        "failed-save",
        "failed-snapshot",
        "clean",
        "save-as-cancel",
        "keep-alive",
        "nested-quit",
        "file-open-modal",
        "file-open-worker",
        "file-open-cancel",
    ],
)
def test_application_quit_keeps_the_whole_session(tmp_path, mode):
    environment = os.environ.copy()
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        environment[key] = str(tmp_path / key.lower())
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path), mode],
        env=environment,
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stdout + result.stderr
