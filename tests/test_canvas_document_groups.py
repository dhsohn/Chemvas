import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.model import Atom, MoleculeModel
    from ui.canvas_document_state import _snapshot_groups as snapshot_groups
    from ui.canvas_document_state import restore_document_groups
    from ui.canvas_group_state import group_state_for, register_group_for
    from ui.canvas_scene_items_state import CanvasSceneItemsState


class _SceneItem:
    def __init__(self, scene_obj, state: dict | None = None) -> None:
        self._scene = scene_obj
        self._state = dict(state or {})

    def scene(self):
        return self._scene

    def data(self, key: int):
        if key == 9:
            return dict(self._state)
        return None


def _canvas_with_items(scene_obj):
    note_item = _SceneItem(scene_obj, {"text": "note", "x": 1.0, "y": 2.0})
    arrow_item = _SceneItem(scene_obj, {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)})
    canvas = SimpleNamespace(
        model=MoleculeModel(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 5.0, 0.0)}),
        scene_items_state=CanvasSceneItemsState(
            note_items=[note_item],
            arrow_items=[arrow_item],
        ),
        scene=lambda: scene_obj,
    )
    return canvas, note_item, arrow_item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for document group tests")
class CanvasDocumentGroupsTest(unittest.TestCase):
    def test_snapshot_groups_maps_members_to_stable_references(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item = _canvas_with_items(scene_obj)
        register_group_for(canvas, {1, 2}, [arrow_item, note_item])

        groups = snapshot_groups(canvas)

        self.assertEqual(
            groups,
            [{"atoms": [1, 2], "items": [["arrows", 0], ["notes", 0]]}],
        )

    def test_snapshot_groups_drops_dead_members_and_empty_groups(self) -> None:
        scene_obj = object()
        canvas, _, arrow_item = _canvas_with_items(scene_obj)
        detached_arrow = _SceneItem(object(), {"kind": "arrow"})
        register_group_for(canvas, {1, 99}, [arrow_item, detached_arrow])
        register_group_for(canvas, {98}, [detached_arrow])

        groups = snapshot_groups(canvas)

        self.assertEqual(groups, [{"atoms": [1], "items": [["arrows", 0]]}])

    def test_snapshot_groups_skips_empty_arrow_states_when_indexing(self) -> None:
        scene_obj = object()
        canvas, _, arrow_item = _canvas_with_items(scene_obj)
        empty_arrow = _SceneItem(scene_obj, {})
        canvas.scene_items_state.arrow_items = [empty_arrow, arrow_item]
        register_group_for(canvas, {1}, [arrow_item])

        groups = snapshot_groups(canvas)

        self.assertEqual(groups, [{"atoms": [1], "items": [["arrows", 0]]}])

    def test_restore_document_groups_rebuilds_registry(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item = _canvas_with_items(scene_obj)
        state = {"groups": [{"atoms": [2], "items": [["arrows", 0], ["notes", 0]]}]}

        restore_document_groups(canvas, state)

        groups = group_state_for(canvas).groups
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group.atom_ids, {2})
        self.assertEqual({id(item) for item in group.items}, {id(arrow_item), id(note_item)})

    def test_restore_document_groups_clears_previous_registry(self) -> None:
        scene_obj = object()
        canvas, _, _ = _canvas_with_items(scene_obj)
        register_group_for(canvas, {1}, [])

        restore_document_groups(canvas, {})

        self.assertEqual(group_state_for(canvas).groups, {})

    def test_snapshot_and_restore_round_trip(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item = _canvas_with_items(scene_obj)
        register_group_for(canvas, {1}, [note_item])
        register_group_for(canvas, {2}, [arrow_item])

        groups_state = snapshot_groups(canvas)
        restored_scene = object()
        restored_canvas, restored_note, restored_arrow = _canvas_with_items(restored_scene)
        restore_document_groups(restored_canvas, {"groups": groups_state})

        groups = group_state_for(restored_canvas).groups
        self.assertEqual(len(groups), 2)
        members = sorted(
            (sorted(group.atom_ids), [id(item) for item in group.items])
            for group in groups.values()
        )
        self.assertEqual(
            members,
            sorted([([1], [id(restored_note)]), ([2], [id(restored_arrow)])]),
        )


if __name__ == "__main__":
    unittest.main()
