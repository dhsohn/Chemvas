import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QTest = None
    QPoint = None
    QPointF = None

if QApplication is not None:
    try:
        from core.document_io import read_document
        from ui.canvas_scene_items_state import ring_items_for
        from ui.canvas_window_access import snapshot_canvas_state_for
        from ui.main_window import MainWindow
        from ui.main_window_canvas_ports import active_canvas_for_window
        from ui.main_window_preview_ports import preview_for_window
        from ui.main_window_service_ports import services_for_window
        from ui.structure_mutation_access import (
            add_benzene_ring_for,
            add_bond_between_points_for,
        )
    except SyntaxError:
        read_document = None
        MainWindow = None
else:
    read_document = None
    MainWindow = None


@unittest.skipUnless(
    QApplication is not None and MainWindow is not None,
    "PyQt6 and an importable MainWindow are required for GUI workbook tab tests",
)
class MainWindowWorkbookTabsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.window.show()
        active_canvas_for_window(self.window).setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _flush_events(self, wait_ms: int = 10) -> None:
        self.app.processEvents()
        QTest.qWait(wait_ms)

    def _workbook_document(self):
        return services_for_window(self.window).workbook_document_service

    def _restore_workbook_and_flush(self, state: dict) -> None:
        self._workbook_document().restore_workbook_document(self.window, state)
        self._flush_events()

    def _new_canvas_sheet(self) -> None:
        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)

    def test_canvas_tab_ui_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "ensure_add_sheet_tab"))
        self.assertFalse(hasattr(self.window, "keep_add_tab_last"))
        self.assertFalse(hasattr(self.window, "on_canvas_tab_moved"))
        self.assertFalse(hasattr(self.window, "can_delete_canvas_sheet"))
        self.assertFalse(hasattr(self.window, "show_canvas_tab_context_menu"))
        self.assertFalse(hasattr(self.window, "delete_canvas_sheet"))

    def test_active_canvas_ui_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "current_zoom_percent"))
        self.assertFalse(hasattr(self.window, "bind_active_canvas"))
        self.assertFalse(hasattr(self.window, "handle_selection_info"))
        self.assertFalse(hasattr(self.window, "refresh_active_canvas_ui"))
        self.assertFalse(hasattr(self.window, "on_canvas_tab_changed"))

    def test_canvas_sheet_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "create_canvas"))
        self.assertFalse(hasattr(self.window, "add_canvas_sheet"))
        self.assertFalse(hasattr(self.window, "open_result_canvas_sheet"))
        self.assertFalse(hasattr(self.window, "new_canvas_sheet"))

    def test_workbook_document_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "clear_canvas_sheets"))
        self.assertFalse(hasattr(self.window, "workbook_state"))
        self.assertFalse(hasattr(self.window, "restore_single_sheet_document"))
        self.assertFalse(hasattr(self.window, "restore_workbook_document"))
        self.assertFalse(hasattr(self.window, "save_document_state"))

    def _build_canvas_sheet_states(self) -> tuple[dict, dict]:
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        reactant_state = snapshot_canvas_state_for(active_canvas_for_window(self.window))

        self._new_canvas_sheet()
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))
        product_state = snapshot_canvas_state_for(active_canvas_for_window(self.window))
        return reactant_state, product_state

    def _build_reordered_workbook_state(self) -> dict:
        self.window.tab_references.canvas_tabs.setTabText(0, "Reactant Sheet")
        add_bond_between_points_for(active_canvas_for_window(self.window), QPointF(-20.0, 0.0), QPointF(20.0, 0.0))

        self._new_canvas_sheet()
        self.window.tab_references.canvas_tabs.setTabText(self.window.tab_references.canvas_tabs.currentIndex(), "Product Sheet")
        add_benzene_ring_for(active_canvas_for_window(self.window), QPointF(0.0, 0.0))

        plus_index = self.window.tab_references.plus_tab_index()
        self.window.tab_references.canvas_tabs.tabBar().moveTab(plus_index, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Reactant Sheet", "Product Sheet", "+"],
        )
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 1)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workbook.chemvas"
            self._workbook_document().save_document_state(self.window, str(path))
            document = read_document(path)
        return document.state

    def test_plus_tab_stays_last_after_move_attempt(self) -> None:
        self._new_canvas_sheet()

        plus_index = self.window.tab_references.plus_tab_index()
        self.window.tab_references.canvas_tabs.tabBar().moveTab(plus_index, 0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )
        self.assertEqual(self.window.tab_references.plus_tab_index(), self.window.tab_references.canvas_tabs.count() - 1)

    def test_preview_panel_tracks_active_canvas_rdkit_adapter(self) -> None:
        first_canvas = active_canvas_for_window(self.window)

        self.assertIs(preview_for_window(self.window).rdkit_adapter, first_canvas.rdkit)

        self._new_canvas_sheet()
        self.app.processEvents()
        QTest.qWait(10)

        second_canvas = active_canvas_for_window(self.window)
        self.assertIsNot(first_canvas, second_canvas)
        self.assertIs(preview_for_window(self.window).rdkit_adapter, second_canvas.rdkit)

        self.window.tab_references.canvas_tabs.setCurrentIndex(0)
        self.app.processEvents()
        QTest.qWait(10)

        self.assertIs(preview_for_window(self.window).rdkit_adapter, first_canvas.rdkit)

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
            self.app.processEvents()
            QTest.qWait(20)

            services_for_window(restored_window).workbook_document_service.restore_workbook_document(
                restored_window,
                state,
            )
            self.app.processEvents()
            QTest.qWait(10)

            self.assertEqual(restored_window.tab_references.canvas_sheet_count(), 2)
            self.assertEqual(
                [restored_window.tab_references.canvas_tabs.tabText(index) for index in range(restored_window.tab_references.canvas_tabs.count())],
                ["Reactant Sheet", "Product Sheet", "+"],
            )
            self.assertEqual(restored_window.tab_references.canvas_tabs.currentIndex(), 1)
            restored_canvas = active_canvas_for_window(restored_window)
            self.assertEqual(restored_window.tab_references.active_canvas_sheet_name(restored_canvas), "Product Sheet")
            self.assertEqual(len(ring_items_for(restored_canvas)), 1)
        finally:
            restored_window.close()
            self.app.processEvents()
            QTest.qWait(10)

    def test_restore_workbook_rejects_invalid_and_non_canvas_sheets(self) -> None:
        reactant_state, product_state = self._build_canvas_sheet_states()
        state = {
            "active_sheet_index": 1,
            "sheets": [
                {"name": "Reactant Sheet", "kind": "canvas", "content": reactant_state},
                "skip-me",
                {"name": "Summary", "kind": "result", "content": {"title": "Ignored"}},
                {"name": "Product Sheet", "kind": "canvas", "content": product_state},
            ],
        }

        with self.assertRaises(ValueError):
            self._workbook_document().restore_workbook_document(self.window, state)

        self._flush_events()
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )

    def test_restore_workbook_rejects_out_of_range_active_sheet_index(self) -> None:
        reactant_state, product_state = self._build_canvas_sheet_states()
        base_state = {
            "sheets": [
                {"name": "Reactant Sheet", "kind": "canvas", "content": reactant_state},
                {"name": "Product Sheet", "kind": "canvas", "content": product_state},
            ]
        }

        for requested_index in (-5, 99):
            with self.subTest(active_sheet_index=requested_index):
                state = deepcopy(base_state)
                state["active_sheet_index"] = requested_index

                with self.assertRaises(ValueError):
                    self._workbook_document().restore_workbook_document(self.window, state)

                self._flush_events()
                self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 1)
                self.assertEqual(self.window.tab_references.active_canvas_sheet_name(active_canvas_for_window(self.window)), "Sheet 2")

    def test_restore_workbook_rejects_empty_or_non_canvas_sheets(self) -> None:
        cases = (
            {"active_sheet_index": 4, "sheets": []},
            {
                "active_sheet_index": 4,
                "sheets": [
                    "skip-me",
                    {"name": "Summary", "kind": "result", "content": {"title": "Ignored"}},
                ],
            },
        )

        for state in cases:
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    self._workbook_document().restore_workbook_document(self.window, deepcopy(state))

                self._flush_events()
                self.assertEqual(
                    [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
                    ["Sheet 1", "+"],
                )

    def test_restore_workbook_resyncs_sheet_name_counter_for_new_canvas_tabs(self) -> None:
        reactant_state, product_state = self._build_canvas_sheet_states()
        state = {
            "active_sheet_index": 1,
            "sheets": [
                {"name": "Sheet 1", "kind": "canvas", "content": reactant_state},
                {"name": "Sheet 2", "kind": "canvas", "content": product_state},
            ],
        }

        self._restore_workbook_and_flush(state)
        self._new_canvas_sheet()
        self._flush_events()

        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "Sheet 3", "+"],
        )
        self.assertEqual(self.window.tab_references.active_canvas_sheet_name(active_canvas_for_window(self.window)), "Sheet 3")

    def test_restore_workbook_rejects_invalid_active_index_and_canvas_content(self) -> None:
        _, product_state = self._build_canvas_sheet_states()
        state = {
            "active_sheet_index": "abc",
            "sheets": [
                {"name": "Sheet 1", "kind": "canvas", "content": "broken"},
                {"name": "Product Sheet", "kind": "canvas", "content": product_state},
            ],
        }

        with self.assertRaises(ValueError):
            self._workbook_document().restore_workbook_document(self.window, state)

        self._flush_events()
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )

    def test_delete_canvas_sheet_keeps_last_remaining_canvas(self) -> None:
        services_for_window(self.window).canvas_tab_ui_service.delete_canvas_sheet(self.window, 0)
        self._flush_events()

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 1)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 0)

    def test_delete_canvas_sheet_ignores_plus_tab_target(self) -> None:
        self._new_canvas_sheet()
        plus_index = self.window.tab_references.plus_tab_index()

        services_for_window(self.window).canvas_tab_ui_service.delete_canvas_sheet(self.window, plus_index)
        self._flush_events()

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 2)
        self.assertEqual(
            [self.window.tab_references.canvas_tabs.tabText(index) for index in range(self.window.tab_references.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )
        self.assertEqual(self.window.tab_references.canvas_tabs.currentIndex(), 1)
