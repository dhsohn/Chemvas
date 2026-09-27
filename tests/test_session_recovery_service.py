from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest import mock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QMessageBox

from chemvas.bootstrap.window_registry import open_new_window
from chemvas.features.session import (
    DocDescriptor,
    RestoredDoc,
    WithheldDoc,
    is_quitting,
)
from chemvas.shell.window_registry import forget_window, open_windows
from chemvas.ui.canvas.canvas_document_metadata_state import (
    CanvasDocumentMetadataState,
    canonical_document_digest,
)
from chemvas.ui.molecule.structure_mutation_access import add_bond_between_points_for
from chemvas.ui.session.session_recovery_service import (
    SessionRecoveryService,
    collect_open_documents,
)
from chemvas.ui.session.session_snapshot_store import (
    RestoreResult,
    SessionSnapshotStore,
)
from chemvas.ui.window.main_window_ports import active_canvas_for_window
from tests.calculation_plan_support import _document_state, _plan
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state
from tests.subprocess_support import source_subprocess_env


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeStatusBar:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int]] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append((message, timeout))


class _FakeWindow:
    def __init__(self, name: str) -> None:
        self.name = name
        self._status_bar = _FakeStatusBar()
        self.closed = False

    def statusBar(self) -> _FakeStatusBar:
        return self._status_bar

    def close_after_confirmation(self) -> None:
        self.closed = True


class _FakeDocService:
    def __init__(self) -> None:
        self.opened: list = []
        self.dirtied: list = []
        self.refreshed: list = []
        self.reusable = True

    def reusable_open_target(self, window):
        if not self.reusable:
            return None
        # The blank canvas a new window opens with.
        return SimpleNamespace(
            runtime_state=canvas_runtime_state(
                document_metadata_state=CanvasDocumentMetadataState(
                    display_name="Canvas 1"
                )
            )
        )

    def open_state(self, window, *, state, file_path, display_name=None):
        canvas = SimpleNamespace(
            window=window, state=state, file_path=file_path, display_name=display_name
        )
        self.opened.append(canvas)
        return canvas

    def mark_dirty(self, canvas) -> None:
        self.dirtied.append(canvas)

    def refresh_tab_title(self, window, canvas) -> None:
        self.refreshed.append((window, canvas))


class _FakeStore:
    def __init__(self, result: RestoreResult) -> None:
        self._result = result
        self.begun = False
        self.saved: list = []
        self.released: list = []
        self.clean_exit = False
        self.events: list[str] = []

    def consume_previous_sessions(self) -> RestoreResult:
        return self._result

    def begin(self) -> None:
        self.begun = True
        self.events.append("begin")

    def save_documents(self, docs) -> None:
        self.saved.append(docs)
        self.events.append("save")

    def release_sessions(self, release) -> None:
        self.released.append(dict(release))
        self.events.append("release")

    def mark_clean_exit(self) -> None:
        self.clean_exit = True


class _FakeSignal:
    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)


def _service(
    store,
    *,
    extra_windows=None,
    current_documents=list,
    open_windows=lambda: (),
    status_service=None,
):
    doc_service = _FakeDocService()
    services = SimpleNamespace(
        canvas_document_service=doc_service,
        status_service=status_service or mock.Mock(),
    )
    spawned = list(extra_windows or [])
    service = SessionRecoveryService(
        store,
        open_new_window=lambda reference: spawned.pop(0),
        open_windows=open_windows,
        services_for_window=lambda window: services,
        current_documents=current_documents,
    )
    return service, doc_service


def test_recovery_warning_survives_successful_new_session_snapshot():
    first = _FakeWindow("first")
    warning = "An unreadable recovery snapshot was retained."
    store = _FakeStore(RestoreResult(warnings=[warning]))
    status = mock.Mock()
    service, _ = _service(
        store,
        open_windows=lambda: [first],
        status_service=status,
    )

    service.restore_previous(first)
    assert service.snapshot_now()

    status.set_recovery_notice.assert_called_with(first, warning)
    with mock.patch.object(store, "save_documents", side_effect=OSError("disk full")):
        assert not service.snapshot_now()
    message = status.set_autosave_error.call_args.args[1]
    assert warning not in message
    assert "disk full" in message
    assert service.snapshot_now()
    status.set_recovery_notice.assert_called_with(first, warning)


