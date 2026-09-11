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
from chemvas.features.session import is_quit_pending, is_quitting
from chemvas.ui.app_data_paths import sessions_dir
from chemvas.ui.main_window_ports import active_canvas_for_window, preview_for_window, services_for_window
from chemvas.ui.session_recovery_service import SessionRecoveryService
from chemvas.ui.session_snapshot_store import new_session_store
from chemvas.ui.structure_mutation_access import add_bond_between_points_for

root, mode = Path(sys.argv[1]), sys.argv[2]
answer_delay_ms = int(sys.argv[3])
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
                QTimer.singleShot(answer_delay_ms, lambda: obj.button(choice).click())
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
        assert not is_quitting() and not is_quit_pending()
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

def request_quit():
    app.quit()
    if mode in cancelled_modes:
        # Quit runs nested modal loops. Observe cancellation only after the
        # request returns, not from a timer that can fire inside those loops.
        QTimer.singleShot(0, check_cancel)
QTimer.singleShot(0, request_quit)
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
    ("mode", "answer_delay_ms"),
    [
        ("save", 70),
        ("discard", 70),
        ("cancel", 70),
        ("save-as", 70),
        ("worker", 70),
        ("failed-save", 70),
        ("failed-snapshot", 70),
        ("clean", 70),
        ("save-as-cancel", 70),
        ("keep-alive", 70),
        ("nested-quit", 70),
        ("file-open-modal", 70),
        ("file-open-worker", 70),
        ("file-open-cancel", 70),
        pytest.param("file-open-cancel", 700, id="slow-file-open-cancel"),
    ],
)
def test_application_quit_keeps_the_whole_session(tmp_path, mode, answer_delay_ms):
    environment = os.environ.copy()
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        environment[key] = str(tmp_path / key.lower())
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path), mode, str(answer_delay_ms)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stdout + result.stderr


