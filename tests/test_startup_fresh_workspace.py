import subprocess
import sys
import textwrap

import pytest

from tests.subprocess_support import source_subprocess_env


@pytest.mark.parametrize("mode", ["icon", "argv", "file-event"])
def test_desktop_launch_never_reopens_previous_documents(tmp_path, mode):
    script = textwrap.dedent("""
        import sys
        from pathlib import Path
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication
        from chemvas.ui import app_data_paths, session_snapshot_store
        from chemvas.features.document_composition import compose_document_state
        from chemvas.core.document_io import write_document
        from chemvas.domain.document import CANVAS_FILE_VERSION
        from chemvas.adapters.qt import FileOpenEventFilter
        from chemvas.features.session import DocDescriptor, request_snapshot
        from chemvas.bootstrap.window_registry import open_windows
        from chemvas.ui.main_window_ports import active_canvas_for_window
        from chemvas.ui.canvas_scene_items_state import note_items_for
        from chemvas.ui.session_snapshot_store import SessionSnapshotStore
        root=Path(sys.argv[1]); mode=sys.argv[2]
        app_data_paths._candidate_dirs=lambda:[root/'app-data']
        session_snapshot_store._pid_alive=lambda pid:False
        def state(text):
            return compose_document_state({'format':'chemvas-document-composition','version':1,'atoms':[],'bonds':[], 'notes':[{'text':text,'x':0,'y':0}]})
        target=root/'requested.chemvas'
        write_document(target,state('requested'),CANVAS_FILE_VERSION)
        previous_path=root/'previous.chemvas'
        write_document(previous_path,state('previous'),CANVAS_FILE_VERSION)
        old_roots=[]
        for name,clean in [('clean',True),('crash',False)]:
            store=SessionSnapshotStore(app_data_paths.sessions_dir(),session_id=name,pid=123456789)
            store.begin()
            store.save_documents([DocDescriptor(state=state(name),file_path=str(previous_path) if clean else None,display_name=name,dirty=not clean)])
            if clean:store.mark_clean_exit()
            old_roots.append(store.session_dir)
        def old_bytes():
            return {str(p):p.read_bytes() for d in old_roots for p in d.rglob('*') if p.is_file()}
        before=old_bytes()
        def execute(app):
            assert 'not opened automatically' in open_windows()[0].statusBar().currentMessage()
            if mode=='file-event':
                class FileEvent(QEvent):
                    def __init__(self):super().__init__(QEvent.Type.FileOpen)
                    def file(self):return str(target)
                event_filter=next(f for f in app.children() if isinstance(f,FileOpenEventFilter))
                assert event_filter.eventFilter(app,FileEvent())
            app.processEvents()
            windows=open_windows()
            assert len(windows)==1,len(windows)
            canvas=active_canvas_for_window(windows[0])
            texts=[n.toPlainText() for n in note_items_for(canvas)]
            assert texts==([] if mode=='icon' else ['requested']),texts
            request_snapshot()
            app.aboutToQuit.emit()
            assert old_bytes()==before
            for window in windows:
                window.close_after_confirmation()
            app.processEvents()
            app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            print('FRESH_START_AND_RETAINED_SNAPSHOTS_PASS',flush=True)
            return 0
        QApplication.exec=execute
        sys.argv=['chemvas',str(target)] if mode=='argv' else ['chemvas']
        from chemvas.bootstrap.application import main
        main()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), mode],
        env=source_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRESH_START_AND_RETAINED_SNAPSHOTS_PASS" in result.stdout
