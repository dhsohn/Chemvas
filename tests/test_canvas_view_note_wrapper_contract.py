import os
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.runtime_services import canvas_runtime_services

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QFont
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from chemvas.ui.canvas_note_controller import CanvasNoteController
    from chemvas.ui.canvas_service_access import canvas_services_for
    from chemvas.ui.canvas_text_style_state import (
        CanvasTextStyleState,
        set_text_style_for,
    )
    from chemvas.ui.note_item_access import apply_note_style_for, update_note_box_for


class _FakeNoteController:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def create_text_note(self, pos, text):
        self.calls.append(("create_text_note", pos, text))
        return "note-item"

    def update_text_note(self, item, text) -> None:
        self.calls.append(("update_text_note", item, text))

    def begin_note_edit(self, item) -> None:
        self.calls.append(("begin_note_edit", item))

    def apply_text_style_to_selected(self) -> None:
        self.calls.append(("apply_text_style_to_selected",))

    def apply_note_style(self, item) -> None:
        self.calls.append(("apply_note_style", item))

    def update_note_box(self, item) -> None:
        self.calls.append(("update_note_box", item))


def _make_canvas_note_view(scene: QGraphicsScene) -> SimpleNamespace:
    view = SimpleNamespace(
        selected_notes=[],
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
        scene=lambda: scene,
        setFocus=mock.Mock(),
    )

    def select_note(target, additive: bool = False) -> None:
        if not additive:
            view.selected_notes.clear()
        if target not in view.selected_notes:
            view.selected_notes.append(target)

    view.select_note = select_note
    view.services = canvas_runtime_services(
        history_service=SimpleNamespace(push=mock.Mock()),
        selection_controller=SimpleNamespace(
            select_note=select_note,
            update_note_selection_box=mock.Mock(),
        ),
    )
    return view


@unittest.skipUnless(
    QApplication is not None, "PyQt6 is required for canvas view note tests"
)
class CanvasViewNoteWrapperContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_add_text_note_uses_note_controller(self) -> None:
        scene = QGraphicsScene()
        fake_controller = _FakeNoteController()
        view = _make_canvas_note_view(scene)
        view.services.interaction.note_controller = fake_controller

        item = canvas_services_for(view).interaction.note_controller.create_text_note(
            QPointF(3.0, 4.0), "Scheme"
        )

        self.assertEqual(item, "note-item")
        self.assertEqual(
            fake_controller.calls, [("create_text_note", QPointF(3.0, 4.0), "Scheme")]
        )

    def test_note_actions_use_note_controller(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        fake_controller = _FakeNoteController()
        view = _make_canvas_note_view(scene)

        view.services.interaction.note_controller = fake_controller

        controller = canvas_services_for(view).interaction.note_controller
        controller.update_text_note(item, "Updated")
        controller.begin_note_edit(item)
        controller.apply_text_style_to_selected()
        apply_note_style_for(view, item)
        update_note_box_for(view, item)

        self.assertEqual(
            fake_controller.calls,
            [
                ("update_text_note", item, "Updated"),
                ("begin_note_edit", item),
                ("apply_text_style_to_selected",),
                ("apply_note_style", item),
                ("update_note_box", item),
            ],
        )

    def test_note_controller_begin_note_edit_selects_note_and_focuses_editor(
        self,
    ) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)
        view = _make_canvas_note_view(scene)
        controller = CanvasNoteController(view)

        controller.begin_note_edit(item)

        self.assertIn(item, view.selected_notes)
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
        view.services.selection.selection_controller.update_note_selection_box.assert_called_once_with(
            item
        )

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
