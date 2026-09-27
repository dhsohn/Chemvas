import os
import unittest
from unittest import mock

from tests.scene_operation_support import _RecordingFakeCanvas

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from chemvas.adapters.qt.renderer import Renderer
from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.canvas.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.molecule.bond_graphics_access import project_point_3d_for
from chemvas.ui.scene.scene_clipboard_state import SceneClipboardState
from chemvas.ui.transactions.document import DocumentSavepoint
from tests.scene_operation_support import (
    _make_note_item,
    scene_clipboard_controller_for,
)

_PASTE_PAYLOAD = {
    "format": "chemvas-selection",
    "version": 2,
    "atoms": [
        {"id": 10, "element": "N", "x": 5.0, "y": 7.0},
        {"id": 11, "element": "C", "x": 25.0, "y": 7.0},
    ],
    "bonds": [{"a": 10, "b": 11, "order": 1, "style": "single", "color": "#000000"}],
    "rings": [],
    "marks": [],
    "scene_items": [
        {"kind": "note", "text": "first", "x": 50.0, "y": 60.0},
        {"kind": "note", "text": "second", "x": 90.0, "y": 60.0},
    ],
    "perspective": {
        "atom_coords_3d": [{"atom_id": 10, "coords": [1.0, 2.0, 3.0]}],
        "projection_center_3d": [1.0, 2.0, 0.0],
        "projection_anchor_2d": [1.0, 2.0],
    },
}


class _ZeroBoundsItem(QGraphicsItem):
    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0.0, 0.0, 0.0, 0.0)

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        return None


