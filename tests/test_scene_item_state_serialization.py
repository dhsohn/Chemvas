import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QApplication, QGraphicsPolygonItem, QGraphicsTextItem

from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.annotations import state as serialization
from chemvas.ui.annotations.materialize import (
    create_note_item_from_state,
    create_scene_item_from_state,
)
from tests.scene_render_context import attach_scene_render_context


class SceneItemStateSerializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_note_state_ignores_arbitrary_item_payload(self) -> None:
        note = QGraphicsTextItem("document text")
        note.setData(0, "note")
        note.setData(9, {"kind": "note", "text": "stale metadata"})
        state = serialization.note_state_dict_for(object(), note)
        self.assertEqual(state["text"], "document text")
        state["text"] = "changed copy"
        self.assertEqual(note.toPlainText(), "document text")

    def test_record_backed_items_ignore_arbitrary_payloads(self) -> None:
        canvas = SimpleNamespace()
        context = attach_scene_render_context(canvas)
        states = [
            {"kind": "arrow", "start": (1.0, 2.0), "end": (10.0, 12.0)},
            {
                "kind": "shape",
                "left": 1.0,
                "top": 2.0,
                "right": 10.0,
                "bottom": 12.0,
                "shape_kind": "rect",
                "stroke_style": "solid",
            },
            {
                "kind": "ts_bracket",
                "left": 1.0,
                "top": 2.0,
                "right": 10.0,
                "bottom": 12.0,
                "bracket_kind": "square_pair",
            },
            {"kind": "orbital", "center": (1.0, 2.0), "orbital_kind": "p"},
        ]
        for state in states:
            with self.subTest(kind=state["kind"]):
                item = create_scene_item_from_state(context, state)
                expected = serialization.scene_item_state_for(canvas, item)
                item.setData(9, {"kind": "note", "text": "stale foreign payload"})
                self.assertEqual(
                    serialization.scene_item_state_for(canvas, item), expected
                )

    def test_scene_item_state_serializes_supported_qt_items_directly(self) -> None:
        note = QGraphicsTextItem("direct")
        note.setData(0, "note")
        note.setPos(QPointF(4.0, -3.0))

        state = serialization.scene_item_state(
            note, mark_center_getter=lambda _: QPointF()
        )
        self.assertEqual(
            {key: state[key] for key in ("kind", "text", "x", "y")},
            {"kind": "note", "text": "direct", "x": 4.0, "y": -3.0},
        )
        self.assertIn("direct", state["html"])

    def test_note_state_serializes_same_sanitized_subset_restored_notes_accept(
        self,
    ) -> None:
        note = QGraphicsTextItem()
        note.setData(0, "note")
        note.setHtml(
            '<div style="background-color:#ffeeaa">'
            '<font color="#123456" face="Courier New" size="4"><u>Legacy</u></font>'
            '<blockquote><ul><li><span style="background-color:#aabbcc">Item</span></li></ul></blockquote>'
            '<img src="file:///tmp/secret"><script>bad()</script>'
            "</div>"
        )

        state = serialization.note_state_dict(note)

        self.assertEqual(state["html"], sanitize_note_html(note.toHtml()))
        self.assertNotIn("<html", state["html"].lower())
        self.assertNotIn("<script", state["html"].lower())
        self.assertNotIn("<img", state["html"].lower())
        self.assertNotIn("file://", state["html"].lower())
        self.assertIn("text-decoration:underline", state["html"])
        self.assertIn("font-family:&#x27;Courier New&#x27;", state["html"])
        self.assertIn("font-size:large", state["html"])
        self.assertIn("color:#123456", state["html"])
        self.assertIn("background-color:#ffeeaa", state["html"])
        self.assertIn("<ul", state["html"])
        self.assertIn("<li", state["html"])

        restored = create_note_item_from_state(
            state,
            note_item_factory=QGraphicsTextItem,
            note_style_applier=lambda item: None,
        )
        resaved = serialization.note_state_dict(restored)

        self.assertEqual(resaved["html"], state["html"])

    def test_state_dict_for_rejects_unowned_ring_payload(self) -> None:
        ring = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(3.0, 0.0), QPointF(1.5, 2.0)])
        )
        ring.setData(0, "ring")
        ring.setData(9, {"kind": "ring", "points": [(9.0, 9.0)], "atom_ids": [42]})

        state = serialization.ring_state_dict_for(object(), ring)

        self.assertEqual(state, {})
