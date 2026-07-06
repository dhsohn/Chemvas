import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication, QGraphicsPolygonItem, QGraphicsTextItem
except ModuleNotFoundError:
    QApplication = None
    QPointF = None
    QPolygonF = None

if QApplication is not None:
    from ui import scene_item_state as facade
    from ui import scene_item_state_serialization as serialization
    from ui.note_html_sanitizer import sanitize_note_html
    from ui.scene_item_restore import create_note_item_from_state


class EmbeddedStateItem:
    def __init__(self, state: dict) -> None:
        self.state = state

    def data(self, role: int):
        return self.state if role == 9 else None


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene item state tests")
class SceneItemStateSerializationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_embedded_scene_item_state_returns_copy_from_role_nine(self) -> None:
        embedded = {"kind": "note", "text": "memo", "x": 1.0, "y": 2.0}
        state = serialization.embedded_scene_item_state(EmbeddedStateItem(embedded))

        self.assertEqual(state, embedded)

        state["text"] = "changed"
        self.assertEqual(embedded["text"], "memo")

    def test_scene_item_state_serializes_supported_qt_items_directly(self) -> None:
        note = QGraphicsTextItem("direct")
        note.setData(0, "note")
        note.setPos(QPointF(4.0, -3.0))

        state = serialization.scene_item_state(note, mark_center_getter=lambda _: QPointF())
        self.assertEqual(
            {key: state[key] for key in ("kind", "text", "x", "y")},
            {"kind": "note", "text": "direct", "x": 4.0, "y": -3.0},
        )
        self.assertIn("direct", state["html"])

    def test_note_state_serializes_same_sanitized_subset_restored_notes_accept(self) -> None:
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

    def test_state_dict_for_prefers_embedded_scene_state(self) -> None:
        ring = QGraphicsPolygonItem(QPolygonF([QPointF(0.0, 0.0), QPointF(3.0, 0.0), QPointF(1.5, 2.0)]))
        ring.setData(0, "ring")
        ring.setData(9, {"kind": "ring", "points": [(9.0, 9.0)], "atom_ids": [42]})

        state = serialization.ring_state_dict_for(object(), ring)

        self.assertEqual(state, {"kind": "ring", "points": [(9.0, 9.0)], "atom_ids": [42]})

    def test_scene_item_state_facade_reexports_serialization_contract(self) -> None:
        self.assertIs(facade.scene_item_state, serialization.scene_item_state)
        self.assertIs(facade.scene_item_state_for, serialization.scene_item_state_for)
        self.assertIs(facade.arrow_state_dict, serialization.arrow_state_dict)


if __name__ == "__main__":
    unittest.main()
