import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    QPointF = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.document_io import read_document
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for GUI workbook tab tests")
class MainWindowWorkbookTabsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _build_reordered_workbook_state(self) -> dict:
        self.window.canvas_tabs.setTabText(0, "Reactant Sheet")
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))

        self.window._new_canvas_sheet()
        self.window.canvas_tabs.setTabText(self.window.canvas_tabs.currentIndex(), "Product Sheet")
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))

        plus_index = self.window.canvas_tabs.indexOf(self.window._sheet_add_tab)
        self.window.canvas_tabs.tabBar().moveTab(plus_index, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Reactant Sheet", "Product Sheet", "+"],
        )
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workbook.ldraw"
            self.window._save_document_state(str(path))
            document = read_document(path)
        return document.state

    def test_plus_tab_stays_last_after_move_attempt(self) -> None:
        self.window._new_canvas_sheet()

        plus_index = self.window.canvas_tabs.indexOf(self.window._sheet_add_tab)
        self.window.canvas_tabs.tabBar().moveTab(plus_index, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )
        self.assertEqual(self.window.canvas_tabs.indexOf(self.window._sheet_add_tab), self.window.canvas_tabs.count() - 1)

    def test_preview_panel_tracks_active_canvas_rdkit_adapter(self) -> None:
        first_canvas = self.window.canvas

        self.assertIs(self.window.preview_3d._rdkit, first_canvas.rdkit)

        self.window._new_canvas_sheet()
        self.app.processEvents()
        QTest.qWait(10)

        second_canvas = self.window.canvas
        self.assertIsNot(first_canvas, second_canvas)
        self.assertIs(self.window.preview_3d._rdkit, second_canvas.rdkit)

        self.window.canvas_tabs.setCurrentIndex(0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIs(self.window.preview_3d._rdkit, first_canvas.rdkit)

    def test_save_workbook_ignores_reordered_plus_tab(self) -> None:
        state = self._build_reordered_workbook_state()

        self.assertEqual(state["active_sheet_index"], 1)
        self.assertEqual([sheet["name"] for sheet in state["sheets"]], ["Reactant Sheet", "Product Sheet"])
        self.assertTrue(all(sheet["name"] != "+" for sheet in state["sheets"]))
        self.assertEqual(len(state["sheets"][0]["content"]["model"]["bonds"]), 1)
        self.assertEqual(len(state["sheets"][1]["content"]["ring_fills"]), 1)

    def test_restore_workbook_uses_canvas_relative_active_sheet_index(self) -> None:
        state = self._build_reordered_workbook_state()

        restored_window = MainWindow()
        try:
            restored_window.show()
            restored_window.raise_()
            restored_window.activateWindow()
            self.app.processEvents()
            QTest.qWait(20)

            restored_window._restore_workbook_document(state)
            self.app.processEvents()
            QTest.qWait(10)

            self.assertEqual(restored_window._canvas_sheet_count(), 2)
            self.assertEqual(
                [restored_window.canvas_tabs.tabText(index) for index in range(restored_window.canvas_tabs.count())],
                ["Reactant Sheet", "Product Sheet", "+"],
            )
            self.assertEqual(restored_window.canvas_tabs.currentIndex(), 1)
            self.assertEqual(restored_window._active_canvas_sheet_name(), "Product Sheet")
            self.assertEqual(len(restored_window.canvas.ring_items), 1)
        finally:
            restored_window.close()
            self.app.processEvents()
            QTest.qWait(10)
