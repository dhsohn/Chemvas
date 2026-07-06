import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from ui.canvas_atom_graphics_state import set_atom_item_for
    from ui.canvas_bond_graphics_state import bond_items_for
    from ui.canvas_group_state import group_state_for, register_group_for
    from ui.canvas_model_access import model_for
    from ui.canvas_scene_items_state import add_selected_note_for, append_scene_item_for
    from ui.history_commands import GroupSceneItemsCommand, UngroupSceneItemsCommand
    from ui.scene_group_operations import (
        expand_note_selection_to_groups_for,
        expand_selection_to_groups_for,
        group_selection_for,
        group_selection_targets_for,
        selected_group_rects_for,
        ungroup_selection_for,
    )


class _History:
    def __init__(self) -> None:
        self.commands = []

    def push(self, command) -> None:
        self.commands.append(command)


if QApplication is not None:

    class _Canvas(QGraphicsView):
        def __init__(self) -> None:
            super().__init__(QGraphicsScene())
            self.history = _History()
            self.runtime_state = SimpleNamespace(history_service=self.history)
            self.selection_controller = SimpleNamespace(
                select_note=mock.Mock(),
                toggle_note_selection=mock.Mock(),
                update_selection_outline=mock.Mock(),
            )
            self.services = SimpleNamespace(selection_controller=self.selection_controller)

        def add_scene_item(self, kind: str, *, selected: bool = False):
            item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
            item.setData(0, kind)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self.scene().addItem(item)
            if selected:
                item.setSelected(True)
            return item


def _add_atom(canvas, x: float = 0.0, y: float = 0.0, *, selected: bool = False):
    atom_id = model_for(canvas).add_atom("C", x, y)
    item = canvas.add_scene_item("atom", selected=selected)
    item.setData(1, atom_id)
    set_atom_item_for(canvas, atom_id, item)
    return atom_id, item


def _add_bond(canvas, a: int, b: int, *, selected: bool = False):
    bond_id = model_for(canvas).add_bond(a, b)
    item = canvas.add_scene_item("bond", selected=selected)
    item.setData(1, bond_id)
    bond_items_for(canvas)[bond_id] = [item]
    return bond_id, item


def _add_arrow(canvas, *, selected: bool = False):
    item = canvas.add_scene_item("arrow", selected=selected)
    append_scene_item_for(canvas, "arrow_items", item)
    return item


def _add_mark(canvas, *, atom_id=None, selected: bool = False):
    item = canvas.add_scene_item("mark", selected=selected)
    item.setData(1, {"kind": "plus", "atom_id": atom_id})
    append_scene_item_for(canvas, "mark_items", item)
    return item


def _add_ring(canvas, atom_ids, *, selected: bool = False):
    item = canvas.add_scene_item("ring", selected=selected)
    item.setData(2, list(atom_ids))
    append_scene_item_for(canvas, "ring_items", item)
    return item


