from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, NoReturn

from chemvas import __version__
from chemvas.ui.main_window_path_logic import is_desktop_document_path

if TYPE_CHECKING:
    from collections.abc import Iterator

IGNORED_STDERR_SUBSTRINGS = (
    "TSM AdjustCapsLockLEDForKeyTransitionHandling",
    "error messaging the mach port for IMKCFRunLoopWakeUpReliable",
    "qt.qpa.keymapper: Mismatch between Cocoa",
    # Qt's Wayland backend (e.g. WSLg) warns on every non-popup mouse grab —
    # opening any menu prints this once or twice. Harmless and unactionable.
    "This plugin supports grabbing the mouse only for popup windows",
)

DOCUMENT_PATCH_COMMANDS = frozenset(("apply-patch", "inspect-document"))
DOCUMENT_COMPOSITION_COMMANDS = frozenset(("compose-document",))
DOCUMENT_LAYOUT_COMMANDS = frozenset(("check-layout",))
SCHEME_LAYOUT_COMMANDS = frozenset(("layout-document",))
DOCUMENT_TEMPLATE_COMMANDS = frozenset(("insert-template",))
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
    ("insert-template", "insert a native ring template in a new document"),
    ("layout-document", "align structure blocks and captions in a new document"),
    ("pack-step", "create one elementary-step JSON artifact"),
    ("render-document", "render a document to SVG, PNG or PDF"),
    ("select-precomplex", "review and select a precomplex endpoint pair"),
)


def _should_filter_stderr(platform: str | None = None) -> bool:
    return (platform or sys.platform) in {"darwin", "linux"}


def _startup_document_path(argv: list[str]) -> str | None:
    for argument in argv[1:]:
        if argument.startswith("-"):
            continue
        if is_desktop_document_path(argument):
            return argument
    return None


def _root_help() -> str:
    command_help = "\n".join(
        f"  {command:<18} {description}"
        for command, description in HEADLESS_SUBCOMMAND_HELP
    )
    return (
        "Usage:\n"
        "  chemvas [document]\n"
        "  chemvas <command> [options]\n\n"
        "Run with no arguments to launch the desktop app.\n"
        "Pass a .chemvas, .svg, or .mol document to open it at startup.\n\n"
        "Options:\n"
        "  -h, --help         show this help message and exit\n"
        "  --version          show version and exit\n\n"
        f"Headless commands:\n{command_help}\n"
    )


def _windows_console_notice(error: str = "") -> NoReturn:
    from PyQt6.QtWidgets import QApplication, QMessageBox

    console_notice_app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.information(
        None,
        "Chemvas command line",
        error + "Use chemvas-cli.exe for command-line options and document commands.\n"
        "Use chemvas.exe to draw or open a document.",
    )
    # Keep the application alive until the modal notice has closed.
    del console_notice_app
    raise SystemExit(2)


def _reject_startup_argument(argument: str) -> NoReturn:
    message = (
        f"chemvas: error: unrecognized argument: {argument}\n"
        "Run 'chemvas --help' for supported commands and document types.\n"
    )
    if sys.platform == "win32" and sys.stdout is None:
        _windows_console_notice(message)
    sys.stderr.write(message)
    raise SystemExit(2)


def _validate_desktop_arguments(arguments: list[str]) -> None:
    """Reject CLI mistakes before loading Qt, preserving documented Qt options."""
    # QApplication/QGuiApplication consume these options themselves. Validate
    # their shape here, but pass the original Unicode argv through unchanged.
    value_options = {
        "-platform",
        "-platformpluginpath",
        "-platformtheme",
        "-plugin",
        "-qwindowgeometry",
        "-qwindowicon",
        "-qwindowtitle",
        "-session",
        "-display",
        "-geometry",
        "-style",
        "-stylesheet",
    }
    flag_options = {"-reverse", "-widgetcount"}
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        option = argument[1:] if argument.startswith("--") else argument
        if not argument.startswith("-") and is_desktop_document_path(argument):
            index += 1
        elif option in flag_options:
            index += 1
        elif option in value_options:
            if index + 1 >= len(arguments) or (
                arguments[index + 1].startswith("-")
                and option not in {"-qwindowgeometry", "-geometry", "-qwindowtitle"}
            ):
                _reject_startup_argument(argument)
            index += 2
        elif any(
            option.startswith(prefix) and len(option) > len(prefix)
            for prefix in ("-style=", "-stylesheet=", "-qmljsdebugger=")
        ):
            index += 1
        else:
            _reject_startup_argument(argument)


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
    # The Windows GUI bootloader has no standard streams. Keep command-line
    # operations on the console companion rather than losing their reports.
    if (
        sys.platform == "win32"
        and sys.stdout is None
        and len(sys.argv) > 1
        and sys.argv[1]
        in {"-h", "--help", "--version", *dict(HEADLESS_SUBCOMMAND_HELP)}
    ):
        _windows_console_notice()

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

    if len(sys.argv) > 1 and sys.argv[1] in SCHEME_LAYOUT_COMMANDS:
        from chemvas.bootstrap.document_layout import run

        with _filtered_stderr():
            result = run(sys.argv[1:])
        raise SystemExit(result)

    if len(sys.argv) > 1 and sys.argv[1] in DOCUMENT_TEMPLATE_COMMANDS:
        from chemvas.bootstrap.document_template import run

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

    _validate_desktop_arguments(sys.argv[1:])

    with _filtered_stderr():
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication

        from chemvas.adapters.macos_app_identity import apply_macos_app_name
        from chemvas.adapters.qt import FileOpenEventFilter
        from chemvas.bootstrap.file_open import open_document
        from chemvas.bootstrap.window_registry import open_new_window
        from chemvas.branding import APP_NAME, APP_VERSION, app_icon

        # Must precede QApplication: Qt reads the macOS application name once,
        # while it builds the Cocoa menu bar.
        apply_macos_app_name(APP_NAME)

        # A document's point-sized text must keep the same size relative to its
        # scene-unit bonds on 72-DPI (Cocoa) and 96-DPI displays. Qt still handles
        # device-pixel-ratio scaling; only the points-to-scene-pixels rule is fixed.
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_Use96Dpi)
        app = QApplication(sys.argv)
        # PyQt removes Qt options from the supplied Python list. Keep its Unicode
        # strings: Qt's arguments() can recode document paths on Windows.
        desktop_arguments = list(sys.argv)
        for argument in desktop_arguments[1:]:
            if argument.startswith("-") or not is_desktop_document_path(argument):
                _reject_startup_argument(argument)
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_NAME)
        app.setApplicationVersion(APP_VERSION)
        app.setOrganizationName(APP_NAME)
        app.setDesktopFileName("chemvas")
        app.setWindowIcon(app_icon())

        file_open_filter = FileOpenEventFilter(open_document, parent=app)
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
        startup_document_path = _startup_document_path(desktop_arguments)
        if startup_document_path is not None:
            open_document(startup_document_path)
        recovery.start(app)
        # Import RDKit off the GUI thread while the app is idle at startup;
        # otherwise the first selection or 3D preview pays the import as a
        # freeze mid-interaction.
        from chemvas.core.rdkit_adapter import warm_rdkit_in_background

        warm_rdkit_in_background()
        app.exec()
