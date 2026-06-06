import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import (
        QApplication,
        QLineEdit,
        QMainWindow,
        QToolButton,
        QWidget,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_panel_toolbar import (
        MainWindowPanelToolbarCallbacks,
        build_panel_toolbar,
    )
    from ui.main_window_theme import TOOLBAR_ICON_SIZE
    from ui.main_window_ui_assembly_service import MainWindowUIAssemblyService


class _HarnessCanvas:
    def __init__(self) -> None:
        self.insert_controller = SimpleNamespace(begin_smiles_insert=mock.Mock())
        self.scene_transform_controller = SimpleNamespace(flip_selected_items=mock.Mock())
        self.tool_mode_controller = SimpleNamespace(
            get_atom_symbol=mock.Mock(return_value="N"),
            set_atom_symbol=mock.Mock(),
        )
        self.history_service = SimpleNamespace(undo=mock.Mock(), redo=mock.Mock())
        self.services = SimpleNamespace(
            insert_controller=self.insert_controller,
            scene_transform_controller=self.scene_transform_controller,
            tool_mode_controller=self.tool_mode_controller,
            history_service=self.history_service,
        )


class _HarnessWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.canvas = _HarnessCanvas()
        self.preview_3d = QWidget()
        self.save_canvas = mock.Mock()
        self.save_canvas_as = mock.Mock()
        self.load_canvas = mock.Mock()
        self.export_xyz = mock.Mock()
        self.export_figure = mock.Mock()
        self.toggle_preview_panel = mock.Mock()
        self.set_bond_length = mock.Mock()
        self.setup_sheet = mock.Mock()
        self.apply_color_preset = mock.Mock()
        self.apply_ring_fill_preset = mock.Mock()
        self._icon_factory = SimpleNamespace(
            icon_bond_length=self._blank_icon,
            icon_flip_h=self._blank_icon,
            icon_flip_v=self._blank_icon,
            icon_save=self._blank_icon,
            icon_open=self._blank_icon,
            icon_export_xyz=self._blank_icon,
            icon_preview_panel=self._blank_icon,
            icon_setup_sheet=self._blank_icon,
            icon_undo=self._blank_icon,
            icon_redo=self._blank_icon,
            icon_color=self._blank_icon,
            icon_ring_fill=self._blank_icon,
        )
        self.ui_references = SimpleNamespace(require_icon_factory=lambda: self._icon_factory)

    def _blank_icon(self) -> QIcon:
        return QIcon()

    def populate_palette_menu(self, menu, callback) -> None:
        action = menu.addAction("Black")
        action.triggered.connect(lambda checked=False: callback("#000000"))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for panel toolbar tests")
class MainWindowPanelToolbarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene_transform_controller_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.scene_transform_controller,
        )
        self.insert_controller_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.insert_controller,
        )
        self.tool_mode_controller_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.tool_mode_controller,
        )
        self.history_service_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.history_service,
        )
        self.panel_callbacks = MainWindowPanelToolbarCallbacks(
            save_canvas=mock.Mock(),
            save_canvas_as=mock.Mock(),
            load_canvas=mock.Mock(),
            export_figure=mock.Mock(),
            export_xyz=mock.Mock(),
            toggle_preview_panel=mock.Mock(),
            setup_sheet=mock.Mock(),
        )
        self.button_service = MainWindowUIAssemblyService(
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            history_service_for_window=self.history_service_for_window,
            build_tool_actions_for_window=mock.Mock(),
            panel_toolbar_callbacks=self.panel_callbacks,
        )

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_build_panel_toolbar_wires_actions_inputs_and_buttons(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_panel_toolbar(
            window,
            create_toolbar_button=self.button_service.create_toolbar_button,
            create_file_project_menu_button=self.button_service.create_file_project_menu_button,
            create_corner_menu_button=self.button_service.create_corner_menu_button,
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            history_service_for_window=self.history_service_for_window,
            callbacks=self.panel_callbacks,
        )

        self.assertEqual(assembly.panel_bar.objectName(), "topRoleToolbar")
        self.assertEqual(assembly.panel_bar.iconSize().width(), TOOLBAR_ICON_SIZE)
        self.assertEqual(assembly.save_button.toolTip(), "File")
        self.assertEqual(assembly.load_action.statusTip(), "Open a drawing or workbook")
        self.assertTrue(assembly.preview_panel_button.isCheckable())
        self.assertTrue(assembly.preview_panel_button.isChecked())
        self.assertIs(assembly.export_xyz_button, assembly.panel_bar.findChild(QToolButton, "export_xyz_button"))
        self.assertIs(assembly.setup_sheet_button, assembly.panel_bar.findChild(QToolButton, "setup_sheet_button"))
        self.assertIs(assembly.undo_button, assembly.panel_bar.findChild(QToolButton, "undo_button"))
        self.assertIs(assembly.redo_button, assembly.panel_bar.findChild(QToolButton, "redo_button"))

        assembly.save_action.trigger()
        assembly.save_as_action.trigger()
        assembly.load_action.trigger()
        export_figure_action = next(
            action for action in assembly.save_button.menu().actions() if action.text() == "Export Figure..."
        )
        export_figure_action.trigger()
        self.panel_callbacks.save_canvas.assert_called_once_with(window)
        self.panel_callbacks.save_canvas_as.assert_called_once_with(window)
        self.panel_callbacks.load_canvas.assert_called_once_with(window)
        self.panel_callbacks.export_figure.assert_called_once_with(window)
        window.save_canvas.assert_not_called()
        window.save_canvas_as.assert_not_called()
        window.load_canvas.assert_not_called()
        window.export_figure.assert_not_called()

        assembly.atom_input.setText("Cl")
        window.canvas.tool_mode_controller.set_atom_symbol.assert_called_with("Cl")

        smiles_input = next(
            widget
            for widget in assembly.panel_bar.findChildren(QLineEdit)
            if widget.placeholderText() == "SMILES..."
        )
        smiles_button = assembly.panel_bar.findChild(QToolButton, "smiles_render_button")
        smiles_input.setText("CCO")
        smiles_button.click()
        window.canvas.insert_controller.begin_smiles_insert.assert_called_once_with("CCO")

        assembly.export_xyz_button.click()
        assembly.preview_panel_button.click()
        assembly.setup_sheet_button.click()
        self.panel_callbacks.export_xyz.assert_called_once_with(window)
        self.panel_callbacks.toggle_preview_panel.assert_called_once_with(window, False)
        self.panel_callbacks.setup_sheet.assert_called_once_with(window)
        window.export_xyz.assert_not_called()
        window.toggle_preview_panel.assert_not_called()
        window.setup_sheet.assert_not_called()
        assembly.undo_button.click()
        assembly.redo_button.click()
        window.canvas.history_service.undo.assert_called_once_with()
        window.canvas.history_service.redo.assert_called_once_with()
        removed_tooltips = {"Bond Length", "Color", "Ring Fill"}
        self.assertFalse(
            any(button.toolTip() in removed_tooltips for button in assembly.panel_bar.findChildren(QToolButton))
        )
        window.set_bond_length.assert_not_called()

        flip_buttons = [
            button
            for button in assembly.panel_bar.findChildren(QToolButton)
            if button.toolTip().startswith("Flip")
        ]
        self.assertEqual(len(flip_buttons), 2)
        flip_buttons[0].click()
        flip_buttons[1].click()
        window.canvas.scene_transform_controller.flip_selected_items.assert_has_calls(
            [mock.call(horizontal=True), mock.call(horizontal=False)]
        )
        self.assertEqual(self.history_service_for_window.call_count, 2)


if __name__ == "__main__":
    unittest.main()
