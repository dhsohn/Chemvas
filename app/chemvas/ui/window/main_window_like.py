"""The main window as ``ui`` code sees it: the shell window with its runtime typed.

``chemvas.shell.main_window.MainWindow`` is generic in the runtime classes
bootstrap supplies, because the shell cannot import ``ui``. This alias binds
those parameters once: ``ui`` code annotates its ``window`` parameters with
it and gets the concrete services, state and tab references plus every
``QMainWindow`` operation, and bootstrap instantiates it. Tests satisfy it
with fakes that carry the members they exercise.
"""

from __future__ import annotations

from typing import TypeAlias

from chemvas.shell.main_window import MainWindow
from chemvas.ui.preview3d.preview_3d import Preview3D
from chemvas.ui.window.main_window_service_types import MainWindowServices
from chemvas.ui.window.main_window_state import MainWindowState
from chemvas.ui.window.main_window_tab_references import MainWindowTabReferences
from chemvas.ui.window.main_window_ui_references import MainWindowUiReferences

# A runtime alias, not a ``type`` statement: bootstrap calls it to build the window.
MainWindowLike: TypeAlias = MainWindow[  # noqa: UP040
    MainWindowServices,
    MainWindowState,
    MainWindowTabReferences,
    MainWindowUiReferences,
    Preview3D,
]

__all__ = ["MainWindowLike"]
