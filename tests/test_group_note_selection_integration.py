import json
import os
import unittest
from math import hypot
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
)

from chemvas.ui.canvas_atom_graphics_state import set_atom_item_for
from chemvas.ui.canvas_callback_state import callback_state_for
from chemvas.ui.canvas_document_state import snapshot_canvas_document_state
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_scene_items_state import (
    append_scene_item_for,
    selected_notes_for,
)
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.move_access import move_item_for
from chemvas.ui.scene_decoration_access import add_arrow_for
from chemvas.ui.scene_group_operations import (
    expand_selection_to_groups_for,
    group_selection_for,
)
from chemvas.ui.selection_collection_access import (
    selection_snapshot_for,
    selection_status_count_for,
)
from chemvas.ui.structure_mutation_access import (
    add_atom_for,
    add_benzene_ring_for,
    add_bond_for,
)
from tests.canvas_factory import build_canvas_view


class GroupedNoteSelectionIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def _add_atom(self, canvas, x: float):
        atom_id = model_for(canvas).add_atom("C", x, 0.0)
        item = QGraphicsRectItem(0.0, 0.0, 5.0, 5.0)
        item.setData(0, "atom")
        item.setData(1, atom_id)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        canvas.scene().addItem(item)
        set_atom_item_for(canvas, atom_id, item)
        return atom_id, item

    def _dispose_canvas(self, canvas) -> None:
        schedule_canvas_deletion_for(canvas)
        QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def test_pasted_single_multiple_and_mixed_note_counts(self) -> None:
        canvas = build_canvas_view()
        self.addCleanup(self._dispose_canvas, canvas)
        clipboard = canvas.services.scene_operations.scene_clipboard_controller
        notes = [
            canvas.services.interaction.note_controller.create_text_note(
                QPointF(index * 40.0, 40.0), f"note {index}"
            )
            for index in range(2)
        ]
        clipboard.select_pasted_content(set(), notes[:1])
        self.assertTrue(notes[0].isSelected())
        self.assertIn(notes[0], selected_notes_for(canvas))
        self.assertEqual(selection_status_count_for(canvas), 1)

        clipboard.select_pasted_content(set(), notes)
        self.assertEqual(selection_status_count_for(canvas), 2)
        atom_id, _ = self._add_atom(canvas, 80.0)
        clipboard.select_pasted_content({atom_id}, notes)
        self.assertEqual(selection_status_count_for(canvas), 3)

        canvas.services.selection.selection_controller.clear_note_selection()
        self.assertEqual(selection_status_count_for(canvas), 1)
        canvas.scene().clearSelection()
        self.assertEqual(selection_status_count_for(canvas), 0)

    def test_group_toggle_does_not_count_its_note_twice(self) -> None:
        canvas = build_canvas_view()
        self.addCleanup(self._dispose_canvas, canvas)
        atom_id, atom_item = self._add_atom(canvas, 0.0)
        note = canvas.services.interaction.note_controller.create_text_note(
            QPointF(40.0, 40.0), "group label"
        )
        canvas.services.scene_operations.scene_clipboard_controller.select_pasted_content(
            {atom_id}, [note]
        )
        self.assertTrue(group_selection_for(canvas))
        selection = canvas.services.selection.selection_controller
        selection.clear_note_selection()
        canvas.scene().clearSelection()

        selection.toggle_item_selection(atom_item)
        self.assertIn(note, selected_notes_for(canvas))
        self.assertEqual(selection_status_count_for(canvas), 2)
        selection.toggle_item_selection(atom_item)
        self.assertEqual(selection_status_count_for(canvas), 0)

    def test_grouped_note_follows_shift_click_and_drag(self) -> None:
        canvas = build_canvas_view()
        self.addCleanup(self._dispose_canvas, canvas)
        canvas.services.tool_controller.set_active("select")
        _, atom_item_a = self._add_atom(canvas, 0.0)
        _, atom_item_b = self._add_atom(canvas, 80.0)
        note = canvas.services.interaction.note_controller.create_text_note(
            QPointF(40.0, 40.0), "label"
        )
        append_scene_item_for(canvas, "note_items", note)

        atom_item_a.setSelected(True)
        atom_item_b.setSelected(True)
        canvas.services.selection.selection_controller.select_note(note, additive=True)
        self.assertTrue(group_selection_for(canvas))
        self.assertEqual(len(group_state_for(canvas).groups), 1)

        canvas.services.selection.selection_controller.clear_note_selection()
        canvas.scene().clearSelection()
        self.assertNotIn(note, selected_notes_for(canvas))

        # Shift-click routes through toggle_item_selection, whose
        # set_scene_items_selected_for blocks the selectionChanged expansion hook,
        # so the grouped note must be toggled explicitly through the note service.
        canvas.services.selection.selection_controller.toggle_item_selection(
            atom_item_a
        )
        self.assertTrue(atom_item_a.isSelected())
        self.assertTrue(atom_item_b.isSelected())
        self.assertIn(note, selected_notes_for(canvas))

        # The selected note must ride along in the drag snapshot; the drag path
        # moves every snapshot selection item, so the note follows the group.
        snapshot = selection_snapshot_for(canvas)
        self.assertIn(note, snapshot.selection_items)
        before = note.pos()
        move_item_for(canvas, note, 25.0, 10.0, update_selection=False)
        self.assertEqual(note.pos().x() - before.x(), 25.0)
        self.assertEqual(note.pos().y() - before.y(), 10.0)

        # Toggling the same member again drops the whole group, note included.
        canvas.services.selection.selection_controller.toggle_item_selection(
            atom_item_a
        )
        self.assertFalse(atom_item_a.isSelected())
        self.assertFalse(atom_item_b.isSelected())
        self.assertNotIn(note, selected_notes_for(canvas))

    def test_redone_group_paste_drags_ring_sidechain_and_annotations_together(self):
        for redo_cycles in (1, 3):
            with self.subTest(redo_cycles=redo_cycles):
                canvas = build_canvas_view()
                self.addCleanup(self._dispose_canvas, canvas)
                canvas.resize(800, 600)
                canvas.setSceneRect(-300, -200, 700, 500)
                canvas.services.tool_controller.set_active("select")
                model = model_for(canvas)
                add_benzene_ring_for(canvas, QPointF(-140, 0))
                ring_atom = max(model.atoms, key=lambda aid: model.atoms[aid].x)
                attachment = model.atoms[ring_atom]
                sidechain = add_atom_for(canvas, "C", attachment.x + 40, attachment.y)
                oxygen = add_atom_for(canvas, "O", attachment.x + 80, attachment.y)
                add_bond_for(canvas, ring_atom, sidechain)
                add_bond_for(canvas, sidechain, oxygen)
                arrow = add_arrow_for(canvas, QPointF(0, 0), QPointF(100, 0), "arrow")
                note = canvas.services.interaction.note_controller.create_text_note(
                    QPointF(-140, -90), "reaction"
                )
                original_ids = set(model.atoms)
                original_positions = {
                    aid: (atom.x, atom.y) for aid, atom in model.atoms.items()
                }
                original_item_positions = {arrow: arrow.pos(), note: note.pos()}
                clipboard = canvas.services.scene_operations.scene_clipboard_controller
                clipboard.select_pasted_content(original_ids, [arrow, note])
                self.assertTrue(group_selection_for(canvas))
                payload = clipboard.selection_payload_for_clipboard()
                self.assertTrue(
                    clipboard.paste_selection_from_clipboard(
                        payload_provider=lambda payload=payload: (
                            payload,
                            json.dumps(payload),
                        )
                    )
                )
                copied_ids = set(model.atoms) - original_ids
                self.assertEqual(len(copied_ids), 8)
                history = history_service_for_access(canvas)
                for _ in range(redo_cycles):
                    history.undo()
                    self.assertEqual(set(model.atoms), original_ids)
                    self.assertEqual(len(group_state_for(canvas).groups), 1)
                    history.redo()
                    self.assertEqual(set(model.atoms), original_ids | copied_ids)

                groups = group_state_for(canvas).groups
                self.assertEqual(len(groups), 2)
                copied_group = next(
                    group for group in groups.values() if group.atom_ids == copied_ids
                )
                self.assertEqual(
                    {item.data(0) for item in copied_group.items}, {"arrow", "note"}
                )
                copied_arrow = next(
                    item for item in copied_group.items if item.data(0) == "arrow"
                )
                before_positions = {
                    aid: (atom.x, atom.y) for aid, atom in model.atoms.items()
                }
                before_lengths = {
                    bid: hypot(
                        model.atoms[bond.a].x - model.atoms[bond.b].x,
                        model.atoms[bond.a].y - model.atoms[bond.b].y,
                    )
                    for bid, bond in enumerate(model.bonds)
                    if bond is not None
                }
                before_items = {item: item.pos() for item in copied_group.items}
                self.app.processEvents()
                start = canvas.mapFromScene(copied_arrow.sceneBoundingRect().center())
                delta = QPoint(24, 80)
                # No click or selection repair between Redo and this drag.
                QTest.mousePress(
                    canvas.viewport(), Qt.MouseButton.LeftButton, pos=start
                )
                QTest.mouseRelease(
                    canvas.viewport(), Qt.MouseButton.LeftButton, pos=start + delta
                )
                self.app.processEvents()

                for aid in copied_ids:
                    self.assertAlmostEqual(
                        model.atoms[aid].x, before_positions[aid][0] + 24
                    )
                    self.assertAlmostEqual(
                        model.atoms[aid].y, before_positions[aid][1] + 80
                    )
                for item, before in before_items.items():
                    self.assertEqual(item.pos(), before + QPointF(delta))
                for aid, before in original_positions.items():
                    self.assertEqual((model.atoms[aid].x, model.atoms[aid].y), before)
                for item, before in original_item_positions.items():
                    self.assertEqual(item.pos(), before)
                for bid, before in before_lengths.items():
                    bond = model.bonds[bid]
                    self.assertAlmostEqual(
                        hypot(
                            model.atoms[bond.a].x - model.atoms[bond.b].x,
                            model.atoms[bond.a].y - model.atoms[bond.b].y,
                        ),
                        before,
                    )
                self.assertEqual(copied_group.atom_ids, copied_ids)
                history.undo()
                for aid, (x, y) in before_positions.items():
                    self.assertAlmostEqual(model.atoms[aid].x, x)
                    self.assertAlmostEqual(model.atoms[aid].y, y)
                history.redo()
                for aid in copied_ids:
                    self.assertAlmostEqual(
                        model.atoms[aid].x, before_positions[aid][0] + 24
                    )
                    self.assertAlmostEqual(
                        model.atoms[aid].y, before_positions[aid][1] + 80
                    )

    def test_failed_group_paste_redo_restores_selection_document_and_history(self):
        canvas = build_canvas_view()
        self.addCleanup(self._dispose_canvas, canvas)
        canvas.services.tool_controller.set_active("select")
        add_benzene_ring_for(canvas, QPointF(-140, 0))
        ring_atom = max(
            model_for(canvas).atoms, key=lambda aid: model_for(canvas).atoms[aid].x
        )
        oxygen = add_atom_for(canvas, "O", -80, 0)
        add_bond_for(canvas, ring_atom, oxygen)
        original_ids = set(model_for(canvas).atoms)
        arrow = add_arrow_for(canvas, QPointF(0, 0), QPointF(100, 0), "arrow")
        note = canvas.services.interaction.note_controller.create_text_note(
            QPointF(0, -80), "reaction"
        )
        clipboard = canvas.services.scene_operations.scene_clipboard_controller
        clipboard.select_pasted_content(original_ids, [arrow, note])
        self.assertTrue(group_selection_for(canvas))
        payload = clipboard.selection_payload_for_clipboard()
        self.assertTrue(
            clipboard.paste_selection_from_clipboard(
                payload_provider=lambda: (payload, json.dumps(payload))
            )
        )
        copied_ids = set(model_for(canvas).atoms) - original_ids
        copied_group = next(
            group
            for group in group_state_for(canvas).groups.values()
            if group.atom_ids == copied_ids
        )
        copied_note = next(
            item for item in copied_group.items if item.data(0) == "note"
        )
        history = history_service_for_access(canvas)
        history.undo()
        before_document = snapshot_canvas_document_state(canvas)
        before_groups = dict(group_state_for(canvas).groups)
        before_selection = set(canvas.scene().selectedItems())
        before_notes = set(selected_notes_for(canvas))
        before_undo = list(history.state.history)
        self.assertTrue(history.state.redo_stack)
        failure = RuntimeError("selection expansion failed after changing selection")
        injected = False

        def expand_then_fail(target):
            nonlocal injected
            expand_selection_to_groups_for(target)
            if not injected and len(group_state_for(target).groups) == 2:
                injected = True
                self.assertIn(
                    copied_note, selection_snapshot_for(target).selection_items
                )
                self.assertEqual(
                    selection_snapshot_for(target).selected_atom_ids, copied_ids
                )
                raise failure

        with mock.patch.object(
            callback_state_for(canvas),
            "scene_selection_group",
            side_effect=lambda: expand_then_fail(canvas),
        ):
            with self.assertRaises(RuntimeError) as caught:
                history.redo()

        self.assertIs(caught.exception, failure)
        self.assertTrue(injected)
        self.assertEqual(snapshot_canvas_document_state(canvas), before_document)
        self.assertEqual(group_state_for(canvas).groups, before_groups)
        self.assertEqual(set(canvas.scene().selectedItems()), before_selection)
        self.assertEqual(set(selected_notes_for(canvas)), before_notes)
        self.assertEqual(history.state.history, before_undo)
        # Mixed scene/group history keeps its existing conservative policy:
        # a failed redo is discarded, while the document and prior undo survive.
        self.assertEqual(history.state.redo_stack, [])
        self.assertTrue(
            clipboard.paste_selection_from_clipboard(
                payload_provider=lambda: (payload, json.dumps(payload))
            )
        )
        self.assertEqual(len(group_state_for(canvas).groups), 2)
        self.assertEqual(selection_snapshot_for(canvas).selected_atom_ids, copied_ids)
