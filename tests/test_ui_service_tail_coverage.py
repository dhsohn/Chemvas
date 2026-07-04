import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsPathItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QMainWindow,
        QToolButton,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_color_mutation_service import CanvasColorMutationService
    from ui.canvas_note_controller import CanvasNoteController
    from ui.canvas_ring_fill_scene_service import CanvasRingFillSceneService
    from ui.canvas_scene_items_state import (
        selected_notes_for,
        set_scene_item_collection_for,
        set_selected_notes_for,
    )
    from ui.canvas_text_style_state import CanvasTextStyleState
    from ui.handle_mutation_service import HandleMutationService
    from ui.main_window_panel_toolbar import MainWindowPanelToolbarCallbacks
    from ui.main_window_toolbar_buttons import ArrowButton
    from ui.main_window_ui_assembly_service import MainWindowUIAssemblyService
    from ui.note_item_access import set_committed_note_text_for
    from ui.scene_item_restore import create_orbital_item_from_state
    from ui.scene_paste_apply_logic import apply_paste_payload
    from ui.scene_transform_logic import flip_scene_item_state


def _history_service(push=None):
    return SimpleNamespace(push=push if push is not None else mock.Mock())


def _panel_toolbar_callbacks() -> "MainWindowPanelToolbarCallbacks":
    return MainWindowPanelToolbarCallbacks(
        save_canvas=mock.Mock(),
        save_canvas_as=mock.Mock(),
        load_canvas=mock.Mock(),
        export_figure=mock.Mock(),
        export_mol=mock.Mock(),
        open_preview_window=mock.Mock(),
        new_canvas=mock.Mock(),
        show_rotate_options=mock.Mock(),
            set_note_font_family=mock.Mock(),
    )


def _color_service_for(canvas) -> CanvasColorMutationService:
    graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=(set(), set())))
    return CanvasColorMutationService(canvas, graph_service=graph_service)


class _FakeRingItem:
    def __init__(self, atom_ids) -> None:
        self._atom_ids = atom_ids
        self._polygon = QPolygonF()
        self.setPolygon = mock.Mock(side_effect=self._set_polygon)

    def _set_polygon(self, polygon) -> None:
        self._polygon = QPolygonF(polygon)

    def data(self, key):
        if key == 2:
            return self._atom_ids
        return None

    def polygon(self):
        return QPolygonF(self._polygon)


class _CurvedEndpointItem:
    def __init__(self) -> None:
        self._data = {
            2: {
                "start": QPointF(0.0, 0.0),
                "end": QPointF(10.0, 0.0),
                "control": QPointF(5.0, 8.0),
            }
        }
        self.setData = mock.Mock(side_effect=self._set_data)

    def data(self, key):
        return self._data.get(key)

    def _set_data(self, key, value) -> None:
        self._data[key] = value


class _NoteItem:
    def __init__(self, rect: QRectF) -> None:
        self._rect = QRectF(rect)

    def sceneBoundingRect(self) -> QRectF:
        return QRectF(self._rect)


