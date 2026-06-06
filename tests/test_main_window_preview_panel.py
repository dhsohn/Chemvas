import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QDockWidget, QMainWindow, QWidget
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_preview_panel import build_preview_panel_dock


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preview_widget = QWidget()


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for preview panel tests")
class MainWindowPreviewPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_preview_panel_dock_creates_locked_right_dock(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_preview_panel_dock(window, preview_widget=window.preview_widget)

        self.assertIs(assembly.splitter.widget(0), window.preview_widget)
        self.assertEqual(assembly.splitter.count(), 1)
        self.assertEqual(assembly.dock.allowedAreas(), Qt.DockWidgetArea.RightDockWidgetArea)
        self.assertEqual(assembly.dock.minimumWidth(), 320)
        self.assertEqual(assembly.dock.maximumWidth(), 420)
        self.assertFalse(
            bool(
                assembly.dock.features()
                & QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        )
        self.assertEqual(assembly.dock.titleBarWidget().height(), 0)


if __name__ == "__main__":
    unittest.main()
