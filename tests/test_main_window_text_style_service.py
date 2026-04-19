import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QColor
except ModuleNotFoundError:
    QColor = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QColor is not None:
    from ui.main_window_text_style_service import MainWindowTextStyleService


@unittest.skipUnless(QColor is not None, "PyQt6 is required for main window text style service tests")
class MainWindowTextStyleServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.window = SimpleNamespace(canvas=mock.Mock())
        self.service = MainWindowTextStyleService()

    def test_color_actions_apply_only_valid_colors_and_forward_dialog_metadata(self) -> None:
        valid = QColor("#112233")
        invalid = QColor()
        get_text_color = mock.Mock(return_value=valid)
        get_box_color = mock.Mock(return_value=invalid)
        get_border_color = mock.Mock(return_value=invalid)

        self.service.set_text_color(self.window, get_color=get_text_color)
        self.service.set_note_box_color(self.window, get_color=get_box_color)
        self.service.set_note_border_color(self.window, get_color=get_border_color)

        self.window.canvas.set_text_color.assert_called_once_with(valid)
        self.window.canvas.set_note_box_color.assert_not_called()
        self.window.canvas.set_note_border_color.assert_not_called()
        get_text_color.assert_called_once_with(parent=self.window, title="Text Color")
        get_box_color.assert_called_once_with(parent=self.window, title="Box Color")
        get_border_color.assert_called_once_with(parent=self.window, title="Border Color")

    def test_set_text_align_maps_labels_and_falls_back_to_left(self) -> None:
        self.service.set_text_align(self.window, "Left")
        self.service.set_text_align(self.window, "Center")
        self.service.set_text_align(self.window, "Right")
        self.service.set_text_align(self.window, "Unexpected")

        self.assertEqual(
            [call.args[0] for call in self.window.canvas.set_text_alignment.call_args_list],
            ["left", "center", "right", "left"],
        )

    def test_set_text_preset_dispatches_supported_presets_only(self) -> None:
        self.service.set_text_preset(self.window, "ACS")
        self.service.set_text_preset(self.window, "Paper Thin")
        self.service.set_text_preset(self.window, "Paper Bold")
        self.service.set_text_preset(self.window, "Unknown")

        self.window.canvas.apply_text_preset_acs.assert_called_once_with()
        self.window.canvas.apply_text_preset_paper_thin.assert_called_once_with()
        self.window.canvas.apply_text_preset_paper_bold.assert_called_once_with()
        self.assertEqual(self.window.canvas.method_calls[-3:], [
            mock.call.apply_text_preset_acs(),
            mock.call.apply_text_preset_paper_thin(),
            mock.call.apply_text_preset_paper_bold(),
        ])


if __name__ == "__main__":
    unittest.main()
