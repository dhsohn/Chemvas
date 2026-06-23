from __future__ import annotations

import pytest


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
