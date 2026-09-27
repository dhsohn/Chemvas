import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from chemvas.ui.canvas.canvas_note_controller import CanvasNoteController
from chemvas.ui.canvas.canvas_scene_items_state import (
    CanvasSceneItemsState,
)
from chemvas.ui.canvas.canvas_text_style_state import (
    CanvasTextStyleState,
    set_text_style_for,
)


def _make_canvas_note_view(scene: QGraphicsScene) -> SimpleNamespace:
    view = SimpleNamespace(
        scene=lambda: scene,
        setFocus=mock.Mock(),
        runtime_state=canvas_runtime_state(
            scene_items_state=CanvasSceneItemsState(),
            text_style_state=CanvasTextStyleState(
                note_padding=6.0,
                note_box_enabled=True,
                note_border_enabled=True,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.4,
                note_border_color=QColor("#111111"),
                note_border_width=1.2,
                text_font_family="Arial",
                text_font_size=13,
                text_font_weight=QFont.Weight.DemiBold,
                text_italic=True,
                text_color=QColor("#334455"),
                text_alignment=Qt.AlignmentFlag.AlignRight,
                text_line_spacing=1.25,
            ),
        ),
    )

    def select_note(target, additive: bool = False) -> None:
        selected_notes = view.runtime_state.selection_state.selected_notes
        if not additive:
            selected_notes.clear()
        if target not in selected_notes:
            selected_notes.append(target)

    view.select_note = select_note
    view.services = canvas_runtime_services(
        history_service=SimpleNamespace(push=mock.Mock()),
        selection=SimpleNamespace(
            select_note=select_note,
            update_note_selection_box=mock.Mock(),
        ),
    )
    return view


class CanvasViewNoteWrapperContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_note_controller_begin_note_edit_selects_note_and_focuses_editor(
        self,
    ) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        view = _make_canvas_note_view(scene)
        controller = CanvasNoteController(view)

        controller.begin_note_edit(item)

        self.assertIn(item, view.runtime_state.selection_state.selected_notes)
        self.assertEqual(
            item.textInteractionFlags(), Qt.TextInteractionFlag.TextEditorInteraction
        )
        self.assertTrue(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
        self.assertIs(scene.focusItem(), item)
        view.setFocus.assert_called_once()

    def test_note_controller_apply_note_style_updates_font_and_boxes(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Styled")
        scene.addItem(item)
        view = _make_canvas_note_view(scene)
        controller = CanvasNoteController(view)

        controller.apply_note_style(item)

        font = item.font()
        self.assertEqual(font.family(), "Arial")
        self.assertEqual(font.pointSize(), 13)
        self.assertEqual(font.weight(), QFont.Weight.DemiBold)
        self.assertTrue(font.italic())
        self.assertEqual(item.defaultTextColor().name(), "#334455")
        self.assertEqual(
            item.document().defaultTextOption().alignment(), Qt.AlignmentFlag.AlignRight
        )
        self.assertIsNotNone(item.data(20))
        self.assertTrue(item.data(20).isVisible())
        view.services.selection.update_note_selection_box.assert_called_once_with(item)

    def test_note_controller_update_text_note_and_box_toggle(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Old")
        scene.addItem(item)
        view = _make_canvas_note_view(scene)
        controller = CanvasNoteController(view)

        controller.update_text_note(item, "Updated")
        self.assertEqual(item.toPlainText(), "Updated")
        self.assertTrue(item.data(20).isVisible())

        set_text_style_for(view, "note_box_enabled", False)
        set_text_style_for(view, "note_border_enabled", False)
        controller.update_note_box(item)
        self.assertIsInstance(item.data(20), QGraphicsRectItem)
        self.assertFalse(item.data(20).isVisible())
