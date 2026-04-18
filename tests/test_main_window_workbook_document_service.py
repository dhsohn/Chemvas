import os
import sys
import unittest
from pathlib import Path
from unittest import mock

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
    try:
        from ui.main_window import MainWindow
        from ui.main_window_workbook_document_service import MainWindowWorkbookDocumentService
    except SyntaxError:
        MainWindow = None
        MainWindowWorkbookDocumentService = None
else:
    MainWindow = None
    MainWindowWorkbookDocumentService = None


@unittest.skipUnless(
    QApplication is not None and MainWindow is not None and MainWindowWorkbookDocumentService is not None,
    "PyQt6 and workbook document service are required for tests",
)
class MainWindowWorkbookDocumentServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        QTest.qWait(20)
        self.service = MainWindowWorkbookDocumentService()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _flush_events(self, wait_ms: int = 10) -> None:
        self.app.processEvents()
        QTest.qWait(wait_ms)

    def _build_canvas_sheet_states(self) -> tuple[dict, dict]:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        reactant_state = self.window.canvas.snapshot_state()

        self.window._new_canvas_sheet()
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        product_state = self.window.canvas.snapshot_state()
        return reactant_state, product_state

    def test_clear_canvas_sheets_removes_canvases_and_resets_plus_tab_placeholder(self) -> None:
        self.window._new_canvas_sheet()
        old_plus_tab = self.window._sheet_add_tab
        canvases = [canvas for _, canvas in self.window._canvas_tab_entries()]

        delete_later_patches = [
            mock.patch.object(canvas, "deleteLater")
            for canvas in canvases
        ]
        with delete_later_patches[0] as delete_first, delete_later_patches[1] as delete_second:
            self.service.clear_canvas_sheets(self.window)

        self.assertEqual(self.window.canvas_tabs.count(), 0)
        self.assertIsNot(self.window._sheet_add_tab, old_plus_tab)
        self.assertEqual(self.window._sheet_tab_bar._add_tab_index, -1)
        delete_first.assert_called_once_with()
        delete_second.assert_called_once_with()

    def test_workbook_state_and_save_document_state_use_canvas_relative_sheet_index(self) -> None:
        self.window.canvas_tabs.setTabText(0, "Reactant Sheet")
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        self.window._new_canvas_sheet()
        self.window.canvas_tabs.setTabText(self.window.canvas_tabs.currentIndex(), "Product Sheet")
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))

        self.window.canvas_tabs.setCurrentIndex(1)
        state = self.service.workbook_state(self.window)

        self.assertEqual(state["active_sheet_index"], 1)
        self.assertEqual([sheet["name"] for sheet in state["sheets"]], ["Reactant Sheet", "Product Sheet"])
        self.assertNotIn("+", [sheet["name"] for sheet in state["sheets"]])

        write_document_fn = mock.Mock()
        self.service.save_document_state(self.window, "/tmp/workbook.ldraw", write_document_fn=write_document_fn)
        write_document_fn.assert_called_once_with(
            "/tmp/workbook.ldraw",
            state,
            self.window.WORKBOOK_FILE_VERSION,
        )

    def test_save_document_state_uses_canvas_export_for_single_sheet(self) -> None:
        self.window.canvas.save_to_file = mock.Mock()
        write_document_fn = mock.Mock()

        self.service.save_document_state(self.window, "/tmp/single.ldraw", write_document_fn=write_document_fn)

        self.window.canvas.save_to_file.assert_called_once_with("/tmp/single.ldraw")
        write_document_fn.assert_not_called()

    def test_restore_single_sheet_document_resets_counter_last_index_and_refreshes_ui(self) -> None:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        state = self.window.canvas.snapshot_state()
        self.window._new_canvas_sheet()

        with mock.patch.object(self.window, "_refresh_active_canvas_ui") as refresh_active_canvas_ui:
            self.service.restore_single_sheet_document(self.window, state)

        self.assertEqual(self.window._canvas_sheet_count(), 1)
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window._canvas_name_counter, 1)
        self.assertEqual(self.window._last_canvas_tab_index, 0)
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 0)
        refresh_active_canvas_ui.assert_called_once_with()

    def test_restore_workbook_document_filters_invalid_sheets_and_clamps_index(self) -> None:
        reactant_state, product_state = self._build_canvas_sheet_states()
        state = {
            "active_sheet_index": 99,
            "sheets": [
                {"name": "Reactant Sheet", "kind": "canvas", "content": reactant_state},
                "skip-me",
                {"name": "Summary", "kind": "result", "content": {"title": "Ignored"}},
                {"name": "Product Sheet", "kind": "canvas", "content": product_state},
            ],
        }

        self.service.restore_workbook_document(self.window, state)
        self._flush_events()

        self.assertEqual(self.window._canvas_sheet_count(), 2)
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Reactant Sheet", "Product Sheet", "+"],
        )
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 1)
        self.assertEqual(self.window._active_canvas_sheet_name(), "Product Sheet")

    def test_restore_workbook_document_adds_fallback_sheet_and_resyncs_counter(self) -> None:
        state = {
            "active_sheet_index": "abc",
            "sheets": [
                "skip-me",
                {"name": "Summary", "kind": "result", "content": {"title": "Ignored"}},
            ],
        }

        self.service.restore_workbook_document(self.window, state)
        self._flush_events()

        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window._canvas_name_counter, 1)

        self.window._new_canvas_sheet()
        self._flush_events()

        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )


if __name__ == "__main__":
    unittest.main()
