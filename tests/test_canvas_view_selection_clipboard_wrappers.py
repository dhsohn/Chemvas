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
    from ui.canvas_atom_graphics_state import set_atom_dots_for, set_atom_items_for
    from ui.canvas_bond_graphics_state import set_bond_items_for
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_scene_items_state import set_scene_item_collection_for
    from ui.mark_item_access import mark_kinds_by_atom_for
    from ui.scene_clipboard_transaction_logic import _copy_bounds_for_items
    from ui.selection_collection_access import (
        append_ring_selection_atom_ids,
        append_selected_item_ids,
        append_unique_scene_item,
        selected_atom_ids_for_transform_for,
        selected_items_for_transform_for,
        selected_mark_atom_ids_for,
        selected_scene_items_for,
        selection_items_for_copy_for,
    )
    from ui.selection_geometry_access import extend_bounds_with_item_rect
    from ui.selection_scene_access import selected_scene_notes_for


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
        )
        set_scene_item_collection_for(view, "selected_notes", [included_note, other_scene_note])

        selected_items = selected_items_for_transform_for(view)

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
        )
        set_scene_item_collection_for(view, "selected_notes", [selected_note, other_scene_note])

        self.assertEqual(selected_scene_notes_for(view), [selected_note])
        self.assertEqual(
            selected_scene_items_for(view, excluded_kinds={"selection_outline"}),
            [selected_atom, selected_note],
        )

    def test_append_unique_scene_item_skips_duplicates_and_excluded_kinds(self) -> None:
        atom = _FakeItem("atom")
        handle = _FakeItem("handle")
        items = []
        seen = set()

        self.assertTrue(append_unique_scene_item(items, seen, atom, excluded_kinds={"handle"}))
        self.assertFalse(append_unique_scene_item(items, seen, atom, excluded_kinds={"handle"}))
        self.assertFalse(append_unique_scene_item(items, seen, handle, excluded_kinds={"handle"}))
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

        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("atom", data1=1))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("bond", data1=7))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", data2=[2, "bad", 99]))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", polygon=polygon))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("other"))

        self.assertEqual(atom_ids, {1, 2, 3})
        self.assertEqual(bond_ids, {7})
        self.assertEqual(selected_mark_atom_ids_for(view), {2})

    def test_selection_items_for_copy_covers_empty_child_and_skip_paths(self) -> None:
        with mock.patch("ui.selection_collection_access.selected_scene_items_for", return_value=[]):
            self.assertEqual(selection_items_for_copy_for(SimpleNamespace(bond_items={})), [])

        child = _FakeItem("note")
        invalid_bond = _FakeItem("bond", data1="bad")
        invalid_bond._children = [child]
        with mock.patch("ui.selection_collection_access.selected_scene_items_for", return_value=[invalid_bond]):
            copied = selection_items_for_copy_for(SimpleNamespace(bond_items={}))
        self.assertEqual(copied, [invalid_bond, child])

        root = _FakeItem("note", children=[_FakeItem("note")])
        with (
            mock.patch("ui.selection_collection_access.selected_scene_items_for", return_value=[root]),
            mock.patch("ui.selection_collection_access.append_unique_scene_item", return_value=False) as append_unique,
        ):
            self.assertEqual(
                selection_items_for_copy_for(SimpleNamespace(bond_items={})),
                [],
            )
        append_unique.assert_called_once()

    def test_selection_copy_helpers_delegate_paths(self) -> None:
        child = _FakeItem("note")
        with mock.patch("ui.selection_collection_access.selected_scene_items_for", return_value=[child]):
            self.assertEqual(selection_items_for_copy_for(SimpleNamespace(bond_items={})), [child])

        controller = SimpleNamespace(
            clipboard_controller=SimpleNamespace(
                selection_payload_for_clipboard=mock.Mock(return_value={"atoms": [1]}),
                clipboard_selection_payload=mock.Mock(return_value=({"atoms": [2]}, "payload-json")),
                select_pasted_content=mock.Mock(),
            ),
        )

        self.assertEqual(controller.clipboard_controller.selection_payload_for_clipboard(), {"atoms": [1]})
        self.assertEqual(controller.clipboard_controller.clipboard_selection_payload(), ({"atoms": [2]}, "payload-json"))
        controller.clipboard_controller.select_pasted_content({4}, [child])
        controller.clipboard_controller.select_pasted_content.assert_called_once_with({4}, [child])

        bounds_item = SimpleNamespace(sceneBoundingRect=lambda: QRectF(1.0, 2.0, 3.0, 4.0))
        rect = _copy_bounds_for_items([bounds_item])
        self.assertEqual(rect, QRectF(1.0, 2.0, 3.0, 4.0))

    def test_selection_items_for_copy_includes_selected_bond_endpoint_atom_graphics(self) -> None:
        selected_bond = _FakeItem("bond", data1=0)
        bond_graphic = _FakeItem("bond", data1=0)
        atom_label = _FakeItem("atom", data1=1)
        atom_dot = _FakeItem("atom", data1=2)
        view = SimpleNamespace(model=SimpleNamespace(bonds=[Bond(1, 2, 1)]))
        set_bond_items_for(view, {0: [bond_graphic]})
        set_atom_items_for(view, {1: atom_label})
        set_atom_dots_for(view, {2: atom_dot})

        with mock.patch("ui.selection_collection_access.selected_scene_items_for", return_value=[selected_bond]):
            copied = selection_items_for_copy_for(view)

        self.assertEqual(copied, [bond_graphic, atom_label, atom_dot])

    def test_helper_tails_cover_invalid_metadata_bounds_and_mark_kind_filters(self) -> None:
        view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0)}),
            mark_registry=CanvasMarkRegistry({
                1: [
                    _FakeItem("mark", data1="bad"),
                    _FakeItem("mark", data1={"kind": 7}),
                ],
                2: [
                    _FakeItem("mark", data1={"kind": "plus"}),
                ],
            }),
        )
        self.assertEqual(mark_kinds_by_atom_for(view), {2: ["plus"]})

        xs: list[float] = []
        ys: list[float] = []
        extend_bounds_with_item_rect(xs, ys, None)
        extend_bounds_with_item_rect(
            xs,
            ys,
            SimpleNamespace(sceneBoundingRect=lambda: QRectF(-1.0, 2.0, 3.0, 4.0)),
        )
        self.assertEqual(xs, [-1.0, 2.0])
        self.assertEqual(ys, [2.0, 6.0])

        atom_ids = set()
        bond_ids = set()
        append_ring_selection_atom_ids(view, atom_ids, "bad")
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("atom", data1="bad"))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("bond", data1="bad"))
        append_selected_item_ids(view, atom_ids, bond_ids, _FakeItem("ring", data2="bad", polygon=QPolygonF()))
        self.assertEqual(atom_ids, set())
        self.assertEqual(bond_ids, set())

    def test_selected_atom_ids_for_transform_includes_bond_endpoints_and_skips_invalid_bonds(self) -> None:
        scene = SimpleNamespace(
            selectedItems=lambda: [
                _FakeItem("atom", data1=7),
                _FakeItem("bond", data1=0),
                _FakeItem("bond", data1=1),
                _FakeItem("bond", data1=2),
                _FakeItem("bond", data1=9),
            ]
        )
        view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(
                bonds=[
                    Bond(1, 2, 1),
                    None,
                    Bond(3, 4, 2),
                ]
            ),
        )

        atom_ids = selected_atom_ids_for_transform_for(view)

        self.assertEqual(atom_ids, {1, 2, 3, 4, 7})

    def test_flip_actions_use_scene_transform_controller(self) -> None:
        controller = SimpleNamespace(flip_selected_items=mock.Mock())
        view = SimpleNamespace(services=SimpleNamespace(scene_transform_controller=controller))

        view.services.scene_transform_controller.flip_selected_items(horizontal=True)
        view.services.scene_transform_controller.flip_selected_items(horizontal=False)

        controller.flip_selected_items.assert_has_calls([mock.call(horizontal=True), mock.call(horizontal=False)])
        self.assertEqual(controller.flip_selected_items.call_count, 2)

    def test_clipboard_and_delete_actions_use_split_controllers(self) -> None:
        clipboard_controller = SimpleNamespace(
            copy_selection_to_clipboard=mock.Mock(return_value=True),
            paste_selection_from_clipboard=mock.Mock(return_value=False),
        )
        delete_controller = SimpleNamespace(
            delete_selected_items=mock.Mock(return_value=True),
        )
        view = SimpleNamespace(
            services=SimpleNamespace(
                scene_clipboard_controller=clipboard_controller,
                scene_delete_controller=delete_controller,
            )
        )

        self.assertTrue(view.services.scene_clipboard_controller.copy_selection_to_clipboard())
        self.assertFalse(view.services.scene_clipboard_controller.paste_selection_from_clipboard())
        self.assertTrue(view.services.scene_delete_controller.delete_selected_items())

        clipboard_controller.copy_selection_to_clipboard.assert_called_once_with()
        clipboard_controller.paste_selection_from_clipboard.assert_called_once_with()
        delete_controller.delete_selected_items.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