def _polygon_points(polygon) -> list[tuple[float, float]]:
    return [(round(point.x(), 6), round(point.y(), 6)) for point in polygon]


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for UI service tail coverage tests")
class UIServiceTailCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_update_ring_fills_for_atoms_returns_for_empty_atom_ids(self) -> None:
        canvas = SimpleNamespace(ring_items=mock.Mock())

        CanvasRingFillSceneService(canvas).update_ring_fills_for_atoms(set())

        canvas.ring_items.assert_not_called()

    def test_rotate_ring_fills_3d_refreshes_matching_list_backed_ring(self) -> None:
        ring_item = _FakeRingItem([1, 2, 3])
        skipped_item = _FakeRingItem([4, 5, 6])
        canvas = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: SimpleNamespace(x=0.0, y=0.0),
                    2: SimpleNamespace(x=2.0, y=0.0),
                    3: SimpleNamespace(x=1.0, y=1.5),
                    4: SimpleNamespace(x=10.0, y=10.0),
                    5: SimpleNamespace(x=11.0, y=10.0),
                    6: SimpleNamespace(x=10.5, y=11.0),
                }
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(bond_length_px=12.0)),
        )
        set_scene_item_collection_for(canvas, "ring_items", [ring_item, skipped_item])

        CanvasRingFillSceneService(canvas).rotate_ring_fills_3d(
            {1, 2, 3},
            (0.0, 0.0, 0.0),
            0.25,
            0.5,
            1.0,
        )

        ring_item.setPolygon.assert_called_once()
        self.assertEqual(
            _polygon_points(ring_item.setPolygon.call_args.args[0]),
            [(0.0, 0.0), (2.0, 0.0), (1.0, 1.5)],
        )
        skipped_item.setPolygon.assert_not_called()

    def test_update_curved_endpoint_ignores_unknown_endpoint_name(self) -> None:
        canvas = SimpleNamespace(
            _update_selection_outline=mock.Mock(),
        )
        item = _CurvedEndpointItem()

        HandleMutationService(canvas).update_curved_endpoint(item, QPointF(2.0, 3.0), "middle")

        item.setData.assert_not_called()
        canvas._update_selection_outline.assert_not_called()

    def test_arrow_button_paints_up_triangle_when_rect_is_large_enough(self) -> None:
        owner = QMainWindow()
        self.addCleanup(owner.close)
        button = ArrowButton("up", owner)
        button.resize(24, 24)
        button.show()

        self.app.processEvents()
        pixmap = button.grab()

        self.assertFalse(pixmap.isNull())

    def test_arrow_button_paint_returns_when_adjusted_rect_is_empty(self) -> None:
        class _TinyRectArrowButton(ArrowButton):
            def rect(self):
                return QRect(0, 0, 1, 1)

        owner = QMainWindow()
        self.addCleanup(owner.close)
        button = _TinyRectArrowButton("up", owner)
        button.resize(24, 24)
        button.show()

        self.app.processEvents()
        pixmap = button.grab()

        self.assertFalse(pixmap.isNull())

    def test_corner_menu_button_allows_menu_without_default_action_or_icon(self) -> None:
        service = MainWindowUIAssemblyService(
            scene_transform_controller_for_window=mock.Mock(),
            insert_controller_for_window=mock.Mock(),
            history_service_for_window=mock.Mock(),
            build_tool_actions_for_window=mock.Mock(),
            panel_toolbar_callbacks=_panel_toolbar_callbacks(),
        )
        button = service.create_corner_menu_button(
            icon=None,
            tooltip="More",
            style_sheet="padding: 0;",
            popup_mode=QToolButton.ToolButtonPopupMode.InstantPopup,
            menu_builder=lambda menu: menu.addAction("Only action"),
            default_action=None,
        )
        self.addCleanup(button.close)

        self.assertIsNone(button.defaultAction())
        self.assertTrue(button.icon().isNull())
        self.assertEqual(button.toolTip(), "More")
        self.assertEqual([action.text() for action in button.menu().actions()], ["Only action"])

    def test_create_orbital_item_from_state_returns_none_when_builder_has_no_parts(self) -> None:
        item = create_orbital_item_from_state(
            {"kind": "orbital", "center": (4.0, 5.0), "orbital_kind": "sp3"},
            build_orbital_items=mock.Mock(return_value=[]),
            orbital_base_handle_dist=32.0,
        )

        self.assertIsNone(item)

    def test_flip_scene_item_state_flips_valid_note_vertically_from_bottom_edge(self) -> None:
        note_item = _NoteItem(QRectF(3.0, 4.0, 10.0, 6.0))

        state = flip_scene_item_state(
            note_item,
            {"kind": "note", "text": "note", "x": 3.0, "y": 4.0},
            center=QPointF(0.0, 20.0),
            horizontal=False,
            transformed_atom_positions={},
            atoms={},
            flip_point=mock.Mock(),
            ts_bracket_rect_from_state=mock.Mock(),
        )

        self.assertEqual(state["x"], 3.0)
        self.assertEqual(state["y"], 30.0)

    def test_color_mutation_helpers_ignore_invalid_ring_fill_color_and_atom_self_references(self) -> None:
        ring_item = QGraphicsPathItem()
        ring_item.setData(0, "ring")
        fill_pushes = []
        fill_canvas = SimpleNamespace(
            _ring_state_dict=mock.Mock(),
            services=SimpleNamespace(history_service=_history_service(fill_pushes.append)),
        )

        _color_service_for(fill_canvas).apply_ring_fill_color(ring_item, QColor())

        fill_canvas._ring_state_dict.assert_not_called()
        self.assertEqual(fill_pushes, [])

        atom_item = QGraphicsPathItem()
        atom_item.setData(0, "atom")
        atom_item.setData(1, 7)
        atom_canvas = SimpleNamespace(
            model=SimpleNamespace(atoms={7: SimpleNamespace(color="#112233")}),
            atom_items={7: atom_item},
            atom_dots={7: atom_item},
            services=SimpleNamespace(
                history_service=_history_service(),
                atom_label_service=SimpleNamespace(implicit_carbon_dot_brush=mock.Mock()),
            ),
            push_command=mock.Mock(),
        )

        _color_service_for(atom_canvas)._apply_atom_color(atom_item, QColor("#112233"))

        atom_canvas.services.atom_label_service.implicit_carbon_dot_brush.assert_not_called()
        atom_canvas.push_command.assert_not_called()

    def test_note_controller_noop_focus_out_deselects_then_reedit_reselects(self) -> None:
        item = QGraphicsTextItem("Stable")
        set_committed_note_text_for(item, "Stable")
        canvas = SimpleNamespace(
            select_note=mock.Mock(),
            scene=mock.Mock(return_value=QGraphicsScene()),
            setFocus=mock.Mock(),
            push_command=mock.Mock(),
            services=SimpleNamespace(
                history_service=_history_service(),
                selection_controller=SimpleNamespace(select_note=mock.Mock()),
            ),
        )
        set_selected_notes_for(canvas, [item])
        canvas.scene().addItem(item)
        controller = CanvasNoteController(canvas)

        controller.handle_note_focus_out(item)
        # An unchanged note pushes no command, but clicking away deselects it.
        canvas.push_command.assert_not_called()
        self.assertNotIn(item, selected_notes_for(canvas))

        controller.begin_note_edit(item)
        # Re-editing a now-deselected note selects it again.
        canvas.services.selection_controller.select_note.assert_called_once_with(item, additive=False)
        canvas.setFocus.assert_called_once_with(Qt.FocusReason.MouseFocusReason)

    def test_apply_note_style_uses_legacy_line_height_value_when_enum_value_is_wrapped(self) -> None:
        class _FakeOption:
            def setAlignment(self, value) -> None:
                self.alignment = value

        class _FakeDocument:
            def __init__(self) -> None:
                self.option = _FakeOption()

            def defaultTextOption(self):
                return self.option

            def setDefaultTextOption(self, option) -> None:
                self.saved_option = option

        class _HeightType:
            value = 42

        class _FakeBlockFormat:
            class LineHeightTypes:
                ProportionalHeight = _HeightType()

            def setLineHeight(self, value, height_type) -> None:
                self.height = (value, height_type)

        class _FakeCursor:
            SelectionType = SimpleNamespace(Document="document")
            last_instance = None

            def __init__(self, document) -> None:
                self.document = document
                _FakeCursor.last_instance = self

            def select(self, selection) -> None:
                self.selection = selection

            def mergeBlockFormat(self, block_format) -> None:
                self.block_format = block_format

        document = _FakeDocument()
        item = SimpleNamespace(
            setFont=mock.Mock(),
            setDefaultTextColor=mock.Mock(),
            document=mock.Mock(return_value=document),
        )
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                text_font_family="Arial",
                text_font_size=12,
                text_font_weight=QFont.Weight.Bold,
                text_italic=False,
                text_color=QColor("#123456"),
                text_alignment=Qt.AlignmentFlag.AlignLeft,
                text_line_spacing=1.4,
            ),
            services=SimpleNamespace(
                history_service=_history_service(),
                selection_controller=SimpleNamespace(update_note_selection_box=mock.Mock()),
            ),
        )
        controller = CanvasNoteController(canvas)
        controller.update_note_box = mock.Mock()

        with mock.patch("ui.canvas_note_controller.QTextBlockFormat", _FakeBlockFormat), mock.patch(
            "ui.canvas_note_controller.QTextCursor",
            _FakeCursor,
        ):
            controller.apply_note_style(item)

        self.assertEqual(_FakeCursor.last_instance.block_format.height, (140, 42))
        controller.update_note_box.assert_called_once_with(item)
        canvas.services.selection_controller.update_note_selection_box.assert_called_once_with(item)

    def test_apply_note_style_accepts_legacy_line_height_constant_without_value(self) -> None:
        class _FakeDocument:
            def defaultTextOption(self):
                return mock.Mock()

            def setDefaultTextOption(self, option) -> None:
                self.saved_option = option

        class _FakeBlockFormat:
            class LineHeightTypes:
                ProportionalHeight = "legacy-proportional-height"

            def setLineHeight(self, value, height_type) -> None:
                self.height = (value, height_type)

        class _FakeCursor:
            SelectionType = SimpleNamespace(Document="document")
            last_instance = None

            def __init__(self, document) -> None:
                _FakeCursor.last_instance = self

            def select(self, selection) -> None:
                self.selection = selection

            def mergeBlockFormat(self, block_format) -> None:
                self.block_format = block_format

        item = SimpleNamespace(
            setFont=mock.Mock(),
            setDefaultTextColor=mock.Mock(),
            document=mock.Mock(return_value=_FakeDocument()),
        )
        canvas = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                text_font_family="Arial",
                text_font_size=12,
                text_font_weight=QFont.Weight.Bold,
                text_italic=False,
                text_color=QColor("#123456"),
                text_alignment=Qt.AlignmentFlag.AlignLeft,
                text_line_spacing=1.4,
            ),
            services=SimpleNamespace(
                history_service=_history_service(),
                selection_controller=SimpleNamespace(update_note_selection_box=mock.Mock()),
            ),
        )
        controller = CanvasNoteController(canvas)
        controller.update_note_box = mock.Mock()

        with mock.patch("ui.canvas_note_controller.QTextBlockFormat", _FakeBlockFormat), mock.patch(
            "ui.canvas_note_controller.QTextCursor",
            _FakeCursor,
        ):
            controller.apply_note_style(item)

        self.assertEqual(
            _FakeCursor.last_instance.block_format.height,
            (140, "legacy-proportional-height"),
        )

    def test_apply_paste_payload_skips_translated_scene_state_that_builds_no_item(self) -> None:
        result = apply_paste_payload(
            atoms=[],
            bonds=[],
            rings=[{"kind": "ring"}],
            marks=[],
            scene_items=[],
            dx=1.0,
            dy=2.0,
            add_atom=mock.Mock(),
            apply_atom_color=mock.Mock(),
            set_atom_annotation=mock.Mock(),
            add_or_update_atom_label=mock.Mock(),
            add_bond=mock.Mock(),
            restore_bond_from_state=mock.Mock(),
            translated_scene_item_state=mock.Mock(return_value={"kind": "ring"}),
            create_scene_item_from_state=mock.Mock(return_value=None),
        )

        self.assertFalse(result.has_changes())
        self.assertEqual(result.added_scene_items, [])

    def test_apply_paste_payload_accepts_atom_without_string_color(self) -> None:
        add_atom = mock.Mock(return_value=42)
        apply_atom_color = mock.Mock()
        add_or_update_atom_label = mock.Mock()

        result = apply_paste_payload(
            atoms=[{"id": 5, "element": "N", "x": 1.5, "y": 2.5, "color": None}],
            bonds=[],
            rings=[],
            marks=[],
            scene_items=[],
            dx=10.0,
            dy=20.0,
            add_atom=add_atom,
            apply_atom_color=apply_atom_color,
            set_atom_annotation=mock.Mock(),
            add_or_update_atom_label=add_or_update_atom_label,
            add_bond=mock.Mock(),
            restore_bond_from_state=mock.Mock(),
            translated_scene_item_state=mock.Mock(),
            create_scene_item_from_state=mock.Mock(),
        )

        add_atom.assert_called_once_with("N", 11.5, 22.5)
        apply_atom_color.assert_not_called()
        add_or_update_atom_label.assert_not_called()
        self.assertEqual(result.atom_id_map, {5: 42})
        self.assertTrue(result.has_changes())


if __name__ == "__main__":
    unittest.main()
