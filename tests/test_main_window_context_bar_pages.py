import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
    QToolButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.shell.theme import (
    CONTEXT_BAR_BUTTON_HEIGHT,
)
from chemvas.ui.canvas_tool_settings_state import tool_settings_state_for
from chemvas.ui.main_window_context_bar_pages import (
    MainWindowContextBarPageBuilder,
    bond_label_for_state,
)
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    services_for_window,
)


class MainWindowContextBarPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = build_main_window()
        self.insert_controller = active_canvas_for_window(
            self.window
        ).services.structure.insert_controller
        self.tool_mode_controller = SimpleNamespace(
            get_arrow_line_width=mock.Mock(return_value=2.0),
            get_arrow_head_scale=mock.Mock(return_value=0.4),
            set_arrow_line_width=mock.Mock(),
            set_arrow_head_scale=mock.Mock(),
            get_atom_symbol=mock.Mock(return_value="N"),
            set_atom_symbol=mock.Mock(),
        )
        self.insert_controller_for_window = mock.Mock(
            return_value=self.insert_controller
        )
        self.tool_mode_controller_for_window = mock.Mock(
            return_value=self.tool_mode_controller
        )
        self.tool_state_service = mock.Mock()
        self.activate_bond_style_for_window = mock.Mock()
        self.set_bond_length_value_for_window = mock.Mock()
        self.bond_length_px_for_window = mock.Mock(return_value=20.0)
        self.apply_color_preset_for_window = mock.Mock()
        self.apply_ring_fill_preset_for_window = mock.Mock()
        self.rotate_selection_for_window = mock.Mock()
        self.flip_selection_for_window = mock.Mock()
        self.align_selection_for_window = mock.Mock()
        self.distribute_selection_for_window = mock.Mock()
        self.note_controller_for_window = mock.Mock(return_value=None)
        self.builder = MainWindowContextBarPageBuilder(
            insert_controller_for_window=self.insert_controller_for_window,
            tool_mode_controller_for_window=self.tool_mode_controller_for_window,
            tool_state_service=self.tool_state_service,
            activate_bond_style_for_window=self.activate_bond_style_for_window,
            set_bond_length_value_for_window=self.set_bond_length_value_for_window,
            bond_length_px_for_window=self.bond_length_px_for_window,
            apply_color_preset_for_window=self.apply_color_preset_for_window,
            apply_ring_fill_preset_for_window=self.apply_ring_fill_preset_for_window,
            rotate_selection_for_window=self.rotate_selection_for_window,
            flip_selection_for_window=self.flip_selection_for_window,
            align_selection_for_window=self.align_selection_for_window,
            distribute_selection_for_window=self.distribute_selection_for_window,
            note_controller_for_window=self.note_controller_for_window,
        )

    def tearDown(self) -> None:
        document_service = services_for_window(self.window).canvas_document_service
        for canvas in self.window.tab_references.all_canvases():
            document_service.mark_clean(canvas)
        self.window.close()
        self.app.processEvents()

    def test_bond_label_for_state_maps_known_bond_styles(self) -> None:
        self.assertEqual(bond_label_for_state("single", 1), "Single")
        self.assertEqual(bond_label_for_state("hash", 1), "Hash")
        self.assertIsNone(bond_label_for_state("unknown", 1))

    def test_arrow_button_uses_kind_when_its_display_label_changes(self) -> None:
        from chemvas.ui import main_window_context_bar_page_factories as factories

        with mock.patch.object(
            factories,
            "ARROW_MENU_SPECS",
            [("Changed display label", "curved_double")],
        ):
            pages = self.builder.build(self.window)
        pages.arrow_buttons["curved_double"].click()

        self.tool_state_service.set_arrow_type.assert_called_once_with(
            self.window, "curved_double"
        )

    def test_builder_returns_pages_and_wires_bond_ring_template_arrow_actions(
        self,
    ) -> None:
        pages = self.builder.build(self.window)

        self.assertEqual(
            set(pages.pages),
            {
                "empty",
                "bond",
                "arrow",
                "bracket",
                "atom",
                "text",
                "ring",
                "mark",
                "select",
                "orbital",
                "shape",
                "line",
                "color",
                "ring_fill",
            },
        )
        self.assertIn("Single", pages.bond_buttons)
        self.assertEqual(pages.bond_buttons["Single"].text(), "")
        self.assertFalse(pages.bond_buttons["Single"].icon().isNull())
        self.assertIn("curved_double", pages.arrow_buttons)
        self.assertIn("double_dagger", pages.bracket_buttons)
        self.assertIn("minus", pages.mark_buttons)
        self.assertIn("circled_plus", pages.mark_buttons)
        self.assertIn("circled_minus", pages.mark_buttons)
        self.assertIsNotNone(pages.bond_group)
        self.assertIsNotNone(pages.ring_group)
        self.assertIn((6, "benzene"), pages.ring_buttons)
        self.assertEqual(pages.ring_buttons[(6, "benzene")].text(), "")
        self.assertFalse(pages.ring_buttons[(6, "benzene")].icon().isNull())
        self.assertIsNotNone(pages.mark_group)
        self.assertIsNotNone(pages.arrow_group)
        self.assertEqual(pages.arrow_buttons["curved_double"].text(), "")
        self.assertFalse(pages.arrow_buttons["curved_double"].icon().isNull())
        self.assertIsNotNone(pages.bracket_group)
        self.assertIsInstance(pages.atom_input, QLineEdit)
        self.assertIs(
            pages.atom_input, pages.pages["atom"].findChild(QLineEdit, "atomInput")
        )
        page_labels = {
            key: [
                label.text()
                for label in page.findChildren(QLabel)
                if label.objectName() == "toolbarSectionLabel"
            ]
            for key, page in pages.pages.items()
        }
        self.assertEqual(page_labels["bond"], ["Bond"])
        self.assertEqual(page_labels["ring"], ["Ring"])
        self.assertEqual(page_labels["arrow"], ["Arrow"])
        self.assertEqual(page_labels["bracket"], ["Bracket"])
        self.assertEqual(page_labels["atom"], ["Atom"])
        self.assertEqual(page_labels["orbital"], ["Orbital"])
        self.assertEqual(page_labels["color"], ["Color"])
        self.assertEqual(page_labels["ring_fill"], ["Ring Fill"])
        self.assertEqual(pages.atom_input.placeholderText(), "Atom")
        self.assertEqual(pages.atom_input.text(), "N")
        self.assertEqual(pages.atom_input.maxLength(), 255)

        pages.bond_buttons["Hash"].click()

        self.activate_bond_style_for_window.assert_called_once_with(self.window, "Hash")
        length_spin = pages.pages["bond"].findChild(QDoubleSpinBox, "bondLengthInput")
        self.assertIsNotNone(length_spin)
        self.assertEqual(length_spin.value(), 20.0)
        # Focus/blur without a real edit must not commit (no spurious rescale).
        length_spin.editingFinished.emit()
        self.set_bond_length_value_for_window.assert_not_called()
        length_spin.setValue(28.5)
        length_spin.editingFinished.emit()
        self.set_bond_length_value_for_window.assert_called_once_with(self.window, 28.5)

        template_button = next(
            button
            for button in pages.pages["ring"].findChildren(QToolButton)
            if button.toolTip() == "Benzene"
        )
        with mock.patch.object(
            self.insert_controller, "begin_ring_template_insert"
        ) as insert:
            self.assertTrue(template_button.isCheckable())
            self.assertFalse(template_button.isChecked())
            template_button.click()

        insert.assert_called_once_with(6, style="benzene")
        self.assertTrue(template_button.isChecked())
        self.insert_controller_for_window.assert_called_once_with(self.window)

        pages.mark_buttons["minus"].click()
        self.assertTrue(pages.mark_buttons["minus"].isChecked())
        pages.mark_buttons["circled_plus"].click()
        self.tool_state_service.set_mark_kind.assert_any_call(self.window, "minus")
        self.tool_state_service.set_mark_kind.assert_any_call(
            self.window, "circled_plus"
        )
        self.assertTrue(pages.mark_buttons["circled_plus"].isChecked())
        self.assertEqual(pages.mark_buttons["circled_plus"].text(), "")
        self.assertFalse(pages.mark_buttons["circled_plus"].icon().isNull())

        pages.arrow_buttons["curved_double"].click()
        preset_button = next(
            button
            for button in pages.pages["arrow"].findChildren(QToolButton)
            if button.toolTip() == "Bold arrow preset"
        )
        preset_button.click()

        self.tool_state_service.set_arrow_type.assert_called_once_with(
            self.window, "curved_double"
        )
        self.tool_state_service.set_arrow_preset.assert_called_once_with(
            self.window, "Bold"
        )
        self.tool_mode_controller_for_window.assert_called_once_with(self.window)
        self.assertEqual(
            pages.arrow_buttons["curved_double"].width(), CONTEXT_BAR_BUTTON_HEIGHT
        )
        self.assertEqual(
            pages.arrow_buttons["curved_double"].height(), CONTEXT_BAR_BUTTON_HEIGHT
        )
        self.assertEqual(preset_button.height(), CONTEXT_BAR_BUTTON_HEIGHT)
        self.assertEqual(preset_button.width(), CONTEXT_BAR_BUTTON_HEIGHT)
        self.assertEqual(preset_button.text(), "")
        self.assertFalse(preset_button.icon().isNull())
        width_button = next(
            button
            for button in pages.pages["arrow"].findChildren(QToolButton)
            if button.toolTip() == "Arrow line width"
        )
        head_button = next(
            button
            for button in pages.pages["arrow"].findChildren(QToolButton)
            if button.toolTip() == "Arrow head size"
        )
        self.assertEqual(width_button.size().width(), CONTEXT_BAR_BUTTON_HEIGHT)
        self.assertEqual(head_button.size().height(), CONTEXT_BAR_BUTTON_HEIGHT)
        self.assertIsNotNone(width_button.menu())
        self.assertIsNotNone(head_button.menu())

        sliders = pages.pages["arrow"].findChildren(QSlider)
        self.assertEqual([slider.value() for slider in sliders], [20, 40])
        self.assertEqual(
            [slider.objectName() for slider in sliders],
            ["arrowCompactSlider", "arrowCompactSlider"],
        )
        self.assertEqual(
            [slider.height() for slider in sliders], [CONTEXT_BAR_BUTTON_HEIGHT] * 2
        )
        self.assertEqual(
            [slider.sizeHint().height() for slider in sliders],
            [CONTEXT_BAR_BUTTON_HEIGHT] * 2,
        )
        arrow_labels = [
            label
            for label in pages.pages["arrow"].findChildren(QLabel)
            if label.objectName() == "arrowCompactLabel"
        ]
        self.assertEqual(arrow_labels, [])
        sliders[0].setValue(51)
        sliders[1].setValue(25)
        self.tool_mode_controller.set_arrow_line_width.assert_called_once_with(5.1)
        self.tool_mode_controller.set_arrow_head_scale.assert_called_once_with(0.25)
        pages.atom_input.setText("Cl")
        self.tool_mode_controller.set_atom_symbol.assert_called_once_with("Cl")

        pages.bracket_buttons["dagger"].click()
        self.tool_state_service.set_bracket_type.assert_called_once_with(
            self.window, "dagger"
        )
        self.assertTrue(pages.bracket_buttons["dagger"].isChecked())

        color_button = next(
            button
            for button in pages.pages["color"].findChildren(QToolButton)
            if button.toolTip() == "Color: Blue"
        )
        color_button.click()
        self.apply_color_preset_for_window.assert_called_once_with(
            self.window, "#2f6ed3"
        )

        ring_fill_button = next(
            button
            for button in pages.pages["ring_fill"].findChildren(QToolButton)
            if button.toolTip() == "Ring Fill: Yellow"
        )
        ring_fill_button.click()
        self.apply_ring_fill_preset_for_window.assert_called_once_with(
            self.window, "#f4d06f"
        )

    def test_select_page_wires_flip_rotate_align_and_distribute(self) -> None:
        pages = self.builder.build(self.window)
        page = pages.pages["select"]

        page.findChild(QToolButton, "flip_horizontal_button").click()
        page.findChild(QToolButton, "flip_vertical_button").click()
        self.flip_selection_for_window.assert_has_calls(
            [
                mock.call(self.window, horizontal=True),
                mock.call(self.window, horizontal=False),
            ]
        )

        angle = page.findChild(QSpinBox, "rotateAngleInput")
        angle.setValue(30)
        page.findChild(QToolButton, "rotateApplyButton").click()
        self.rotate_selection_for_window.assert_called_once_with(self.window, 30.0)

        for mode in ("left", "center", "right", "top", "middle", "bottom"):
            page.findChild(QToolButton, f"align_{mode}_button").click()
        self.assertEqual(
            [call.args[1] for call in self.align_selection_for_window.call_args_list],
            ["left", "center", "right", "top", "middle", "bottom"],
        )
        for axis in ("horizontal", "vertical"):
            page.findChild(QToolButton, f"distribute_{axis}_button").click()
        self.assertEqual(
            [
                call.args[1]
                for call in self.distribute_selection_for_window.call_args_list
            ],
            ["horizontal", "vertical"],
        )
        # The SMILES field and Insert button sit on the Ring page.
        ring_page = pages.pages["ring"]
        field = ring_page.findChild(QLineEdit, "contextSmilesInput")
        field.setText("c1ccccc1")
        with mock.patch.object(
            self.insert_controller, "begin_smiles_insert"
        ) as begin_smiles_insert:
            ring_page.findChild(QToolButton, "smiles_render_button").click()
        begin_smiles_insert.assert_called_once_with("c1ccccc1")
        # The eraser has no options: its page is quiet.
        self.assertEqual(pages.pages["empty"].findChildren(QToolButton), [])

    def test_rare_arrow_kinds_share_one_menu_button(self) -> None:
        pages = self.builder.build(self.window)
        more = pages.arrow_buttons["arc_90_left"]

        self.assertIs(more, pages.arrow_buttons["inhibit"])
        self.assertEqual(more.objectName(), "more_arrows_button")
        self.assertNotIn("reaction", [b.objectName() for b in [more]])
        self.assertIsNot(pages.arrow_buttons["reaction"], more)
        self.assertEqual(
            [action.text() for action in more.menu().actions()],
            [
                "Equilibrium, forward favored",
                "Equilibrium, reverse favored",
                "Inhibition",
                "Arc 90°",
                "Arc 180°",
                "Arc 270°",
            ],
        )

        inhibit = next(a for a in more.menu().actions() if a.text() == "Inhibition")
        inhibit.trigger()

        self.tool_state_service.set_arrow_type.assert_called_once_with(
            self.window, "inhibit"
        )
        self.assertEqual(more.toolTip(), "More arrows: Inhibition")
        # The button wears the picked entry's own icon.
        self.assertEqual(more.icon().cacheKey(), inhibit.icon().cacheKey())

    def test_reflecting_a_rare_arrow_kind_dresses_the_menu_button(self) -> None:
        canvas = active_canvas_for_window(self.window)
        tool_settings_state_for(canvas).active_arrow_type = "arc_180_left"

        services_for_window(self.window).context_bar_service.reflect_arrow_state(
            self.window
        )

        more = self.window.findChild(QToolButton, "more_arrows_button")
        self.assertTrue(more.isChecked())
        self.assertEqual(more.toolTip(), "More arrows: Arc 180\u00b0")