def test_quit_stops_if_windows_change_during_confirmation():
    from chemvas.features.session import is_quit_pending, is_quitting

    first = _FakeWindow("first")
    windows = [first]
    status = mock.Mock()
    store = _FakeStore(RestoreResult())

    def confirm(_window):
        windows.append(_FakeWindow("unexpected"))
        return True

    service = SessionRecoveryService(
        store,
        open_new_window=lambda reference=None: None,
        open_windows=lambda: tuple(windows),
        services_for_window=lambda _window: SimpleNamespace(
            document_action_service=SimpleNamespace(confirm_close_window=confirm),
            status_service=status,
        ),
    )
    assert service.intercept_application_quit()
    assert len(windows) == 2
    assert not is_quit_pending() and not is_quitting()
    assert not service._closing_application
    assert not store.saved
    assert "open windows changed" in status.set_quit_notice.call_args.args[1]


def test_quit_finishes_when_recovered_originals_cannot_be_removed():
    from chemvas.features.session import is_quitting

    first = _FakeWindow("first")
    first.tab_references = SimpleNamespace(all_canvases=list)
    first.setEnabled = mock.Mock()
    status = mock.Mock()
    store = _FakeStore(
        RestoreResult(docs=[RestoredDoc({}, None, "Draft", True)], release={"old": ()})
    )
    services = SimpleNamespace(
        canvas_document_service=_FakeDocService(),
        document_action_service=SimpleNamespace(confirm_close_window=lambda _w: True),
        status_service=status,
    )
    service = SessionRecoveryService(
        store,
        open_new_window=lambda reference=None: None,
        open_windows=lambda: (first,),
        services_for_window=lambda _window: services,
        current_documents=list,
    )
    unrecognized = ValueError(
        "Recovery directory contains unrecognized files: old. "
        "Its contents have been kept."
    )

    with mock.patch.object(store, "release_sessions", side_effect=unrecognized):
        assert service.restore_previous(first) == 1
        assert service.intercept_application_quit()

    assert is_quitting()
    assert first.closed
    assert not store.released
    status.set_autosave_error.assert_called_with(first, None)
    assert "unrecognized files" in status.set_recovery_notice.call_args.args[1]


def test_start_leaves_recovery_guidance_to_the_persistent_notice(qapp):
    first = _FakeWindow("first")
    status = mock.Mock()
    warning = "Unsaved work is available."
    service = SessionRecoveryService(
        _FakeStore(RestoreResult()),
        open_new_window=lambda reference=None: None,
        open_windows=lambda: (first,),
        services_for_window=lambda _window: SimpleNamespace(status_service=status),
        current_documents=list,
        recovery_warnings=(warning,),
    )
    first.statusBar().showMessage("Already open: a.chemvas")

    service.start(SimpleNamespace(aboutToQuit=_FakeSignal()))

    status.set_recovery_notice.assert_called_with(first, warning)
    assert first.statusBar().messages == [("Already open: a.chemvas", 0)]
    service._timer.stop()


