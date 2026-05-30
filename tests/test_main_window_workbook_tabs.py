import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

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
        from ui.main_window import MainWindow
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
        self.window.canvas.setFocus()
        self.app.processEvents()
        QTest.qWait(20)

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()
        QTest.qWait(10)

    def _flush_events(self, wait_ms: int = 10) -> None:
        self.app.processEvents()
        QTest.qWait(wait_ms)

    def _restore_workbook_and_flush(self, state: dict) -> None:
        self.window._restore_workbook_document(state)
        self._flush_events()

    def test_canvas_tab_ui_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        service.can_delete_canvas_sheet.return_value = True
        self.window._canvas_tab_ui_service = service
        pos = QPoint(1, 1) if QPoint is not None else None

        self.window._ensure_add_sheet_tab()
        self.window._keep_add_tab_last()
        self.window._on_canvas_tab_moved(0, 1)
        self.assertTrue(self.window._can_delete_canvas_sheet(0))
        self.window._show_canvas_tab_context_menu(pos)
        self.window._delete_canvas_sheet(0)
        self.window._new_canvas_sheet()

        service.ensure_add_sheet_tab.assert_called_once_with(self.window)
        service.keep_add_tab_last.assert_called_once_with(self.window)
        service.on_canvas_tab_moved.assert_called_once_with(self.window, 0, 1)
        service.can_delete_canvas_sheet.assert_called_once_with(self.window, 0)
        service.show_canvas_tab_context_menu.assert_called_once_with(self.window, pos)
        service.delete_canvas_sheet.assert_called_once_with(self.window, 0)
        service.new_canvas_sheet.assert_called_once_with(self.window)

    def test_active_canvas_ui_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        service.current_zoom_percent.return_value = 175
        self.window._active_canvas_ui_service = service

        self.window._bind_active_canvas()
        self.window._handle_selection_info("H2O", "18.0")
        self.assertEqual(self.window._current_zoom_percent(), 175)
        self.window._refresh_active_canvas_ui()
        self.window._on_canvas_tab_changed(0)

        service.bind_active_canvas.assert_called_once_with(self.window)
        service.handle_selection_info.assert_called_once_with(self.window, "H2O", "18.0")
        service.current_zoom_percent.assert_called_once_with(self.window)
        service.refresh_active_canvas_ui.assert_called_once_with(self.window)
        service.on_canvas_tab_changed.assert_called_once_with(self.window, 0)

    def test_canvas_sheet_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        created_canvas = object()
        added_canvas = object()
        opened_canvas = object()
        service.create_canvas.return_value = created_canvas
        service.add_canvas_sheet.return_value = added_canvas
        service.open_result_canvas_sheet.return_value = ("Result 1", opened_canvas)
        self.window._canvas_sheet_service = service

        self.assertIs(self.window._create_canvas(template=None), created_canvas)
        self.assertIs(
            self.window._add_canvas_sheet(name="Sheet X", state={"atoms": []}, select=False, template=None),
            added_canvas,
        )
        self.assertEqual(
            self.window._open_result_canvas_sheet("Product", select=True, exact_name=True),
            ("Result 1", opened_canvas),
        )

        service.create_canvas.assert_called_once_with(self.window, template=None)
        service.add_canvas_sheet.assert_called_once_with(
            self.window,
            name="Sheet X",
            state={"atoms": []},
            select=False,
            template=None,
        )
        service.open_result_canvas_sheet.assert_called_once_with(
            self.window,
            "Product",
            select=True,
            exact_name=True,
        )

    def test_workbook_document_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        service.workbook_state.return_value = {"active_sheet_index": 0, "sheets": []}
        self.window._workbook_document_service = service

        self.window._clear_canvas_sheets()
        self.assertEqual(self.window._workbook_state(), {"active_sheet_index": 0, "sheets": []})
        self.window._restore_single_sheet_document({"atoms": []})
        self.window._restore_workbook_document({"sheets": [{"name": "Sheet 1"}]})
        self.window._save_document_state("/tmp/test.chemvas")

        service.clear_canvas_sheets.assert_called_once_with(self.window)
        service.workbook_state.assert_called_once_with(self.window)
        service.restore_single_sheet_document.assert_called_once_with(self.window, {"atoms": []})
        service.restore_workbook_document.assert_called_once_with(
            self.window,
            {"sheets": [{"name": "Sheet 1"}]},
        )
        service.save_document_state.assert_called_once_with(self.window, "/tmp/test.chemvas")

    def _build_canvas_sheet_states(self) -> tuple[dict, dict]:
        self.window.canvas.add_bond_from_points(QPointF(-20.0, 0.0), QPointF(20.0, 0.0))
        reactant_state = self.window.canvas.snapshot_state()

        self.window._new_canvas_sheet()
        self.window.canvas.add_benzene_ring(QPointF(0.0, 0.0))
        product_state = self.window.canvas.snapshot_state()
        return reactant_state, product_state

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
            path = Path(temp_dir) / "workbook.chemvas"
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
            self.window._restore_workbook_document(state)

        self._flush_events()
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
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
                    self.window._restore_workbook_document(state)

                self._flush_events()
                self.assertEqual(self.window.canvas_tabs.currentIndex(), 1)
                self.assertEqual(self.window._active_canvas_sheet_name(), "Sheet 2")

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
                    self.window._restore_workbook_document(deepcopy(state))

                self._flush_events()
                self.assertEqual(
                    [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
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
        self.window._new_canvas_sheet()
        self._flush_events()

        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "Sheet 3", "+"],
        )
        self.assertEqual(self.window._active_canvas_sheet_name(), "Sheet 3")

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
            self.window._restore_workbook_document(state)

        self._flush_events()
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )

    def test_delete_canvas_sheet_keeps_last_remaining_canvas(self) -> None:
        self.window._delete_canvas_sheet(0)
        self._flush_events()

        self.assertEqual(self.window._canvas_sheet_count(), 1)
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "+"],
        )
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 0)

    def test_delete_canvas_sheet_ignores_plus_tab_target(self) -> None:
        self.window._new_canvas_sheet()
        plus_index = self.window.canvas_tabs.indexOf(self.window._sheet_add_tab)

        self.window._delete_canvas_sheet(plus_index)
        self._flush_events()

        self.assertEqual(self.window._canvas_sheet_count(), 2)
        self.assertEqual(
            [self.window.canvas_tabs.tabText(index) for index in range(self.window.canvas_tabs.count())],
            ["Sheet 1", "Sheet 2", "+"],
        )
        self.assertEqual(self.window.canvas_tabs.currentIndex(), 1)
