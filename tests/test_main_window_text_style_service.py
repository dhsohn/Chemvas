import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor

from chemvas.ui.main_window_text_style_service import MainWindowTextStyleService


class MainWindowTextStyleServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.style_controller = mock.Mock()
        self.window = SimpleNamespace()
        self.style_controller_for_window = mock.Mock(return_value=self.style_controller)
        self.service = MainWindowTextStyleService(
            style_controller_for_window=self.style_controller_for_window,
        )

    def test_color_actions_apply_only_valid_colors_and_forward_dialog_metadata(
        self,
    ) -> None:
        valid = QColor("#112233")
        invalid = QColor()
        get_text_color = mock.Mock(return_value=valid)
        get_box_color = mock.Mock(return_value=invalid)
        get_border_color = mock.Mock(return_value=invalid)

        self.service.set_text_color(self.window, get_color=get_text_color)
        self.service.set_note_box_color(self.window, get_color=get_box_color)
        self.service.set_note_border_color(self.window, get_color=get_border_color)

        self.style_controller.set_text_color.assert_called_once_with(valid)
        self.style_controller.set_note_box_color.assert_not_called()
        self.style_controller.set_note_border_color.assert_not_called()
        self.assertEqual(
            self.style_controller_for_window.call_args_list, [mock.call(self.window)]
        )
        get_text_color.assert_called_once_with(parent=self.window, title="Text Color")
        get_box_color.assert_called_once_with(parent=self.window, title="Box Color")
        get_border_color.assert_called_once_with(
            parent=self.window, title="Border Color"
        )

    def test_set_text_preset_dispatches_supported_presets_only(self) -> None:
        self.service.set_text_preset(self.window, "ACS")
        self.service.set_text_preset(self.window, "Paper Thin")
        self.service.set_text_preset(self.window, "Paper Bold")
        self.service.set_text_preset(self.window, "Unknown")

        self.style_controller.apply_text_preset_acs.assert_called_once_with()
        self.style_controller.apply_text_preset_paper_thin.assert_called_once_with()
        self.style_controller.apply_text_preset_paper_bold.assert_called_once_with()
        self.assertEqual(self.style_controller_for_window.call_count, 3)
        self.assertEqual(
            self.style_controller.method_calls[-3:],
            [
                mock.call.apply_text_preset_acs(),
                mock.call.apply_text_preset_paper_thin(),
                mock.call.apply_text_preset_paper_bold(),
            ],
        )
