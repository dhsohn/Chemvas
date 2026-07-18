import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.main_window_preview_window import build_preview_window


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.preview_widget = QWidget()


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for preview panel tests"
)
class MainWindowPreviewPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_preview_window_wraps_preview_widget_and_hides_on_close(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_preview_window(
            window,
            preview_widget=window.preview_widget,
        )

        self.assertIs(window.preview_widget.parent(), assembly.preview_window)
        self.assertEqual(assembly.preview_window.windowTitle(), "Molecule Info")
        self.assertGreaterEqual(assembly.preview_window.minimumWidth(), 420)
        self.assertIsNone(
            assembly.preview_window.findChild(QWidget, "preview_export_xyz_button")
        )
        assembly.preview_window.show()
        self.app.processEvents()
        self.assertTrue(assembly.preview_window.isVisible())

        assembly.preview_window.close()
        self.app.processEvents()
        self.assertFalse(assembly.preview_window.isVisible())


if __name__ == "__main__":
    unittest.main()
