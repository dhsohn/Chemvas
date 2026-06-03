import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QPolygonF
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, Bond
    from ui.canvas_view import CanvasView


class _FakeItem:
    def __init__(self, kind: str, *, data1=None, data2=None, scene_token=None, polygon=None, children=None) -> None:
        self._kind = kind
        self._data1 = data1
        self._data2 = data2
        self._scene_token = scene_token
        self._polygon = polygon
        self._children = list(children or [])

    def data(self, key):
        if key == 0:
            return self._kind
        if key == 1:
            return self._data1
        if key == 2:
            return self._data2
        return None

    def scene(self):
        return self._scene_token

    def polygon(self):
        return self._polygon

    def childItems(self):
        return list(self._children)


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewSelectionClipboardWrappersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_selected_items_for_transform_filters_excluded_items_and_deduplicates_notes(self) -> None:
        scene = SimpleNamespace()
        kept_atom = _FakeItem("atom", scene_token=scene)
        excluded_handle = _FakeItem("handle", scene_token=scene)
        excluded_note_box = _FakeItem("note_box", scene_token=scene)
        included_note = _FakeItem("note", scene_token=scene)
        other_scene_note = _FakeItem("note", scene_token=object())

        scene.selectedItems = lambda: [kept_atom, excluded_handle, excluded_note_box, included_note]
        view = SimpleNamespace(
            scene=lambda: scene,
            selected_notes=[included_note, other_scene_note],
        )

        selected_items = CanvasView._selected_items_for_transform(view)

        self.assertEqual(selected_items, [kept_atom, included_note])

    def test_selected_scene_notes_and_items_filter_scene_membership_and_excluded_kinds(self) -> None:
        scene = SimpleNamespace()
        selected_atom = _FakeItem("atom", scene_token=scene)
        selected_outline = _FakeItem("selection_outline", scene_token=scene)
        selected_note = _FakeItem("note", scene_token=scene)
        other_scene_note = _FakeItem("note", scene_token=object())

        scene.selectedItems = lambda: [selected_atom, selected_outline, selected_note]
        view = SimpleNamespace(
            scene=lambda: scene,
            selected_notes=[selected_note, other_scene_note],
        )

        self.assertEqual(CanvasView._selected_scene_notes(view), [selected_note])
        self.assertEqual(
            CanvasView._selected_scene_items(view, excluded_kinds={"selection_outline"}),
            [selected_atom, selected_note],
        )

    def test_append_unique_scene_item_skips_duplicates_and_excluded_kinds(self) -> None:
        atom = _FakeItem("atom")
        handle = _FakeItem("handle")
        items = []
        seen = set()

        self.assertTrue(CanvasView._append_unique_scene_item(items, seen, atom, excluded_kinds={"handle"}))
        self.assertFalse(CanvasView._append_unique_scene_item(items, seen, atom, excluded_kinds={"handle"}))
        self.assertFalse(CanvasView._append_unique_scene_item(items, seen, handle, excluded_kinds={"handle"}))
        self.assertEqual(items, [atom])

    def test_selected_id_helpers_cover_atom_bond_ring_polygon_and_mark_fallback_paths(self) -> None:
        polygon = QPolygonF(
            [
                QPointF(-1.0, -1.0),
                QPointF(2.0, -1.0),
                QPointF(2.0, 2.0),
                QPointF(-1.0, 2.0),
            ]
        )
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 3.0, 0.0),
                    3: Atom("N", 1.0, 1.0),
                }
            ),
            scene=lambda: SimpleNamespace(
                selectedItems=lambda: [
                    _FakeItem("mark", data1={"atom_id": 2}),
                    _FakeItem("mark", data1={"atom_id": "bad"}),
                    _FakeItem("mark", data1={"atom_id": 99}),
                    _FakeItem("arrow"),
                ]
            ),
        )
        atom_ids = set()
        bond_ids = set()

        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("atom", data1=1))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("bond", data1=7))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", data2=[2, "bad", 99]))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", polygon=polygon))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("other"))

        self.assertEqual(atom_ids, {1, 2, 3})
        self.assertEqual(bond_ids, {7})
        self.assertEqual(CanvasView._selected_mark_atom_ids(view), {2})

    def test_selection_copy_and_wrapper_helpers_cover_empty_skip_and_delegate_paths(self) -> None:
        with mock.patch.object(CanvasView, "_selected_scene_items", return_value=[]):
            self.assertEqual(CanvasView._selection_items_for_copy(SimpleNamespace(bond_items={})), [])

        child = _FakeItem("note")
        invalid_bond = _FakeItem("bond", data1="bad")
        invalid_bond._children = [child]
        with mock.patch.object(CanvasView, "_selected_scene_items", return_value=[invalid_bond]):
            copied = CanvasView._selection_items_for_copy(SimpleNamespace(bond_items={}))
        self.assertEqual(copied, [invalid_bond, child])

        root = _FakeItem("note", children=[_FakeItem("note")])
        with (
            mock.patch.object(CanvasView, "_selected_scene_items", return_value=[root]),
            mock.patch.object(CanvasView, "_append_unique_scene_item", return_value=False) as append_unique,
        ):
            self.assertEqual(
                CanvasView._selection_items_for_copy(SimpleNamespace(bond_items={})),
                [],
            )
        append_unique.assert_called_once()

        controller = SimpleNamespace(
            _selection_payload_for_clipboard=mock.Mock(return_value={"atoms": [1]}),
            _clipboard_selection_payload=mock.Mock(return_value=({"atoms": [2]}, "payload-json")),
            _select_pasted_content=mock.Mock(),
        )
        view = SimpleNamespace(_scene_ops_controller=controller)

        self.assertEqual(CanvasView._selection_payload_for_clipboard(view), {"atoms": [1]})
        self.assertEqual(CanvasView._clipboard_selection_payload(view), ({"atoms": [2]}, "payload-json"))
        CanvasView._select_pasted_content(view, {4}, [child])
        controller._select_pasted_content.assert_called_once_with({4}, [child])

        with mock.patch(
            "ui.canvas_view.SceneOpsController._copy_bounds_for_items",
            return_value=QRectF(1.0, 2.0, 3.0, 4.0),
            create=True,
        ) as copy_bounds:
            rect = CanvasView._copy_bounds_for_items([child])
        self.assertEqual(rect, QRectF(1.0, 2.0, 3.0, 4.0))
        copy_bounds.assert_called_once_with([child])

    def test_helper_tails_cover_invalid_metadata_bounds_and_mark_kind_filters(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            _marks_by_atom={
                1: [
                    _FakeItem("mark", data1="bad"),
                    _FakeItem("mark", data1={"kind": 7}),
                ],
                2: [
                    _FakeItem("mark", data1={"kind": "plus"}),
                ],
            },
        )
        self.assertEqual(CanvasView._mark_kinds_by_atom(view), {2: ["plus"]})

        xs: list[float] = []
        ys: list[float] = []
        CanvasView._extend_bounds_with_item_rect(xs, ys, None)
        CanvasView._extend_bounds_with_item_rect(
            xs,
            ys,
            SimpleNamespace(sceneBoundingRect=lambda: QRectF(-1.0, 2.0, 3.0, 4.0)),
        )
        self.assertEqual(xs, [-1.0, 2.0])
        self.assertEqual(ys, [2.0, 6.0])

        atom_ids = set()
        bond_ids = set()
        CanvasView._append_ring_selection_atom_ids(view, atom_ids, "bad")
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("atom", data1="bad"))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("bond", data1="bad"))
        CanvasView._append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", data2="bad", polygon=QPolygonF()))
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, set())

    def test_selected_atom_ids_for_transform_includes_bond_endpoints_and_skips_invalid_bonds(self) -> None:
        view = SimpleNamespace(
            _selected_ids=lambda: ({7}, {0, 1, 2, 9}),
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    None,
                    Bond(3, 4, 2),
                ]
            ),
        )

        atom_ids = CanvasView._selected_atom_ids_for_transform(view)

        self.assertEqual(atom_ids, {1, 2, 3, 4, 7})

    def test_flip_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = SimpleNamespace(flip_selected_items=mock.Mock())
        view = SimpleNamespace(_scene_ops_controller=controller)

        CanvasView.flip_horizontal(view)
        CanvasView.flip_vertical(view)

        controller.flip_selected_items.assert_has_calls([mock.call(horizontal=True), mock.call(horizontal=False)])
        self.assertEqual(controller.flip_selected_items.call_count, 2)

    def test_clipboard_and_delete_wrappers_delegate_to_scene_ops_controller(self) -> None:
        controller = SimpleNamespace(
            copy_selection_to_clipboard=mock.Mock(return_value=True),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
            delete_selected_items=mock.Mock(return_value=True),
        )
        view = SimpleNamespace(_scene_ops_controller=controller)

        self.assertTrue(CanvasView.copy_selection_to_clipboard(view))
        self.assertFalse(CanvasView.paste_selection_from_clipboard(view))
        self.assertTrue(CanvasView.delete_selected_items(view))

        controller.copy_selection_to_clipboard.assert_called_once_with()
        controller.paste_selection_from_clipboard.assert_called_once_with()
        controller.delete_selected_items.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