class SceneOpsControllerPasteEdgesTest(unittest.TestCase):
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

    def test_paste_selection_from_clipboard_rejects_missing_and_empty_payloads(
        self,
    ) -> None:
        canvas = _RecordingFakeCanvas()
        controller = scene_clipboard_controller_for(canvas)

        controller.clipboard_selection_payload = lambda: (None, None)
        self.assertFalse(controller.paste_selection_from_clipboard())

        controller.clipboard_selection_payload = lambda: (
            {
                "format": "chemvas-selection",
                "version": 2,
                "atoms": [],
                "bonds": [],
                "rings": [],
                "marks": [],
                "scene_items": [],
            },
            "payload-json",
        )
        self.assertFalse(controller.paste_selection_from_clipboard())

    def test_select_pasted_content_skips_missing_atoms_and_none_scene_items(
        self,
    ) -> None:
        canvas = _RecordingFakeCanvas()
        note_item = _make_note_item("note", 14.0, 16.0)
        canvas.add_item(note_item)
        controller = scene_clipboard_controller_for(canvas)

        controller.select_pasted_content({99}, [None, note_item])

        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.select_note_calls, [(note_item, True)])
        self.assertEqual(canvas.update_selection_outline_calls, 1)
        self.assertTrue(note_item.isSelected())

    def test_paste_selection_from_clipboard_keeps_paste_state_when_everything_is_dropped(
        self,
    ) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "old-source"
        canvas.scene_clipboard_state.paste_count = 7
        canvas.translate_empty_kinds = {"skip"}
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                "bad-atom",
                {"id": "bad"},
                {"id": 1, "element": "C", "x": "bad", "y": 2.0},
            ],
            "bonds": [
                "bad-bond",
                {"a": 1, "b": 2, "order": 1, "style": "single", "color": "#000000"},
            ],
            "rings": [],
            "marks": [],
            "scene_items": [
                {"kind": "skip", "x": 1.0, "y": 2.0},
            ],
        }
        controller.clipboard_selection_payload = lambda: (payload, "new-source")

        self.assertFalse(controller.paste_selection_from_clipboard())
        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "old-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 7)
        self.assertEqual(canvas.atom_color_calls, [])
        self.assertEqual(canvas.atom_label_calls, [])
        self.assertEqual(canvas.created_scene_item_states, [])
        self.assertEqual(canvas.record_additions_calls, [])

    def test_paste_selection_from_clipboard_applies_explicit_carbon_and_additive_note_selection(
        self,
    ) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.translate_empty_kinds = {"skip"}
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {
                    "id": 10,
                    "element": "C",
                    "x": 5.0,
                    "y": 7.0,
                    "color": "#123456",
                    "explicit_label": True,
                },
            ],
            "bonds": [
                {"a": 10, "b": 99, "order": 2, "style": "double", "color": "#abcdef"},
            ],
            "rings": [],
            "marks": [],
            "scene_items": [
                {"kind": "skip", "x": 1.0, "y": 2.0},
                {"kind": "note", "text": "copied", "x": 50.0, "y": 60.0},
            ],
        }
        controller.clipboard_selection_payload = lambda: (payload, "fresh-source")

        self.assertTrue(controller.paste_selection_from_clipboard())

        self.assertEqual(canvas.scene_clipboard_state.paste_source_json, "fresh-source")
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 1)
        self.assertEqual(canvas.atom_color_calls, [(0, "#123456")])
        self.assertEqual(
            canvas.atom_label_calls,
            [
                {
                    "atom_id": 0,
                    "element": "C",
                    "record": False,
                    "allow_merge": False,
                    "show_carbon": True,
                }
            ],
        )
        self.assertEqual(
            canvas.created_scene_item_states,
            [{"kind": "note", "text": "copied", "x": 68.0, "y": 78.0}],
        )
        self.assertEqual(canvas.select_note_calls, [(canvas.created_items[0], True)])
        self.assertEqual(canvas.record_additions_calls, [(0, 0, canvas.created_items)])
        self.assertEqual(canvas.clear_note_selection_calls, 1)
        self.assertEqual(canvas.update_selection_outline_calls, 1)

    def test_paste_relayouts_alias_after_its_bond_is_available(self) -> None:
        canvas = CanvasView(renderer=Renderer())
        controller = canvas.services.scene_clipboard_controller
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 10, "element": "CF3", "x": 0.0, "y": 0.0},
                {"id": 11, "element": "C", "x": 20.0, "y": 0.0},
            ],
            "bonds": [
                {
                    "a": 10,
                    "b": 11,
                    "order": 1,
                    "style": "single",
                    "color": "#000000",
                }
            ],
            "rings": [],
            "marks": [],
            "scene_items": [],
        }

        self.assertTrue(
            controller.paste_selection_from_clipboard(
                payload_provider=lambda: (payload, "alias-payload")
            )
        )

        label = visible_atom_item_for(canvas, 0)
        self.assertIsNotNone(label)
        self.assertEqual(label.toPlainText(), "F3C")
        self.assertEqual(canvas.model.atoms[0].element, "CF3")
        canvas.deleteLater()

    def _paste_failure_canvas(self) -> CanvasView:
        canvas = CanvasView(renderer=Renderer())
        self.addCleanup(canvas.deleteLater)
        builder = canvas.services.structure_build_service
        canvas.model.add_atom("C", 0.0, 0.0)
        canvas.model.add_atom("C", 40.0, 0.0)
        canvas.model.add_bond(0, 1, 1)
        builder.render_model()
        builder.sprout_regular_ring_from_atom(0, 5)
        builder.sprout_regular_ring_from_atom(1, 6)
        canvas.services.history_service.undo()
        canvas.services.scene_item_controller.create_scene_item_from_state(
            {"kind": "note", "text": "keep", "x": 4.0, "y": 60.0}
        )
        self.assertTrue(canvas.services.selection.select_all())
        canvas.runtime_state.scene_clipboard_state.record_paste_source("old-source", 3)
        return canvas

    def _assert_failed_paste_is_restored_by_its_savepoint(
        self, failure_point: str
    ) -> None:
        canvas = self._paste_failure_canvas()
        controller = canvas.services.scene_clipboard_controller
        history = canvas.services.history_service
        clipboard = canvas.runtime_state.scene_clipboard_state
        session = canvas.services.canvas_document_session_service
        before = session.snapshot_state()
        scene_items = tuple(canvas.scene().items())
        selected_items = set(canvas.scene().selectedItems())
        selected_notes = list(canvas.runtime_state.selection_state.selected_notes)
        coords_3d = dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)
        history_list = history.state.history
        redo_list = history.state.redo_stack
        history_before = tuple(history_list)
        redo_before = tuple(redo_list)
        failure = RuntimeError(f"paste {failure_point} failure")
        if failure_point == "second note":
            scene_item_controller = canvas.services.scene_item_controller
            create_item = scene_item_controller.create_scene_item_from_state
            created = []

            def fail_on_second_note(state):
                if created:
                    raise failure
                created.append(create_item(state))
                return created[-1]

            failing = mock.patch.object(
                scene_item_controller,
                "create_scene_item_from_state",
                side_effect=fail_on_second_note,
            )
        elif failure_point == "recording":
            failing = mock.patch.object(
                canvas.services.canvas_history_recording_service,
                "record_additions",
                side_effect=failure,
            )
        elif failure_point == "push":
            failing = mock.patch.object(history, "push", side_effect=failure)
        else:
            # Fails after the paste was pushed onto the undo stack.
            failing = mock.patch.object(
                SceneClipboardState, "record_paste_source", side_effect=failure
            )

        def paste() -> bool:
            return controller.paste_selection_from_clipboard(
                payload_provider=lambda: (_PASTE_PAYLOAD, "fresh-source")
            )

        with failing, self.assertRaises(RuntimeError) as raised:
            paste()

        self.assertIs(raised.exception, failure)
        self.assertEqual(session.snapshot_state(), before)
        self.assertEqual(tuple(canvas.scene().items()), scene_items)
        self.assertEqual(set(canvas.scene().selectedItems()), selected_items)
        self.assertEqual(
            list(canvas.runtime_state.selection_state.selected_notes), selected_notes
        )
        self.assertEqual(
            canvas.runtime_state.atom_coords_3d_state.atom_coords_3d, coords_3d
        )
        self.assertEqual(
            (clipboard.paste_source_json, clipboard.paste_count), ("old-source", 3)
        )
        self.assertIs(history.state.history, history_list)
        self.assertIs(history.state.redo_stack, redo_list)
        self.assertEqual(tuple(history_list), history_before)
        self.assertEqual(tuple(redo_list), redo_before)

        self.assertTrue(paste())
        self.assertEqual(len(history_list), len(history_before) + 1)
        history.undo()
        self.assertEqual(session.snapshot_state(), before)

    def test_failed_paste_is_restored_by_its_savepoint(self) -> None:
        for failure_point in ("second note", "recording", "push", "paste source"):
            with self.subTest(failure_point=failure_point):
                self._assert_failed_paste_is_restored_by_its_savepoint(failure_point)

    def test_failed_paste_restore_is_not_preceded_by_relative_repair(self) -> None:
        canvas = self._paste_failure_canvas()
        controller = canvas.services.scene_clipboard_controller
        selected_items = set(canvas.scene().selectedItems())
        failure = RuntimeError("paste recording failure")
        restore_error = RuntimeError("paste restore failed")

        with (
            mock.patch.object(
                canvas.services.canvas_history_recording_service,
                "record_additions",
                side_effect=failure,
            ),
            mock.patch.object(
                DocumentSavepoint,
                "restore",
                autospec=True,
                return_value=RestoreOutcome(
                    authoritative=False, errors=(restore_error,)
                ),
            ) as restore,
            self.assertRaises(RuntimeError) as raised,
        ):
            controller.paste_selection_from_clipboard(
                payload_provider=lambda: (_PASTE_PAYLOAD, "fresh-source")
            )

        self.assertIs(raised.exception, failure)
        restore.assert_called_once()
        self.assertTrue(
            any("paste restore failed" in note for note in failure.__notes__)
        )
        # Nothing but the savepoint undoes the paste: when its restore is not
        # authoritative, the pasted notes and their selection stay in place.
        pasted_notes = {
            note.toPlainText() for note in canvas.runtime_state.note_items()
        }
        self.assertTrue({"first", "second"} <= pasted_notes)
        self.assertNotEqual(set(canvas.scene().selectedItems()), selected_items)

    def test_paste_selection_from_clipboard_remaps_perspective_state(self) -> None:
        canvas = _RecordingFakeCanvas()
        rotation = canvas.runtime_state.rotation_state
        rotation.projection_center_3d = (100.0, 100.0, 0.0)
        rotation.projection_anchor_2d = (100.0, 100.0)
        controller = scene_clipboard_controller_for(canvas)
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": 10, "element": "C", "x": 5.0, "y": 7.0},
                {"id": 11, "element": "N", "x": 25.0, "y": 7.0},
            ],
            "bonds": [
                {"a": 10, "b": 11, "order": 1, "style": "single", "color": "#000000"}
            ],
            "rings": [],
            "marks": [],
            "scene_items": [],
            "perspective": {
                "atom_coords_3d": [
                    {"atom_id": 10, "coords": [1.0, 2.0, 3.0]},
                    {"atom_id": 11, "coords": [4.0, 5.0, 6.0]},
                ],
                "projection_center_3d": [7.0, 8.0, 9.0],
                "projection_anchor_2d": [10.0, 11.0],
            },
        }
        controller.clipboard_selection_payload = lambda: (payload, "perspective-source")

        self.assertTrue(controller.paste_selection_from_clipboard())

        coords_3d = canvas.runtime_state.atom_coords_3d_state.atom_coords_3d
        self.assertEqual(set(coords_3d), {0, 1})
        self.assertEqual(coords_3d[0][2], -6.0)
        self.assertEqual(coords_3d[1][2], -3.0)
        self.assertEqual(rotation.projection_center_3d, (100.0, 100.0, 0.0))
        self.assertEqual(rotation.projection_anchor_2d, (100.0, 100.0))
        for atom_id, coords in coords_3d.items():
            projected_x, projected_y = project_point_3d_for(canvas, coords)
            atom = canvas.model.atoms[atom_id]
            self.assertAlmostEqual(projected_x, atom.x)
            self.assertAlmostEqual(projected_y, atom.y)

    def test_copy_selection_to_clipboard_returns_false_for_invalid_bounds(self) -> None:
        canvas = _RecordingFakeCanvas()
        controller = scene_clipboard_controller_for(canvas)
        item = _ZeroBoundsItem()
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        item.setData(0, "note")
        item.setData(9, {"kind": "note", "text": "flat", "x": 0.0, "y": 0.0})
        canvas.add_item(item, selected=True)
        controller.selection_payload_for_clipboard = lambda: {
            "format": "chemvas-selection",
            "version": 2,
            "scene_items": [{"kind": "note", "text": "flat", "x": 0.0, "y": 0.0}],
        }

        self.assertFalse(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)

    def test_copy_selection_to_clipboard_resets_paste_source_when_copy_has_no_selection_data(
        self,
    ) -> None:
        canvas = _RecordingFakeCanvas()
        canvas.scene_clipboard_state.paste_source_json = "stale-source"
        canvas.scene_clipboard_state.paste_count = 4
        controller = scene_clipboard_controller_for(canvas)
        item = _make_note_item("copy", 12.0, 14.0)
        canvas.add_item(item, selected=True)
        controller.selection_payload_for_clipboard = lambda: None

        self.assertTrue(controller.copy_selection_to_clipboard())
        self.assertIsNone(canvas.scene_clipboard_state.paste_source_json)
        self.assertEqual(canvas.scene_clipboard_state.paste_count, 0)
        mime_data = QApplication.clipboard().mimeData()
        self.assertTrue(mime_data.hasImage())
        self.assertFalse(mime_data.hasFormat(canvas.CLIPBOARD_SELECTION_MIME))
