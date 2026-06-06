import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QAction, QIcon, QKeySequence, QPixmap
    from PyQt6.QtWidgets import (
        QApplication,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QToolBar,
        QToolButton,
        QWidget,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.main_window_config import LEFT_TOOLBAR_ACTION_ORDER
    from ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks
    from ui.main_window_theme import MAIN_WINDOW_STYLESHEET
    from ui.main_window_toolbar_buttons import ArrowButton, CornerMenuButton
    from ui.main_window_ui_assembly_service import (
        MainWindowUIAssemblyService,
    )


class _HarnessCanvas:
    def __init__(self) -> None:
        self.undo = mock.Mock()
        self.redo = mock.Mock()
        self.flip_horizontal = mock.Mock()
        self.flip_vertical = mock.Mock()
        self.begin_smiles_insert = mock.Mock()
        self.insert_controller = SimpleNamespace(begin_smiles_insert=mock.Mock())
        self.scene_transform_controller = SimpleNamespace(flip_selected_items=mock.Mock())
        self.tool_mode_controller = SimpleNamespace(
            get_atom_symbol=mock.Mock(return_value="N"),
            set_atom_symbol=mock.Mock(),
        )
        self.history_service = SimpleNamespace(
            undo=mock.Mock(),
            redo=mock.Mock(),
        )
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
            icon_templates=self._blank_icon,
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

    def populate_template_menu(self, menu: QMenu) -> None:
        menu.addAction("Template")

    def populate_arrow_menu(self, menu: QMenu) -> None:
        menu.addAction("Arrow")

    def populate_palette_menu(self, menu: QMenu, callback) -> None:
        action = menu.addAction("Black")
        action.triggered.connect(lambda checked=False: callback("#000000"))


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for main window UI assembly tests")
class MainWindowUIAssemblyServiceTest(unittest.TestCase):
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
        self.build_tool_actions_for_window = mock.Mock(side_effect=self._build_tool_actions_for_window)
        self.panel_toolbar_callbacks = MainWindowPanelToolbarCallbacks(
            save_canvas=mock.Mock(),
            save_canvas_as=mock.Mock(),
            load_canvas=mock.Mock(),
            export_figure=mock.Mock(),
            export_xyz=mock.Mock(),
            toggle_preview_panel=mock.Mock(),
            setup_sheet=mock.Mock(),
            populate_palette_menu=mock.Mock(),
            apply_color_preset=mock.Mock(),
            apply_ring_fill_preset=mock.Mock(),
            set_bond_length=mock.Mock(),
        )
        self.service = MainWindowUIAssemblyService(
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            history_service_for_window=self.history_service_for_window,
            build_tool_actions_for_window=self.build_tool_actions_for_window,
            panel_toolbar_callbacks=self.panel_toolbar_callbacks,
        )

    def tearDown(self) -> None:
        self.app.processEvents()

    def _build_tool_actions_for_window(self, window, tool_group) -> dict[str, QAction]:
        actions: dict[str, QAction] = {}
        for key in [*LEFT_TOOLBAR_ACTION_ORDER, "arrow", "ts_bracket"]:
            if key in actions:
                continue
            action = QAction(key, window)
            action.setCheckable(True)
            tool_group.addAction(action)
            actions[key] = action
        return actions

    def _filled_icon(self) -> QIcon:
        pixmap = QPixmap(8, 8)
        pixmap.fill(Qt.GlobalColor.black)
        return QIcon(pixmap)

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
        self.assertEqual(button.statusTip(), "Load")
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
        self.assertEqual(button.statusTip(), "Save")
        self.assertEqual(button.styleSheet(), "padding: 0;")
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.assertEqual([action.text() for action in button.menu().actions()], ["Save As..."])

    def test_button_factories_cover_icon_only_and_paint_paths(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)
        icon = self._filled_icon()

        toolbar_button = self.service.create_toolbar_button(
            icon=icon,
            tooltip="Plain",
        )
        self.assertEqual(toolbar_button.toolTip(), "Plain")
        self.assertEqual(toolbar_button.statusTip(), "Plain")
        self.assertTrue(toolbar_button.autoRaise())
        self.assertFalse(toolbar_button.icon().isNull())
        toolbar_button.click()

        corner_button = self.service.create_corner_menu_button(
            icon=icon,
            tooltip="Palette",
            style_sheet="padding: 1px;",
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=lambda menu: menu.addAction("Pick"),
        )
        self.assertIsNone(corner_button.defaultAction())
        self.assertFalse(corner_button.icon().isNull())
        self.assertEqual([action.text() for action in corner_button.menu().actions()], ["Pick"])

        up_button = ArrowButton("up", owner)
        down_button = ArrowButton("down", owner)
        menu_indicator = CornerMenuButton(owner)
        self.assertTrue(up_button.autoRaise())
        self.assertEqual(up_button.focusPolicy(), Qt.FocusPolicy.NoFocus)

        for widget, size in ((up_button, (8, 6)), (down_button, (20, 20)), (menu_indicator, (18, 18))):
            widget.resize(*size)
            widget.show()
            self.app.processEvents()
            pixmap = widget.grab()
            self.assertFalse(pixmap.isNull())

    def test_create_save_menu_button_uses_save_as_action_menu(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        save_action = QAction("Save", owner)
        save_as_action = QAction("Save As...", owner)

        button = self.service.create_save_menu_button(save_action, save_as_action)

        self.assertIs(button.defaultAction(), save_action)
        self.assertEqual(button.toolTip(), "Save")
        self.assertEqual(button.statusTip(), "Save")
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.assertEqual(button.menu().actions(), [save_as_action])

    def test_create_file_project_menu_button_uses_file_project_actions(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        save_action = QAction("Save", owner)
        load_action = QAction("Load", owner)
        save_as_action = QAction("Save As...", owner)

        export_action = QAction("Export Figure...", owner)
        button = self.service.create_file_project_menu_button(
            save_action, load_action, save_as_action, export_action
        )

        self.assertIs(button.defaultAction(), save_action)
        self.assertEqual(button.toolTip(), "File")
        self.assertEqual(button.statusTip(), "Save, load, export, or save as the current file")
        self.assertEqual(button.popupMode(), QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        non_separator = [action for action in button.menu().actions() if not action.isSeparator()]
        self.assertEqual(
            non_separator, [load_action, save_action, save_as_action, export_action]
        )
        self.assertEqual(sum(1 for action in button.menu().actions() if action.isSeparator()), 1)

    def test_init_toolbars_builds_bars_and_wires_inputs(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_toolbars(window)

        self.assertEqual(len(window.findChildren(QToolBar)), 2)
        self.assertEqual(assembly.left_bar.orientation(), Qt.Orientation.Vertical)
        self.assertEqual(
            [action.text() for action in assembly.left_bar.actions() if not action.isSeparator()],
            [
                "select",
                "bond",
                "text",
                "mark_plus",
                "mark_minus",
                "mark_radical",
                "benzene",
                "template",
                "arrow",
                "ts_bracket",
                "perspective",
            ],
        )
        self.assertEqual(
            sum(1 for action in assembly.left_bar.actions() if action.isSeparator()),
            3,
        )
        self.assertTrue(assembly.tool_actions["bond"].isChecked())
        self.assertEqual(assembly.atom_input.text(), "N")
        self.assertIs(assembly.save_button.defaultAction(), assembly.save_action)
        menu_actions = [
            action for action in assembly.save_button.menu().actions() if not action.isSeparator()
        ]
        self.assertEqual(
            menu_actions[:3],
            [assembly.load_action, assembly.save_action, assembly.save_as_action],
        )
        self.assertEqual(menu_actions[3].text(), "Export Figure...")
        self.assertEqual(assembly.save_button.toolTip(), "File")
        self.assertEqual(assembly.load_action.statusTip(), "Open a drawing or workbook")
        self.assertEqual(assembly.save_action.statusTip(), "Save the current drawing")
        self.assertEqual(assembly.save_as_action.statusTip(), "Save the current drawing to a new file")
        self.assertNotIn(
            "Bond Length",
            [button.toolTip() for button in assembly.left_bar.findChildren(QToolButton)],
        )
        self.assertNotIn(
            "Load",
            [button.toolTip() for button in assembly.panel_bar.findChildren(QToolButton)],
        )
        self.assertIn(
            "Bond Length",
            [button.toolTip() for button in assembly.panel_bar.findChildren(QToolButton)],
        )

        section_labels = [
            label.text()
            for label in assembly.panel_bar.findChildren(QLabel)
            if label.objectName() == "toolbarSectionLabel"
        ]
        # Top panel-bar section labels were removed; icon groups rely on
        # separators + tooltips instead.
        self.assertEqual(section_labels, [])

        assembly.atom_input.setText("Cl")
        window.canvas.tool_mode_controller.set_atom_symbol.assert_called_with("Cl")
        self.tool_mode_controller_for_window.assert_called_once_with(window)

        smiles_input = next(
            widget for widget in assembly.panel_bar.findChildren(QLineEdit) if widget.placeholderText() == "SMILES..."
        )
        smiles_button = assembly.panel_bar.findChild(QToolButton, "smiles_render_button")
        self.assertIsNotNone(smiles_button)
        self.assertEqual(smiles_button.text(), "Insert")
        self.assertEqual(smiles_button.statusTip(), "Insert the typed SMILES structure")
        self.assertIs(assembly.export_xyz_button, assembly.panel_bar.findChild(QToolButton, "export_xyz_button"))
        self.assertIs(
            assembly.preview_panel_button,
            assembly.panel_bar.findChild(QToolButton, "preview_panel_button"),
        )
        self.assertTrue(assembly.preview_panel_button.isCheckable())
        self.assertTrue(assembly.preview_panel_button.isChecked())
        self.assertIs(assembly.setup_sheet_button, assembly.panel_bar.findChild(QToolButton, "setup_sheet_button"))
        self.assertIs(assembly.undo_button, assembly.panel_bar.findChild(QToolButton, "undo_button"))
        self.assertIs(assembly.redo_button, assembly.panel_bar.findChild(QToolButton, "redo_button"))

        smiles_input.setText("CCO")
        smiles_button.click()
        window.canvas.insert_controller.begin_smiles_insert.assert_called_once_with("CCO")
        self.insert_controller_for_window.assert_called_once_with(window)
        self.scene_transform_controller_for_window.assert_called_once_with(window)
        assembly.save_action.trigger()
        assembly.save_as_action.trigger()
        assembly.load_action.trigger()
        export_figure_action = next(
            action for action in assembly.save_button.menu().actions() if action.text() == "Export Figure..."
        )
        export_figure_action.trigger()
        self.panel_toolbar_callbacks.save_canvas.assert_called_once_with(window)
        self.panel_toolbar_callbacks.save_canvas_as.assert_called_once_with(window)
        self.panel_toolbar_callbacks.load_canvas.assert_called_once_with(window)
        self.panel_toolbar_callbacks.export_figure.assert_called_once_with(window)
        window.save_canvas.assert_not_called()
        window.save_canvas_as.assert_not_called()
        window.load_canvas.assert_not_called()
        window.export_figure.assert_not_called()
        assembly.export_xyz_button.click()
        assembly.preview_panel_button.click()
        assembly.setup_sheet_button.click()
        self.panel_toolbar_callbacks.export_xyz.assert_called_once_with(window)
        self.panel_toolbar_callbacks.toggle_preview_panel.assert_called_once_with(window, False)
        self.panel_toolbar_callbacks.setup_sheet.assert_called_once_with(window)
        window.export_xyz.assert_not_called()
        window.toggle_preview_panel.assert_not_called()
        window.setup_sheet.assert_not_called()
        assembly.undo_button.click()
        assembly.redo_button.click()
        window.canvas.history_service.undo.assert_called_once_with()
        window.canvas.history_service.redo.assert_called_once_with()
        self.assertEqual(self.history_service_for_window.call_args_list, [mock.call(window), mock.call(window)])

    def test_apply_theme_sets_stylesheet(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)

        self.service.apply_theme(window)

        self.assertEqual(window.styleSheet(), MAIN_WINDOW_STYLESHEET)


if __name__ == "__main__":
    unittest.main()
