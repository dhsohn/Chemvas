import os
import unittest
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

if QApplication is not None:
    try:
        from ui.canvas_window_access import snapshot_canvas_state_for
        from ui.main_window import MainWindow
        from ui.main_window_canvas_ports import active_canvas_for_window
        from ui.main_window_document_dialogs import SheetSetupSelection
        from ui.main_window_service_ports import services_for_window
        from ui.main_window_workbook_document_service import (
            MainWindowWorkbookDocumentService,
        )
        from ui.structure_mutation_access import (
            add_benzene_ring_for,
            add_bond_between_points_for,
        )
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
        services_for_window(self.window).canvas_sheet_service._sheet_setup_prompt = (
            lambda window, *, current_size, current_orientation: SheetSetupSelection(
                size=current_size,
                orientation=current_orientation,
            )
        )
        self.active_canvas_ui = mock.Mock()
        self.save_active_canvas_to_file_for_window = mock.Mock()
        self.service = MainWindowWorkbookDocumentService(
            active_canvas_ui=self.active_canvas_ui,
            canvas_sheet=services_for_window(self.window).canvas_sheet_service,
            save_active_canvas_to_file_for_window=self.save_active_canvas_to_file_for_window,
            tab_refs_for_window=lambda window: window.tab_references,
            active_canvas_sheet_index_for_window=lambda window: window.tab_references.active_canvas_sheet_index(
                active_canvas_for_window(window)
            ),
            active_canvas_tab_index_for_window=lambda window: window.tab_references.active_canvas_tab_index(
                active_canvas_for_window(window)
            ),
            canvas_sheet_count_for_window=lambda window: window.tab_references.canvas_sheet_count(),
            reset_canvas_name_counter_for_window=lambda window, sheet_names: window.runtime_state.reset_canvas_name_counter(
                sheet_names
            ),
            tab_reactions_suspended_for_window=lambda window: window.runtime_state.tab_reactions_suspended,
            set_tab_reactions_suspended_for_window=lambda window, value: setattr(
                window.runtime_state,
                "tab_reactions_suspended",
                bool(value),
            ),
            set_last_canvas_tab_index_for_window=lambda window, index: setattr(
                window.runtime_state,
                "last_canvas_tab_index",
                index,
            ),
        )

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _flush_events(self, wait_ms: int = 10) -> None:
        self.app.processEvents()
        QTest.qWait(wait_ms)

    def _build_canvas_sheet_states(self) -> tuple[dict, dict]:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        reactant_state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        product_state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        return reactant_state, product_state

    def test_clear_canvas_sheets_removes_canvases_and_resets_plus_tab_placeholder(self) -> None:
        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)
        old_plus_tab = self.window.tab_references.sheet_add_tab
        canvases = [canvas for _, canvas in self.window.tab_references.canvas_tab_entries()]

        delete_later_patches = [
            mock.patch.object(canvas, "deleteLater")
            for canvas in canvases
        ]
        with delete_later_patches[0] as delete_first, delete_later_patches[1] as delete_second:
            self.service.clear_canvas_sheets(self.window)

        self.assertEqual(self.window.tab_references.canvas_tabs.count(), 0)
        self.assertIsNot(self.window.tab_references.sheet_add_tab, old_plus_tab)
        self.assertEqual(self.window.tab_references.plus_tab_index(), -1)
        delete_first.assert_called_once_with()
        delete_second.assert_called_once_with()

    def test_workbook_state_and_save_document_state_use_canvas_relative_sheet_index(self) -> None:
        self.window.tab_references.canvas_tabs.setTabText(0, "Reactant Sheet")
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)
        self.window.tab_references.canvas_tabs.setTabText(self.window.tab_references.canvas_tabs.currentIndex(), "Product Sheet")
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))

        self.window.tab_references.canvas_tabs.setCurrentIndex(1)
        state = self.service.workbook_state(self.window)

        self.assertEqual(state["active_sheet_index"], 1)
        self.assertEqual([sheet["name"] for sheet in state["sheets"]], ["Reactant Sheet", "Product Sheet"])
        self.assertNotIn("+", [sheet["name"] for sheet in state["sheets"]])

        write_document_fn = mock.Mock()
        self.service.save_document_state(self.window, "/tmp/workbook.chemvas", write_document_fn=write_document_fn)
        write_document_fn.assert_called_once_with(
            "/tmp/workbook.chemvas",
            state,
            self.window.WORKBOOK_FILE_VERSION,
        )

    def test_save_document_state_uses_canvas_export_for_single_sheet(self) -> None:
        write_document_fn = mock.Mock()

        self.service.save_document_state(self.window, "/tmp/single.chemvas", write_document_fn=write_document_fn)

        self.save_active_canvas_to_file_for_window.assert_called_once_with(self.window, "/tmp/single.chemvas")
        write_document_fn.assert_not_called()

    def test_restore_single_sheet_document_resets_counter_last_index_and_refreshes_ui(self) -> None:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)

        self.service.restore_single_sheet_document(self.window, state)

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 1)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window.runtime_state.next_canvas_sheet_name(), "Sheet 2")
        self.assertEqual(self.window.runtime_state.last_canvas_tab_index, 0)
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 0)
        self.active_canvas_ui.refresh_active_canvas_ui.assert_called_once_with(self.window)

    def test_restore_workbook_document_restores_active_sheet_and_refreshes_ui(self) -> None:
        reactant_state, product_state = self._build_canvas_sheet_states()
        self.active_canvas_ui.refresh_active_canvas_ui.reset_mock()
        state = {
            "active_sheet_index": 1,
            "sheets": [
                {"name": "Reactant Sheet", "kind": "canvas", "content": reactant_state},
                {"name": "Product Sheet", "kind": "canvas", "content": product_state},
            ],
        }

        self.service.restore_workbook_document(self.window, state)

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 2)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Reactant Sheet", "Product Sheet", "+"],
        )
        self.assertEqual(self.window.tab_references.active_canvas_sheet_name(active_canvas_for_window(self.window)), "Product Sheet")
        self.active_canvas_ui.refresh_active_canvas_ui.assert_called_once_with(self.window)

    def test_restore_workbook_document_rejects_invalid_sheets_without_mutating_tabs(self) -> None:
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

        with self.assertRaises(ValueError):
            self.service.restore_workbook_document(self.window, state)
        self._flush_events()

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 2)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 1)
        self.assertEqual(self.window.tab_references.active_canvas_sheet_name(active_canvas_for_window(self.window)), "Sheet 2")

    def test_restore_workbook_document_rejects_non_canvas_workbook_without_fallback_sheet(self) -> None:
        state = {
            "active_sheet_index": "abc",
            "sheets": [
                "skip-me",
                {"name": "Summary", "kind": "result", "content": {"title": "Ignored"}},
            ],
        }

        with self.assertRaises(ValueError):
            self.service.restore_workbook_document(self.window, state)
        self._flush_events()

        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window.runtime_state.next_canvas_sheet_name(), "Sheet 2")


if __name__ == "__main__":
    unittest.main()
