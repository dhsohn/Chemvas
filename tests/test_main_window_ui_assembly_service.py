import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction, QIcon, QKeySequence
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDockWidget,
        QLineEdit,
        QMainWindow,
        QMenu,
        QSlider,
        QToolBar,
        QToolButton,
        QWidget,
    )
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from ui.main_window import MainWindow
    from ui.main_window_config import LEFT_TOOLBAR_ACTION_ORDER
    from ui.main_window_theme import MAIN_WINDOW_STYLESHEET
    from ui.main_window_ui_assembly_service import MainWindowUIAssemblyService


class _HarnessCanvas:
    def __init__(self) -> None:
        self.undo = mock.Mock()
        self.redo = mock.Mock()
        self.flip_horizontal = mock.Mock()
        self.flip_vertical = mock.Mock()
        self.begin_smiles_insert = mock.Mock()
        self.get_atom_symbol = mock.Mock(return_value="N")
        self.set_atom_symbol = mock.Mock()


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.canvas = _HarnessCanvas()
        self.preview_3d = QWidget()
        self._save_canvas = mock.Mock()
        self._save_canvas_as = mock.Mock()
        self._load_canvas = mock.Mock()
        self._export_xyz = mock.Mock()
        self._set_bond_length = mock.Mock()
        self._apply_color_preset = mock.Mock()
        self._apply_ring_fill_preset = mock.Mock()

    def _build_tool_actions(self, tool_group) -> dict[str, QAction]:
        actions: dict[str, QAction] = {}
        for key in [*LEFT_TOOLBAR_ACTION_ORDER, "arrow", "ts_bracket"]:
            if key in actions:
                continue
            action = QAction(key, self)
            action.setCheckable(True)
            tool_group.addAction(action)
            actions[key] = action
        return actions

    def _blank_icon(self) -> QIcon:
        return QIcon()

    _icon_templates = _blank_icon
    _icon_bond_length = _blank_icon
    _icon_flip_h = _blank_icon
    _icon_flip_v = _blank_icon
    _icon_save = _blank_icon
    _icon_open = _blank_icon
    _icon_export_xyz = _blank_icon
    _icon_undo = _blank_icon
    _icon_redo = _blank_icon
    _icon_color = _blank_icon
    _icon_ring_fill = _blank_icon

    def _populate_template_menu(self, menu: QMenu) -> None:
        menu.addAction("Template")

    def _populate_arrow_menu(self, menu: QMenu) -> None:
        menu.addAction("Arrow")

    def _populate_palette_menu(self, menu: QMenu, callback) -> None:
        action = menu.addAction("Black")
        action.triggered.connect(lambda checked=False: callback("#000000"))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window UI assembly tests")
class MainWindowUIAssemblyServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.service = MainWindowUIAssemblyService()

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_create_toolbar_button_sets_properties_and_callback(self) -> None:
        callback = mock.Mock()
        shortcut = QKeySequence("Ctrl+L")

        button = self.service.create_toolbar_button(
            icon=QIcon(),
            tooltip="Load",
            callback=callback,
            shortcut=shortcut,
            text="Load",
            object_name="load_button",
            style_sheet="color: red;",
            auto_raise=False,
            cursor=Qt.CursorShape.PointingHandCursor,
        )

        self.assertEqual(button.toolTip(), "Load")
        self.assertEqual(button.text(), "Load")
        self.assertEqual(button.objectName(), "load_button")
        self.assertEqual(button.styleSheet(), "color: red;")
        self.assertFalse(button.autoRaise())
        self.assertEqual(button.cursor().shape(), Qt.CursorShape.PointingHandCursor)

        button.click()
        callback.assert_called_once_with(False)

    def test_create_corner_menu_button_prefers_default_action_and_builds_menu(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        save_action = QAction("Save", owner)

        button = self.service.create_corner_menu_button(
            icon=QIcon(),
            tooltip="Save",
            style_sheet="padding: 0;",
            popup_mode=QToolButton.ToolButtonPopupMode.MenuButtonPopup,
            menu_builder=lambda menu: menu.addAction("Save As..."),
            default_action=save_action,
        )

        self.assertIs(button.defaultAction(), save_action)
        self.assertEqual(button.toolTip(), "Save")
        self.assertEqual(button.styleSheet(), "padding: 0;")
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.assertEqual([action.text() for action in button.menu().actions()], ["Save As..."])

    def test_create_save_menu_button_uses_save_as_action_menu(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        save_action = QAction("Save", owner)
        save_as_action = QAction("Save As...", owner)

        button = self.service.create_save_menu_button(save_action, save_as_action)

        self.assertIs(button.defaultAction(), save_action)
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.assertEqual(button.menu().actions(), [save_as_action])

    def test_init_toolbars_builds_bars_and_wires_inputs(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_toolbars(window)

        self.assertEqual(len(window.findChildren(QToolBar)), 2)
        self.assertEqual(assembly.left_bar.orientation(), Qt.Orientation.Vertical)
        self.assertTrue(assembly.tool_actions["bond"].isChecked())
        self.assertEqual(assembly.atom_input.text(), "N")
        self.assertIs(assembly.save_button.defaultAction(), assembly.save_action)
        self.assertEqual(assembly.save_button.menu().actions(), [assembly.save_as_action])

        assembly.atom_input.setText("Cl")
        window.canvas.set_atom_symbol.assert_called_with("Cl")

        smiles_input = next(
            widget for widget in assembly.panel_bar.findChildren(QLineEdit) if widget.placeholderText() == "SMILES..."
        )
        smiles_button = assembly.panel_bar.findChild(QToolButton, "smiles_render_button")
        self.assertIsNotNone(smiles_button)

        smiles_input.setText("CCO")
        smiles_button.click()
        window.canvas.begin_smiles_insert.assert_called_once_with("CCO")

    def test_init_panels_builds_locked_preview_dock(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_panels(window)

        self.assertIs(assembly.splitter.widget(0), window.preview_3d)
        self.assertEqual(assembly.splitter.count(), 1)
        self.assertEqual(assembly.dock.allowedAreas(), Qt.DockWidgetArea.RightDockWidgetArea)
        self.assertEqual(assembly.dock.minimumWidth(), 320)
        self.assertEqual(assembly.dock.maximumWidth(), 420)
        self.assertFalse(
            bool(
                assembly.dock.features()
                & QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
        )
        self.assertEqual(assembly.dock.titleBarWidget().height(), 0)

    def test_apply_theme_sets_stylesheet(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)

        self.service.apply_theme(window)

        self.assertEqual(window.styleSheet(), MAIN_WINDOW_STYLESHEET)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window UI assembly tests")
class MainWindowUIAssemblyArrowDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.service = MainWindowUIAssemblyService()
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

            dialog.accept()
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
            self.service.open_arrow_settings(self.window)

        set_preset.assert_called_once_with("Fine")
        set_width.assert_called_once_with(4)
        set_head.assert_called_once_with(0.4)
        set_snap.assert_called_once_with(False)
        set_symmetry.assert_called_once_with(True)
        set_snap_step.assert_called_once_with(0.22)


if __name__ == "__main__":
    unittest.main()
