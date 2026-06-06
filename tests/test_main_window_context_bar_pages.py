import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication, QSlider, QToolButton
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_canvas_ports import active_canvas_for_window
    from ui.main_window_context_bar_pages import (
        MainWindowContextBarPageBuilder,
        bond_label_for_state,
    )


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for context bar page tests")
class MainWindowContextBarPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()
        self.insert_controller = active_canvas_for_window(self.window).services.insert_controller
        self.tool_mode_controller = SimpleNamespace(
            get_arrow_line_width=mock.Mock(return_value=2.0),
            get_arrow_head_scale=mock.Mock(return_value=0.4),
            set_arrow_line_width=mock.Mock(),
            set_arrow_head_scale=mock.Mock(),
        )
        self.insert_controller_for_window = mock.Mock(return_value=self.insert_controller)
        self.tool_mode_controller_for_window = mock.Mock(return_value=self.tool_mode_controller)
        self.tool_state_service = mock.Mock()
        self.activate_bond_style_for_window = mock.Mock()
        self.set_bond_length_for_window = mock.Mock()
        self.builder = MainWindowContextBarPageBuilder(
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            tool_state_service=self.tool_state_service,
            activate_bond_style_for_window=self.activate_bond_style_for_window,
            set_bond_length_for_window=self.set_bond_length_for_window,
        )

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_bond_label_for_state_maps_known_bond_styles(self) -> None:
        self.assertEqual(bond_label_for_state("single", 1), "Single")
        self.assertEqual(bond_label_for_state("hash", 1), "Hash")
        self.assertIsNone(bond_label_for_state("unknown", 1))

    def test_builder_returns_pages_and_wires_bond_template_arrow_actions(self) -> None:
        pages = self.builder.build(self.window)

        self.assertEqual(set(pages.pages), {"empty", "bond", "template", "arrow", "atom", "ring"})
        self.assertIn("Single", pages.bond_buttons)
        self.assertIn("curved_double", pages.arrow_buttons)
        self.assertIsNotNone(pages.bond_group)
        self.assertIsNotNone(pages.arrow_group)

        pages.bond_buttons["Hash"].click()

        self.activate_bond_style_for_window.assert_called_once_with(self.window, "Hash")
        length_button = next(
            button
            for button in pages.pages["bond"].findChildren(QToolButton)
            if button.toolTip() == "Set the default bond length"
        )
        length_button.click()
        self.set_bond_length_for_window.assert_called_once_with(self.window)

        template_button = next(
            button
            for button in pages.pages["template"].findChildren(QToolButton)
            if button.toolTip() == "Cyclopropane"
        )
        with mock.patch.object(self.insert_controller, "begin_ring_template_insert") as insert:
            template_button.click()

        insert.assert_called_once_with(3, style="regular")
        self.insert_controller_for_window.assert_called_once_with(self.window)

        pages.arrow_buttons["curved_double"].click()
        preset_button = next(
            button
            for button in pages.pages["arrow"].findChildren(QToolButton)
            if button.toolTip() == "Bold arrow preset"
        )
        preset_button.click()

        self.tool_state_service.set_arrow_type.assert_called_once_with(self.window, "Curved Double")
        self.tool_state_service.set_arrow_preset.assert_called_once_with(self.window, "Bold")
        self.tool_mode_controller_for_window.assert_called_once_with(self.window)

        sliders = pages.pages["arrow"].findChildren(QSlider)
        self.assertEqual([slider.value() for slider in sliders], [2, 40])
        sliders[0].setValue(5)
        sliders[1].setValue(25)
        self.tool_mode_controller.set_arrow_line_width.assert_called_once_with(5)
        self.tool_mode_controller.set_arrow_head_scale.assert_called_once_with(0.25)


if __name__ == "__main__":
    unittest.main()
