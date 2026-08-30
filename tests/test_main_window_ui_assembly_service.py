import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

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
    from chemvas.shell.theme import MAIN_WINDOW_STYLESHEET
    from chemvas.shell.toolbar_buttons import ArrowButton, CornerMenuButton
    from chemvas.ui.main_window_config import TOOLBAR_TOOL_ACTION_ORDER
    from chemvas.ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks
    from chemvas.ui.main_window_ui_assembly_service import (
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
        self.scene_transform_controller = SimpleNamespace(
            flip_selected_items=mock.Mock()
        )
        self.tool_mode_controller = SimpleNamespace(
            get_atom_symbol=mock.Mock(return_value="N"),
            set_atom_symbol=mock.Mock(),
        )
        self.history_service = SimpleNamespace(
            undo=mock.Mock(),
            redo=mock.Mock(),
        )
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


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for main window UI assembly tests"
)
class MainWindowUIAssemblyServiceTest(unittest.TestCase):
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
        self.build_tool_actions_for_window = mock.Mock(
            side_effect=self._build_tool_actions_for_window
        )
        self.panel_toolbar_callbacks = MainWindowPanelToolbarCallbacks(
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
        self.service = MainWindowUIAssemblyService(
            scene_transform_controller_for_window=self.scene_transform_controller_for_window,
            insert_controller_for_window=self.insert_controller_for_window,
            build_tool_actions_for_window=self.build_tool_actions_for_window,
            panel_toolbar_callbacks=self.panel_toolbar_callbacks,
        )

    def tearDown(self) -> None:
        self.app.processEvents()

    def _build_tool_actions_for_window(self, window, tool_group) -> dict[str, QAction]:
        actions: dict[str, QAction] = {}
        for key in TOOLBAR_TOOL_ACTION_ORDER:
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

    def _menu(self, menu_bar, title: str) -> QMenu:
        return next(
            menu
            for action in menu_bar.actions()
            if (menu := action.menu()) is not None and menu.title() == title
        )

    def _menu_action(self, menu: QMenu, text: str) -> QAction:
        return next(action for action in menu.actions() if action.text() == text)

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

    def test_button_factories_cover_icon_only_and_paint_paths(self) -> None:
        owner = QWidget()
        self.addCleanup(owner.close)

        toolbar_button = self.service.create_toolbar_button(
            icon=self._filled_icon(),
            tooltip="Plain",
        )
        self.assertEqual(toolbar_button.toolTip(), "Plain")
        self.assertEqual(toolbar_button.statusTip(), "Plain")
        self.assertTrue(toolbar_button.autoRaise())
        self.assertFalse(toolbar_button.icon().isNull())
        toolbar_button.click()

        up_button = ArrowButton("up", owner)
        down_button = ArrowButton("down", owner)
        menu_indicator = CornerMenuButton(owner)
        self.assertTrue(up_button.autoRaise())
        self.assertEqual(up_button.focusPolicy(), Qt.FocusPolicy.NoFocus)

        for widget, size in (
            (up_button, (8, 6)),
            (down_button, (20, 20)),
            (menu_indicator, (18, 18)),
        ):
            widget.resize(*size)
            widget.show()
            self.app.processEvents()
            pixmap = widget.grab()
            self.assertFalse(pixmap.isNull())

    def test_init_toolbars_builds_slim_drawing_bar(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_toolbars(window)

        self.assertEqual(len(window.findChildren(QToolBar)), 1)
        tool_action_texts = [
            action.text()
            for action in assembly.panel_bar.actions()
            if not action.isSeparator() and action.text() in TOOLBAR_TOOL_ACTION_ORDER
        ]
        # The "note" tool is embedded as a font-dropdown menu button (a widget),
        # so it is not added as a plain action on the toolbar.
        self.assertEqual(
            tool_action_texts,
            [key for key in TOOLBAR_TOOL_ACTION_ORDER if key != "note"],
        )
        note_button = assembly.panel_bar.findChild(QToolButton, "toolButton_note")
        self.assertIsNotNone(note_button)
        self.assertIsNotNone(note_button.menu())
        self.assertEqual(
            sum(1 for action in assembly.panel_bar.actions() if action.isSeparator()),
            4,
        )
        self.assertTrue(assembly.tool_actions["bond"].isChecked())
        self.assertIsNotNone(
            assembly.panel_bar.findChild(QToolButton, "toolButton_delete")
        )
        # Document/history/preview commands live on the menu bar now.
        for removed_name in (
            "open_button",
            "new_canvas_button",
            "preview_panel_button",
            "undo_button",
            "redo_button",
            "export_xyz_button",
            "setup_sheet_button",
        ):
            self.assertIsNone(
                assembly.panel_bar.findChild(QToolButton, removed_name),
                removed_name,
            )
        self.assertNotIn(
            "Tools",
            [toolbar.windowTitle() for toolbar in window.findChildren(QToolBar)],
        )

        # The SMILES quick-insert bar lives on the top toolbar. It has no
        # section label (the field is self-describing via placeholder/tooltip),
        # so the only section labels remain on the tool-options bar.
        section_labels = [
            label.text()
            for label in assembly.panel_bar.findChildren(QLabel)
            if label.objectName() == "toolbarSectionLabel"
        ]
        self.assertEqual(section_labels, [])

        self.assertIsNone(assembly.panel_bar.findChild(QLineEdit, "atomInput"))
        self.assertEqual(
            [
                line_edit.objectName()
                for line_edit in assembly.panel_bar.findChildren(QLineEdit)
            ],
            ["contextSmilesInput"],
        )
        self.assertIsNotNone(
            assembly.panel_bar.findChild(QToolButton, "smiles_render_button")
        )

        window.canvas.insert_controller.begin_smiles_insert.assert_not_called()
        self.insert_controller_for_window.assert_not_called()
        self.scene_transform_controller_for_window.assert_not_called()
        assembly.panel_bar.findChild(QToolButton, "flip_horizontal_button").click()
        assembly.panel_bar.findChild(QToolButton, "flip_vertical_button").click()
        window.canvas.scene_transform_controller.flip_selected_items.assert_has_calls(
            [mock.call(horizontal=True), mock.call(horizontal=False)]
        )
        self.scene_transform_controller_for_window.assert_has_calls(
            [mock.call(window), mock.call(window)]
        )

    def test_init_menu_bar_builds_file_edit_view_help_menus(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_menu_bar(window)
        menu_bar = assembly.menu_bar

        self.assertEqual(
            [
                action.menu().title()
                for action in menu_bar.actions()
                if action.menu() is not None
            ],
            ["File", "Edit", "View", "Calculation", "Help"],
        )

        file_menu = self._menu(menu_bar, "File")
        file_texts = [
            action.text() for action in file_menu.actions() if not action.isSeparator()
        ]
        self.assertEqual(
            file_texts,
            [
                "New Canvas",
                "Open...",
                "Open Recent",
                "Save",
                "Save As...",
                "Canvas Size...",
                "Export Figure...",
                "Export MOL...",
            ],
        )
        self.assertIsNotNone(self._menu_action(file_menu, "Open Recent").menu())
        for text, callback in (
            ("New Canvas", self.panel_toolbar_callbacks.new_canvas),
            ("Open...", self.panel_toolbar_callbacks.load_canvas),
            ("Save", self.panel_toolbar_callbacks.save_canvas),
            ("Save As...", self.panel_toolbar_callbacks.save_canvas_as),
            ("Export Figure...", self.panel_toolbar_callbacks.export_figure),
            ("Export MOL...", self.panel_toolbar_callbacks.export_mol),
        ):
            self._menu_action(file_menu, text).trigger()
            callback.assert_called_once_with(window)
        self.assertEqual(
            self._menu_action(file_menu, "Save").shortcut(),
            QKeySequence(QKeySequence.StandardKey.Save),
        )
        self.assertEqual(
            self._menu_action(file_menu, "Open...").shortcut(),
            QKeySequence(QKeySequence.StandardKey.Open),
        )

        edit_menu = self._menu(menu_bar, "Edit")
        edit_texts = [
            action.text() for action in edit_menu.actions() if not action.isSeparator()
        ]
        self.assertEqual(
            edit_texts,
            [
                "Undo",
                "Redo",
                "Cut",
                "Copy",
                "Paste",
                "Select All",
                "Group",
                "Ungroup",
                "Flip Horizontal",
                "Flip Vertical",
                "Rotate...",
            ],
        )
        self.assertIs(assembly.undo_action, self._menu_action(edit_menu, "Undo"))
        self.assertIs(assembly.redo_action, self._menu_action(edit_menu, "Redo"))
        self.assertEqual(
            assembly.undo_action.shortcut(),
            QKeySequence(QKeySequence.StandardKey.Undo),
        )
        self.assertEqual(
            assembly.redo_action.shortcut(),
            QKeySequence(QKeySequence.StandardKey.Redo),
        )
        # The canvas key-press path owns these sequences; the menu items must
        # not register competing window-level shortcuts.
        for text in ("Cut", "Copy", "Paste", "Select All", "Group", "Ungroup"):
            self.assertTrue(
                self._menu_action(edit_menu, text).shortcut().isEmpty(), text
            )
        self._menu_action(edit_menu, "Rotate...").trigger()
        self.panel_toolbar_callbacks.show_rotate_options.assert_called_once_with(window)
        with (
            mock.patch(
                "chemvas.ui.main_window_menu_bar.cut_selection_for_window"
            ) as cut_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.copy_selection_for_window"
            ) as copy_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.paste_selection_for_window"
            ) as paste_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.select_all_for_window"
            ) as select_all_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.group_selection_for_window"
            ) as group_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.ungroup_selection_for_window"
            ) as ungroup_port,
        ):
            for text, port in (
                ("Cut", cut_port),
                ("Copy", copy_port),
                ("Paste", paste_port),
                ("Select All", select_all_port),
                ("Group", group_port),
                ("Ungroup", ungroup_port),
            ):
                self._menu_action(edit_menu, text).trigger()
                port.assert_called_once_with(window)
        with mock.patch(
            "chemvas.ui.main_window_menu_bar.scene_transform_controller_for_window",
            side_effect=lambda w: (
                w.canvas.services.scene_operations.scene_transform_controller
            ),
        ):
            self._menu_action(edit_menu, "Flip Horizontal").trigger()
            self._menu_action(edit_menu, "Flip Vertical").trigger()
        window.canvas.scene_transform_controller.flip_selected_items.assert_has_calls(
            [mock.call(horizontal=True), mock.call(horizontal=False)]
        )

        view_menu = self._menu(menu_bar, "View")
        view_texts = [
            action.text() for action in view_menu.actions() if not action.isSeparator()
        ]
        self.assertEqual(
            view_texts,
            ["Actual Size", "Fit to Window", "Zoom In", "Zoom Out", "Molecule Info"],
        )
        for text, key in (
            ("Actual Size", "F5"),
            ("Fit to Window", "F6"),
            ("Zoom In", "F7"),
            ("Zoom Out", "F8"),
        ):
            self.assertEqual(
                self._menu_action(view_menu, text).shortcut(),
                QKeySequence(key),
            )
        with (
            mock.patch(
                "chemvas.ui.main_window_menu_bar.reset_zoom_for_window"
            ) as reset_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.fit_canvas_to_view_for_window"
            ) as fit_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.zoom_in_for_window"
            ) as zoom_in_port,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.zoom_out_for_window"
            ) as zoom_out_port,
        ):
            for text, port in (
                ("Actual Size", reset_port),
                ("Fit to Window", fit_port),
                ("Zoom In", zoom_in_port),
                ("Zoom Out", zoom_out_port),
            ):
                self._menu_action(view_menu, text).trigger()
                port.assert_called_once_with(window)
        self._menu_action(view_menu, "Molecule Info").trigger()
        self.panel_toolbar_callbacks.open_preview_window.assert_called_once_with(window)

        calculation_menu = self._menu(menu_bar, "Calculation")
        self.assertEqual(
            [
                action.text()
                for action in calculation_menu.actions()
                if not action.isSeparator()
            ],
            ["Edit States and Steps..."],
        )
        with mock.patch(
            "chemvas.ui.main_window_menu_bar.edit_calculation_plan_for_window"
        ) as edit_plan:
            self._menu_action(calculation_menu, "Edit States and Steps...").trigger()
        edit_plan.assert_called_once_with(window)

    def test_menu_bar_canvas_size_runs_sheet_setup_dialog(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_menu_bar(window)
        file_menu = self._menu(assembly.menu_bar, "File")
        selection = SimpleNamespace(size="Letter", orientation="landscape")

        with (
            mock.patch(
                "chemvas.ui.main_window_menu_bar.sheet_size_for_window",
                return_value="A4",
            ),
            mock.patch(
                "chemvas.ui.main_window_menu_bar.sheet_orientation_for_window",
                return_value="portrait",
            ),
            mock.patch(
                "chemvas.ui.main_window_menu_bar.prompt_sheet_setup",
                return_value=selection,
            ) as prompt,
            mock.patch(
                "chemvas.ui.main_window_menu_bar.set_sheet_setup_for_window"
            ) as set_sheet,
        ):
            self._menu_action(file_menu, "Canvas Size...").trigger()

        prompt.assert_called_once_with(
            window, current_size="A4", current_orientation="portrait"
        )
        set_sheet.assert_called_once_with(window, "Letter", "landscape")

    def test_menu_bar_canvas_size_keeps_sheet_when_dialog_cancelled(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        assembly = self.service.init_menu_bar(window)
        file_menu = self._menu(assembly.menu_bar, "File")

        with (
            mock.patch(
                "chemvas.ui.main_window_menu_bar.sheet_size_for_window",
                return_value="A4",
            ),
            mock.patch(
                "chemvas.ui.main_window_menu_bar.sheet_orientation_for_window",
                return_value="portrait",
            ),
            mock.patch(
                "chemvas.ui.main_window_menu_bar.prompt_sheet_setup",
                return_value=None,
            ),
            mock.patch(
                "chemvas.ui.main_window_menu_bar.set_sheet_setup_for_window"
            ) as set_sheet,
        ):
            self._menu_action(file_menu, "Canvas Size...").trigger()

        set_sheet.assert_not_called()

    def test_init_menu_bar_builds_help_menu_with_about_actions(self) -> None:
        window = _HarnessWindow()
        self.addCleanup(window.close)

        with mock.patch(
            "chemvas.ui.main_window_menu_bar.show_about_dialog"
        ) as show_about:
            assembly = self.service.init_menu_bar(window)

            help_menu = self._menu(assembly.menu_bar, "Help")
            actions = [
                action for action in help_menu.actions() if not action.isSeparator()
            ]
            self.assertEqual(
                [action.text() for action in actions],
                ["About Chemvas", "About Qt", "Chemvas on GitHub"],
            )

            about_action = next(
                action for action in actions if action.text() == "About Chemvas"
            )
            self.assertEqual(about_action.menuRole(), QAction.MenuRole.AboutRole)
            about_qt_action = next(
                action for action in actions if action.text() == "About Qt"
            )
            self.assertEqual(about_qt_action.menuRole(), QAction.MenuRole.AboutQtRole)

            show_about.assert_not_called()
            about_action.trigger()
            show_about.assert_called_once_with(window)

    def test_apply_theme_sets_stylesheet(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)

        self.service.apply_theme(window)

        self.assertEqual(window.styleSheet(), MAIN_WINDOW_STYLESHEET)


if __name__ == "__main__":
    unittest.main()
