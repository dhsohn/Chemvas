import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QPushButton,
        QSlider,
        QToolButton,
    )
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window tests")
class MainWindowDialogActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_open_arrow_settings_initial_values_and_signal_wiring(self) -> None:
        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Arrow Settings")

            combo = dialog.findChild(QComboBox)
            sliders = dialog.findChildren(QSlider)
            checks = dialog.findChildren(QCheckBox)

            self.assertIsNotNone(combo)
            self.assertEqual([combo.itemText(index) for index in range(combo.count())], ["Default", "Bold", "Fine"])
            self.assertEqual(combo.currentText(), "Default")

            width_slider = next(slider for slider in sliders if slider.minimum() == 1 and slider.maximum() == 6)
            head_slider = next(slider for slider in sliders if slider.minimum() == 10 and slider.maximum() == 60)
            snap_slider = next(slider for slider in sliders if slider.minimum() == 5 and slider.maximum() == 40)
            snap_check = next(check for check in checks if check.text() == "Curve Snap")
            symmetry_check = next(check for check in checks if check.text() == "Curve Symmetry")

            self.assertEqual(width_slider.value(), 2)
            self.assertEqual(head_slider.value(), 35)
            self.assertEqual(snap_slider.value(), 15)
            self.assertTrue(snap_check.isChecked())
            self.assertFalse(symmetry_check.isChecked())

            combo.setCurrentText("Fine")
            width_slider.setValue(4)
            head_slider.setValue(40)
            snap_slider.setValue(22)
            snap_check.setChecked(False)
            symmetry_check.setChecked(True)

            return QDialog.DialogCode.Accepted

        with (
            mock.patch.object(self.window, "_set_arrow_preset") as set_preset,
            mock.patch.object(self.window.canvas, "get_arrow_line_width", return_value=2.5),
            mock.patch.object(self.window.canvas, "get_arrow_head_scale", return_value=0.35),
            mock.patch.object(self.window.canvas, "get_curved_snap", return_value=True),
            mock.patch.object(self.window.canvas, "get_curved_symmetry", return_value=False),
            mock.patch.object(self.window.canvas, "get_curved_snap_step", return_value=0.15),
            mock.patch.object(self.window.canvas, "set_arrow_line_width") as set_width,
            mock.patch.object(self.window.canvas, "set_arrow_head_scale") as set_head,
            mock.patch.object(self.window.canvas, "set_curved_snap") as set_snap,
            mock.patch.object(self.window.canvas, "set_curved_symmetry") as set_symmetry,
            mock.patch.object(self.window.canvas, "set_curved_snap_step") as set_snap_step,
            mock.patch.object(QDialog, "exec", new=drive_dialog),
        ):
            self.window._open_arrow_settings()

        set_preset.assert_called_once_with("Fine")
        set_width.assert_called_once_with(4)
        set_head.assert_called_once_with(0.4)
        set_snap.assert_called_once_with(False)
        set_symmetry.assert_called_once_with(True)
        set_snap_step.assert_called_once_with(0.22)

    def test_set_bond_length_uses_dialog_controls_and_applies_confirmed_value(self) -> None:
        renderer = SimpleNamespace(style=SimpleNamespace(bond_length_px=24.0))

        def drive_dialog(dialog: QDialog):
            self.assertEqual(dialog.windowTitle(), "Bond Length")

            spin = dialog.findChild(QDoubleSpinBox)
            ok_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "OK")
            cancel_button = next(button for button in dialog.findChildren(QPushButton) if button.text() == "Cancel")
            up_button = dialog.findChild(QToolButton, "spinUpButton")
            down_button = dialog.findChild(QToolButton, "spinDownButton")

            self.assertIsNotNone(spin)
            self.assertIsNotNone(up_button)
            self.assertIsNotNone(down_button)
            self.assertEqual(spin.value(), 24.0)
            self.assertEqual(spin.minimum(), 10.0)
            self.assertEqual(spin.maximum(), 200.0)
            self.assertEqual(spin.decimals(), 1)

            up_button.click()
            up_button.click()
            down_button.click()
            self.assertEqual(spin.value(), 25.0)
            self.assertEqual(ok_button.text(), "OK")
            self.assertEqual(cancel_button.text(), "Cancel")
            ok_button.click()

            return QDialog.DialogCode.Accepted

        with (
            mock.patch.object(self.window.canvas, "renderer", new=renderer),
            mock.patch.object(self.window.canvas, "set_bond_length") as set_bond_length,
            mock.patch.object(QDialog, "exec", new=drive_dialog),
        ):
            self.window._set_bond_length()

        set_bond_length.assert_called_once_with(25.0)


if __name__ == "__main__":
    unittest.main()
