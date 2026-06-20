import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

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

if QApplication is not None:
    from core.model import Atom, Bond, MoleculeModel
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_scene_items_state import set_scene_item_collection_for
    from ui.scene_clipboard_controller import SceneClipboardController
    from ui.scene_clipboard_logic import (
        build_selection_clipboard_payload,
        clipboard_payload_candidates,
        decode_clipboard_selection_payload,
    )
    from ui.scene_clipboard_state import SceneClipboardState


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
        if kind == "mark":
            mark_data = {key: state.get(key) for key in ("atom_id", "dx", "dy", "text") if key in state}
            if "mark_kind" in state:
                mark_data["kind"] = state.get("mark_kind")
            item.setData(1, mark_data)
            item.setPos(float(state.get("x", 0.0)), float(state.get("y", 0.0)))
    return item


def _make_text_item(kind: str, text: str, state: dict) -> QGraphicsTextItem:
    item = _set_selectable(QGraphicsTextItem(text))
    item.setData(0, kind)
    item.setData(9, dict(state))
    if kind == "note" and "text" in state:
        item.setPlainText(str(state["text"]))
    if kind == "mark":
        mark_data = {key: state.get(key) for key in ("atom_id", "dx", "dy", "text") if key in state}
        if "mark_kind" in state:
            mark_data["kind"] = state.get("mark_kind")
        item.setData(1, mark_data)
    if kind in {"mark", "note"}:
        item.setPos(float(state.get("x", 0.0)), float(state.get("y", 0.0)))
    return item


