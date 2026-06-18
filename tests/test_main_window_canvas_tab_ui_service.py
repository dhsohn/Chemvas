import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None
    QPoint = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_tab_ui_service import MainWindowCanvasTabUIService
    from ui.main_window_document_dialogs import SheetSetupSelection
    from ui.main_window_service_ports import services_for_window


class _FakeAction:
    def __init__(self) -> None:
        self._enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def isEnabled(self) -> bool:
        return self._enabled


class _FakeMenu:
    def __init__(self, choose_delete: bool) -> None:
        self.choose_delete = choose_delete
        self.action = None
        self.labels = []

    def addAction(self, label: str):
        self.labels.append(label)
        self.action = _FakeAction()
        return self.action

    def exec(self, _pos):
        if self.choose_delete:
            return self.action
        return None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window canvas tab UI tests")
class MainWindowCanvasTabUIServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        services_for_window(self.window).canvas_sheet_service._sheet_setup_prompt = (
            lambda window, *, current_size, current_orientation: SheetSetupSelection(
                size=current_size,
                orientation=current_orientation,
            )
        )
        self.active_canvas_ui = mock.Mock()
        self.service = MainWindowCanvasTabUIService(
            active_canvas_ui=self.active_canvas_ui,
            tab_refs_for_window=lambda window: window.tab_references,
            repositioning_add_tab_for_window=lambda window: window.runtime_state.repositioning_add_tab,
            set_repositioning_add_tab_for_window=lambda window, value: setattr(
                window.runtime_state,
                "repositioning_add_tab",
                bool(value),
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

    def test_ensure_add_sheet_tab_recreates_missing_plus_tab_and_keeps_it_last(self) -> None:
        tab_refs = self.window.tab_references
        plus_index = tab_refs.plus_tab_index()
        self.window.tab_references.canvas_tabs.removeTab(plus_index)
        tab_refs.set_sheet_add_tab_index(-1)

        self.service.ensure_add_sheet_tab(self.window)

        self.assertEqual(self.window.tab_references.canvas_tabs.tabText(tab_refs.plus_tab_index()), "+")
        self.assertEqual(tab_refs.plus_tab_index(), self.window.tab_references.canvas_tabs.count() - 1)

        self.window.runtime_state.repositioning_add_tab = True
        self.window.tab_references.canvas_tabs.tabBar().moveTab(tab_refs.plus_tab_index(), 0)
        self.window.runtime_state.repositioning_add_tab = False

        self.service.keep_add_tab_last(self.window)

        self.assertEqual(tab_refs.plus_tab_index(), self.window.tab_references.canvas_tabs.count() - 1)

    def test_can_delete_delete_and_new_canvas_sheet_follow_sheet_guards(self) -> None:
        self.assertFalse(self.service.can_delete_canvas_sheet(self.window, 0))
        self.assertFalse(self.service.can_delete_canvas_sheet(self.window, self.window.tab_references.plus_tab_index()))

        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)

        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 2)
        self.assertTrue(self.service.can_delete_canvas_sheet(self.window, 0))

        self.service.delete_canvas_sheet(self.window, 0)

        self.active_canvas_ui.refresh_active_canvas_ui.assert_called_once_with(self.window)
        self.assertEqual(self.window.tab_references.canvas_sheet_count(), 1)
        self.assertEqual(self.window.tab_references.plus_tab_index(), self.window.tab_references.canvas_tabs.count() - 1)
        self.assertFalse(self.service.can_delete_canvas_sheet(self.window, 0))

    def test_main_window_new_canvas_sheet_delegates_to_canvas_sheet_service(self) -> None:
        services_for_window(self.window).canvas_sheet_service = mock.Mock()

        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)

        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet.assert_called_once_with(self.window)

    def test_show_canvas_tab_context_menu_routes_delete_only_when_enabled(self) -> None:
        services_for_window(self.window).canvas_sheet_service.new_canvas_sheet(self.window)
        pos = self.window.tab_references.canvas_tabs.tabBar().tabRect(0).center() if QPoint is not None else QPoint(1, 1)

        with mock.patch.object(self.service, "delete_canvas_sheet") as delete_canvas_sheet:
            menu = _FakeMenu(choose_delete=True)
            self.service.show_canvas_tab_context_menu(
                self.window,
                pos,
                menu_factory=lambda _parent: menu,
            )

        self.assertEqual(menu.labels, ["Delete Sheet"])
        delete_canvas_sheet.assert_called_once_with(self.window, 0)

        single_sheet_window = MainWindow()
        try:
            single_service = MainWindowCanvasTabUIService(
                active_canvas_ui=mock.Mock(),
                tab_refs_for_window=lambda window: window.tab_references,
                repositioning_add_tab_for_window=lambda window: window.runtime_state.repositioning_add_tab,
                set_repositioning_add_tab_for_window=lambda window, value: setattr(
                    window.runtime_state,
                    "repositioning_add_tab",
                    bool(value),
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
            pos = single_sheet_window.tab_references.canvas_tabs.tabBar().tabRect(0).center() if QPoint is not None else QPoint(1, 1)
            with mock.patch.object(single_service, "delete_canvas_sheet") as delete_canvas_sheet:
                menu = _FakeMenu(choose_delete=True)
                single_service.show_canvas_tab_context_menu(
                    single_sheet_window,
                    pos,
                    menu_factory=lambda _parent: menu,
                )
            self.assertFalse(menu.action.isEnabled())
            delete_canvas_sheet.assert_not_called()
        finally:
            single_sheet_window.close()
            self.app.processEvents()

    def test_keep_add_tab_last_and_context_menu_ignore_guard_cases(self) -> None:
        self.window.runtime_state.repositioning_add_tab = True
        with mock.patch.object(type(self.window.tab_references), "move_sheet_tab") as move_tab:
            self.service.keep_add_tab_last(self.window)
        move_tab.assert_not_called()
        self.assertFalse(self.service.can_delete_canvas_sheet(self.window, -1))

        plus_pos = (
            self.window.tab_references.canvas_tabs.tabBar().tabRect(self.window.tab_references.plus_tab_index()).center()
            if QPoint is not None
            else QPoint(1, 1)
        )
        with mock.patch.object(self.service, "delete_canvas_sheet") as delete_canvas_sheet:
            menu_factory = mock.Mock()
            self.service.show_canvas_tab_context_menu(self.window, QPoint(-100, -100), menu_factory=menu_factory)
            self.service.show_canvas_tab_context_menu(self.window, plus_pos, menu_factory=menu_factory)
        menu_factory.assert_not_called()
        delete_canvas_sheet.assert_not_called()

    def test_delete_canvas_sheet_handles_non_canvas_current_widget_and_missing_deleted_widget(self) -> None:
        widget = mock.Mock()
        tabs = SimpleNamespace(
            removed=[],
            current_index=3,
            fallback_widget=object(),
            widget=lambda index: widget,
            removeTab=lambda index: tabs.removed.append(index),
            currentIndex=lambda: tabs.current_index,
            currentWidget=lambda: tabs.fallback_widget,
            setCurrentIndex=mock.Mock(),
        )
        tab_refs = SimpleNamespace(
            canvas_tabs=tabs,
            plus_tab_index=lambda: 4,
        )
        fake_window = SimpleNamespace(
            tab_references=tab_refs,
            runtime_state=SimpleNamespace(
                tab_reactions_suspended=False,
                repositioning_add_tab=False,
                last_canvas_tab_index=None,
            ),
            tab_reactions_suspended=False,
            last_canvas_tab_index=None,
        )

        with mock.patch.object(self.service, "can_delete_canvas_sheet", return_value=True), mock.patch.object(
            self.service, "ensure_add_sheet_tab"
        ) as ensure_add_sheet_tab:
            self.service.delete_canvas_sheet(fake_window, 2)

        ensure_add_sheet_tab.assert_called_once_with(fake_window)
        self.assertEqual(tabs.removed, [2])
        tabs.setCurrentIndex.assert_called_once_with(2)
        self.assertEqual(fake_window.runtime_state.last_canvas_tab_index, 2)
        widget.deleteLater.assert_called_once_with()
        self.active_canvas_ui.refresh_active_canvas_ui.assert_called_once_with(fake_window)

    def test_on_canvas_tab_moved_and_delete_canvas_sheet_short_circuit_when_guard_blocks(self) -> None:
        with mock.patch.object(self.service, "keep_add_tab_last") as keep_add_tab_last:
            self.service.on_canvas_tab_moved(self.window, 0, 1)
        keep_add_tab_last.assert_called_once_with(self.window)

        with mock.patch.object(self.service, "can_delete_canvas_sheet", return_value=False), mock.patch.object(
            self.service, "ensure_add_sheet_tab"
        ) as ensure_add_sheet_tab:
            self.service.delete_canvas_sheet(self.window, 0)

        ensure_add_sheet_tab.assert_not_called()
        self.active_canvas_ui.refresh_active_canvas_ui.assert_not_called()


if __name__ == "__main__":
    unittest.main()
