import os
import runpy
import sys
import types
import unittest
from contextlib import contextmanager
from unittest import mock

import chemvas.branding
import chemvas.main as chemvas_main
import main as app_main
from chemvas.file_open import FileOpenEventFilter


class _QApplicationMetadataStub:
    """Records the app-surface calls main() makes on the QApplication.

    The real QApplication carries these; the fakes below mirror that surface so
    main()'s branding/identity and file-open wiring is exercised rather than
    raising.
    """

    def installEventFilter(self, event_filter: object) -> None:
        self.installed_event_filter = event_filter

    def setApplicationName(self, name: str) -> None:
        self.application_name = name

    def setApplicationDisplayName(self, name: str) -> None:
        self.application_display_name = name

    def setApplicationVersion(self, version: str) -> None:
        self.application_version = version

    def setOrganizationName(self, name: str) -> None:
        self.organization_name = name

    def setDesktopFileName(self, name: str) -> None:
        self.desktop_file_name = name

    def setWindowIcon(self, icon: object) -> None:
        self.window_icon = icon


class MainStderrFilterTest(unittest.TestCase):
    def test_app_main_reexports_chemvas_main_symbols(self) -> None:
        self.assertIs(app_main.IGNORED_STDERR_SUBSTRINGS, chemvas_main.IGNORED_STDERR_SUBSTRINGS)
        self.assertIs(app_main._filtered_stderr, chemvas_main._filtered_stderr)
        self.assertIs(app_main._should_filter_stderr, chemvas_main._should_filter_stderr)
        self.assertIs(app_main._stderr_filter_loop, chemvas_main._stderr_filter_loop)
        self.assertIs(app_main.main, chemvas_main.main)

    def _capture_stderr_output(self, platform: str, lines: list[str]) -> str:
        original_stderr_fd = os.dup(2)
        capture_read_fd, capture_write_fd = os.pipe()
        capture_read_closed = False
        try:
            os.dup2(capture_write_fd, 2)
            os.close(capture_write_fd)
            with app_main._filtered_stderr(platform=platform):
                for line in lines:
                    os.write(2, line.encode("utf-8"))
            os.dup2(original_stderr_fd, 2)
            with os.fdopen(capture_read_fd, "r", encoding="utf-8") as capture_reader:
                output = capture_reader.read()
            capture_read_closed = True
            return output
        finally:
            os.dup2(original_stderr_fd, 2)
            os.close(original_stderr_fd)
            if not capture_read_closed:
                os.close(capture_read_fd)

    def test_filtered_stderr_suppresses_known_macos_noise(self) -> None:
        output = self._capture_stderr_output(
            platform="darwin",
            lines=[
                "visible line\n",
                "TSM AdjustCapsLockLEDForKeyTransitionHandling noise\n",
                "second visible line\n",
            ],
        )

        self.assertIn("visible line", output)
        self.assertIn("second visible line", output)
        self.assertNotIn("TSM AdjustCapsLockLEDForKeyTransitionHandling", output)

    def test_filtered_stderr_is_noop_outside_macos(self) -> None:
        output = self._capture_stderr_output(
            platform="linux",
            lines=["qt.qpa.keymapper: Mismatch between Cocoa should remain visible\n"],
        )

        self.assertIn("qt.qpa.keymapper: Mismatch between Cocoa should remain visible", output)

    def test_should_filter_stderr_uses_current_platform_by_default(self) -> None:
        with mock.patch.object(chemvas_main.sys, "platform", "darwin"):
            self.assertTrue(app_main._should_filter_stderr())
        with mock.patch.object(chemvas_main.sys, "platform", "linux"):
            self.assertFalse(app_main._should_filter_stderr())

    def test_main_constructs_window_and_executes_application(self) -> None:
        events: list[tuple[str, object]] = []

        class FakeApplication(_QApplicationMetadataStub):
            instances: list["FakeApplication"] = []

            def __init__(self, args) -> None:
                self.args = args
                self.exec_called = False
                FakeApplication.instances.append(self)

            def exec(self) -> None:
                self.exec_called = True
                events.append(("exec", self.args))

        class FakeMainWindow:
            instances: list["FakeMainWindow"] = []

            def __init__(self) -> None:
                self.shown = False
                FakeMainWindow.instances.append(self)

            def show(self) -> None:
                self.shown = True
                events.append(("show", None))

        qt_widgets_module = types.ModuleType("PyQt6.QtWidgets")
        qt_widgets_module.QApplication = FakeApplication
        main_window_module = types.ModuleType("ui.main_window")
        main_window_module.MainWindow = FakeMainWindow

        @contextmanager
        def fake_filtered_stderr(*args, **kwargs):
            events.append(("enter", kwargs))
            yield
            events.append(("exit", None))

        sentinel_icon = object()
        argv = ["chemvas", "--style", "Fusion"]
        with (
            mock.patch.dict(
                sys.modules,
                {
                    "PyQt6.QtWidgets": qt_widgets_module,
                    "ui.main_window": main_window_module,
                },
            ),
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(chemvas.branding, "app_icon", lambda: sentinel_icon),
        ):
            with mock.patch.object(chemvas_main, "_filtered_stderr", fake_filtered_stderr):
                app_main.main()

        self.assertEqual(FakeApplication.instances[0].args, argv)
        self.assertTrue(FakeApplication.instances[0].exec_called)
        self.assertTrue(FakeMainWindow.instances[0].shown)
        application = FakeApplication.instances[0]
        self.assertEqual(application.application_name, "Chemvas")
        self.assertEqual(application.application_display_name, "Chemvas")
        self.assertEqual(application.application_version, chemvas.__version__)
        self.assertEqual(application.desktop_file_name, "chemvas")
        self.assertIs(application.window_icon, sentinel_icon)
        self.assertIsInstance(application.installed_event_filter, FileOpenEventFilter)
        self.assertEqual([event[0] for event in events], ["enter", "show", "exec", "exit"])

    def test_main_loads_startup_canvas_file_argument(self) -> None:
        events: list[tuple[str, object]] = []

        class FakeApplication(_QApplicationMetadataStub):
            def __init__(self, args) -> None:
                self.args = args

            def exec(self) -> None:
                events.append(("exec", self.args))

        class FakeMainWindow:
            def __init__(self) -> None:
                document_action_service = types.SimpleNamespace(
                    load_canvas_from_path=lambda window, path: events.append(("load", path))
                )
                self._services = types.SimpleNamespace(document_action_service=document_action_service)

            def show(self) -> None:
                events.append(("show", None))

        qt_widgets_module = types.ModuleType("PyQt6.QtWidgets")
        qt_widgets_module.QApplication = FakeApplication
        main_window_module = types.ModuleType("ui.main_window")
        main_window_module.MainWindow = FakeMainWindow

        @contextmanager
        def fake_filtered_stderr(*args, **kwargs):
            events.append(("enter", kwargs))
            yield
            events.append(("exit", None))

        argv = ["chemvas", "--style", "Fusion", "/tmp/start.chemvas"]
        with (
            mock.patch.dict(
                sys.modules,
                {
                    "PyQt6.QtWidgets": qt_widgets_module,
                    "ui.main_window": main_window_module,
                },
            ),
            mock.patch.object(sys, "argv", argv),
            mock.patch.object(chemvas_main, "_filtered_stderr", fake_filtered_stderr),
            mock.patch.object(chemvas.branding, "app_icon", lambda: object()),
        ):
            app_main.main()

        self.assertEqual(events, [("enter", {}), ("show", None), ("load", "/tmp/start.chemvas"), ("exec", argv), ("exit", None)])

    def test_main_module_executes_main_when_run_as_script(self) -> None:
        events: list[str] = []

        class FakeApplication(_QApplicationMetadataStub):
            def __init__(self, args) -> None:
                self.args = args
                events.append("app")

            def exec(self) -> None:
                events.append("exec")

        class FakeMainWindow:
            def show(self) -> None:
                events.append("show")

        pyqt6_module = types.ModuleType("PyQt6")
        pyqt6_module.__path__ = []
        qt_widgets_module = types.ModuleType("PyQt6.QtWidgets")
        qt_widgets_module.QApplication = FakeApplication
        pyqt6_module.QtWidgets = qt_widgets_module

        ui_module = types.ModuleType("ui")
        ui_module.__path__ = []
        main_window_module = types.ModuleType("ui.main_window")
        main_window_module.MainWindow = FakeMainWindow
        ui_module.main_window = main_window_module

        class FakeRecoveryService:
            def restore_previous(self, window, *, include_clean_session: bool = True) -> None:
                events.append("restore")

            def start(self, app) -> None:
                events.append("start")

        recovery_module = types.ModuleType("ui.session_recovery_service")
        recovery_module.create_session_recovery_service = lambda: FakeRecoveryService()
        ui_module.session_recovery_service = recovery_module

        with mock.patch.dict(
            sys.modules,
            {
                "PyQt6": pyqt6_module,
                "PyQt6.QtWidgets": qt_widgets_module,
                "ui": ui_module,
                "ui.main_window": main_window_module,
                "ui.session_recovery_service": recovery_module,
            },
        ):
            with (
                mock.patch.object(sys, "platform", "linux"),
                mock.patch.object(sys, "argv", ["python", "app/main.py"]),
                mock.patch.object(chemvas.branding, "app_icon", lambda: object()),
            ):
                runpy.run_module("main", run_name="__main__")

        self.assertEqual(events, ["app", "show", "restore", "start", "exec"])


if __name__ == "__main__":
    unittest.main()