def _make_ring_item(atom_ids: list[int], *, state: dict | None = None) -> QGraphicsPolygonItem:
    polygon = QPolygonF([QPointF(0.0, 0.0), QPointF(12.0, 0.0), QPointF(6.0, 10.0)])
    item = _set_selectable(QGraphicsPolygonItem(polygon))
    item.setData(0, "ring")
    item.setData(2, list(atom_ids))
    item.setData(9, state or {"kind": "ring", "atom_ids": list(atom_ids), "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)]})
    return item


def scene_clipboard_controller_for(canvas) -> SceneClipboardController:
    return SceneClipboardController(canvas)


def _valid_note_clipboard_payload() -> dict:
    return {
        "format": "chemvas-selection",
        "version": 1,
        "atoms": [],
        "bonds": [],
        "rings": [],
        "marks": [],
        "scene_items": [{"kind": "note", "text": "note", "x": 1.0, "y": 2.0}],
    }


class _BrokenSceneItem:
    def __init__(
        self,
        kind: str,
        *,
        state: dict | None = None,
        data1=None,
        data2=None,
        scene_value=None,
        raise_scene: bool = False,
    ) -> None:
        self._kind = kind
        self._state = dict(state) if isinstance(state, dict) else state
        self._data1 = data1
        self._data2 = data2
        self._scene_value = scene_value
        self._raise_scene = raise_scene

    def data(self, role: int):
        if role == 0:
            return self._kind
        if role == 1:
            return self._data1
        if role == 2:
            return self._data2
        if role == 9:
            return self._state
        return None

    def scene(self):
        if self._raise_scene:
            raise RuntimeError("dangling")
        return self._scene_value


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene clipboard logic tests")
class SceneClipboardLogicTest(unittest.TestCase):
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

    def test_build_selection_clipboard_payload_skips_invalid_bonds_atoms_rings_and_marks(self) -> None:
        scene = object()
        valid_mark = _BrokenSceneItem(
            "mark",
            state={"kind": "mark", "atom_id": 2, "x": 1.0, "y": 2.0},
            scene_value=scene,
        )
        duplicate_selected_mark = valid_mark
        runtime_mark = _BrokenSceneItem(
            "mark",
            state={"kind": "mark", "atom_id": 2, "x": 9.0, "y": 9.0},
            raise_scene=True,
        )
        off_scene_mark = _BrokenSceneItem(
            "mark",
            state={"kind": "mark", "atom_id": 2, "x": 5.0, "y": 6.0},
            scene_value=object(),
        )
        empty_linked_mark = _BrokenSceneItem("mark", state={}, scene_value=scene)
        empty_mark = _BrokenSceneItem("mark", state={}, scene_value=scene)
        scene_note = _BrokenSceneItem("note", state={"kind": "note", "text": "keep", "x": 4.0, "y": 5.0})
        empty_scene_item = _BrokenSceneItem("arrow", state={})
        wrong_scene_ring = _BrokenSceneItem("ring", state={"kind": "ring"}, scene_value=object())
        broken_ring = _BrokenSceneItem("ring", state={"kind": "ring"}, raise_scene=True)
        invalid_ids_ring = _BrokenSceneItem("ring", state={"kind": "ring"}, data2=[1, "bad"], scene_value=scene)
        empty_state_ring = _BrokenSceneItem("ring", state={}, data2=[1, 2], scene_value=scene)

        payload = build_selection_clipboard_payload(
            selected_items=[duplicate_selected_mark, empty_mark, scene_note, empty_scene_item],
            explicit_atom_ids={1, 3},
            selected_bond_ids={0, 1, 99},
            bonds=[Bond(1, 2, 1, style="single", color="#111111"), None],
            ring_items=[wrong_scene_ring, broken_ring, invalid_ids_ring, empty_state_ring],
            marks_by_atom={2: [valid_mark, valid_mark, off_scene_mark, runtime_mark, empty_linked_mark]},
            scene=scene,
            atom_state_getter=lambda atom_id: (
                {}
                if atom_id == 3
                else {"element": "C", "x": float(atom_id), "y": 0.0, "color": "#000000", "explicit_label": False}
            ),
            bond_state_getter=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            scene_item_state_getter=lambda item: dict(item.data(9) or {}),
            version=7,
        )

        self.assertEqual(
            payload,
            {
                "format": "chemvas-selection",
                "version": 7,
                "atoms": [
                    {"id": 1, "element": "C", "x": 1.0, "y": 0.0, "color": "#000000", "explicit_label": False},
                    {"id": 2, "element": "C", "x": 2.0, "y": 0.0, "color": "#000000", "explicit_label": False},
                ],
                "bonds": [{"a": 1, "b": 2, "order": 1, "style": "single", "color": "#111111"}],
                "rings": [],
                "marks": [{"kind": "mark", "atom_id": 2, "x": 1.0, "y": 2.0}],
                "scene_items": [{"kind": "note", "text": "keep", "x": 4.0, "y": 5.0}],
            },
        )

    def test_clipboard_payload_candidates_handles_invalid_utf8(self) -> None:
        from PyQt6.QtCore import QMimeData

        mime_data = QMimeData()
        mime_data.setData(_FakeCanvas.CLIPBOARD_SELECTION_MIME, b"\xff")
        mime_data.setImageData(QImage(4, 4, QImage.Format.Format_ARGB32))

        candidates = clipboard_payload_candidates(
            mime_data,
            mime_type=_FakeCanvas.CLIPBOARD_SELECTION_MIME,
        )

        self.assertEqual(candidates, [])

    def test_decode_clipboard_selection_payload_skips_invalid_candidates_until_valid_dict(self) -> None:
        valid_payload = _valid_note_clipboard_payload()
        valid_payload_json = json.dumps(valid_payload, separators=(",", ":"))
        payload, payload_json = decode_clipboard_selection_payload(
            [
                "not-json",
                "[]",
                '{"format":"wrong","version":1}',
                '{"format":"chemvas-selection","version":999}',
                valid_payload_json,
            ],
            version=1,
        )

        self.assertEqual(payload, valid_payload)
        self.assertEqual(payload_json, valid_payload_json)

    def test_selection_payload_extends_atom_and_bond_selection_and_keeps_related_scene_items(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={
                1: Atom("C", 0.0, 0.0, color="#111111", explicit_label=True),
                2: Atom("O", 20.0, 0.0, color="#222222"),
                3: Atom("N", 40.0, 0.0, color="#333333"),
            },
            bonds=[
                Bond(1, 2, 1, style="single", color="#444444"),
                Bond(2, 3, 2, style="double", color="#555555"),
            ],
        )

        atom_item = _make_rect_item("atom", data1=1)
        bond_item = _make_rect_item("bond", data1=0)
        linked_mark = _make_text_item("mark", "linked", {"kind": "mark", "atom_id": 2, "x": 3.0, "y": 4.0})
        free_mark = _make_rect_item("mark", state={"kind": "mark", "atom_id": None, "x": 50.0, "y": 60.0})
        ring_item = _make_ring_item([1, 2])
        note_item = _make_text_item("note", "note", {"kind": "note", "text": "note", "x": 80.0, "y": 90.0})
        arrow_item = _make_rect_item("arrow", state={"kind": "arrow", "start": (5.0, 6.0), "end": (7.0, 8.0)})

        canvas.mark_registry.by_atom[2] = [linked_mark]
        set_scene_item_collection_for(canvas, "ring_items", [ring_item])
        for item in (atom_item, bond_item, free_mark, note_item, arrow_item):
            canvas.add_item(item, selected=True)
        canvas.add_item(linked_mark, selected=False)
        canvas.add_item(ring_item, selected=False)

        controller = scene_clipboard_controller_for(canvas)
        payload = controller.selection_payload_for_clipboard()

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["format"], "chemvas-selection")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(
            payload["atoms"],
            [
                {"id": 1, "element": "C", "x": 0.0, "y": 0.0, "color": "#111111", "explicit_label": True},
                {"id": 2, "element": "O", "x": 20.0, "y": 0.0, "color": "#222222", "explicit_label": False},
            ],
        )
        self.assertEqual(payload["bonds"], [{"a": 1, "b": 2, "order": 1, "style": "single", "color": "#444444"}])
        self.assertEqual(
            payload["rings"],
            [
                {
                    "kind": "ring",
                    "points": [(0.0, 0.0), (12.0, 0.0), (6.0, 10.0)],
                    "atom_ids": [1, 2],
                    "color": None,
                    "alpha": 0.0,
                }
            ],
        )
        self.assertCountEqual(
            payload["marks"],
            [
                {
                    "kind": "mark",
                    "mark_kind": None,
                    "text": None,
                    "atom_id": 2,
                    "dx": None,
                    "dy": None,
                    "x": 3.0,
                    "y": 4.0,
                },
                {
                    "kind": "mark",
                    "mark_kind": None,
                    "text": None,
                    "atom_id": None,
                    "dx": None,
                    "dy": None,
                    "x": 50.0,
                    "y": 60.0,
                },
            ],
        )
        self.assertCountEqual(
            payload["scene_items"],
            [
                {"kind": "note", "text": "note", "x": 80.0, "y": 90.0},
                {"kind": "arrow", "start": (5.0, 6.0), "end": (7.0, 8.0)},
            ],
        )

    def test_selection_payload_filters_invalid_entries_and_retains_only_valid_scene_state(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0)},
            bonds=[Bond(1, 1, 1)],
        )

        invalid_atom = _make_rect_item("atom", data1="bad")
        invalid_bond = _make_rect_item("bond", data1=9)
        invalid_mark = _make_text_item("unknown", "mark", {})
        invalid_ring = _make_ring_item([1], state={"kind": "ring", "atom_ids": [], "points": []})
        invalid_ring.setData(2, [])
        empty_scene_item = _make_rect_item("arrow", state={})
        valid_note = _make_text_item("note", "keep", {"kind": "note", "text": "keep", "x": 10.0, "y": 11.0})

        for item in (invalid_atom, invalid_bond, invalid_mark, invalid_ring, empty_scene_item, valid_note):
            canvas.add_item(item, selected=True)
        set_scene_item_collection_for(canvas, "ring_items", [invalid_ring])

        controller = scene_clipboard_controller_for(canvas)
        payload = controller.selection_payload_for_clipboard()

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["atoms"], [])
        self.assertEqual(payload["bonds"], [])
        self.assertEqual(payload["rings"], [])
        self.assertEqual(payload["marks"], [])
        self.assertEqual(payload["scene_items"], [{"kind": "note", "text": "keep", "x": 10.0, "y": 11.0}])

    def test_selection_payload_returns_none_when_every_selected_entry_is_invalid_or_empty(self) -> None:
        canvas = _FakeCanvas()
        canvas.model = MoleculeModel(
            atoms={1: Atom("C", 0.0, 0.0)},
            bonds=[Bond(1, 1, 1)],
        )

        invalid_atom = _make_rect_item("atom", data1="bad")
        invalid_bond = _make_rect_item("bond", data1=99)
        invalid_mark = _make_text_item("unknown", "mark", {})
        invalid_ring = _make_ring_item([1], state={"kind": "ring", "atom_ids": [], "points": []})
        invalid_ring.setData(2, [])
        invalid_scene_item = _make_rect_item("arrow", state={})

        for item in (invalid_atom, invalid_bond, invalid_mark, invalid_ring, invalid_scene_item):
            canvas.add_item(item, selected=True)
        set_scene_item_collection_for(canvas, "ring_items", [invalid_ring])

        controller = scene_clipboard_controller_for(canvas)

        self.assertIsNone(controller.selection_payload_for_clipboard())

    def test_clipboard_selection_payload_uses_custom_mime_and_rejects_wrong_format_or_version(self) -> None:
        canvas = _FakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        clipboard = QApplication.clipboard()

        valid_payload = _valid_note_clipboard_payload()
        custom_json = json.dumps(valid_payload, separators=(",", ":"))

        clipboard.setMimeData(canvas.new_mime_data(custom_json.encode("utf-8")))
        payload, returned_json = controller.clipboard_selection_payload()
        self.assertEqual(payload, valid_payload)
        self.assertEqual(returned_json, custom_json)

        image = QImage(4, 4, QImage.Format.Format_ARGB32)
        clipboard.setMimeData(canvas.new_image_mime_data(image))
        self.assertEqual(controller.clipboard_selection_payload(), (None, None))

        clipboard.setMimeData(canvas.new_mime_data(b'{"format":"not-chemvas-selection","version":1}'))
        self.assertEqual(controller.clipboard_selection_payload(), (None, None))

        invalid_version_mime = canvas.new_mime_data(b'{"format":"chemvas-selection","version":999}')
        invalid_version_mime.setImageData(QImage(4, 4, QImage.Format.Format_ARGB32))
        clipboard.setMimeData(invalid_version_mime)
        self.assertEqual(controller.clipboard_selection_payload(), (None, None))


class _FakeCanvas:
    CLIPBOARD_SELECTION_MIME = "application/x-chemvas-selection+json"
    CLIPBOARD_SELECTION_VERSION = 1

    def __init__(self) -> None:
        self._scene = QGraphicsScene()
        self.model = MoleculeModel()
        self.ring_items: list[QGraphicsItem] = []
        self.mark_registry = CanvasMarkRegistry()
        self.scene_clipboard_state = SceneClipboardState()
        self.scene_clipboard_state.paste_source_json = None
        self.scene_clipboard_state.paste_count = 0
        self.history_service = SimpleNamespace(push=mock.Mock())
        self.services = SimpleNamespace(history_service=self.history_service)

    def scene(self) -> QGraphicsScene:
        return self._scene

    def add_item(self, item: QGraphicsItem, *, selected: bool = False) -> None:
        self._scene.addItem(item)
        if selected:
            item.setSelected(True)

    def _selected_items_for_transform(self):
        return list(self._scene.selectedItems())

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