def _add_note(canvas, *, selected: bool = False):
    item = canvas.add_scene_item("note", selected=False)
    append_scene_item_for(canvas, "note_items", item)
    if selected:
        add_selected_note_for(canvas, item)
    return item


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for scene group operation tests")
class SceneGroupOperationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_group_selection_rejects_a_single_connected_fragment(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0, selected=True)
        _add_bond(canvas, atom_a, atom_b, selected=True)

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(group_state_for(canvas).groups, {})
        self.assertEqual(canvas.history.commands, [])

    def test_group_selection_rejects_empty_selection(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas)

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(canvas.history.commands, [])

    def test_group_selection_groups_fragments_and_standalone_items(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        arrow = _add_arrow(canvas, selected=True)
        note = _add_note(canvas, selected=True)

        self.assertTrue(group_selection_for(canvas))

        groups = group_state_for(canvas).groups
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group.atom_ids, {atom_a})
        self.assertEqual({id(item) for item in group.items}, {id(arrow), id(note)})
        self.assertEqual(len(canvas.history.commands), 1)
        self.assertIsInstance(canvas.history.commands[0], GroupSceneItemsCommand)

    def test_group_selection_includes_standalone_marks(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        mark = _add_mark(canvas, atom_id=None, selected=True)

        self.assertTrue(group_selection_for(canvas))

        group = next(iter(group_state_for(canvas).groups.values()))
        self.assertEqual(group.atom_ids, {atom_a})
        self.assertEqual({id(item) for item in group.items}, {id(mark)})

    def test_group_selection_excludes_atom_bound_marks(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 30.0, 0.0, selected=True)
        # A mark pinned to a selected atom is not an independent unit, so the
        # selection is a single connected fragment plus its mark and cannot group.
        _add_mark(canvas, atom_id=atom_b, selected=True)
        _add_bond(canvas, atom_a, atom_b, selected=True)

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(group_state_for(canvas).groups, {})

    def test_group_selection_is_noop_for_identical_membership(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)
        self.assertTrue(group_selection_for(canvas))

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(len(canvas.history.commands), 1)

    def test_group_selection_absorbs_overlapping_groups_with_undo(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0, selected=True)
        atom_c, _ = _add_atom(canvas, 20.0, 0.0, selected=True)
        register_group_for(canvas, {atom_a, atom_b}, [])

        self.assertTrue(group_selection_for(canvas))

        state = group_state_for(canvas)
        self.assertEqual(len(state.groups), 1)
        merged = next(iter(state.groups.values()))
        self.assertEqual(merged.atom_ids, {atom_a, atom_b, atom_c})

        command = canvas.history.commands[-1]
        command.undo(canvas)
        self.assertEqual(len(state.groups), 1)
        self.assertEqual(next(iter(state.groups.values())).atom_ids, {atom_a, atom_b})
        command.redo(canvas)
        self.assertEqual(len(state.groups), 1)
        self.assertEqual(next(iter(state.groups.values())).atom_ids, {atom_a, atom_b, atom_c})

    def test_ungroup_selection_removes_intersecting_groups_with_undo(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0)
        group_id = register_group_for(canvas, {atom_a, atom_b}, [])

        self.assertTrue(ungroup_selection_for(canvas))

        state = group_state_for(canvas)
        self.assertEqual(state.groups, {})
        command = canvas.history.commands[-1]
        self.assertIsInstance(command, UngroupSceneItemsCommand)
        command.undo(canvas)
        self.assertEqual(state.groups[group_id].atom_ids, {atom_a, atom_b})
        command.redo(canvas)
        self.assertEqual(state.groups, {})

    def test_ungroup_selection_without_group_membership_is_noop(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)

        self.assertFalse(ungroup_selection_for(canvas))
        self.assertEqual(canvas.history.commands, [])

    def test_expand_selection_selects_all_group_members(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        _, bond_item = _add_bond(canvas, atom_a, atom_b)
        arrow = _add_arrow(canvas)
        note = _add_note(canvas)
        register_group_for(canvas, {atom_a, atom_b}, [arrow, note])
        item_a.setSelected(True)

        expand_selection_to_groups_for(canvas)

        self.assertTrue(item_b.isSelected())
        self.assertTrue(bond_item.isSelected())
        self.assertTrue(arrow.isSelected())
        canvas.selection_controller.select_note.assert_called_once_with(note, additive=True)
        canvas.selection_controller.update_selection_outline.assert_called_once_with()
        self.assertFalse(group_state_for(canvas).expanding)

    def test_expand_selection_is_noop_when_group_fully_selected(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        register_group_for(canvas, {atom_a}, [arrow])
        item_a.setSelected(True)
        arrow.setSelected(True)

        expand_selection_to_groups_for(canvas)

        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_expand_selection_deselects_stale_group_note_when_group_leaves_selection(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        note = _add_note(canvas, selected=True)
        register_group_for(canvas, {atom_a}, [arrow, note])
        # Simulate the rubber band moving off the group: Qt deselected the
        # group's scene members but the note-service selection is untouched.
        atom_b, item_b = _add_atom(canvas, 50.0, 0.0)
        item_b.setSelected(True)

        expand_selection_to_groups_for(canvas)

        # The lingering note must not re-anchor the group...
        self.assertFalse(item_a.isSelected())
        self.assertFalse(arrow.isSelected())
        # ...and must itself be deselected so the group drops as a unit.
        canvas.selection_controller.toggle_note_selection.assert_called_once_with(note)
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_expand_selection_keeps_notes_only_group_selection(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        register_group_for(canvas, set(), [note_a, note_b])
        _, item = _add_atom(canvas)
        item.setSelected(True)

        expand_selection_to_groups_for(canvas)

        canvas.selection_controller.toggle_note_selection.assert_not_called()

    def test_expand_selection_ignores_ungrouped_selection(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        register_group_for(canvas, {atom_b}, [])
        item_a.setSelected(True)

        expand_selection_to_groups_for(canvas)

        self.assertFalse(item_b.isSelected())
        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_group_selection_targets_extends_to_group_members(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        _, bond_item = _add_bond(canvas, atom_a, atom_b)
        arrow = _add_arrow(canvas)
        register_group_for(canvas, {atom_a, atom_b}, [arrow])

        extended = group_selection_targets_for(canvas, [item_a])

        extended_ids = {id(item) for item in extended}
        self.assertEqual(extended_ids, {id(item_a), id(item_b), id(bond_item), id(arrow)})

    def test_group_selection_targets_expands_from_ring_atom_ids(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        ring = _add_ring(canvas, [atom_a, atom_b])
        arrow = _add_arrow(canvas)
        register_group_for(canvas, {atom_a, atom_b}, [arrow])

        # Shift-clicking the ring fill must resolve the group via the ring's atom
        # IDs, not just atom/bond targets, and pull in the rest of the group.
        extended = group_selection_targets_for(canvas, [ring])

        extended_ids = {id(item) for item in extended}
        self.assertEqual(
            extended_ids,
            {id(ring), id(item_a), id(item_b), id(arrow)},
        )

    def test_group_selection_refreshes_outline_for_immediate_feedback(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)

        self.assertTrue(group_selection_for(canvas))
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

        self.assertTrue(ungroup_selection_for(canvas))
        self.assertEqual(canvas.selection_controller.update_selection_outline.call_count, 2)

    def test_selected_group_rects_cover_all_group_members(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas, 0.0, 0.0, selected=True)
        arrow = _add_arrow(canvas)
        arrow.setRect(100.0, 40.0, 20.0, 10.0)
        register_group_for(canvas, {atom_a}, [arrow])

        rects = selected_group_rects_for(canvas)

        self.assertEqual(len(rects), 1)
        rect = rects[0]
        self.assertLessEqual(rect.left(), 0.0)
        self.assertGreaterEqual(rect.right(), 120.0)
        self.assertGreaterEqual(rect.bottom(), 50.0)

    def test_group_command_undo_redo_refreshes_outline(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)
        self.assertTrue(group_selection_for(canvas))
        command = canvas.history.commands[-1]

        command.undo(canvas)
        command.redo(canvas)

        self.assertEqual(canvas.selection_controller.update_selection_outline.call_count, 3)

    def test_ungroup_command_undo_redo_refreshes_outline(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        register_group_for(canvas, {atom_a}, [])
        self.assertTrue(ungroup_selection_for(canvas))
        command = canvas.history.commands[-1]

        command.undo(canvas)
        command.redo(canvas)

        self.assertEqual(canvas.selection_controller.update_selection_outline.call_count, 3)

    def test_selected_group_rects_for_notes_only_group(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        register_group_for(canvas, set(), [note_a, note_b])

        rects = selected_group_rects_for(canvas)

        self.assertEqual(len(rects), 1)

    def test_selected_group_rects_require_full_notes_only_group_selection(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas)
        register_group_for(canvas, set(), [note_a, note_b])

        # A partially-selected notes-only group must not draw a box claiming
        # more than drag/delete/copy would act on.
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_expand_note_selection_selects_rest_of_notes_only_group(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas)
        register_group_for(canvas, set(), [note_a, note_b])

        expand_note_selection_to_groups_for(canvas, note_a)

        canvas.selection_controller.select_note.assert_called_once_with(note_b, additive=True)
        self.assertFalse(group_state_for(canvas).expanding)

    def test_expand_note_selection_skips_mixed_groups_and_reentry(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas)
        note = _add_note(canvas, selected=True)
        other = _add_note(canvas)
        register_group_for(canvas, {atom_a}, [note, other])

        # Mixed groups expand through the scene selectionChanged hook instead.
        expand_note_selection_to_groups_for(canvas, note)
        canvas.selection_controller.select_note.assert_not_called()

        notes_only_canvas = _Canvas()
        note_a = _add_note(notes_only_canvas, selected=True)
        note_b = _add_note(notes_only_canvas)
        register_group_for(notes_only_canvas, set(), [note_a, note_b])
        group_state_for(notes_only_canvas).expanding = True

        expand_note_selection_to_groups_for(notes_only_canvas, note_a)
        notes_only_canvas.selection_controller.select_note.assert_not_called()

    def test_selected_group_rects_ignore_note_only_selection_of_mixed_group(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas)
        note = _add_note(canvas, selected=True)
        register_group_for(canvas, {atom_a}, [note])

        # A mixed group keys off scene selection; a lone note-tool selection
        # must not draw a box implying the whole group is selected.
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_selected_group_rects_empty_without_group_selection(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 50.0, 0.0)
        register_group_for(canvas, {atom_b}, [])

        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_group_selection_targets_resolves_atom_bound_mark_to_group(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        mark = _add_mark(canvas, atom_id=atom_a)
        register_group_for(canvas, {atom_a}, [arrow])

        # Shift-clicking the charge on a grouped atom must toggle the whole
        # group, not just the mark.
        extended = group_selection_targets_for(canvas, [mark])

        extended_ids = {id(item) for item in extended}
        self.assertEqual(extended_ids, {id(mark), id(item_a), id(arrow)})

    def test_expand_selection_triggers_from_atom_bound_mark(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        _add_mark(canvas, atom_id=atom_a, selected=True)
        register_group_for(canvas, {atom_a}, [arrow])

        expand_selection_to_groups_for(canvas)

        self.assertTrue(item_a.isSelected())
        self.assertTrue(arrow.isSelected())
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_group_selection_targets_includes_grouped_notes(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        note = _add_note(canvas)
        register_group_for(canvas, {atom_a}, [note])

        extended = group_selection_targets_for(canvas, [item_a])

        self.assertIn(id(note), {id(item) for item in extended})

    def test_group_selection_targets_without_group_returns_targets(self) -> None:
        canvas = _Canvas()
        _, item_a = _add_atom(canvas)

        self.assertEqual(group_selection_targets_for(canvas, [item_a]), [item_a])


if __name__ == "__main__":
    unittest.main()