def test_alternate_recovery_warning_has_a_safe_action_and_survives_autosave(
    tmp_path, monkeypatch, qapp
):
    from chemvas.ui.session import session_recovery_service as module

    primary = tmp_path / "primary"
    alternate = tmp_path / "fallback"
    previous = alternate / "previous"
    primary_store = _FakeStore(RestoreResult())
    primary_store.prune_completed_sessions = mock.Mock()
    primary_store.unrestored_snapshot_directories = mock.Mock(return_value=[])
    alternate_store = mock.Mock()
    alternate_store.unrestored_snapshot_directories.return_value = [previous]
    monkeypatch.setattr(module, "sessions_dir", lambda: primary)
    monkeypatch.setattr(module, "existing_session_roots", lambda: (primary, alternate))
    monkeypatch.setattr(
        module,
        "new_session_store",
        lambda root: primary_store if root == primary else alternate_store,
    )
    service = module.create_session_recovery_service(
        open_new_window=lambda reference=None: None
    )
    first = _FakeWindow("first")
    status = mock.Mock()
    service._open_windows = lambda: (first,)
    service._services_for_window = lambda window: SimpleNamespace(status_service=status)
    service._current_documents = list

    service.start(SimpleNamespace(aboutToQuit=_FakeSignal()))
    assert service.snapshot_now()
    message = status.set_recovery_notice.call_args.args[1]
    assert "Recover Unsaved Work" in message
    status.set_autosave_error.assert_called_with(first, None)
    alternate_store.consume_previous_sessions.assert_not_called()
    alternate_store.release_sessions.assert_not_called()
    alternate_store.begin.assert_not_called()
    service._timer.stop()


def test_restored_untitled_names_are_reserved_and_windows_cascade_from_previous():
    from chemvas.shell.window_registry import next_document_name

    first, second, third = (_FakeWindow(name) for name in ("first", "second", "third"))
    result = RestoreResult(
        docs=[
            RestoredDoc({}, None, "Canvas 6", True),
            RestoredDoc({}, None, "Canvas 6", True),
            RestoredDoc({}, None, "Canvas 2", True),
        ]
    )
    service, documents = _service(_FakeStore(result), extra_windows=[second, third])
    service._open_new_window = mock.Mock(side_effect=[second, third])

    service.restore_previous(first)

    restored_names = [canvas.display_name for canvas in documents.opened]
    new_names = [next_document_name() for _ in range(8)]
    assert len(set(restored_names + new_names)) == len(restored_names + new_names)
    assert service._open_new_window.call_args_list == [
        mock.call(first),
        mock.call(second),
    ]


def test_restore_previous_rebuilds_windows_and_marks_recovered_dirty():
    first = _FakeWindow("first")
    second = _FakeWindow("second")
    result = RestoreResult(
        docs=[
            RestoredDoc(
                state={"m": 1}, file_path=None, display_name="Canvas 1", dirty=True
            ),
            RestoredDoc(
                state={"m": 2},
                file_path="/a/x.chemvas",
                display_name="x.chemvas",
                dirty=True,
            ),
        ],
        recovered_unsaved=1,
    )
    service, doc_service = _service(_FakeStore(result), extra_windows=[second])

    recovered = service.restore_previous(first)

    assert recovered == 2
    # First doc reuses the first window; the second spawns a new one.
    assert [c.window for c in doc_service.opened] == [first, second]
    assert [c.display_name for c in doc_service.opened] == [
        "Canvas 1",
        "x.chemvas (recovered copy)",
    ]
    # Only the unsaved doc is forced dirty.
    assert doc_service.dirtied == doc_service.opened
    assert all(c.file_path is None for c in doc_service.opened)
    assert first.statusBar().messages
    assert "Recovered 2 unsaved documents" in first.statusBar().messages[0][0]


def test_restore_gives_each_doc_its_own_window_when_first_is_occupied():
    # e.g. a crash-recovery launch that also opened a startup file: the first
    # window is taken, so recovered docs must not pile up as tabs there.
    first = _FakeWindow("first")
    spawned = [_FakeWindow("w1"), _FakeWindow("w2")]
    result = RestoreResult(
        docs=[
            RestoredDoc(
                state={"m": 1}, file_path="/a.chemvas", display_name="a", dirty=True
            ),
            RestoredDoc(
                state={"m": 2}, file_path="/b.chemvas", display_name="b", dirty=True
            ),
        ]
    )
    service, doc_service = _service(_FakeStore(result), extra_windows=list(spawned))
    doc_service.reusable = False  # first window already holds a document

    service.restore_previous(first)

    assert [canvas.window for canvas in doc_service.opened] == spawned  # never `first`


def test_restore_previous_is_silent_when_nothing_to_recover():
    first = _FakeWindow("first")
    service, doc_service = _service(_FakeStore(RestoreResult()))

    assert service.restore_previous(first) == 0
    assert doc_service.opened == []
    assert first.statusBar().messages == []


