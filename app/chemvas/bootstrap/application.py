from __future__ import annotations

import os
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from chemvas import __version__

IGNORED_STDERR_SUBSTRINGS = (
    "TSM AdjustCapsLockLEDForKeyTransitionHandling",
    "error messaging the mach port for IMKCFRunLoopWakeUpReliable",
    "qt.qpa.keymapper: Mismatch between Cocoa",
    # Qt's Wayland backend (e.g. WSLg) warns on every non-popup mouse grab —
    # opening any menu prints this once or twice. Harmless and unactionable.
    "This plugin supports grabbing the mouse only for popup windows",
)

STARTUP_DOCUMENT_SUFFIXES = frozenset((".chemvas", ".svg"))
DOCUMENT_PATCH_COMMANDS = frozenset(("apply-patch", "inspect-document"))
DOCUMENT_COMPOSITION_COMMANDS = frozenset(("compose-document",))
DOCUMENT_LAYOUT_COMMANDS = frozenset(("check-layout",))
DOCUMENT_RENDER_COMMANDS = frozenset(("render-document",))
CALCULATION_BUNDLE_COMMANDS = frozenset(
    (
        "attach-plan",
        "generate-precomplex",
        "inspect",
        "inspect-plan",
        "inspect-precomplex",
        "pack-step",
        "select-precomplex",
    )
)
HEADLESS_SUBCOMMAND_HELP = (
    ("apply-patch", "validate or apply a Chemvas graph patch"),
    ("attach-plan", "embed a calculation plan in a new document"),
    ("compose-document", "create a Chemvas document from a strict composition"),
    ("check-layout", "report deterministic layout collisions without editing"),
    ("generate-precomplex", "generate bounded endpoint precomplex candidates"),
    ("inspect", "inspect connected structures as JSON"),
    ("inspect-document", "inspect the complete chemical graph as JSON"),
    ("inspect-plan", "inspect embedded calculation states and steps"),
    ("inspect-precomplex", "inspect persisted candidate XYZ and provenance"),
    ("pack-step", "create one elementary-step JSON artifact"),
    ("render-document", "render a document to SVG or PNG"),
    ("select-precomplex", "review and select a precomplex endpoint pair"),
)
HEADLESS_SUBCOMMANDS = tuple(command for command, _help in HEADLESS_SUBCOMMAND_HELP)


def _should_filter_stderr(platform: str | None = None) -> bool:
    return (platform or sys.platform) in {"darwin", "linux"}


def _startup_document_path(argv: list[str]) -> str | None:
    for argument in argv[1:]:
        if argument.startswith("-"):
            continue
        if Path(argument).suffix.lower() in STARTUP_DOCUMENT_SUFFIXES:
            return argument
    return None


def _root_help() -> str:
    command_help = "\n".join(
        f"  {command:<18} {description}"
        for command, description in HEADLESS_SUBCOMMAND_HELP
    )
    return (
        "Usage:\n"
        "  chemvas\n"
        "  chemvas <command> [options]\n\n"
        "Run with no arguments to launch the desktop app.\n\n"
        "Options:\n"
        "  -h, --help         show this help message and exit\n"
        "  --version          show version and exit\n\n"
        f"Headless commands:\n{command_help}\n"
    )


def _stderr_filter_loop(
    read_fd: int,
    write_fd: int,
    ignored_substrings: tuple[str, ...] = IGNORED_STDERR_SUBSTRINGS,
) -> None:
    with (
        os.fdopen(read_fd, "r", buffering=1) as reader,
        os.fdopen(write_fd, "w", buffering=1) as writer,
    ):
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
    thread = threading.Thread(
        target=_stderr_filter_loop, args=(read_fd, forward_stderr_fd), daemon=True
    )
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
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
        sys.stdout.write(_root_help())
        raise SystemExit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        sys.stdout.write(f"chemvas {__version__}\n")
        raise SystemExit(0)

    if len(sys.argv) > 1 and sys.argv[1] in DOCUMENT_COMPOSITION_COMMANDS:
        from chemvas.bootstrap.document_composition import run

        raise SystemExit(run(sys.argv[1:]))

    if len(sys.argv) > 1 and sys.argv[1] in DOCUMENT_LAYOUT_COMMANDS:
        from chemvas.bootstrap.document_layout_check import run

        with _filtered_stderr():
            result = run(sys.argv[1:])
        raise SystemExit(result)

    if len(sys.argv) > 1 and sys.argv[1] in DOCUMENT_PATCH_COMMANDS:
        from chemvas.bootstrap.document_patch import run

        raise SystemExit(run(sys.argv[1:]))

    if len(sys.argv) > 1 and sys.argv[1] in DOCUMENT_RENDER_COMMANDS:
        from chemvas.bootstrap.document_render import run

        with _filtered_stderr():
            result = run(sys.argv[1:])
        raise SystemExit(result)

    if len(sys.argv) > 1 and sys.argv[1] in CALCULATION_BUNDLE_COMMANDS:
        from chemvas.bootstrap.calculation_bundle import run

        raise SystemExit(run(sys.argv[1:]))

    with _filtered_stderr():
        from PyQt6.QtWidgets import QApplication

        from chemvas.adapters.macos_app_identity import apply_macos_app_name
        from chemvas.adapters.qt import FileOpenEventFilter
        from chemvas.bootstrap.file_open import open_document
        from chemvas.bootstrap.window_registry import open_new_window
        from chemvas.branding import APP_NAME, APP_VERSION, app_icon

        # Must precede QApplication: Qt reads the macOS application name once,
        # while it builds the Cocoa menu bar.
        apply_macos_app_name(APP_NAME)

        app = QApplication(sys.argv)
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName(APP_NAME)
        app.setDesktopFileName("chemvas")
        app.setWindowIcon(app_icon())

        file_open_filter = FileOpenEventFilter(open_document)
        app.installEventFilter(file_open_filter)

        from chemvas.ui.session_recovery_service import create_session_recovery_service

        window = open_new_window()
        recovery = create_session_recovery_service()
        # Auto-restore the previous session (recovered crash work + last
        # workspace) on every launch, then open any explicitly-requested file the
        # same way a macOS double-click does — through open_document, which
        # reuses a blank window or opens its own and, via the duplicate-open
        # guard, switches to the file if the restore already reopened it. Both
        # the argv and the QEvent.FileOpen paths therefore behave identically.
        recovery.restore_previous(window)
        startup_document_path = _startup_document_path(sys.argv)
        if startup_document_path is not None:
            open_document(startup_document_path)
        recovery.start(app)
        # Import RDKit off the GUI thread while the app is idle at startup;
        # otherwise the first selection or 3D preview pays the import as a
        # freeze mid-interaction.
        from chemvas.core.rdkit_adapter import warm_rdkit_in_background

        warm_rdkit_in_background()
        app.exec()
