import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QImage, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if QApplication is not None:
    from core.model import Atom, Bond, MoleculeModel
    from ui.scene_ops_controller import SceneOpsController


def _set_selectable(item: QGraphicsItem) -> QGraphicsItem:
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    return item


def _make_rect_item(
    kind: str,
    *,
    data1=None,
    state: dict | None = None,
    rect: QRectF | None = None,
) -> QGraphicsRectItem:
    item = _set_selectable(QGraphicsRectItem(rect or QRectF(0.0, 0.0, 10.0, 10.0)))
    item.setData(0, kind)
    if data1 is not None:
        item.setData(1, data1)
    if state is not None:
        item.setData(9, dict(state))
    return item


def _make_text_item(kind: str, text: str, state: dict) -> QGraphicsTextItem:
    item = _set_selectable(QGraphicsTextItem(text))
    item.setData(0, kind)
    item.setData(9, dict(state))
    return item


def _make_ring_item(atom_ids: list[int], *, state: dict | None = None, add_to_scene: bool = True) -> QGraphicsPolygonItem:
    polygon = QPolygonF([QPointF(0.0, 0.0), QPointF(12.0, 0.0), QPointF(6.0, 10.0)])
    item = _set_selectable(QGraphicsPolygonItem(polygon))
    item.setData(0, "ring")
    item.setData(2, list(atom_ids))
    item.setData(9, state or {"kind": "ring", "atom_ids": list(atom_ids), "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]})
    if not add_to_scene:
        item.setParentItem(None)
    return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene ops controller clipboard payload tests")
class SceneOpsControllerClipboardPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def tearDown(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.clear(mode=clipboard.Mode.Clipboard)

    def test_selection_payload_for_clipboard_collects_valid_atoms_bonds_rings_marks_and_scene_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0, color="#111111", explicit_label=True),
                2: Atom("O", 20.0, 0.0, color="#222222"),
                3: Atom("N", 40.0, 0.0, color="#333333"),
            },
            bonds=[Bond(1, 2, 2, style="double", color="#444444"), Bond(2, 3, 1, style="single", color="#555555")],
        )
        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        ring_item = _make_ring_item([1, 2])
        linked_mark = _make_text_item(
            "mark",
            "linked",
            {"kind": "mark", "atom_id": 1, "x": 3.0, "y": 4.0},
        )
        free_mark = _make_rect_item(
            "mark",
            state={"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0},
        )
        note_item = _make_text_item("note", "note", {"kind": "note", "text": "note", "x": 80.0, "y": 90.0})
        arrow_item = _make_rect_item(
            "arrow",
            state={"kind": "arrow", "start": (5.0, 6.0), "end": (7.0, 8.0)},
        )

        canvas._marks_by_atom[1] = [linked_mark]
        canvas.ring_items = [ring_item]
        for item in (atom_item, bond_item, linked_mark, free_mark, note_item, arrow_item):
            canvas.add_item(item, selected=True)
        canvas.add_item(ring_item, selected=False)

        controller = SceneOpsController(canvas)
        payload = controller._selection_payload_for_clipboard()

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["format"], "lightdraw-selection")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(
            payload["atoms"],
            [
                {"id": 1, "element": "C", "x": 0.0, "y": 0.0, "color": "#111111", "explicit_label": True},
                {"id": 2, "element": "O", "x": 20.0, "y": 0.0, "color": "#222222", "explicit_label": False},
            ],
        )
        self.assertEqual(
            payload["bonds"],
            [{"a": 1, "b": 2, "order": 2, "style": "double", "color": "#444444"}],
        )
        self.assertEqual(
            payload["rings"],
            [{"kind": "ring", "atom_ids": [1, 2], "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]}],
        )
        self.assertEqual(len(payload["marks"]), 2)
        self.assertIn({"kind": "mark", "atom_id": 1, "x": 3.0, "y": 4.0}, payload["marks"])
        self.assertIn({"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0}, payload["marks"])
        self.assertEqual(len(payload["scene_items"]), 2)
        self.assertIn({"kind": "note", "text": "note", "x": 80.0, "y": 90.0}, payload["scene_items"])
        self.assertIn({"kind": "arrow", "start": (5.0, 6.0), "end": (7.0, 8.0)}, payload["scene_items"])

    def test_selection_payload_for_clipboard_filters_invalid_selection_entries(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0),
                2: Atom("O", 20.0, 0.0),
            },
            bonds=[Bond(1, 2, 1, style="single", color="#555555")],
        )
        valid_atom = _make_rect_item("atom", data1=1)
        invalid_atom = _make_rect_item("atom", data1="bad")
        valid_bond = _make_rect_item("bond", data1=0)
        invalid_bond = _make_rect_item("bond", data1=99)
        valid_mark = _make_text_item("mark", "mark", {"kind": "mark", "atom_id": 1, "x": 6.0, "y": 7.0})
        invalid_mark = _make_text_item("mark", "mark", {})
        valid_ring = _make_ring_item([1, 2])
        invalid_ring = _make_ring_item([1, 2], state={"kind": "ring", "atom_ids": [1, 2], "points": []}, add_to_scene=False)
        invalid_ring.setData(2, [])
        scene_note = _make_text_item("note", "note", {"kind": "note", "text": "still here", "x": 10.0, "y": 11.0})

        canvas._marks_by_atom[1] = [valid_mark]
        canvas.ring_items = [valid_ring, invalid_ring]
        for item in (valid_atom, invalid_atom, valid_bond, invalid_bond, valid_mark, invalid_mark, scene_note):
            canvas.add_item(item, selected=True)
        canvas.add_item(valid_ring, selected=False)

        controller = SceneOpsController(canvas)
        payload = controller._selection_payload_for_clipboard()

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(
            payload["atoms"],
            [
                {"id": 1, "element": "C", "x": 0.0, "y": 0.0, "color": "#000000", "explicit_label": False},
                {"id": 2, "element": "O", "x": 20.0, "y": 0.0, "color": "#000000", "explicit_label": False},
            ],
        )
        self.assertEqual(payload["bonds"], [{"a": 1, "b": 2, "order": 1, "style": "single", "color": "#555555"}])
        self.assertEqual(payload["rings"], [{"kind": "ring", "atom_ids": [1, 2], "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]}])
        self.assertEqual(payload["marks"], [{"kind": "mark", "atom_id": 1, "x": 6.0, "y": 7.0}])
        self.assertEqual(payload["scene_items"], [{"kind": "note", "text": "still here", "x": 10.0, "y": 11.0}])

    def test_clipboard_selection_payload_prefers_custom_mime_over_cached_fallback(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        clipboard = QApplication.clipboard()
        payload_json = json.dumps({"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]}, separators=(",", ":"))
        stale_payload_json = json.dumps({"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "arrow"}]}, separators=(",", ":"))
        canvas._clipboard_selection_payload_json = stale_payload_json

        clipboard.setMimeData(canvas.new_mime_data(payload_json.encode("utf-8")))

        payload, returned_json = controller._clipboard_selection_payload()

        self.assertEqual(payload, {"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]})
        self.assertEqual(returned_json, payload_json)

    def test_clipboard_selection_payload_falls_back_to_cached_json_for_image_only_clipboard(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        clipboard = QApplication.clipboard()
        payload_json = json.dumps({"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]}, separators=(",", ":"))
        canvas._clipboard_selection_payload_json = payload_json

        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        clipboard.setMimeData(canvas.new_image_mime_data(image))

        payload, returned_json = controller._clipboard_selection_payload()

        self.assertEqual(payload, {"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]})
        self.assertEqual(returned_json, payload_json)

    def test_clipboard_selection_payload_rejects_wrong_type_or_version_before_fallback(self) -> None:
        canvas = _FakeCanvas()
        controller = SceneOpsController(canvas)
        clipboard = QApplication.clipboard()
        payload_json = json.dumps({"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]}, separators=(",", ":"))
        canvas._clipboard_selection_payload_json = payload_json

        clipboard.setMimeData(canvas.new_mime_data(b'{"format":"not-lightdraw-selection","version":1}'))
        payload, returned_json = controller._clipboard_selection_payload()
        self.assertIsNone(payload)
        self.assertIsNone(returned_json)

        invalid_version_mime = canvas.new_mime_data(b'{"format":"lightdraw-selection","version":999}')
        invalid_version_mime.setImageData(QImage(4, 4, QImage.Format.Format_ARGB32))
        clipboard.setMimeData(invalid_version_mime)
        payload, returned_json = controller._clipboard_selection_payload()
        self.assertEqual(payload, {"format": "lightdraw-selection", "version": 1, "scene_items": [{"kind": "note"}]})
        self.assertEqual(returned_json, payload_json)


class _FakeCanvas:
    CLIPBOARD_SELECTION_MIME = "application/x-lightdraw-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.model = MoleculeModel()
        self.ring_items: list[QGraphicsItem] = []
        self._marks_by_atom: dict[int, list[QGraphicsItem]] = {}
        self._clipboard_selection_payload_json = None
        self._clipboard_paste_source_json = None
        self._clipboard_paste_count = 0

    def scene(self) -> QGraphicsScene:
        return self._scene

    def add_item(self, item: QGraphicsItem, *, selected: bool = False) -> None:
        self._scene.addItem(item)
        if selected:
            item.setSelected(True)

    def _selected_items_for_transform(self):
        return list(self._scene.selectedItems())

    def _selected_ids(self) -> tuple[set[int], set[int]]:
        atom_ids: set[int] = set()
        bond_ids: set[int] = set()
        for item in self._scene.selectedItems():
            kind = item.data(0)
            data = item.data(1)
            if kind == "atom" and isinstance(data, int):
                atom_ids.add(data)
            elif kind == "bond" and isinstance(data, int):
                bond_ids.add(data)
        return atom_ids, bond_ids

    def _atom_state_dict(self, atom_id: int) -> dict:
        atom = self.model.atoms[atom_id]
        return {
            "element": atom.element,
            "x": atom.x,
            "y": atom.y,
            "color": atom.color,
            "explicit_label": atom.explicit_label,
        }

    @staticmethod
    def _bond_state_dict(bond: Bond) -> dict:
        return {
            "a": bond.a,
            "b": bond.b,
            "order": bond.order,
            "style": bond.style,
            "color": bond.color,
        }

    def scene_item_state(self, item: QGraphicsItem) -> dict:
        state = item.data(9)
        return dict(state) if isinstance(state, dict) else {}

    def new_mime_data(self, payload: bytes):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setData(self.CLIPBOARD_SELECTION_MIME, payload)
        return mime_data

    @staticmethod
    def new_image_mime_data(image: QImage):
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setImageData(image)
        return mime_data


if __name__ == "__main__":
    unittest.main()
