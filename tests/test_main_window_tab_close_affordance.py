from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget
except ModuleNotFoundError:
    QApplication = None
    QTabWidget = None
    QWidget = None

if QApplication is not None:
    from ui.main_window_tab_close_affordance import (
        CanvasTabCloseAffordance,
        CanvasTabCloseButtonStyle,
        apply_close_button_visibility,
        close_button_position,
        visible_close_indices,
    )
else:
    from ui.main_window_tab_close_affordance import visible_close_indices


class VisibleCloseIndicesTest(unittest.TestCase):
    def test_current_and_hovered_are_both_revealed(self) -> None:
        self.assertEqual(
            visible_close_indices(count=3, current_index=0, hovered_index=2),
            {0, 2},
        )

    def test_current_alone_when_nothing_hovered(self) -> None:
        self.assertEqual(
            visible_close_indices(count=3, current_index=1, hovered_index=-1),
            {1},
        )

    def test_out_of_range_indices_are_ignored(self) -> None:
        self.assertEqual(
            visible_close_indices(count=2, current_index=5, hovered_index=-1),
            set(),
        )

    def test_empty_strip_reveals_nothing(self) -> None:
        self.assertEqual(
            visible_close_indices(count=0, current_index=0, hovered_index=0),
            set(),
        )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for close affordance tests")
class CanvasTabCloseAffordanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def _tabs(self, count: int) -> QTabWidget:
        tabs = QTabWidget()
        self.addCleanup(tabs.deleteLater)
        tabs.setTabsClosable(True)
        for index in range(count):
            tabs.addTab(QWidget(), f"Tab {index + 1}")
        return tabs

    def _hidden_flags(self, tabs: QTabWidget) -> list[bool]:
        tab_bar = tabs.tabBar()
        assert tab_bar is not None
        position = close_button_position(tab_bar)
        flags: list[bool] = []
        for index in range(tab_bar.count()):
            button = tab_bar.tabButton(index, position)
            self.assertIsNotNone(button, f"close button missing for tab {index}")
            flags.append(button.isHidden())
        return flags

    def test_only_current_tab_close_button_shows_at_rest(self) -> None:
        tabs = self._tabs(3)
        tabs.setCurrentIndex(0)
        tab_bar = tabs.tabBar()
        assert tab_bar is not None
        CanvasTabCloseAffordance(tab_bar)

        self.assertEqual(self._hidden_flags(tabs), [False, True, True])

    def test_hovered_tab_close_button_is_revealed(self) -> None:
        tabs = self._tabs(3)
        tabs.setCurrentIndex(0)
        tab_bar = tabs.tabBar()
        assert tab_bar is not None

        apply_close_button_visibility(tab_bar, hovered_index=2)

        self.assertEqual(self._hidden_flags(tabs), [False, True, False])

    def test_current_change_moves_the_revealed_close_button(self) -> None:
        tabs = self._tabs(3)
        tabs.setCurrentIndex(0)
        tab_bar = tabs.tabBar()
        assert tab_bar is not None
        CanvasTabCloseAffordance(tab_bar)

        tabs.setCurrentIndex(1)

        self.assertEqual(self._hidden_flags(tabs), [True, False, True])

    def test_close_buttons_use_the_app_glyph_style(self) -> None:
        tabs = self._tabs(3)
        tabs.setCurrentIndex(0)
        tab_bar = tabs.tabBar()
        assert tab_bar is not None
        CanvasTabCloseAffordance(tab_bar)

        position = close_button_position(tab_bar)
        for index in range(tab_bar.count()):
            button = tab_bar.tabButton(index, position)
            self.assertIsNotNone(button, f"close button missing for tab {index}")
            self.assertIsInstance(button.style(), CanvasTabCloseButtonStyle)


if __name__ == "__main__":
    unittest.main()