def test_snapshot_now_persists_the_current_documents():
    sentinel = [object()]
    service, _ = _service(
        _FakeStore(RestoreResult()), current_documents=lambda: sentinel
    )

    service.snapshot_now()

    assert service._store.saved == [sentinel]


@pytest.mark.parametrize("dirty", [True, False])
def test_collect_open_documents_withholds_only_an_unsaved_warning_snapshot(dirty):
    warning = "The calculation plan was not saved because it is stale."
    state = {"model": {}}
    canvas = SimpleNamespace(
        services=canvas_runtime_services(
            canvas_document_session_service=SimpleNamespace(
                snapshot_state_with_warnings=mock.Mock(return_value=(state, [warning]))
            )
        ),
        runtime_state=canvas_runtime_state(
            document_metadata_state=CanvasDocumentMetadataState(
                display_name="Canvas 1",
                clean_digest="edited" if dirty else canonical_document_digest(state),
            )
        ),
    )
    window = SimpleNamespace(
        tab_references=SimpleNamespace(all_canvases=lambda: [canvas])
    )

    with mock.patch(
        "chemvas.ui.session.session_recovery_service.default_open_windows",
        return_value=(window,),
    ):
        documents = collect_open_documents()

    if dirty:
        assert documents == [
            WithheldDoc(key=canvas, display_name="Canvas 1", reason=warning)
        ]
    else:
        [saved] = documents
        assert isinstance(saved, DocDescriptor)
        assert saved.key is canvas and not saved.dirty


def test_collect_open_documents_does_not_skip_an_unwired_window():
    with (
        mock.patch(
            "chemvas.ui.session.session_recovery_service.default_open_windows",
            return_value=(object(),),
        ),
        pytest.raises(AttributeError, match="tab_references"),
    ):
        collect_open_documents()


def test_snapshot_now_swallows_store_errors_and_reports_failure():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("first")
    status_service = mock.Mock()

    def boom(_docs):
        raise RuntimeError("disk full")

    store.save_documents = boom  # type: ignore[method-assign]
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    assert service.snapshot_now() is False  # must not raise; reports the failure
    status_service.set_autosave_error.assert_called_once_with(
        window, "Autosave paused: disk full"
    )


def test_snapshot_error_publication_tolerates_a_destroyed_qt_window():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("destroyed")
    status_service = mock.Mock()
    status_service.set_autosave_error.side_effect = RuntimeError(
        "wrapped C/C++ object has been deleted"
    )
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    service._set_snapshot_error("Autosave paused: disk full")

    status_service.set_autosave_error.assert_called_once_with(
        window, "Autosave paused: disk full"
    )