STALE_PLAN_SCRIPT = r"""
import hashlib
import json
import os
from pathlib import Path
import sys
from copy import deepcopy

from PyQt6.QtCore import QEvent, QObject, QPointF, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from chemvas.bootstrap.window_registry import open_new_window, open_windows
from chemvas.core.document_io import read_document
from chemvas.features.calculation_bundle import validate_calculation_plan
from chemvas.features.session import is_quit_pending, is_quitting
from chemvas.ui.app_data_paths import sessions_dir
from chemvas.ui.canvas_calculation_plan_state import calculation_plan_for
from chemvas.ui.main_window_ports import active_canvas_for_window, services_for_window
from chemvas.ui.session_recovery_service import SessionRecoveryService
from chemvas.ui.session_snapshot_store import new_session_store
from chemvas.ui.structure_mutation_access import add_bond_between_points_for, add_bond_for
from tests.test_calculation_plan import _document_state, _plan

root, mode = Path(sys.argv[1]), sys.argv[2]
answer_delay_ms = int(sys.argv[3])
app = QApplication([])
app.setApplicationName("Chemvas")
app.setOrganizationName("Chemvas")
windows = [open_new_window() for _ in range(3)]
first = active_canvas_for_window(windows[0])
state = _document_state()
state["calculation_plan"] = _plan()
validate_calculation_plan(state, state["calculation_plan"])
documents = services_for_window(windows[0]).canvas_document_service
documents.replace_canvas_with_state(windows[0], first, state=state, file_path=None)
for name, window in zip("abc", windows):
    if name != "a":
        add_bond_between_points_for(active_canvas_for_window(window), QPointF(0, 0), QPointF(40, 0))
    assert services_for_window(window).document_action_service.save_canvas_to_path(window, str(root / (name + ".chemvas")))
original_file = (root / "a.chemvas").read_bytes()
if mode == "untitled-discard":
    documents.set_file_path(first, None)
    documents.set_display_name(first, "Unsaved plan")
store = new_session_store(sessions_dir())
service = SessionRecoveryService(store, interval_ms=20)
service.start(app)
# A supported graph edit joins two planned components, making their references stale.
add_bond_for(first, 0, 2)
add_bond_between_points_for(active_canvas_for_window(windows[2]), QPointF(0, 80), QPointF(40, 80))
assert documents.is_dirty(first)
raw_plan = deepcopy(calculation_plan_for(first))
assert raw_plan is not None
assert service.snapshot_now() is False, "Regular autosave must still reject omitted plan data"
manifest_path = store.session_dir / "session.json"
before_snapshot = manifest_path.read_bytes()
before_history = first.services.history_service.capture_stack_snapshot()
answers = []
class Answer(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Show or not isinstance(obj, QMessageBox) or obj.property("answered"):
            return False
        obj.setProperty("answered", True)
        title = obj.windowTitle()
        if title == "Save Changes":
            first_prompt = not answers
            choice = QMessageBox.StandardButton.Save
            if first_prompt and mode not in {"save", "save-decline"}:
                choice = QMessageBox.StandardButton.Discard
            if not first_prompt and mode == "discard-cancel":
                choice = QMessageBox.StandardButton.Cancel
        elif title == "Calculation Plan Needs Attention":
            choice = QMessageBox.StandardButton.No if mode == "save-decline" else QMessageBox.StandardButton.Yes
        elif title == "Save Adjusted Document":
            choice = QMessageBox.StandardButton.Ok
        else:
            raise AssertionError((title, obj.text()))
        answers.append((title, choice.name))
        QTimer.singleShot(answer_delay_ms, lambda: obj.button(choice).click())
        return False
answer = Answer(app)
app.installEventFilter(answer)
cancelled = mode in {"discard-cancel", "save-decline", "failed-final-write"}
if mode == "failed-final-write":
    def fail_write(docs):
        raise OSError("injected final manifest failure")
    store.save_documents = fail_write
if cancelled:
    def check_cancel():
        assert open_windows() == tuple(windows)
        assert all(window.isVisible() and window.isEnabled() for window in windows)
        assert not is_quitting() and not is_quit_pending()
        assert documents.is_dirty(first)
        assert len(first.model.bonds) == 3
        assert calculation_plan_for(first) == raw_plan
        assert first.services.history_service.capture_stack_snapshot() == before_history
        assert manifest_path.read_bytes() == before_snapshot
        assert (root / "a.chemvas").read_bytes() == original_file
        print(json.dumps({"mode": mode, "cancelled_safely": True, "answers": answers}), flush=True)
        os._exit(0)

def request_quit():
    app.quit()
    if cancelled:
        # All nested confirmations must finish before cancellation assertions.
        QTimer.singleShot(0, check_cancel)
QTimer.singleShot(0, request_quit)
QTimer.singleShot(4000, lambda: os._exit(91))
assert app.exec() == 0
assert not cancelled, "Quit should have remained cancelled"
manifest = json.loads(manifest_path.read_text())
assert manifest["clean_exit"]
assert not open_windows()
expected = {"b.chemvas", "c.chemvas"} if mode == "untitled-discard" else {"a.chemvas", "b.chemvas", "c.chemvas"}
assert {Path(entry["file_path"]).name for entry in manifest["docs"]} == expected
assert all(not entry["dirty"] and entry["snapshot"] is None for entry in manifest["docs"])
assert len(read_document(root / "c.chemvas").state["model"]["bonds"]) == 2
if mode == "save":
    saved = read_document(root / "a.chemvas").state
    assert len(saved["model"]["bonds"]) == 3 and "calculation_plan" not in saved
else:
    assert (root / "a.chemvas").read_bytes() == original_file
restored = new_session_store(sessions_dir()).consume_previous_sessions()
assert {Path(doc.file_path).name for doc in restored.docs} == expected
assert restored.recovered_unsaved == 0
print(json.dumps({"mode": mode, "reopened_paths": sorted(expected), "answers": answers,
                  "original_hash": hashlib.sha256(original_file).hexdigest()}), flush=True)
"""


@pytest.mark.parametrize(
    ("mode", "answer_delay_ms"),
    [
        ("discard", 50),
        ("untitled-discard", 50),
        ("discard-cancel", 50),
        ("save", 50),
        ("save-decline", 50),
        ("failed-final-write", 50),
        pytest.param("discard-cancel", 700, id="slow-discard-cancel"),
    ],
)
def test_quit_respects_close_decisions_for_a_stale_plan(
    tmp_path, mode, answer_delay_ms
):
    environment = os.environ.copy()
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        environment[key] = str(tmp_path / key.lower())
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            STALE_PLAN_SCRIPT,
            str(tmp_path),
            mode,
            str(answer_delay_ms),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode == 0, result.stdout + result.stderr
