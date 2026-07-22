import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import (
        QApplication,
        QMenu,
        QToolBar,
        QToolButton,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    try:
        from chemvas.bootstrap.main_window import build_main_window
        from chemvas.ui.canvas_insert_state import insert_state_for
        from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
        from chemvas.ui.main_window_ports import (
            active_canvas_for_window,
            services_for_window,
        )
        from chemvas.ui.main_window_theme import TOOLBAR_THICKNESS
    except SyntaxError:
        build_main_window = None
else:
    build_main_window = None


class _FakeItem:
    def __init__(self, kind: str) -> None:
        self._kind = kind

    def data(self, key):
        if key == 0:
            return self._kind
        return None


@unittest.skipUnless(
    QApplication is not None and build_main_window is not None,
    "PyQt6 and an importable build_main_window are required for main window tests",
)
class MainWindowToolbarActionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()

    def _dark_pixel_count(
        self,
        icon: QIcon,
        *,
        center_only: bool = False,
        mode: QIcon.Mode = QIcon.Mode.Normal,
        state: QIcon.State = QIcon.State.Off,
    ) -> int:
        pixmap = icon.pixmap(30, 30, mode, state)
        image = pixmap.toImage()
        count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                if center_only and not (10 <= x <= 20 and 10 <= y <= 20):
                    continue
                color = image.pixelColor(x, y)
                if color.alpha() <= 0:
                    continue
                luminance = (
                    0.2126 * color.red()
                    + 0.7152 * color.green()
                    + 0.0722 * color.blue()
                )
                if luminance < 125:
                    count += 1
        return count

    def _dark_pixel_count_in_rect(self, image, rect) -> int:
        count = 0
        for y in range(rect.top(), rect.bottom() + 1):
            for x in range(rect.left(), rect.right() + 1):
                color = image.pixelColor(x, y)
                if color.alpha() <= 0:
                    continue
                luminance = (
                    0.2126 * color.red()
                    + 0.7152 * color.green()
                    + 0.0722 * color.blue()
                )
                if luminance < 125:
                    count += 1
        return count

    def test_select_and_perspective_toolbar_icons_have_visible_glyphs(self) -> None:
        for action_key in ("select", "perspective"):
            with self.subTest(action_key=action_key):
                icon = self.window.ui_references.tool_actions[action_key].icon()
                self.assertFalse(icon.isNull())
                self.assertGreaterEqual(self._dark_pixel_count(icon), 60)
                self.assertGreaterEqual(
                    self._dark_pixel_count(icon, center_only=True), 10
                )
                self.assertGreaterEqual(
                    self._dark_pixel_count(icon, mode=QIcon.Mode.Disabled), 60
                )
                self.assertGreaterEqual(
                    self._dark_pixel_count(
                        icon, mode=QIcon.Mode.Selected, state=QIcon.State.On
                    ),
                    60,
                )

    def test_top_toolbar_keeps_select_and_perspective_actions_visible(self) -> None:
        self.assertNotIn(
            "Tools",
            [toolbar.windowTitle() for toolbar in self.window.findChildren(QToolBar)],
        )
        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )
        actions = [
            action
            for action in panel_bar.actions()
            if not action.isSeparator() and action.text() in {"Select", "Perspective"}
        ]
        action_texts = [action.text() for action in actions]

        self.assertEqual(action_texts, ["Select", "Perspective"])
        self.assertEqual(panel_bar.iconSize().width(), 18)
        self.assertEqual(panel_bar.iconSize().height(), 18)
        for text in ("Select", "Perspective"):
            with self.subTest(text=text):
                action = next(action for action in actions if action.text() == text)
                self.assertFalse(action.icon().isNull())

    def test_toolbar_rows_share_toolbar_thickness(self) -> None:
        self.window.resize(900, 560)
        self.window.show()
        self.app.processEvents()

        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )
        options_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Options"
        )

        self.assertNotIn(
            "Tools",
            [toolbar.windowTitle() for toolbar in self.window.findChildren(QToolBar)],
        )
        self.assertEqual(panel_bar.height(), TOOLBAR_THICKNESS)
        self.assertEqual(options_bar.height(), TOOLBAR_THICKNESS)

    def test_color_and_ring_fill_live_in_top_toolbar_and_palette_options_bar(
        self,
    ) -> None:
        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )

        self.assertNotIn(
            "Tools",
            [toolbar.windowTitle() for toolbar in self.window.findChildren(QToolBar)],
        )
        self.assertIn("Color", [action.text() for action in panel_bar.actions()])
        self.assertIn("Ring Fill", [action.text() for action in panel_bar.actions()])
        self.assertNotIn("Template", [action.text() for action in panel_bar.actions()])
        self.assertNotIn(
            "Bond Length",
            [button.toolTip() for button in panel_bar.findChildren(QToolButton)],
        )
        self.assertIn(
            "Color",
            [button.toolTip() for button in panel_bar.findChildren(QToolButton)],
        )
        self.assertIn(
            "Ring Fill",
            [button.toolTip() for button in panel_bar.findChildren(QToolButton)],
        )

        self.window.ui_references.tool_actions["color"].trigger()
        color_button = next(
            widget
            for widget in self.window.findChildren(QToolButton)
            if widget.toolTip() == "Color: Blue"
        )
        self.assertEqual(
            self.window.statusBar().currentMessage(), "Color: choose a swatch"
        )
        self.assertEqual(
            services_for_window(self.window).status_service.status_context_texts()[
                "tool"
            ],
            "Tool: Color",
        )
        self.assertIsNotNone(color_button)

        self.window.ui_references.tool_actions["ring_fill"].trigger()
        ring_fill_button = next(
            widget
            for widget in self.window.findChildren(QToolButton)
            if widget.toolTip() == "Ring Fill: Yellow"
        )
        self.assertEqual(
            self.window.runtime_state.context_bar_page_override, "ring_fill"
        )
        self.assertEqual(
            self.window.statusBar().currentMessage(), "Ring Fill: choose fill color"
        )
        self.assertEqual(
            services_for_window(self.window).status_service.status_context_texts()[
                "tool"
            ],
            "Tool: Ring Fill",
        )
        self.assertIsNotNone(ring_fill_button)

    def test_top_toolbar_renders_select_and_perspective_button_glyphs(self) -> None:
        self.window.resize(800, 420)
        self.window.show()
        self.app.processEvents()
        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )
        image = panel_bar.grab().toImage()

        # The visible toolbar uses 18px Lucide-style line icons, so the
        # move/select glyph has fewer dark pixels than the previous label
        # button while the native-size guard above still catches blank icons.
        for text, min_dark_pixels in (("Select", 24), ("Perspective", 20)):
            with self.subTest(text=text):
                action = next(
                    action for action in panel_bar.actions() if action.text() == text
                )
                widget = panel_bar.widgetForAction(action)
                self.assertIsNotNone(widget)
                self.assertTrue(widget.isVisible())
                self.assertFalse(widget.icon().isNull())
                self.assertEqual(widget.iconSize(), panel_bar.iconSize())
                rect = widget.geometry().intersected(image.rect())
                self.assertGreaterEqual(
                    self._dark_pixel_count_in_rect(image, rect), min_dark_pixels
                )

    def test_top_toolbar_renders_select_and_perspective_glyphs_when_checked(
        self,
    ) -> None:
        self.window.resize(900, 560)
        self.window.show()
        self.app.processEvents()
        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )

        for action_key, min_dark_pixels in (("select", 24), ("perspective", 20)):
            with self.subTest(action_key=action_key):
                action = self.window.ui_references.tool_actions[action_key]
                action.trigger()
                self.app.processEvents()
                image = panel_bar.grab().toImage()
                widget = panel_bar.widgetForAction(action)
                self.assertIsNotNone(widget)
                self.assertTrue(widget.isVisible())
                self.assertFalse(widget.icon().isNull())
                self.assertEqual(widget.iconSize(), panel_bar.iconSize())
                rect = widget.geometry().intersected(image.rect())
                self.assertGreaterEqual(
                    self._dark_pixel_count_in_rect(image, rect), min_dark_pixels
                )

    def test_top_toolbar_keeps_all_tool_actions_visible_in_compact_window(self) -> None:
        self.window.resize(800, 420)
        self.window.show()
        self.app.processEvents()
        panel_bar = next(
            toolbar
            for toolbar in self.window.findChildren(QToolBar)
            if toolbar.windowTitle() == "Panels"
        )

        tool_action_texts = {
            "Select",
            "Bond",
            "Atom",
            "Mark",
            "Ring",
            "Color",
            "Ring Fill",
            "Arrow",
            "Brackets",
            "Perspective",
        }
        for action in panel_bar.actions():
            if action.isSeparator():
                continue
            if action.text() not in tool_action_texts:
                continue
            with self.subTest(action=action.text()):
                widget = panel_bar.widgetForAction(action)
                self.assertIsNotNone(widget)
                self.assertTrue(widget.isVisible())

    def test_template_entries_and_template_menu_preserve_ring_size_and_style(
        self,
    ) -> None:
        tool_routing_service = services_for_window(self.window).tool_routing_service
        with mock.patch.object(
            active_canvas_for_window(self.window).services.structure.insert_controller,
            "begin_ring_template_insert",
        ) as begin_insert:
            entries = dict(tool_routing_service.template_entries(self.window))
            entries["Benzene"]()
            entries["Cyclopropane"]()
            entries["Cycloheptane"]()
            entries["Cyclooctane"]()
            entries["Cyclohexane (Chair)"]()

        self.assertEqual(begin_insert.call_args_list[0].args, (6,))
        self.assertEqual(begin_insert.call_args_list[0].kwargs, {"style": "benzene"})
        self.assertEqual(begin_insert.call_args_list[1].args, (3,))
        self.assertEqual(begin_insert.call_args_list[1].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[2].args, (7,))
        self.assertEqual(begin_insert.call_args_list[2].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[3].args, (8,))
        self.assertEqual(begin_insert.call_args_list[3].kwargs, {"style": "regular"})
        self.assertEqual(begin_insert.call_args_list[4].args, (6,))
        self.assertEqual(begin_insert.call_args_list[4].kwargs, {"style": "chair"})

        menu = QMenu()
        tool_routing_service.populate_template_menu(self.window, menu)
        self.assertEqual(
            [action.text() for action in menu.actions()],
            [
                "Benzene",
                "Cyclopropane",
                "Cyclobutane",
                "Cyclopentane",
                "Cyclohexane (Chair)",
                "Cyclohexane (Chair, flipped)",
                "Cycloheptane",
                "Cyclooctane",
            ],
        )

    def test_ring_action_shows_template_icon_buttons_and_routes_current_canvas(
        self,
    ) -> None:
        insert_controller = active_canvas_for_window(
            self.window
        ).services.structure.insert_controller
        with mock.patch.object(
            insert_controller,
            "begin_ring_template_insert",
            wraps=insert_controller.begin_ring_template_insert,
        ) as begin_insert:
            self.window.ui_references.tool_actions["benzene"].trigger()

            button = next(
                widget
                for widget in self.window.findChildren(QToolButton)
                if widget.toolTip() == "Benzene"
            )
            self.assertIsNone(self.window.runtime_state.context_bar_page_override)
            self.assertTrue(
                self.window.ui_references.tool_actions["benzene"].isChecked()
            )
            self.assertTrue(button.isChecked())
            self.assertTrue(
                insert_state_for(active_canvas_for_window(self.window)).template_active
            )
            self.assertEqual(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_ring_size,
                6,
            )
            self.assertEqual(
                insert_state_for(
                    active_canvas_for_window(self.window)
                ).template_ring_style,
                "benzene",
            )
            self.assertEqual(
                self.window.statusBar().currentMessage(),
                "Ring: click to place template",
            )
            self.assertEqual(
                services_for_window(self.window).status_service.status_context_texts()[
                    "tool"
                ],
                "Tool: Ring",
            )

            self.window.ui_references.tool_actions["select"].trigger()
            self.app.processEvents()
            self.assertFalse(button.isChecked())

        begin_insert.assert_called_once_with(6, "benzene")

    def test_arrow_action_shows_context_icon_buttons_and_routes_type_and_preset(
        self,
    ) -> None:
        self.window.ui_references.tool_actions["arrow"].trigger()

        arrow_button = next(
            widget
            for widget in self.window.findChildren(QToolButton)
            if widget.toolTip() == "Curved Double"
        )
        preset_button = next(
            widget
            for widget in self.window.findChildren(QToolButton)
            if widget.toolTip() == "Bold arrow preset"
        )

        arrow_button.click()
        preset_button.click()

        settings = tool_settings_state_for(active_canvas_for_window(self.window))
        self.assertEqual(settings.active_arrow_type, "curved_double")
        self.assertEqual(settings.arrow_line_width, 2.2)
        self.assertEqual(settings.arrow_head_scale, 0.4)

    def test_brackets_action_shows_context_icon_buttons_and_routes_type(self) -> None:
        self.window.ui_references.tool_actions["ts_bracket"].trigger()

        dagger_button = next(
            widget
            for widget in self.window.findChildren(QToolButton)
            if widget.toolTip() == "Dagger"
        )
        dagger_button.click()

        settings = tool_settings_state_for(active_canvas_for_window(self.window))
        self.assertEqual(settings.active_bracket_type, "dagger")
        self.assertEqual(
            active_canvas_for_window(self.window).services.tooling.tools.active.name,
            "ts_bracket",
        )

    def test_tool_routing_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "template_entries"))
        self.assertFalse(hasattr(self.window, "acs_color_palette"))
        self.assertFalse(hasattr(self.window, "populate_template_menu"))
        self.assertFalse(hasattr(self.window, "populate_arrow_menu"))
        self.assertFalse(hasattr(self.window, "populate_palette_menu"))
        self.assertFalse(hasattr(self.window, "activate_arrow_type_from_menu"))
        self.assertFalse(hasattr(self.window, "activate_arrow_preset_from_menu"))
        self.assertFalse(hasattr(self.window, "apply_color_preset"))
        self.assertFalse(hasattr(self.window, "apply_ring_fill_preset"))

    def test_context_page_state_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "sync_tool_actions_from_canvas"))
        self.assertFalse(hasattr(self.window, "set_tool_with_status"))
        self.assertFalse(hasattr(self.window, "show_context_page"))

    def test_tool_state_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "set_bond_style"))
        self.assertFalse(hasattr(self.window, "set_arrow_type"))
        self.assertFalse(hasattr(self.window, "set_bracket_type"))
        self.assertFalse(hasattr(self.window, "set_orbital_type"))
        self.assertFalse(hasattr(self.window, "set_orbital_phase"))
        self.assertFalse(hasattr(self.window, "set_arrow_preset"))

    def test_text_style_service_surface_stays_off_main_window(self) -> None:
        self.assertFalse(hasattr(self.window, "set_text_color"))
        self.assertFalse(hasattr(self.window, "set_text_align"))
        self.assertFalse(hasattr(self.window, "set_note_box_color"))
        self.assertFalse(hasattr(self.window, "set_note_border_color"))
        self.assertFalse(hasattr(self.window, "set_text_preset"))

    def test_main_window_uses_icon_factory_without_icon_wrappers(self) -> None:
        factory = mock.Mock()
        self.window.ui_references.icon_factory = factory

        icon = QIcon()
        factory.icon_select.return_value = icon

        self.assertIs(
            self.window.ui_references.require_icon_factory().icon_select(), icon
        )
        self.assertFalse(hasattr(self.window, "icon_factory"))
        self.assertFalse(hasattr(self.window, "_icon_select"))
        factory.icon_select.assert_called_once_with()

    def test_tool_action_public_methods_delegate_to_service_without_build_wrapper(
        self,
    ) -> None:
        self.assertFalse(hasattr(self.window, "activate_bond_style_tool"))
        self.assertFalse(hasattr(self.window, "build_tool_actions"))
        self.assertFalse(hasattr(self.window, "new_tool_action"))

    def test_arrow_menu_helpers_route_type_and_preset_through_existing_methods(
        self,
    ) -> None:
        tool_routing_service = services_for_window(self.window).tool_routing_service
        tool_routing_service.activate_arrow_type_from_menu(self.window, "Curved Double")
        tool_routing_service.activate_arrow_preset_from_menu(self.window, "Bold")
        settings = tool_settings_state_for(active_canvas_for_window(self.window))

        self.assertEqual(settings.active_arrow_type, "curved_double")
        self.assertEqual(settings.arrow_line_width, 2.2)
        self.assertEqual(settings.arrow_head_scale, 0.4)

        menu = QMenu()
        tool_routing_service.populate_arrow_menu(self.window, menu)
        preset_menu = next(
            action.menu() for action in menu.actions() if action.menu() is not None
        )
        menu.actions()[0].trigger()
        preset_menu.actions()[0].trigger()

        self.assertEqual(settings.active_arrow_type, "reaction")
        self.assertEqual(settings.arrow_line_width, 1.2)
        self.assertEqual(settings.arrow_head_scale, 0.3)
        self.assertEqual(
            [action.text() for action in menu.actions() if action.menu() is None],
            [
                "Reaction",
                "Equilibrium",
                "Resonance",
                "Curved Single",
                "Curved Double",
                "Inhibition",
                "Dotted",
            ],
        )

    def test_text_preset_and_palette_menu_helpers_delegate_correctly(self) -> None:
        text_style_service = services_for_window(self.window).text_style_service
        with (
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.style_controller,
                "apply_text_preset_acs",
            ) as acs,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.style_controller,
                "apply_text_preset_paper_thin",
            ) as paper_thin,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.style_controller,
                "apply_text_preset_paper_bold",
            ) as paper_bold,
        ):
            text_style_service.set_text_preset(self.window, "ACS")
            text_style_service.set_text_preset(self.window, "Paper Thin")
            text_style_service.set_text_preset(self.window, "Paper Bold")
            text_style_service.set_text_preset(self.window, "Unknown")

        acs.assert_called_once_with()
        paper_thin.assert_called_once_with()
        paper_bold.assert_called_once_with()

        palette_calls = []
        menu = QMenu()
        tool_routing_service = services_for_window(self.window).tool_routing_service
        tool_routing_service.populate_palette_menu(
            self.window, menu, lambda value: palette_calls.append(value)
        )
        self.assertEqual(
            [action.text() for action in menu.actions()],
            [label for label, _ in tool_routing_service.acs_color_palette()],
        )
        menu.actions()[0].trigger()
        self.assertEqual(palette_calls, ["#000000"])

    def test_apply_color_and_ring_fill_presets_filter_selected_items_and_update_color_tool(
        self,
    ) -> None:
        color_tool = SimpleNamespace(set_color=mock.Mock())
        active_canvas_for_window(self.window).services.tooling.tools.tools["color"] = (
            color_tool
        )
        selected_items = [_FakeItem("atom"), _FakeItem("ring"), _FakeItem("note")]
        scene = SimpleNamespace(selectedItems=lambda: selected_items)

        with (
            mock.patch(
                "chemvas.ui.main_window_tool_routing_service.QTimer.singleShot",
                side_effect=lambda _delay, callback: callback(),
            ),
            mock.patch.object(
                active_canvas_for_window(self.window), "scene", return_value=scene
            ),
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.input.tool_mode_controller,
                "set_tool",
            ) as set_tool,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.canvas_color_mutation_service,
                "apply_color_to_items",
            ) as apply_color,
            mock.patch.object(
                active_canvas_for_window(
                    self.window
                ).services.scene_operations.canvas_color_mutation_service,
                "apply_ring_fill_color_to_items",
            ) as apply_fill,
        ):
            services_for_window(self.window).tool_routing_service.apply_color_preset(
                self.window, "#2f6ed3"
            )
            services_for_window(
                self.window
            ).tool_routing_service.apply_ring_fill_preset(self.window, "#f4d06f")

        color_tool.set_color.assert_called_once()
        self.assertEqual(color_tool.set_color.call_args.args[0].name(), "#2f6ed3")
        set_tool.assert_called_once_with("color")
        apply_color.assert_called_once()
        self.assertEqual(
            [item.data(0) for item in apply_color.call_args.args[0]],
            ["atom", "ring", "note"],
        )
        self.assertEqual(apply_color.call_args.args[1].name(), "#2f6ed3")
        apply_fill.assert_called_once()
        self.assertEqual(
            [item.data(0) for item in apply_fill.call_args.args[0]],
            ["ring"],
        )
        self.assertEqual(apply_fill.call_args.args[1].name(), "#f4d06f")


if __name__ == "__main__":
    unittest.main()