def test_snapshot_error_publication_does_not_hide_wiring_errors():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("broken")
    status_service = mock.Mock()
    status_service.set_autosave_error.side_effect = RuntimeError(
        "status bar must be initialized before autosave status"
    )
    service, _ = _service(
        store,
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    with pytest.raises(RuntimeError, match="status bar must be initialized"):
        service._set_snapshot_error("Autosave paused: disk full")


def test_successful_retry_clears_the_persistent_snapshot_error():
    store = _FakeStore(RestoreResult())
    window = _FakeWindow("first")
    status_service = mock.Mock()
    attempts = 0

    def save_documents(docs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("disk full")
        store.saved.append(docs)

    store.save_documents = save_documents  # type: ignore[method-assign]
    service, _ = _service(
        store,
        current_documents=lambda: ["doc"],
        open_windows=lambda: (window,),
        status_service=status_service,
    )

    assert service.snapshot_now() is False
    assert store.saved == []
    assert service.snapshot_now() is True

    assert store.saved == [["doc"]]
    assert status_service.set_autosave_error.call_args_list == [
        mock.call(window, "Autosave paused: disk full"),
        mock.call(window, None),
    ]


def _mapped_drawing(window):
    """Open a drawing whose calculation plan maps its atoms, as saved from the
    Reaction Mapping panel."""
    canvas = active_canvas_for_window(window)
    state = _document_state()
    state["calculation_plan"] = _plan()
    canvas.services.canvas_document_session_service.apply_state(state)
    return canvas


def _break_mapping(canvas) -> None:
    """Delete a mapped bond, which leaves the plan's components behind."""
    bond = canvas.services.graph_service.bond_id_between(0, 1)
    canvas.services.scene_delete_controller.delete_bond(bond)


def _snapshot_files(store) -> dict[str, tuple[str, bytes]]:
    manifest = json.loads((store.session_dir / "session.json").read_bytes())
    return {
        entry["display_name"]: (
            entry["snapshot"],
            (store.session_dir / entry["snapshot"]).read_bytes(),
        )
        for entry in manifest["docs"]
    }


def _snapshot_state(store, name: str) -> dict:
    return json.loads(_snapshot_files(store)[name][1])["state"]


def _autosave_notice(window) -> str:
    return window.services.status_service.autosave_error_label.text()


def _close_windows(qt_application, service) -> None:
    if service._timer is not None:
        service._timer.stop()
    for window in open_windows():
        window.services.canvas_document_service.mark_clean(
            active_canvas_for_window(window)
        )
        forget_window(window)
        window.close()
    qt_application.processEvents()


def test_a_document_autosave_cannot_write_keeps_its_snapshot_without_pausing_others(
    qt_application, tmp_path
):
    mapped_window, other_window = open_new_window(), open_new_window()
    mapped = _mapped_drawing(mapped_window)
    other = active_canvas_for_window(other_window)
    add_bond_between_points_for(other, QPointF(0, 0), QPointF(40, 0))
    name = mapped.runtime_state.document_metadata_state.display_name
    other_name = other.runtime_state.document_metadata_state.display_name
    store = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service = SessionRecoveryService(store, open_new_window=open_new_window)
    try:
        service.start(SimpleNamespace())
        before = _snapshot_files(store)
        assert set(before) == {name, other_name}

        _break_mapping(mapped)
        mapped.runtime_state.tool_settings_state.arrow_line_width = 2.5
        add_bond_between_points_for(other, QPointF(0, 80), QPointF(40, 80))
        assert service.snapshot_now()

        # The other window's edit is saved; the mapped drawing keeps the file
        # its last complete snapshot wrote.
        assert _snapshot_files(store)[name] == before[name]
        assert len(_snapshot_state(store, other_name)["model"]["atoms"]) == 4
        for window in (mapped_window, other_window):
            notice = _autosave_notice(window)
            assert notice.startswith(
                f"Autosave skipped {name}: The calculation plan was not saved "
                "because the molecular graph no longer matches"
            ), notice
            assert notice.endswith(
                "Recovery keeps its last autosaved copy; edits made since are "
                "not recoverable until this is resolved."
            ), notice

        mapped.services.history_service.undo()
        assert service.snapshot_now()

        assert not _autosave_notice(mapped_window)
        assert not _autosave_notice(other_window)
        saved = _snapshot_state(store, name)
        assert saved["settings"]["arrow_line_width"] == 2.5
        assert saved["calculation_plan"] == _plan()
    finally:
        _close_windows(qt_application, service)


def test_saving_a_document_autosave_withholds_records_it_as_saved(
    qt_application, tmp_path
):
    window = open_new_window()
    mapped = _mapped_drawing(window)
    store = SessionSnapshotStore(tmp_path / "sessions", session_id="current", pid=1)
    service = SessionRecoveryService(store, open_new_window=open_new_window)
    try:
        service.start(SimpleNamespace())
        [(unsaved, _payload)] = _snapshot_files(store).values()
        _break_mapping(mapped)
        assert service.snapshot_now()
        assert _autosave_notice(window)

        path = tmp_path / "mapped.chemvas"
        message_box = mock.Mock()
        message_box.question.return_value = QMessageBox.StandardButton.Yes
        actions = window.services.document_action_service
        assert actions.save_canvas_to_path(window, str(path), message_box=message_box)
        assert service.snapshot_now()

        # The saved file omits the stale plan, which stays in memory.
        session = mapped.services.canvas_document_session_service
        assert session.snapshot_state_with_warnings()[1]
        assert not _autosave_notice(window)
        manifest = json.loads((store.session_dir / "session.json").read_bytes())
        assert manifest["docs"] == [
            {
                "file_path": str(path),
                "display_name": "mapped.chemvas",
                "dirty": False,
                "snapshot": None,
            }
        ]
        assert not (store.session_dir / unsaved).exists()
    finally:
        _close_windows(qt_application, service)


def test_quit_finishes_past_a_document_autosave_cannot_write(
    qt_application, tmp_path, monkeypatch
):
    mapped_window, other_window = open_new_window(), open_new_window()
    mapped = _mapped_drawing(mapped_window)
    _break_mapping(mapped)
    add_bond_between_points_for(
        active_canvas_for_window(other_window), QPointF(0, 0), QPointF(40, 0)
    )
    name = mapped.runtime_state.document_metadata_state.display_name
    store = SessionSnapshotStore(tmp_path, session_id="current", pid=4243)
    service = SessionRecoveryService(store, open_new_window=open_new_window)
    try:
        service.start(SimpleNamespace())
        # A new drawing has no earlier snapshot to keep.
        saved = _snapshot_files(store)
        assert name not in saved and len(saved) == 1
        notice = _autosave_notice(mapped_window)
        assert notice.startswith(f"Autosave skipped {name}: "), notice
        assert notice.endswith(
            "Recovery holds no copy of its unsaved edits until this is resolved."
        ), notice

        # A cancelled close prompt keeps every recovery file.
        monkeypatch.setattr(
            QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Cancel
        )
        assert service.intercept_application_quit()
        assert not is_quitting()
        assert _snapshot_files(store) == saved

        monkeypatch.setattr(
            QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Discard
        )
        assert service.intercept_application_quit()

        assert is_quitting()
        assert not open_windows()
        assert _snapshot_files(store) == {}
        assert not list(store.session_dir.glob("doc-*.json"))
    finally:
        _close_windows(qt_application, service)


def test_recovery_keeps_source_sessions_when_the_snapshot_fails(qapp):
    store = _FakeStore(RestoreResult(release={"old-1": ()}))
    service, _ = _service(store, current_documents=lambda: ["doc"])
    service.start(SimpleNamespace(aboutToQuit=_FakeSignal()))

    def boom(_docs):
        raise RuntimeError("disk full")

    store.save_documents = boom  # type: ignore[method-assign]
    service.restore_previous(_FakeWindow("first"))

    assert store.released == []  # a failed re-snapshot must not delete the sources
    service._timer.stop()


def test_start_begins_session_snapshots_and_arms_hooks(qapp):
    store = _FakeStore(RestoreResult())
    service, _ = _service(store, current_documents=lambda: ["doc"])
    fake_app = SimpleNamespace(aboutToQuit=_FakeSignal())

    service.start(fake_app)

    assert store.begun is True
    assert store.saved == [["doc"]]  # immediate snapshot after begin
    assert service._timer is not None and service._timer.isActive()
    assert fake_app.aboutToQuit.slots == [service._on_about_to_quit]
    service._timer.stop()


def test_production_qobject_owns_the_autosave_timer(qapp):
    store = _FakeStore(RestoreResult())
    service, _ = _service(store, current_documents=list)

    service.start(qapp)

    assert service._timer is not None
    assert service._timer.parent() is qapp
    service._timer.stop()


def test_last_window_close_marks_quitting_before_deferred_snapshot() -> None:
    script = textwrap.dedent(
        """
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtWidgets import QApplication, QWidget
        import weakref

        from chemvas.features.session import is_quitting, snapshot_unless_quitting
        from chemvas.ui.session.session_recovery_service import SessionRecoveryService

        class Store:
            def __init__(self):
                self.saves = 0
                self.clean_exit = False

            def begin(self):
                pass

            def save_documents(self, _docs):
                self.saves += 1

            def mark_clean_exit(self):
                self.clean_exit = True

        class ClosingWindow(QWidget):
            def closeEvent(self, event):
                events.append("close")
                QTimer.singleShot(0, deferred_snapshot)
                super().closeEvent(event)

        def deferred_snapshot():
            events.append(f"snapshot:{is_quitting()}")
            snapshot_unless_quitting()

        app = QApplication([])
        app_reference = weakref.ref(app)
        store = Store()
        events = []
        service = SessionRecoveryService(
            store,
            open_new_window=lambda reference=None: None,
            open_windows=tuple,
            current_documents=list,
        )
        service.start(app)
        window = ClosingWindow()
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        app.lastWindowClosed.connect(
            lambda: events.append(f"last:{is_quitting()}")
        )
        app.aboutToQuit.connect(
            lambda: events.append(f"about:{is_quitting()}")
        )
        window.show()
        QTimer.singleShot(0, window.close)
        exit_code = app.exec()
        print(events, store.saves, store.clean_exit, exit_code)
        assert "last:True" in events
        assert store.saves == 1
        assert store.clean_exit
        assert exit_code == 0
        del app
        assert app_reference() is None
        """
    )
    environment = source_subprocess_env()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=environment,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_consumed_sessions_are_released_only_after_resnapshot(qapp):
    # A crash mid-restore must not destroy the recovered work: the old source
    # sessions are deleted only after the copies are snapshotted into this one.
    store = _FakeStore(RestoreResult(release={"old-1": ("doc-1.json",), "old-2": ()}))
    service, _ = _service(store, current_documents=lambda: ["doc"])
    service.start(SimpleNamespace(aboutToQuit=_FakeSignal()))
    store.events.clear()

    service.restore_previous(_FakeWindow("first"))

    assert store.released == [{"old-1": ("doc-1.json",), "old-2": ()}]
    assert store.events == ["save", "release"]  # snapshot, then release
    service._timer.stop()


def test_consumed_sessions_are_released_after_a_successful_retry(qapp):
    store = _FakeStore(RestoreResult(release={"old-1": ()}))
    attempts = 0

    def save_documents(docs):
        nonlocal attempts
        attempts += 1
        store.events.append("save")
        if attempts == 2:  # the snapshot that hands off the recovered copies
            raise RuntimeError("disk full")
        store.saved.append(docs)

    store.save_documents = save_documents  # type: ignore[method-assign]
    service, _ = _service(store, current_documents=lambda: ["doc"])
    service.start(SimpleNamespace(aboutToQuit=_FakeSignal()))

    service.restore_previous(_FakeWindow("first"))
    assert store.released == []

    assert service.snapshot_now() is True
    assert store.released == [{"old-1": ()}]
    assert store.events[-2:] == ["save", "release"]
    service._timer.stop()


def test_about_to_quit_marks_the_session_clean():
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service._on_about_to_quit()

    assert store.clean_exit is True


def test_about_to_quit_sets_the_quitting_flag():
    from chemvas.features.session import autosave as session_autosave_hook

    session_autosave_hook.reset_quitting()
    store = _FakeStore(RestoreResult())
    service, _ = _service(store)

    service._on_about_to_quit()

    # So deferred window-close snapshots become no-ops and the open set is kept.
    assert session_autosave_hook.is_quitting() is True


def test_startup_retires_stopped_clean_sessions_in_every_recovery_root(
    tmp_path, monkeypatch
):
    from chemvas.ui.session import session_recovery_service as module
    from chemvas.ui.session import session_snapshot_store as store_module
    from chemvas.ui.session.session_snapshot_store import SessionSnapshotStore

    roots = (tmp_path / "primary", tmp_path / "fallback")
    retired = []
    for root in roots:
        previous = SessionSnapshotStore(root, session_id="clean", pid=4242)
        previous.begin()
        previous.mark_clean_exit()
        retired.append(previous.session_dir)
    monkeypatch.setattr(store_module, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(module, "sessions_dir", lambda: roots[0])
    monkeypatch.setattr(module, "existing_session_roots", lambda: roots)

    module.create_session_recovery_service(open_new_window=lambda reference=None: None)

    assert not any(directory.exists() for directory in retired)
