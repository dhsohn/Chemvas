from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_chemvas_app_data(tmp_path_factory, monkeypatch):
    """Redirect Chemvas's writable app-data dir (recent files, autosave
    snapshots) to a throwaway per-test location.

    Saving/opening now records recent files and autosaves snapshots under
    ``QStandardPaths.AppDataLocation``. Patching the single ``app_data_dir()``
    source keeps every test from reading or writing the real user profile, and
    isolates tests from each other.
    """
    try:
        from ui import app_data_paths
    except ModuleNotFoundError:
        yield
        return
    base = tmp_path_factory.mktemp("chemvas_app_data")
    monkeypatch.setattr(app_data_paths, "app_data_dir", lambda: base)
    yield


@pytest.fixture(autouse=True)
def _reset_chemvas_window_registry():
    """Keep the app-level window registry from leaking between tests.

    Chemvas is single-document-per-window; "new canvas" / "open" spawn windows
    tracked in a module-level registry. Reset it around every test so a window
    one test opens cannot influence another.
    """
    try:
        from ui.main_window_app import reset_window_registry
    except ModuleNotFoundError:
        yield
        return
    reset_window_registry()
    yield
    reset_window_registry()
