import os
import unittest
from unittest import mock

from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from tests.mark_support import register_mark_double
from tests.note_support import register_note_double
from tests.ring_support import register_ring_double
from tests.runtime_services import canvas_runtime_services
from tests.runtime_state import canvas_runtime_state
from tests.selection_support import build_selection_controller

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.document import Arrow, MoleculeModel
from chemvas.ui.canvas.canvas_atom_graphics_state import (
    CanvasAtomGraphicsState,
    set_atom_item_for,
)
from chemvas.ui.canvas.canvas_bond_graphics_state import CanvasBondGraphicsState
from chemvas.ui.canvas.canvas_callback_state import CanvasCallbackState
from chemvas.ui.canvas.canvas_group_state import (
    CanvasGroupState,
    register_group_for,
)
from chemvas.ui.canvas.canvas_mark_registry import CanvasMarkRegistry, mark_registry_for
from chemvas.ui.canvas.canvas_scene_items_state import CanvasSceneItemsState
from chemvas.ui.canvas.canvas_text_style_state import CanvasTextStyleState
from chemvas.ui.history.history_commands import (
    GroupSceneItemsCommand,
    UngroupSceneItemsCommand,
)
from chemvas.ui.history.history_operations import CanvasHistoryOperations
from chemvas.ui.scene.scene_group_operations import (
    group_selection_for,
    group_selection_targets_for,
    selected_group_rects_for,
    ungroup_selection_for,
)


class _History:
    def __init__(self) -> None:
        self.commands = []
        self.push_error: BaseException | None = None

    def push(self, command) -> None:
        if self.push_error is not None:
            raise self.push_error
        self.commands.append(command)


class _Canvas(QGraphicsView):
    def __init__(self) -> None:
        super().__init__(QGraphicsScene())
        self.renderer = Renderer()
        self.model = MoleculeModel()
        self.history = _History()
        self.runtime_state = canvas_runtime_state(
            atom_graphics_state=CanvasAtomGraphicsState(),
            bond_graphics_state=CanvasBondGraphicsState(),
            group_state=CanvasGroupState(),
            callback_state=CanvasCallbackState(),
            history_service=self.history,
            mark_registry=CanvasMarkRegistry(),
            scene_items_state=CanvasSceneItemsState(),
            text_style_state=CanvasTextStyleState(),
        )
        self.services = canvas_runtime_services()
        self.selection_controller = build_selection_controller(self, render=False)
        for name in (
            "select_note",
            "toggle_note_selection",
            "update_selection_outline",
        ):
            method = getattr(self.selection_controller, name)
            setattr(self.selection_controller, name, mock.Mock(wraps=method))
        self.selection_controller.update_note_selection_box = mock.Mock()

    def add_scene_item(self, kind: str, *, selected: bool = False):
        item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        item.setData(0, kind)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.scene().addItem(item)
        if selected:
            item.setSelected(True)
        return item


def _add_atom(canvas, x: float = 0.0, y: float = 0.0, *, selected: bool = False):
    atom_id = canvas.model.add_atom("C", x, y)
    item = canvas.add_scene_item("atom", selected=selected)
    item.setData(1, atom_id)
    set_atom_item_for(canvas, atom_id, item)
    return atom_id, item


def _add_bond(canvas, a: int, b: int, *, selected: bool = False):
    bond_id = canvas.model.add_bond(a, b)
    item = canvas.add_scene_item("bond", selected=selected)
    item.setData(1, bond_id)
    canvas.runtime_state.bond_graphics_state.bond_items[bond_id] = [item]
    return bond_id, item


def _add_arrow(canvas, *, selected: bool = False):
    item = canvas.add_scene_item("arrow", selected=selected)
    record_id = len(canvas.runtime_state.arrow_state.records) + 1
    item.setData(3, record_id)
    canvas.runtime_state.arrow_state.records[record_id] = Arrow(
        kind="arrow", start=(0.0, 0.0), end=(5.0, 5.0)
    )
    canvas.runtime_state.append_scene_item("arrow_items", item)
    return item


