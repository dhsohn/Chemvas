import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QAction, QIcon
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
    from chemvas.shell.theme import TOOLBAR_ICON_SIZE
    from chemvas.ui.main_window_config import TOOLBAR_TOOL_ACTION_ORDER
    from chemvas.ui.main_window_panel_toolbar import (
        MainWindowPanelToolbarCallbacks,
        build_panel_toolbar,
    )
    from chemvas.ui.main_window_ui_assembly_service import MainWindowUIAssemblyService


class _HarnessCanvas:
    def __init__(self) -> None:
        self.insert_controller = SimpleNamespace(begin_smiles_insert=mock.Mock())
        self.scene_transform_controller = SimpleNamespace(
            flip_selected_items=mock.Mock()
        )
        self.tool_mode_controller = SimpleNamespace(
            get_atom_symbol=mock.Mock(return_value="N"),
            set_atom_symbol=mock.Mock(),
        )
        self.history_service = SimpleNamespace(undo=mock.Mock(), redo=mock.Mock())
        self.services = canvas_runtime_services(
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
        self.open_preview_window = mock.Mock()
        self.set_bond_length = mock.Mock()
        self.setup_sheet = mock.Mock()
        self.apply_color_preset = mock.Mock()
        self.apply_ring_fill_preset = mock.Mock()
        self._icon_factory = SimpleNamespace(
            icon_flip_h=self._blank_icon,
            icon_flip_v=self._blank_icon,
            icon_rotate=self._blank_icon,
            icon_color=self._blank_icon,
            icon_ring_fill=self._blank_icon,
            icon_orbital=self._blank_icon,
        )
        self.ui_references = SimpleNamespace(
            require_icon_factory=lambda: self._icon_factory
        )

    def _blank_icon(self) -> QIcon:
        return QIcon()


def _build_tool_actions(window, tool_group) -> dict[str, QAction]:
    actions: dict[str, QAction] = {}
    for key in TOOLBAR_TOOL_ACTION_ORDER:
        action = QAction(key, window)
        action.setCheckable(True)
        tool_group.addAction(action)
        actions[key] = action
    return actions


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for panel toolbar tests"
)
class MainWindowPanelToolbarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.scene_transform_controller_for_window = mock.Mock(
            side_effect=lambda window: (
                window.canvas.services.scene_operations.scene_transform_controller
            ),
        )
        self.insert_controller_for_window = mock.Mock(
            side_effect=lambda window: (
                window.canvas.services.structure.insert_controller
            ),
        )
        self.history_service_for_window = mock.Mock(
            side_effect=lambda window: window.canvas.services.history_service,
        )
        self.build_tool_actions = mock.Mock(side_effect=_build_tool_actions)
        self.panel_callbacks = MainWindowPanelToolbarCallbacks(
            save_canvas=mock.Mock(),
            save_canvas_as=mock.Mock(),
            load_canvas=mock.Mock(),
            export_figure=mock.Mock(),
            export_mol=mock.Mock(),
            open_preview_window=mock.Mock(),
            new_canvas=mock.Mock(),
            show_rotate_options=mock.Mock(),
            set_note_font_family=mock.Mock(),
            open_recent_path=mock.Mock(),
        )
        self.button_service = MainWindowUIAssemblyService(
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            build_tool_actions_for_window=mock.Mock(),
            panel_toolbar_callbacks=self.panel_callbacks,
        )

    def tearDown(self) -> None:
        self.app.processEvents()

    def _toolbar_widget_groups(self, toolbar):
        groups = []
        group = []
        for action in toolbar.actions():
            if action.isSeparator():
                if group:
                    groups.append(group)
                    group = []
                continue
            widget = (
                action.defaultWidget()
                if hasattr(action, "defaultWidget")
                else toolbar.widgetForAction(action)
            )
            if widget is None:
                continue
            if isinstance(widget, QLineEdit):
                group.append(widget.placeholderText())
            elif isinstance(widget, QToolButton):
                group.append(widget.objectName() or widget.toolTip())
        if group:
            groups.append(group)
        return groups

    def test_build_panel_toolbar_wires_actions_inputs_and_buttons(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = build_panel_toolbar(
            window,
            create_toolbar_button=self.button_service.create_toolbar_button,
            build_tool_actions=self.build_tool_actions,
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            callbacks=self.panel_callbacks,
        )

        self.assertEqual(assembly.panel_bar.objectName(), "topRoleToolbar")
        self.assertEqual(assembly.panel_bar.iconSize().width(), TOOLBAR_ICON_SIZE)
        self.assertEqual(list(assembly.tool_actions), TOOLBAR_TOOL_ACTION_ORDER)
        self.assertTrue(assembly.tool_actions["bond"].isChecked())
        # Document/history/preview commands moved to the menu bar; the toolbar
        # keeps only drawing-related controls.
        for removed_name in (
            "export_xyz_button",
            "setup_sheet_button",
            "new_canvas_button",
            "open_button",
            "preview_panel_button",
            "undo_button",
            "redo_button",
        ):
            self.assertIsNone(
                assembly.panel_bar.findChild(QToolButton, removed_name),
                removed_name,
            )
        self.assertEqual(
            self._toolbar_widget_groups(assembly.panel_bar)[0],
            [
                "toolButton_select",
                "toolButton_perspective",
                "toolButton_text",
                "toolButton_bond",
                "toolButton_benzene",
                "toolButton_arrow",
                "toolButton_ts_bracket",
            ],
        )
        self.assertIn(
            ["toolButton_mark", "toolButton_orbital"],
            self._toolbar_widget_groups(assembly.panel_bar),
        )
        # Shape sits just right of the note (Text) tool, in the same partition
        # as Color; the eraser closes that partition.
        self.assertIn(
            [
                f"toolButton_{key}"
                for key in ("note", "shape", "color", "ring_fill", "delete")
            ],
            self._toolbar_widget_groups(assembly.panel_bar),
        )
        self.assertIn(
            ["flip_horizontal_button", "flip_vertical_button", "rotate_button"],
            self._toolbar_widget_groups(assembly.panel_bar),
        )
        # The SMILES quick-insert bar closes the toolbar. Its "SMILES" QLabel is
        # neither a tool button nor a line edit, so the widget group is just the
        # input placeholder and Render button.
        self.assertEqual(
            self._toolbar_widget_groups(assembly.panel_bar)[-1],
            ["CC(=O)Oc1ccccc1C(=O)O", "smiles_render_button"],
        )
        primary_button_names = (
            "toolButton_select",
            "toolButton_perspective",
            "toolButton_text",
            "toolButton_bond",
            "toolButton_benzene",
            "toolButton_arrow",
            "toolButton_ts_bracket",
        )
        primary_buttons = [
            assembly.panel_bar.findChild(QToolButton, name)
            for name in primary_button_names
        ]
        self.assertEqual(
            [button.text() for button in primary_buttons],
            [""] * len(primary_button_names),
        )
        self.assertTrue(
            all(button.width() == button.height() for button in primary_buttons)
        )
        note_button = assembly.panel_bar.findChild(QToolButton, "toolButton_note")
        self.assertIsNotNone(note_button.menu())
        self.assertIs(note_button.defaultAction(), assembly.tool_actions["note"])
        # Each font option is previewed in its own family.
        font_actions = note_button.menu().actions()
        self.assertTrue(font_actions)
        self.assertTrue(
            all(action.font().family() == action.text() for action in font_actions)
        )
        line_edits = assembly.panel_bar.findChildren(QLineEdit)
        self.assertEqual(
            [line_edit.objectName() for line_edit in line_edits], ["contextSmilesInput"]
        )
        self.assertIsNone(assembly.panel_bar.findChild(QLineEdit, "atomInput"))

        window.canvas.insert_controller.begin_smiles_insert.assert_not_called()
        window.save_canvas.assert_not_called()
        window.load_canvas.assert_not_called()
        window.export_xyz.assert_not_called()
        window.open_preview_window.assert_not_called()
        window.setup_sheet.assert_not_called()
        removed_tooltips = {"Bond Length"}
        self.assertFalse(
            any(
                button.toolTip() in removed_tooltips
                for button in assembly.panel_bar.findChildren(QToolButton)
            )
        )
        window.set_bond_length.assert_not_called()

        flip_buttons = [
            button
            for button in assembly.panel_bar.findChildren(QToolButton)
            if button.toolTip().startswith("Flip")
        ]
        self.assertEqual(len(flip_buttons), 2)
        self.assertEqual(
            [button.objectName() for button in flip_buttons],
            ["flip_horizontal_button", "flip_vertical_button"],
        )
        flip_buttons[0].click()
        flip_buttons[1].click()
        window.canvas.scene_transform_controller.flip_selected_items.assert_has_calls(
            [mock.call(horizontal=True), mock.call(horizontal=False)]
        )


if __name__ == "__main__":
    unittest.main()
