import os
import unittest
from types import SimpleNamespace

from chemvas.ui.canvas_scene_items_state import require_scene_record_id
from tests.mark_support import seed_mark_items
from tests.note_support import seed_note_items
from tests.runtime_state import canvas_runtime_state

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


from chemvas.domain.document import (
    AnnotationCollection,
    Atom,
    MoleculeModel,
    arrow_from_state,
)
from chemvas.ui.canvas_document_state import _snapshot_groups as snapshot_groups
from chemvas.ui.canvas_document_state import restore_document_groups
from chemvas.ui.canvas_group_state import (
    CanvasGroupState,
    group_state_for,
    register_group_for,
)
from chemvas.ui.canvas_scene_items_state import CanvasSceneItemsState


class _SceneItem:
    def __init__(self, scene_obj, state: dict | None = None) -> None:
        self._data = {}
        self._scene = scene_obj
        self._state = dict(state or {})

    def setData(self, role, value):
        self._data[role] = value

    def scene(self):
        return self._scene

    def data(self, key: int):
        if key == 9:
            return dict(self._state)
        return self._data.get(key)


def _canvas_with_items(scene_obj):
    note_item = _SceneItem(scene_obj, {"text": "note", "x": 1.0, "y": 2.0})
    arrow_item = _SceneItem(
        scene_obj, {"kind": "arrow", "start": (0.0, 0.0), "end": (1.0, 1.0)}
    )
    arrow_item.setData(3, 10)
    mark_item = _SceneItem(
        scene_obj, {"kind": "mark", "mark_kind": "plus", "atom_id": None}
    )
    canvas = SimpleNamespace(
        model=MoleculeModel(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 5.0, 0.0)}),
        runtime_state=canvas_runtime_state(
            group_state=CanvasGroupState(),
            arrow_state=AnnotationCollection(
                records={10: arrow_from_state(arrow_item.data(9))}, order=[10]
            ),
            scene_items_state=CanvasSceneItemsState(
                arrow_items={10: arrow_item},
            ),
        ),
        scene=lambda: scene_obj,
    )
    seed_note_items(canvas, [note_item])
    seed_mark_items(canvas, [mark_item])
    return canvas, note_item, arrow_item, mark_item


class CanvasDocumentGroupsTest(unittest.TestCase):
    def test_snapshot_groups_maps_members_to_stable_references(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item, _ = _canvas_with_items(scene_obj)
        register_group_for(
            canvas,
            {1, 2},
            [require_scene_record_id(item) for item in [arrow_item, note_item]],
        )

        groups = snapshot_groups(canvas)

        self.assertEqual(
            groups,
            [{"atoms": [1, 2], "items": [["arrows", 0], ["notes", 0]]}],
        )

    def test_snapshot_groups_drops_dead_members_and_empty_groups(self) -> None:
        scene_obj = object()
        canvas, _, arrow_item, _ = _canvas_with_items(scene_obj)
        detached_arrow = _SceneItem(object(), {"kind": "arrow"})
        detached_arrow.setData(3, 99999)
        register_group_for(
            canvas,
            {1, 99},
            [require_scene_record_id(item) for item in [arrow_item, detached_arrow]],
        )
        register_group_for(
            canvas, {98}, [require_scene_record_id(item) for item in [detached_arrow]]
        )

        groups = snapshot_groups(canvas)

        self.assertEqual(groups, [{"atoms": [1], "items": [["arrows", 0]]}])

    def test_snapshot_groups_ignores_projections_outside_document_membership(
        self,
    ) -> None:
        scene_obj = object()
        canvas, _, arrow_item, _ = _canvas_with_items(scene_obj)
        empty_arrow = _SceneItem(scene_obj, {})
        canvas.runtime_state.scene_items_state.arrow_items = {
            11: empty_arrow,
            10: arrow_item,
        }
        register_group_for(
            canvas, {1}, [require_scene_record_id(item) for item in [arrow_item]]
        )

        groups = snapshot_groups(canvas)

        self.assertEqual(groups, [{"atoms": [1], "items": [["arrows", 0]]}])

    def test_restore_document_groups_rebuilds_registry(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item, _ = _canvas_with_items(scene_obj)
        state = {"groups": [{"atoms": [2], "items": [["arrows", 0], ["notes", 0]]}]}

        restore_document_groups(canvas, state)

        groups = group_state_for(canvas).groups
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group.atom_ids, {2})
        self.assertEqual(
            set(group.item_ids),
            {require_scene_record_id(arrow_item), require_scene_record_id(note_item)},
        )

    def test_snapshot_and_restore_group_with_standalone_mark(self) -> None:
        scene_obj = object()
        canvas, _, _, mark_item = _canvas_with_items(scene_obj)
        register_group_for(
            canvas, {1}, [require_scene_record_id(item) for item in [mark_item]]
        )

        groups_state = snapshot_groups(canvas)
        self.assertEqual(groups_state, [{"atoms": [1], "items": [["marks", 0]]}])

        restored_scene = object()
        restored_canvas, _, _, restored_mark = _canvas_with_items(restored_scene)
        restore_document_groups(restored_canvas, {"groups": groups_state})

        group = next(iter(group_state_for(restored_canvas).groups.values()))
        self.assertEqual(group.atom_ids, {1})
        self.assertEqual(set(group.item_ids), {require_scene_record_id(restored_mark)})

    def test_restore_document_groups_clears_previous_registry(self) -> None:
        scene_obj = object()
        canvas, _, _, _ = _canvas_with_items(scene_obj)
        register_group_for(canvas, {1}, [require_scene_record_id(item) for item in []])

        restore_document_groups(canvas, {})

        self.assertEqual(group_state_for(canvas).groups, {})

    def test_snapshot_and_restore_round_trip(self) -> None:
        scene_obj = object()
        canvas, note_item, arrow_item, _ = _canvas_with_items(scene_obj)
        register_group_for(
            canvas, {1}, [require_scene_record_id(item) for item in [note_item]]
        )
        register_group_for(
            canvas, {2}, [require_scene_record_id(item) for item in [arrow_item]]
        )

        groups_state = snapshot_groups(canvas)
        restored_scene = object()
        restored_canvas, restored_note, restored_arrow, _ = _canvas_with_items(
            restored_scene
        )
        restore_document_groups(restored_canvas, {"groups": groups_state})

        groups = group_state_for(restored_canvas).groups
        self.assertEqual(len(groups), 2)
        members = sorted(
            (sorted(group.atom_ids), list(group.item_ids)) for group in groups.values()
        )
        self.assertEqual(
            members,
            sorted(
                [
                    ([1], [require_scene_record_id(restored_note)]),
                    ([2], [require_scene_record_id(restored_arrow)]),
                ]
            ),
        )
