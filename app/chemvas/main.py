from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

IGNORED_STDERR_SUBSTRINGS = (
    "TSM AdjustCapsLockLEDForKeyTransitionHandling",
    "error messaging the mach port for IMKCFRunLoopWakeUpReliable",
    "qt.qpa.keymapper: Mismatch between Cocoa",
)

STARTUP_DOCUMENT_SUFFIXES = frozenset((".chemvas", ".json", ".svg"))


def _should_filter_stderr(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def _startup_document_path(argv: list[str]) -> str | None:
    for argument in argv[1:]:
        if argument.startswith("-"):
            continue
        if Path(argument).suffix.lower() in STARTUP_DOCUMENT_SUFFIXES:
            return argument
    return None


def _stderr_filter_loop(
    read_fd: int,
    write_fd: int,
    ignored_substrings: tuple[str, ...] = IGNORED_STDERR_SUBSTRINGS,
) -> None:
    with os.fdopen(read_fd, "r", buffering=1) as reader, os.fdopen(write_fd, "w", buffering=1) as writer:
        for line in reader:
            if any(fragment in line for fragment in ignored_substrings):
                continue
            writer.write(line)
            writer.flush()


@contextmanager
def _filtered_stderr(stderr_fd: int = 2, platform: str | None = None) -> Iterator[None]:
    if not _should_filter_stderr(platform):
        yield
        return

    restore_stderr_fd = os.dup(stderr_fd)
    forward_stderr_fd = os.dup(stderr_fd)
    read_fd, write_fd = os.pipe()
    thread = threading.Thread(target=_stderr_filter_loop, args=(read_fd, forward_stderr_fd), daemon=True)
    os.dup2(write_fd, stderr_fd)
    os.close(write_fd)
    thread.start()
    try:
        yield
    finally:
        os.dup2(restore_stderr_fd, stderr_fd)
        os.close(restore_stderr_fd)
        thread.join(timeout=1.0)


def main() -> None:
    with _filtered_stderr():
        from PyQt6.QtWidgets import QApplication
        from ui.main_window_app import open_new_window

        from chemvas.branding import APP_NAME, APP_VERSION, app_icon
        from chemvas.file_open import FileOpenEventFilter, open_document

        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName(APP_NAME)
        app.setDesktopFileName("chemvas")
        app.setWindowIcon(app_icon())

        file_open_filter = FileOpenEventFilter(open_document)
        app.installEventFilter(file_open_filter)

        from ui.session_recovery_service import create_session_recovery_service

        window = open_new_window()
        recovery = create_session_recovery_service()
        startup_document_path = _startup_document_path(sys.argv)
        if startup_document_path is not None:
            # An explicit file (e.g. a double-clicked document) wins; skip
            # auto-restore so the user gets exactly what they asked for.
            from ui.main_window_ports import services_for_window

            services_for_window(window).document_action_service.load_canvas_from_path(window, startup_document_path)
        else:
            recovery.restore_previous(window)
        recovery.start(app)
        app.exec()
