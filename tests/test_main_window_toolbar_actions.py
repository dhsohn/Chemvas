import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QAction, QIcon
    from PyQt6.QtWidgets import QApplication, QDockWidget, QLineEdit, QMenu, QSplitter, QToolBar, QToolButton
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    try:
        from ui.main_window import MainWindow
        from ui.main_window_ui_assembly_service import (
            CornerMenuButton,
            MainWindowPanelAssembly,
            MainWindowToolbarAssembly,
        )
    except SyntaxError:
        MainWindow = None
        CornerMenuButton = None
        MainWindowPanelAssembly = None
        MainWindowToolbarAssembly = None
else:
    MainWindow = None
    CornerMenuButton = None
    MainWindowPanelAssembly = None
    MainWindowToolbarAssembly = None


class _FakeItem:
    def __init__(self, kind: str) -> None:
        self._kind = kind

    def data(self, key):
        if key == 0:
            return self._kind
        return None


@unittest.skipUnless(
    QApplication is not None and MainWindow is not None,
    "PyQt6 and an importable MainWindow are required for main window tests",
)
class MainWindowToolbarActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.app.processEvents()

    def test_template_entries_and_template_menu_preserve_ring_size_and_style(self) -> None:
        with mock.patch.object(self.window.canvas, "begin_ring_template_insert") as begin_insert:
            entries = dict(self.window._template_entries())
            entries["Cyclopropane"]()
            entries["Cycloheptane"]()
            entries["Cyclooctane"]()
            entries["Cyclohexane (Chair)"]()

        self.assertEqual(begin_insert.call_args_list[0].args, (3,))
        self.assertEqual(begin_insert.call_args_list[0].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[1].args, (7,))
        self.assertEqual(begin_insert.call_args_list[1].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[2].args, (8,))
        self.assertEqual(begin_insert.call_args_list[2].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[3].args, (6,))
        self.assertEqual(begin_insert.call_args_list[3].kwargs, {"style": "chair"})

        menu = QMenu()
        self.window._populate_template_menu(menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            [
                "Cyclopropane",
                "Cyclobutane",
                "Cyclopentane",
                "Cyclohexane (Chair)",
                "Cycloheptane",
                "Cyclooctane",
            ],
        )

    def test_ui_assembly_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._ui_assembly_service = service

        toolbar_button = QToolButton()
        corner_button = CornerMenuButton()
        save_button = CornerMenuButton()
        save_action = QAction("Save", self.window)
        save_as_action = QAction("Save As...", self.window)
        atom_input = QLineEdit()
        tool_actions = {"bond": QAction("Bond", self.window)}
        toolbar_assembly = MainWindowToolbarAssembly(
            left_bar=QToolBar("Tools", self.window),
            panel_bar=QToolBar("Panels", self.window),
            tool_actions=tool_actions,
            atom_input=atom_input,
            save_action=save_action,
            save_as_action=save_as_action,
            save_button=save_button,
        )
        panel_assembly = MainWindowPanelAssembly(
            splitter=QSplitter(),
            dock=QDockWidget("Panels", self.window),
        )
        service.create_toolbar_button.return_value = toolbar_button
        service.create_corner_menu_button.return_value = corner_button
        service.create_save_menu_button.return_value = save_button
        service.init_toolbars.return_value = toolbar_assembly
        service.init_panels.return_value = panel_assembly

        icon = QIcon()
        callback = mock.Mock()
        menu_builder = mock.Mock()
        self.assertIs(
            self.window._create_toolbar_button(
                icon=icon,
                tooltip="Render",
                callback=callback,
                shortcut="Ctrl+R",
                text="Run",
                object_name="render_button",
                style_sheet="color: red;",
                auto_raise=False,
                cursor=None,
            ),
            toolbar_button,
        )
        service.create_toolbar_button.assert_called_once_with(
            icon=icon,
            tooltip="Render",
            callback=callback,
            shortcut="Ctrl+R",
            text="Run",
            object_name="render_button",
            style_sheet="color: red;",
            auto_raise=False,
            cursor=None,
        )

        self.assertIs(
            self.window._create_corner_menu_button(
                icon=icon,
                tooltip="Menu",
                style_sheet="padding: 0;",
                popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
                menu_builder=menu_builder,
                default_action=save_action,
            ),
            corner_button,
        )
        service.create_corner_menu_button.assert_called_once_with(
            icon=icon,
            tooltip="Menu",
            style_sheet="padding: 0;",
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=menu_builder,
            default_action=save_action,
        )

        self.assertIs(self.window._create_save_menu_button(save_action, save_as_action), save_button)
        service.create_save_menu_button.assert_called_once_with(save_action, save_as_action)

        self.window._init_toolbars()
        service.init_toolbars.assert_called_once_with(self.window)
        self.assertIs(self.window._tool_actions, tool_actions)
        self.assertIs(self.window._atom_input, atom_input)

        self.window._init_panels()
        service.init_panels.assert_called_once_with(self.window)
        self.assertIs(self.window.panel_splitter, panel_assembly.splitter)
        self.assertIs(self.window.panel_dock, panel_assembly.dock)

        self.window._apply_theme()
        service.apply_theme.assert_called_once_with(self.window)

    def test_tool_routing_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._tool_routing_service = service
        menu = QMenu()
        callback = mock.Mock()
        icon = QIcon()
        action = QAction("Action", self.window)
        service.add_menu_action.return_value = action
        service.palette_icon.return_value = icon
        service.template_entries.return_value = [("Cyclopropane", callback)]
        service.acs_color_palette.return_value = [("Black", "#000000")]

        self.assertIs(self.window._add_menu_action(menu, "Action", callback, icon), action)
        self.assertIs(self.window._palette_icon("#000000"), icon)
        self.assertEqual(self.window._template_entries(), [("Cyclopropane", callback)])
        self.assertEqual(self.window._acs_color_palette(), [("Black", "#000000")])

        self.window._populate_template_menu(menu)
        self.window._populate_arrow_menu(menu)
        self.window._populate_palette_menu(menu, callback)
        self.window._activate_arrow_type_from_menu("Reaction")
        self.window._activate_arrow_preset_from_menu("Bold")
        self.window._apply_color_preset("#112233")
        self.window._apply_ring_fill_preset("#445566")

        service.add_menu_action.assert_called_once_with(menu, "Action", callback, icon)
        service.palette_icon.assert_called_once_with("#000000")
        service.template_entries.assert_called_once_with(self.window)
        service.acs_color_palette.assert_called_once_with()
        service.populate_template_menu.assert_called_once_with(self.window, menu)
        service.populate_arrow_menu.assert_called_once_with(self.window, menu)
        service.populate_palette_menu.assert_called_once_with(self.window, menu, callback)
        service.activate_arrow_type_from_menu.assert_called_once_with(self.window, "Reaction")
        service.activate_arrow_preset_from_menu.assert_called_once_with(self.window, "Bold")
        self.assertEqual(service.apply_color_preset.call_args.args, (self.window, "#112233"))
        self.assertIn("qtimer", service.apply_color_preset.call_args.kwargs)
        self.assertEqual(service.apply_ring_fill_preset.call_args.args, (self.window, "#445566"))
        self.assertIn("qtimer", service.apply_ring_fill_preset.call_args.kwargs)

    def test_tool_state_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._tool_state_service = service

        self.window._sync_tool_actions_from_canvas()
        self.window._set_tool_with_status("bond", reset_bond_style=False)
        self.window._set_bond_style("Double")
        self.window._set_arrow_type("Curved Double")
        self.window._set_orbital_type("sp2")
        self.window._set_orbital_phase("Phase On")
        self.window._set_arrow_preset("Bold")

        service.sync_tool_actions_from_canvas.assert_called_once_with(self.window)
        service.set_tool_with_status.assert_called_once_with(self.window, "bond", reset_bond_style=False)
        service.set_bond_style.assert_called_once_with(self.window, "Double")
        service.set_arrow_type.assert_called_once_with(self.window, "Curved Double")
        service.set_orbital_type.assert_called_once_with(self.window, "sp2")
        service.set_orbital_phase.assert_called_once_with(self.window, "Phase On")
        service.set_arrow_preset.assert_called_once_with(self.window, "Bold")

    def test_text_style_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._text_style_service = service

        self.window._set_text_color()
        self.window._set_text_align("Center")
        self.window._set_note_box_color()
        self.window._set_note_border_color()
        self.window._set_text_preset("ACS")

        self.assertEqual(service.set_text_color.call_args.args, (self.window,))
        self.assertIn("get_color", service.set_text_color.call_args.kwargs)
        service.set_text_align.assert_called_once_with(self.window, "Center")
        self.assertEqual(service.set_note_box_color.call_args.args, (self.window,))
        self.assertIn("get_color", service.set_note_box_color.call_args.kwargs)
        self.assertEqual(service.set_note_border_color.call_args.args, (self.window,))
        self.assertIn("get_color", service.set_note_border_color.call_args.kwargs)
        service.set_text_preset.assert_called_once_with(self.window, "ACS")

    def test_icon_wrappers_delegate_to_factory(self) -> None:
        factory = mock.Mock()
        self.window._icon_factory = factory

        icon = QIcon()
        polygon = object()
        segments = [("start", "end")]
        rect = object()
        painter = object()
        point = object()

        factory.make_icon.return_value = icon
        factory.icon_select.return_value = icon
        factory.icon_ring.return_value = icon
        factory.icon_setup_sheet.return_value = icon
        factory.icon_arrow_preview.return_value = icon
        factory.icon_template_preview.return_value = icon
        factory.benzene_icon_polygon.return_value = polygon
        factory.benzene_icon_inner_segments.return_value = segments
        factory.chair_icon_rect.return_value = rect
        factory.chair_icon_points.return_value = polygon

        self.assertIs(self.window._make_icon(lambda _p: None, size=24), icon)
        self.assertIs(self.window._icon_select(), icon)
        self.assertIs(self.window._icon_ring(), icon)
        self.assertIs(self.window._icon_setup_sheet(), icon)
        self.assertIs(self.window._icon_arrow_preview("reaction"), icon)
        self.assertIs(self.window._icon_template_preview("Cyclopropane"), icon)
        self.assertIs(self.window._benzene_icon_polygon(point, 10.0), polygon)
        self.assertEqual(self.window._benzene_icon_inner_segments(polygon, point, spacing_scale=0.92), segments)
        self.assertIs(self.window._chair_icon_rect(), rect)
        self.assertIs(self.window._chair_icon_points(rect), polygon)
        self.window._draw_arrow_head(painter, point, point)

        self.assertEqual(factory.make_icon.call_args.args[1], 24)
        factory.icon_select.assert_called_once_with()
        factory.icon_ring.assert_called_once_with()
        factory.icon_setup_sheet.assert_called_once_with()
        factory.icon_arrow_preview.assert_called_once_with("reaction")
        factory.icon_template_preview.assert_called_once_with("Cyclopropane")
        factory.benzene_icon_polygon.assert_called_once_with(point, 10.0)
        factory.benzene_icon_inner_segments.assert_called_once_with(polygon, point, spacing_scale=0.92)
        factory.chair_icon_rect.assert_called_once_with()
        factory.chair_icon_points.assert_called_once_with(rect)
        factory.draw_arrow_head.assert_called_once_with(painter, point, point)

    def test_tool_action_wrappers_delegate_to_service(self) -> None:
        service = mock.Mock()
        self.window._tool_action_service = service
        tool_group = mock.Mock()
        callback = mock.Mock()
        action = QAction("Select", self.window)
        service.build_checkable_tool_action.return_value = ("select", action)
        service.build_tool_actions.return_value = {"select": action}

        self.assertEqual(
            self.window._build_checkable_tool_action(
                tool_group,
                key="select",
                label="Select",
                icon_method="_icon_select",
                tooltip="Pick atoms",
                callback=callback,
            ),
            ("select", action),
        )
        self.window._activate_bond_style_tool("Hash")
        self.window._activate_mark_tool("minus")
        self.assertEqual(self.window._build_tool_actions(tool_group), {"select": action})

        service.build_checkable_tool_action.assert_called_once_with(
            self.window,
            tool_group,
            key="select",
            label="Select",
            icon_method="_icon_select",
            tooltip="Pick atoms",
            callback=callback,
        )
        service.activate_bond_style_tool.assert_called_once_with(self.window, "Hash")
        service.activate_mark_tool.assert_called_once_with(self.window, "minus")
        service.build_tool_actions.assert_called_once_with(self.window, tool_group)

    def test_arrow_menu_helpers_route_type_and_preset_through_existing_methods(self) -> None:
        with (
            mock.patch.object(self.window, "_set_tool_with_status") as set_tool,
            mock.patch.object(self.window, "_set_arrow_type") as set_type,
            mock.patch.object(self.window, "_set_arrow_preset") as set_preset,
            mock.patch.object(self.window, "_open_arrow_settings") as open_settings,
        ):
            self.window._activate_arrow_type_from_menu("Reaction")
            self.window._activate_arrow_preset_from_menu("Bold")
            menu = QMenu()
            self.window._populate_arrow_menu(menu)
            preset_menu = next(action.menu() for action in menu.actions() if action.menu() is not None)
            menu.actions()[0].trigger()
            preset_menu.actions()[0].trigger()
            menu.actions()[-1].trigger()

        self.assertEqual(set_tool.call_args_list[0].args, ("arrow",))
        self.assertEqual(set_tool.call_args_list[1].args, ("arrow",))
        self.assertTrue(any(call.args == ("Reaction",) for call in set_type.call_args_list))
        self.assertTrue(any(call.args == ("Default",) for call in set_preset.call_args_list))
        open_settings.assert_called_once_with()

    def test_text_preset_and_palette_menu_helpers_delegate_correctly(self) -> None:
        with (
            mock.patch.object(self.window.canvas, "apply_text_preset_acs") as acs,
            mock.patch.object(self.window.canvas, "apply_text_preset_paper_thin") as paper_thin,
            mock.patch.object(self.window.canvas, "apply_text_preset_paper_bold") as paper_bold,
        ):
            self.window._set_text_preset("ACS")
            self.window._set_text_preset("Paper Thin")
            self.window._set_text_preset("Paper Bold")
            self.window._set_text_preset("Unknown")

        acs.assert_called_once_with()
        paper_thin.assert_called_once_with()
        paper_bold.assert_called_once_with()

        palette_calls = []
        menu = QMenu()
        self.window._populate_palette_menu(menu, lambda value: palette_calls.append(value))
        self.assertEqual([action.text() for action in menu.actions()], [label for label, _ in self.window._acs_color_palette()])
        menu.actions()[0].trigger()
        self.assertEqual(palette_calls, ["#000000"])

    def test_apply_color_and_ring_fill_presets_filter_selected_items_and_update_color_tool(self) -> None:
        color_tool = SimpleNamespace(_last_color=None)
        self.window.canvas.tools.tools["color"] = color_tool
        selected_items = [_FakeItem("atom"), _FakeItem("ring"), _FakeItem("note")]
        scene = SimpleNamespace(selectedItems=lambda: selected_items)

        with (
            mock.patch("ui.main_window.QTimer.singleShot", side_effect=lambda _delay, callback: callback()),
            mock.patch.object(self.window.canvas, "scene", return_value=scene),
            mock.patch.object(self.window.canvas, "set_tool") as set_tool,
            mock.patch.object(self.window.canvas, "apply_color_to_item") as apply_color,
            mock.patch.object(self.window.canvas, "apply_ring_fill_color") as apply_fill,
        ):
            self.window._apply_color_preset("#1f5eff")
            self.window._apply_ring_fill_preset("#c77c00")

        self.assertEqual(color_tool._last_color, "#1f5eff")
        set_tool.assert_called_once_with("color")
        self.assertEqual([call.args[0].data(0) for call in apply_color.call_args_list], ["atom", "ring"])
        self.assertEqual([call.args[1].name() for call in apply_color.call_args_list], ["#1f5eff", "#1f5eff"])
        self.assertEqual([call.args[0].data(0) for call in apply_fill.call_args_list], ["ring"])
        self.assertEqual([call.args[1].name() for call in apply_fill.call_args_list], ["#c77c00"])


if __name__ == "__main__":
    unittest.main()