def _add_mark(canvas, *, atom_id=None, selected: bool = False):
    item = canvas.add_scene_item("mark", selected=selected)
    item.setData(1, {"kind": "plus", "atom_id": atom_id})
    register_mark_double(canvas, item)
    return item


def _add_ring(canvas, atom_ids, *, selected: bool = False):
    item = canvas.add_scene_item("ring", selected=selected)
    item.setData(2, list(atom_ids))
    register_ring_double(canvas, item)
    return item


def _add_note(canvas, *, selected: bool = False):
    item = canvas.add_scene_item("note", selected=False)
    register_note_double(canvas, item)
    if selected:
        canvas.runtime_state.selection_state.add_selected_note(item)
    return item


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
        self.assertEqual(canvas.runtime_state.group_state.groups, {})
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

        groups = canvas.runtime_state.group_state.groups
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group.atom_ids, {atom_a})
        self.assertEqual(
            set(group.item_ids),
            {require_scene_record_id(arrow), require_scene_record_id(note)},
        )
        self.assertEqual(len(canvas.history.commands), 1)
        self.assertIsInstance(canvas.history.commands[0], GroupSceneItemsCommand)

    def test_blocked_group_history_push_restores_group_runtime(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)
        primary = RuntimeError("re-entrant history mutation is not allowed")
        canvas.history.push_error = primary

        with self.assertRaises(RuntimeError) as caught:
            group_selection_for(canvas)

        self.assertIs(caught.exception, primary)
        self.assertEqual(canvas.runtime_state.group_state.groups, {})
        self.assertEqual(canvas.history.commands, [])

    def test_group_selection_includes_standalone_marks(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        mark = _add_mark(canvas, atom_id=None, selected=True)

        self.assertTrue(group_selection_for(canvas))

        group = next(iter(canvas.runtime_state.group_state.groups.values()))
        self.assertEqual(group.atom_ids, {atom_a})
        self.assertEqual(set(group.item_ids), {require_scene_record_id(mark)})

    def test_group_selection_excludes_atom_bound_marks(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 30.0, 0.0, selected=True)
        # A mark pinned to a selected atom is not an independent unit, so the
        # selection is a single connected fragment plus its mark and cannot group.
        _add_mark(canvas, atom_id=atom_b, selected=True)
        _add_bond(canvas, atom_a, atom_b, selected=True)

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(canvas.runtime_state.group_state.groups, {})

    def test_group_selection_is_noop_for_identical_membership(self) -> None:
        canvas = _Canvas()
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)
        self.assertTrue(group_selection_for(canvas))

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(len(canvas.history.commands), 1)

    def test_group_selection_absorbs_overlapping_groups_with_undo(self) -> None:
        canvas = _Canvas()
        operations = CanvasHistoryOperations(canvas)
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0, selected=True)
        atom_c, _ = _add_atom(canvas, 20.0, 0.0, selected=True)
        register_group_for(
            canvas, {atom_a, atom_b}, [require_scene_record_id(item) for item in []]
        )

        self.assertTrue(group_selection_for(canvas))

        state = canvas.runtime_state.group_state
        self.assertEqual(len(state.groups), 1)
        merged = next(iter(state.groups.values()))
        self.assertEqual(merged.atom_ids, {atom_a, atom_b, atom_c})

        command = canvas.history.commands[-1]
        command.undo(operations)
        self.assertEqual(len(state.groups), 1)
        self.assertEqual(next(iter(state.groups.values())).atom_ids, {atom_a, atom_b})
        command.redo(operations)
        self.assertEqual(len(state.groups), 1)
        self.assertEqual(
            next(iter(state.groups.values())).atom_ids, {atom_a, atom_b, atom_c}
        )

    def test_group_selection_union_keeps_unselected_members_of_absorbed_group(
        self,
    ) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0, selected=True)
        atom_c, _ = _add_atom(canvas, 20.0, 0.0, selected=True)
        register_group_for(
            canvas, {atom_a, atom_b}, [require_scene_record_id(item) for item in []]
        )

        self.assertTrue(group_selection_for(canvas))

        state = canvas.runtime_state.group_state
        self.assertEqual(len(state.groups), 1)
        merged = next(iter(state.groups.values()))
        # atom_a was not selected, but grouping {b, c} over the {a, b} group
        # must not silently strip a's membership.
        self.assertEqual(merged.atom_ids, {atom_a, atom_b, atom_c})

    def test_group_selection_is_noop_for_subset_of_existing_group(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0, selected=True)
        atom_c, _ = _add_atom(canvas, 20.0, 0.0)
        register_group_for(
            canvas,
            {atom_a, atom_b, atom_c},
            [require_scene_record_id(item) for item in []],
        )

        self.assertFalse(group_selection_for(canvas))
        self.assertEqual(canvas.history.commands, [])
        group = next(iter(canvas.runtime_state.group_state.groups.values()))
        self.assertEqual(group.atom_ids, {atom_a, atom_b, atom_c})

    def test_ungroup_selection_removes_intersecting_groups_with_undo(self) -> None:
        canvas = _Canvas()
        operations = CanvasHistoryOperations(canvas)
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 10.0, 0.0)
        group_id = register_group_for(
            canvas, {atom_a, atom_b}, [require_scene_record_id(item) for item in []]
        )

        self.assertTrue(ungroup_selection_for(canvas))

        state = canvas.runtime_state.group_state
        self.assertEqual(state.groups, {})
        command = canvas.history.commands[-1]
        self.assertIsInstance(command, UngroupSceneItemsCommand)
        command.undo(operations)
        self.assertEqual(state.groups[group_id].atom_ids, {atom_a, atom_b})
        command.redo(operations)
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
        register_group_for(
            canvas,
            {atom_a, atom_b},
            [require_scene_record_id(item) for item in [arrow, note]],
        )
        item_a.setSelected(True)

        canvas.services.selection.expand_selection_to_groups()

        self.assertTrue(item_b.isSelected())
        self.assertTrue(bond_item.isSelected())
        self.assertTrue(arrow.isSelected())
        canvas.selection_controller.select_note.assert_called_once_with(
            note, additive=True
        )
        self.assertEqual(
            canvas.selection_controller.update_selection_outline.call_count, 2
        )
        self.assertFalse(canvas.runtime_state.group_state.expanding)

    def test_expand_selection_is_noop_when_group_fully_selected(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [arrow]]
        )
        item_a.setSelected(True)
        arrow.setSelected(True)

        canvas.services.selection.expand_selection_to_groups()

        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_expand_selection_deselects_stale_group_note_when_group_leaves_selection(
        self,
    ) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        note = _add_note(canvas, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [arrow, note]]
        )
        # Simulate the rubber band moving off the group: Qt deselected the
        # group's scene members but the note-service selection is untouched.
        atom_b, item_b = _add_atom(canvas, 50.0, 0.0)
        item_b.setSelected(True)

        canvas.services.selection.expand_selection_to_groups()

        # The lingering note must not re-anchor the group...
        self.assertFalse(item_a.isSelected())
        self.assertFalse(arrow.isSelected())
        # ...and must itself be deselected so the group drops as a unit.
        canvas.selection_controller.toggle_note_selection.assert_called_once_with(note)
        self.assertEqual(
            canvas.selection_controller.update_selection_outline.call_count, 2
        )

    def test_expand_selection_keeps_notes_only_group_selection(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )
        _, item = _add_atom(canvas)
        item.setSelected(True)

        canvas.services.selection.expand_selection_to_groups()

        canvas.selection_controller.toggle_note_selection.assert_not_called()

    def test_expand_selection_ignores_ungrouped_selection(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        register_group_for(
            canvas, {atom_b}, [require_scene_record_id(item) for item in []]
        )
        item_a.setSelected(True)

        canvas.services.selection.expand_selection_to_groups()

        self.assertFalse(item_b.isSelected())
        canvas.selection_controller.update_selection_outline.assert_not_called()

    def test_group_selection_targets_extends_to_group_members(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        _, bond_item = _add_bond(canvas, atom_a, atom_b)
        arrow = _add_arrow(canvas)
        register_group_for(
            canvas,
            {atom_a, atom_b},
            [require_scene_record_id(item) for item in [arrow]],
        )

        extended = group_selection_targets_for(canvas, [item_a])

        extended_ids = {id(item) for item in extended}
        self.assertEqual(
            extended_ids,
            {id(item_a), id(item_b), id(bond_item), id(arrow)},
        )

    def test_group_selection_targets_expands_from_ring_atom_ids(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        atom_b, item_b = _add_atom(canvas, 10.0, 0.0)
        ring = _add_ring(canvas, [atom_a, atom_b])
        arrow = _add_arrow(canvas)
        register_group_for(
            canvas,
            {atom_a, atom_b},
            [require_scene_record_id(item) for item in [arrow]],
        )

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
        self.assertEqual(
            canvas.selection_controller.update_selection_outline.call_count, 2
        )

    def test_selected_group_rects_cover_all_group_members(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas, 0.0, 0.0, selected=True)
        arrow = _add_arrow(canvas)
        arrow.setRect(100.0, 40.0, 20.0, 10.0)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [arrow]]
        )

        rects = selected_group_rects_for(canvas)

        self.assertEqual(len(rects), 1)
        rect = rects[0]
        self.assertLessEqual(rect.left(), 0.0)
        self.assertGreaterEqual(rect.right(), 120.0)
        self.assertGreaterEqual(rect.bottom(), 50.0)

    def test_group_command_undo_redo_refreshes_outline(self) -> None:
        canvas = _Canvas()
        operations = CanvasHistoryOperations(canvas)
        _add_atom(canvas, selected=True)
        _add_arrow(canvas, selected=True)
        self.assertTrue(group_selection_for(canvas))
        command = canvas.history.commands[-1]

        command.undo(operations)
        command.redo(operations)

        self.assertEqual(
            canvas.selection_controller.update_selection_outline.call_count, 3
        )

    def test_ungroup_command_undo_redo_refreshes_outline(self) -> None:
        canvas = _Canvas()
        operations = CanvasHistoryOperations(canvas)
        atom_a, _ = _add_atom(canvas, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in []]
        )
        self.assertTrue(ungroup_selection_for(canvas))
        command = canvas.history.commands[-1]

        command.undo(operations)
        command.redo(operations)

        self.assertEqual(
            canvas.selection_controller.update_selection_outline.call_count, 3
        )

    def test_selected_group_rects_for_notes_only_group(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )

        rects = selected_group_rects_for(canvas)

        self.assertEqual(len(rects), 1)

    def test_selected_group_rects_ignore_qt_selected_note_of_notes_only_group(
        self,
    ) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas)
        note_b = _add_note(canvas)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )
        # A lingering Qt selection (rubber band / mirrored flags) must not
        # bypass the full note-service selection gate.
        note_a.setSelected(True)

        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_expand_selection_ignores_qt_selected_note_of_notes_only_group(
        self,
    ) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas)
        note_b = _add_note(canvas)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )
        note_a.setSelected(True)

        # Notes-only groups have no scene shrink path, so a Qt-selected note
        # must not scene-expand them (sticky-marquee prevention).
        canvas.services.selection.expand_selection_to_groups()

        canvas.selection_controller.select_note.assert_not_called()

    def test_clear_note_selection_clears_qt_flags_of_cleared_notes(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        # Mirrored Qt flags, e.g. from a notes-only group toggle.
        note_a.setSelected(True)
        note_b.setSelected(True)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )
        service = canvas.selection_controller

        # NoteTool press on empty canvas clears the note selection wholesale;
        # the Qt flags must drop too or an invisible selection would remain.
        service.clear_note_selection()

        self.assertEqual(canvas.runtime_state.selection_state.selected_notes, [])
        self.assertFalse(note_a.isSelected())
        self.assertFalse(note_b.isSelected())
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_notes_only_unit_deselect_clears_qt_flags(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas, selected=True)
        note_a.setSelected(True)
        note_b.setSelected(True)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )
        service = canvas.selection_controller

        service.toggle_note_selection(note_a)

        self.assertEqual(canvas.runtime_state.selection_state.selected_notes, [])
        self.assertFalse(note_a.isSelected())
        self.assertFalse(note_b.isSelected())

    def test_selected_group_rects_require_full_notes_only_group_selection(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )

        # A partially-selected notes-only group must not draw a box claiming
        # more than drag/delete/copy would act on.
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_expand_note_selection_selects_rest_of_notes_only_group(self) -> None:
        canvas = _Canvas()
        note_a = _add_note(canvas, selected=True)
        note_b = _add_note(canvas)
        register_group_for(
            canvas, set(), [require_scene_record_id(item) for item in [note_a, note_b]]
        )

        canvas.services.selection.expand_note_selection_to_groups(note_a)

        canvas.selection_controller.select_note.assert_called_once_with(
            note_b, additive=True
        )
        self.assertFalse(canvas.runtime_state.group_state.expanding)

    def test_expand_note_selection_selects_mixed_group_and_skips_reentry(self) -> None:
        canvas = _Canvas()
        atom_a, atom_item = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        note = _add_note(canvas)
        other = _add_note(canvas)
        register_group_for(
            canvas,
            {atom_a},
            [require_scene_record_id(item) for item in [arrow, note, other]],
        )
        service = canvas.selection_controller

        # A direct Note-tool selection is an explicit group anchor even though
        # raw Qt note selection remains excluded from the marquee expansion.
        with mock.patch.object(service, "update_note_selection_box"):
            service.select_note(note, additive=True)

        self.assertIn(note, canvas.runtime_state.selection_state.selected_notes)
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(arrow.isSelected())
        canvas.selection_controller.select_note.assert_any_call(other, additive=True)
        self.assertFalse(canvas.runtime_state.group_state.expanding)

        notes_only_canvas = _Canvas()
        note_a = _add_note(notes_only_canvas, selected=True)
        note_b = _add_note(notes_only_canvas)
        register_group_for(
            notes_only_canvas,
            set(),
            [require_scene_record_id(item) for item in [note_a, note_b]],
        )
        notes_only_canvas.runtime_state.group_state.expanding = True

        notes_only_canvas.services.selection.expand_note_selection_to_groups(note_a)
        notes_only_canvas.selection_controller.select_note.assert_not_called()

    def test_deselecting_mixed_group_note_deselects_whole_group(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas, selected=True)
        arrow = _add_arrow(canvas, selected=True)
        note = _add_note(canvas, selected=True)
        other_note = _add_note(canvas, selected=True)
        # Attached notes are Qt-selectable; a rubber band can Qt-select them.
        note.setSelected(True)
        other_note.setSelected(True)
        register_group_for(
            canvas,
            {atom_a},
            [require_scene_record_id(item) for item in [arrow, note, other_note]],
        )
        service = canvas.selection_controller

        # Note focus-out / NoteTool Ctrl-click deselects through the note
        # service; the mixed group must drop as a unit or the box would span a
        # note that a drag no longer moves.
        service.toggle_note_selection(note)

        self.assertFalse(item_a.isSelected())
        self.assertFalse(arrow.isSelected())
        self.assertNotIn(note, canvas.runtime_state.selection_state.selected_notes)
        self.assertNotIn(
            other_note, canvas.runtime_state.selection_state.selected_notes
        )
        # The notes' Qt selection flags must clear too, or they would keep
        # triggering the group box.
        self.assertFalse(note.isSelected())
        self.assertFalse(other_note.isSelected())
        self.assertEqual(selected_group_rects_for(canvas), [])
        self.assertFalse(canvas.runtime_state.group_state.expanding)

    def test_deselecting_mixed_group_note_clears_qt_selected_bound_mark(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas, selected=True)
        note = _add_note(canvas, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [note]]
        )
        # A charge mark bound to the grouped atom, Qt-selected via rubber band.
        mark = _add_mark(canvas, atom_id=atom_a, selected=True)
        mark_registry_for(canvas).add_for_atom(atom_a, mark)
        service = canvas.selection_controller

        service.toggle_note_selection(note)

        self.assertFalse(item_a.isSelected())
        # The bound mark must drop with the group or its lingering Qt
        # selection would keep re-triggering the group box.
        self.assertFalse(mark.isSelected())
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_clearing_note_selection_deselects_mixed_groups_as_unit(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas, selected=True)
        note = _add_note(canvas, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [note]]
        )
        atom_b, item_b = _add_atom(canvas, 60.0, 0.0, selected=True)
        service = canvas.selection_controller

        # NoteTool press on empty canvas clears the note selection wholesale;
        # the mixed group's scene members must drop with their note.
        service.clear_note_selection()

        self.assertFalse(item_a.isSelected())
        self.assertEqual(canvas.runtime_state.selection_state.selected_notes, [])
        self.assertEqual(selected_group_rects_for(canvas), [])
        # Ungrouped scene selection is untouched.
        self.assertTrue(item_b.isSelected())

    def test_selected_group_rects_ignore_note_only_selection_of_mixed_group(
        self,
    ) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas)
        note = _add_note(canvas, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [note]]
        )

        # A mixed group keys off scene selection; a lone note-tool selection
        # must not draw a box implying the whole group is selected.
        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_selected_group_rects_empty_without_group_selection(self) -> None:
        canvas = _Canvas()
        atom_a, _ = _add_atom(canvas, selected=True)
        atom_b, _ = _add_atom(canvas, 50.0, 0.0)
        register_group_for(
            canvas, {atom_b}, [require_scene_record_id(item) for item in []]
        )

        self.assertEqual(selected_group_rects_for(canvas), [])

    def test_group_selection_targets_resolves_atom_bound_mark_to_group(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        mark = _add_mark(canvas, atom_id=atom_a)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [arrow]]
        )

        # Shift-clicking the charge on a grouped atom must toggle the whole
        # group, not just the mark.
        extended = group_selection_targets_for(canvas, [mark])

        extended_ids = {id(item) for item in extended}
        self.assertEqual(
            extended_ids,
            {id(mark), id(item_a), id(arrow)},
        )

    def test_expand_selection_triggers_from_atom_bound_mark(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        arrow = _add_arrow(canvas)
        _add_mark(canvas, atom_id=atom_a, selected=True)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [arrow]]
        )

        canvas.services.selection.expand_selection_to_groups()

        self.assertTrue(item_a.isSelected())
        self.assertTrue(arrow.isSelected())
        canvas.selection_controller.update_selection_outline.assert_called_once_with()

    def test_group_selection_targets_includes_grouped_notes(self) -> None:
        canvas = _Canvas()
        atom_a, item_a = _add_atom(canvas)
        note = _add_note(canvas)
        register_group_for(
            canvas, {atom_a}, [require_scene_record_id(item) for item in [note]]
        )

        extended = group_selection_targets_for(canvas, [item_a])

        self.assertIn(id(note), {id(item) for item in extended})

    def test_group_selection_targets_without_group_returns_targets(self) -> None:
        canvas = _Canvas()
        _, item_a = _add_atom(canvas)

        self.assertEqual(group_selection_targets_for(canvas, [item_a]), [item_a])
