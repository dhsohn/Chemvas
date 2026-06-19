import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPainterPath, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsScene,
        QGraphicsTextItem,
    )
except ModuleNotFoundError:
    QApplication = None

if QApplication is not None:
    from core.history import (
        UpdateAtomColorCommand,
        UpdateBondCommand,
    )
    from core.model import Atom, Bond, MoleculeModel
    from ui.atom_coords_access import CanvasAtomCoords3DState, atom_coords_3d_for
    from ui.atom_label_access import (
        add_or_update_atom_label,
        atom_item_for_id_for,
        clear_atom_label_for,
        prompt_atom_label_for,
    )
    from ui.benzene_preview_access import (
        clear_benzene_preview_for,
        render_benzene_preview_for,
    )
    from ui.canvas_atom_graphics_state import (
        atom_dots_for,
        atom_items_for,
        set_atom_dots_for,
        set_atom_items_for,
    )
    from ui.canvas_bond_graphics_state import bond_items_for, set_bond_items_for
    from ui.canvas_callback_state import CanvasCallbackState
    from ui.canvas_color_mutation_service import CanvasColorMutationService
    from ui.canvas_document_session_service import CanvasDocumentSessionService
    from ui.canvas_history_service import CanvasHistoryService
    from ui.canvas_history_state import CanvasHistoryState, history_state_for
    from ui.canvas_hover_refresh import refresh_hover_from_cursor_for
    from ui.canvas_insert_state import CanvasInsertState
    from ui.canvas_mark_registry import CanvasMarkRegistry
    from ui.canvas_note_controller import CanvasNoteController
    from ui.canvas_ring_fill_scene_access import (
        create_ring_fill_item_for,
        rotate_ring_fills_3d_for,
        rotate_ring_fills_for,
        update_ring_fills_for_atoms_for,
    )
    from ui.canvas_scene_items_state import (
        selected_notes_for,
        set_scene_item_collection_for,
    )
    from ui.canvas_scene_reset_access import clear_scene_for
    from ui.canvas_service_access import canvas_services_for
    from ui.canvas_smiles_input_state import CanvasSmilesInputState
    from ui.canvas_style_controller import CanvasStyleController
    from ui.canvas_text_style_state import (
        CanvasTextStyleState,
        set_text_style_for,
        text_style_state_for,
    )
    from ui.canvas_tool_mode_controller import CanvasToolModeController
    from ui.canvas_tool_settings_state import (
        CanvasToolSettingsState,
        tool_settings_state_for,
    )
    from ui.curved_arrow_path_service import CurvedArrowPathService
    from ui.handle_mutation_access import (
        set_curved_arrow_path_for,
        update_curved_control_for,
        update_curved_endpoint_for,
        update_orbital_rotate_for,
        update_orbital_scale_for,
    )
    from ui.handle_overlay_access import (
        clear_handles_for,
        show_curved_handles_for,
        show_orbital_handles_for,
    )
    from ui.history_canvas_access import (
        apply_atom_color_for_history,
        remove_atom_for_history,
        remove_bond_for_history,
        restore_atom_from_state_for_history,
        restore_bond_from_state_for_history,
        set_atom_positions_for_history,
        trim_bonds_for_history,
    )
    from ui.history_commands import UpdateSceneItemCommand
    from ui.history_recording_access import record_additions_for, record_bond_update_for
    from ui.hover_highlight_access import (
        add_hover_preview_items_for,
        clear_hover_highlight_for,
    )
    from ui.hover_interaction_access import (
        add_atom_hover_indicator_for,
        add_bond_hover_indicator_for,
        add_bond_style_hover_preview_for,
        add_bond_tool_hover_preview_for,
        add_mark_hover_preview_for,
        update_hover_highlight_for,
    )
    from ui.move_access import shift_selection_outlines_for
    from ui.note_item_access import update_note_box_for
    from ui.note_selection_box import update_note_selection_box_for
    from ui.pick_radius_access import atom_pick_radius_for
    from ui.scene_decoration_access import (
        add_arrow_for,
        add_mark_for,
        add_orbital_for,
        add_ts_bracket_for,
        preview_arrow_for,
        preview_ts_bracket_for,
    )
    from ui.scene_decoration_build_access import (
        add_arrow_head_for,
        build_arrow_item_for,
        build_orbital_items_for,
        build_ts_bracket_item_for,
        ts_bracket_path_for,
    )
    from ui.scene_item_access import (
        apply_scene_item_state,
        attach_scene_item,
        bond_ids_for_ring_item,
        create_scene_item_from_state,
        refresh_bond_geometry_for_ring_item,
        remove_scene_item,
        restore_arrow_from_state,
        restore_mark_from_state,
        restore_note_from_state,
        restore_orbital_from_state,
        restore_ring_from_state,
        restore_scene_item,
        restore_ts_bracket_from_state,
    )
    from ui.scene_item_state import atom_state_dict_for, scene_item_state_for
    from ui.selection_collection_access import (
        selected_chemical_ids_for,
        selected_ids_for,
        selected_items_for_transform_for,
        selection_items_for_copy_for,
    )
    from ui.selection_service_access import (
        clear_note_selection_for,
        refresh_selection_outline_for,
        select_note_for,
        toggle_note_selection_for,
    )
    from ui.selection_service_bundle import build_selection_services
    from ui.selection_style_state import SelectionStyleState
    from ui.structure_build_access import (
        add_benzene_template_for,
        add_structure_template_for,
        fuse_benzene_to_bond_for,
        fuse_chair_to_bond_for,
        fuse_regular_ring_to_bond_for,
        sprout_acetyl_from_atom_for,
        sprout_benzene_from_atom_for,
        sprout_bond_from_atom_for,
        sprout_regular_ring_from_atom_for,
    )
    from ui.structure_mutation_access import (
        add_atom_for,
        add_benzene_ring_for,
        add_bond_between_points_for,
        add_bond_for,
    )


def _selection_controller_for(view):
    services = getattr(view, "services", None)
    if services is None:
        services = SimpleNamespace()
        view.services = services
    graph_service = getattr(services, "canvas_graph_service", None)
    if graph_service is None:
        graph_service = SimpleNamespace(
            expand_connected_atoms=mock.Mock(return_value=set()),
            connected_components=lambda atom_ids: [set(atom_ids)] if atom_ids else [],
        )
        services.canvas_graph_service = graph_service
    return build_selection_services(view, graph_service=graph_service).selection_controller


def _color_service_for(view, *, graph_service=None):
    if graph_service is None:
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=(set(), set())))
    return CanvasColorMutationService(
        view,
        graph_service=graph_service,
        history_service=getattr(getattr(view, "services", None), "history_service", None),
    )


def _document_graph_service():
    return SimpleNamespace(rebuild_bond_adjacency=mock.Mock())


class _FakeCommand:
    def __init__(self) -> None:
        self.undo_calls = 0
        self.redo_calls = 0

    def undo(self, canvas) -> None:
        self.undo_calls += 1

    def redo(self, canvas) -> None:
        self.redo_calls += 1


class _FakeScene:
    def __init__(self, selected_items=None, items_at_pos=None) -> None:
        self._selected_items = list(selected_items or [])
        self._items_at_pos = list(items_at_pos or [])
        self.removed_items = []
        self.clear_selection_calls = 0
        self.focus_item = None

    def selectedItems(self):
        return list(self._selected_items)

    def items(self, *args, **kwargs):
        return list(self._items_at_pos)

    def clear(self) -> None:
        self._selected_items = []
        self._items_at_pos = []

    def clearSelection(self) -> None:
        self.clear_selection_calls += 1
        for item in self._selected_items:
            if hasattr(item, "setSelected"):
                item.setSelected(False)

    def removeItem(self, item) -> None:
        self.removed_items.append(item)

    def setFocusItem(self, item) -> None:
        self.focus_item = item


class _FakeItem:
    def __init__(
        self,
        kind,
        *,
        data1=None,
        data2=None,
        scene_token=None,
        children=None,
        polygon=None,
    ) -> None:
        self._data = {0: kind, 1: data1, 2: data2}
        self._scene_token = scene_token
        self._children = list(children or [])
        self._polygon = polygon
        self._selected = False

    def data(self, key):
        return self._data.get(key)

    def childItems(self):
        return list(self._children)

    def scene(self):
        return self._scene_token

    def polygon(self):
        return self._polygon

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isSelected(self) -> bool:
        return self._selected


@unittest.skipUnless(QApplication is not None, "PyQt6 is required for canvas view tests")
class CanvasViewAdditionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_history_stack_and_tool_selection_helpers(self) -> None:
        runtime_history = mock.Mock()
        runtime_view = SimpleNamespace(
            runtime_state=SimpleNamespace(history_service=runtime_history),
        )
        self.assertIs(runtime_view.runtime_state.history_service, runtime_history)

        first = _FakeCommand()
        second = _FakeCommand()
        third = _FakeCommand()
        history_view = SimpleNamespace(
            history_state=CanvasHistoryState(limit=2, redo_stack=["stale"]),
        )
        history_view.runtime_state = SimpleNamespace(
            history_service=CanvasHistoryService(history_view, history_state_for(history_view))
        )

        history_service = history_view.runtime_state.history_service
        history_service.push(first)
        history_service.push(second)
        history_state_for(history_view).redo_stack = ["stale"]
        history_service.push(third)

        self.assertEqual(history_state_for(history_view).history, [second, third])
        self.assertEqual(history_state_for(history_view).redo_stack, [])

        disabled_view = SimpleNamespace(
            history_state=CanvasHistoryState(enabled=False, limit=2, redo_stack=["redo"]),
        )
        disabled_view.runtime_state = SimpleNamespace(
            history_service=CanvasHistoryService(disabled_view, history_state_for(disabled_view))
        )
        disabled_view.runtime_state.history_service.push(first)
        self.assertEqual(history_state_for(disabled_view).history, [])
        self.assertEqual(history_state_for(disabled_view).redo_stack, ["redo"])

        undo_redo_view = SimpleNamespace(history_state=CanvasHistoryState(history=[first]))
        undo_redo_view.runtime_state = SimpleNamespace(
            history_service=CanvasHistoryService(undo_redo_view, history_state_for(undo_redo_view))
        )
        undo_redo_history = undo_redo_view.runtime_state.history_service
        undo_redo_history.undo()
        self.assertEqual(first.undo_calls, 1)
        self.assertEqual(history_state_for(undo_redo_view).history, [])
        self.assertEqual(history_state_for(undo_redo_view).redo_stack, [first])

        undo_redo_history.redo()
        self.assertEqual(first.redo_calls, 1)
        self.assertEqual(history_state_for(undo_redo_view).history, [first])
        self.assertEqual(history_state_for(undo_redo_view).redo_stack, [])

        failing_undo = _FakeCommand()
        failing_undo.undo = mock.Mock(side_effect=RuntimeError("undo failed"))
        failing_undo_view = SimpleNamespace(history_state=CanvasHistoryState(history=[failing_undo]))
        failing_undo_history = CanvasHistoryService(
            failing_undo_view,
            history_state_for(failing_undo_view),
        )
        with self.assertRaisesRegex(RuntimeError, "undo failed"):
            failing_undo_history.undo()
        self.assertEqual(history_state_for(failing_undo_view).history, [failing_undo])
        self.assertEqual(history_state_for(failing_undo_view).redo_stack, [])

        failing_redo = _FakeCommand()
        failing_redo.redo = mock.Mock(side_effect=RuntimeError("redo failed"))
        failing_redo_view = SimpleNamespace(history_state=CanvasHistoryState(redo_stack=[failing_redo]))
        failing_redo_history = CanvasHistoryService(
            failing_redo_view,
            history_state_for(failing_redo_view),
        )
        with self.assertRaisesRegex(RuntimeError, "redo failed"):
            failing_redo_history.redo()
        self.assertEqual(history_state_for(failing_redo_view).history, [])
        self.assertEqual(history_state_for(failing_redo_view).redo_stack, [failing_redo])

        noop_view = SimpleNamespace(history_state=CanvasHistoryState())
        noop_view.runtime_state = SimpleNamespace(
            history_service=CanvasHistoryService(noop_view, history_state_for(noop_view))
        )
        noop_history = noop_view.runtime_state.history_service
        noop_history.undo()
        noop_history.redo()

        tool_view = SimpleNamespace(
            insert_state=SimpleNamespace(template_active=True, smiles_active=True),
            services=SimpleNamespace(
                tools=SimpleNamespace(set_active=mock.Mock()),
                insert_controller=SimpleNamespace(
                    cancel_template_insert=mock.Mock(),
                    cancel_smiles_insert=mock.Mock(),
                ),
                hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            ),
            refresh_selection_outline=mock.Mock(),
            callback_state=CanvasCallbackState(tool_change=mock.Mock()),
            tool_settings_state=CanvasToolSettingsState(mark_kind="plus"),
        )
        tool_view.services.selection_controller = SimpleNamespace(
            update_selection_outline=tool_view.refresh_selection_outline
        )
        tool_view.services.tool_mode_controller = CanvasToolModeController(
            tool_view,
            insert_controller=tool_view.services.insert_controller,
            hover_refresh=tool_view.services.hover_scene_service.clear_hover_highlight,
            set_active_tool=tool_view.services.tools.set_active,
        )
        canvas_services_for(tool_view).tool_mode_controller.set_tool("bond")
        canvas_services_for(tool_view).tool_mode_controller.set_mark_kind("minus")
        canvas_services_for(tool_view).tool_mode_controller.set_mark_kind("circled_plus")
        canvas_services_for(tool_view).tool_mode_controller.set_mark_kind("unsupported")

        tool_view.services.tools.set_active.assert_any_call("bond")
        tool_view.services.tools.set_active.assert_any_call("mark")
        self.assertEqual(tool_view.services.insert_controller.cancel_template_insert.call_count, 3)
        self.assertEqual(tool_view.services.insert_controller.cancel_smiles_insert.call_count, 3)
        self.assertEqual(tool_settings_state_for(tool_view).mark_kind, "circled_plus")
        self.assertEqual(tool_view.refresh_selection_outline.call_count, 3)
        self.assertEqual(tool_view.callback_state.tool_change.call_count, 3)
        self.assertEqual(tool_view.services.hover_scene_service.clear_hover_highlight.call_count, 3)

    def test_document_session_wrappers_delegate_to_service(self) -> None:
        document_session_service = mock.Mock()
        state = {"model": {"atoms": []}}
        document_session_service.snapshot_state.return_value = state
        view = SimpleNamespace(services=SimpleNamespace(canvas_document_session_service=document_session_service))

        self.assertEqual(canvas_services_for(view).canvas_document_session_service.snapshot_state(), state)
        canvas_services_for(view).canvas_document_session_service.restore_state(state)
        canvas_services_for(view).canvas_document_session_service.save_to_file("/tmp/example.chemvas")
        canvas_services_for(view).canvas_document_session_service.load_from_file("/tmp/example.chemvas")

        document_session_service.snapshot_state.assert_called_once_with()
        document_session_service.restore_state.assert_called_once_with(state)
        document_session_service.save_to_file.assert_called_once_with("/tmp/example.chemvas")
        document_session_service.load_from_file.assert_called_once_with("/tmp/example.chemvas")

    def test_service_and_scene_item_wrappers_delegate(self) -> None:
        scene_item_controller = mock.Mock()
        structure_insert_service = mock.Mock()
        selection_rotation_controller = mock.Mock()
        atom_label_service = mock.Mock()
        model = object()
        structure_insert_service.insert_structure_model.return_value = ({1}, {2})
        selection_rotation_controller.begin_selection_3d_rotation.return_value = True
        scene_item_controller.restore_ring_from_state.return_value = "ring"
        scene_item_controller.restore_note_from_state.return_value = "note"
        scene_item_controller.restore_mark_from_state.return_value = "mark"
        scene_item_controller.restore_arrow_from_state.return_value = "arrow"
        scene_item_controller.restore_ts_bracket_from_state.return_value = "ts"
        scene_item_controller.restore_orbital_from_state.return_value = "orbital"
        scene_item_controller.create_scene_item_from_state.return_value = "item"
        scene_item_controller.bond_ids_for_ring_item.return_value = {9}

        view = SimpleNamespace(
            services=SimpleNamespace(
                structure_insert_service=structure_insert_service,
                selection_rotation_controller=selection_rotation_controller,
                atom_label_service=atom_label_service,
                scene_item_controller=scene_item_controller,
                scene_decoration_build_service=SimpleNamespace(mark_center=lambda item: QPointF(1.0, 2.0)),
            ),
        )

        result = canvas_services_for(view).structure_insert_service.insert_structure_model(
            model,
            center=QPointF(3.0, 4.0),
            title="Inserted",
        )
        self.assertEqual(result, ({1}, {2}))
        self.assertEqual(scene_item_state_for(view, None), {})
        self.assertEqual(restore_ring_from_state(view, {"kind": "ring"}), "ring")
        self.assertEqual(restore_note_from_state(view, {"kind": "note"}), "note")
        self.assertEqual(restore_mark_from_state(view, {"kind": "mark"}), "mark")
        self.assertEqual(restore_arrow_from_state(view, {"kind": "arrow"}), "arrow")
        self.assertEqual(restore_ts_bracket_from_state(view, {"kind": "ts"}), "ts")
        self.assertEqual(restore_orbital_from_state(view, {"kind": "orbital"}), "orbital")
        self.assertEqual(create_scene_item_from_state(view, {"kind": "note"}), "item")
        self.assertEqual(bond_ids_for_ring_item(view, "ring-item"), {9})
        refresh_bond_geometry_for_ring_item(view, "ring-item")
        attach_scene_item(view, "attached-item")
        restore_scene_item(view, "scene-item")
        remove_scene_item(view, "scene-item")
        apply_scene_item_state(view, "scene-item", {"kind": "note"})

        self.assertTrue(
            view.services.selection_rotation_controller.begin_selection_3d_rotation(
                axis_hint=7,
                press_pos=QPointF(1.0, 2.0),
            )
        )
        view.services.selection_rotation_controller.update_selection_3d_rotation(3.0, -4.0)
        view.services.selection_rotation_controller.end_selection_3d_rotation()
        self.assertEqual(atom_label_service.merge_overlapping_atoms(3), atom_label_service.merge_overlapping_atoms.return_value)
        add_or_update_atom_label(
            view,
            5,
            "N",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )

        structure_insert_service.insert_structure_model.assert_called_once_with(
            model,
            center=QPointF(3.0, 4.0),
            title="Inserted",
        )
        selection_rotation_controller.begin_selection_3d_rotation.assert_called_once_with(
            axis_hint=7,
            press_pos=QPointF(1.0, 2.0),
        )
        selection_rotation_controller.update_selection_3d_rotation.assert_called_once_with(3.0, -4.0)
        selection_rotation_controller.end_selection_3d_rotation.assert_called_once_with()
        atom_label_service.merge_overlapping_atoms.assert_called_once_with(3)
        atom_label_service.add_or_update_atom_label.assert_called_once_with(
            5,
            "N",
            clear_smiles=False,
            record=False,
            allow_merge=False,
            show_carbon=True,
        )
        scene_item_controller.refresh_bond_geometry_for_ring_item.assert_called_once_with("ring-item")
        scene_item_controller.attach_scene_item.assert_called_once_with("attached-item")
        scene_item_controller.restore_scene_item.assert_called_once_with("scene-item")
        scene_item_controller.remove_scene_item.assert_called_once_with("scene-item")
        scene_item_controller.apply_scene_item_state.assert_called_once_with("scene-item", {"kind": "note"})

    def test_atom_label_access_delegates_clear_and_prompt_to_atom_label_service(self) -> None:
        atom_label_service = mock.Mock()
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0, explicit_label=False),
                    2: Atom("O", 1.0, 0.0, explicit_label=True),
                }
            ),
            services=SimpleNamespace(atom_label_service=atom_label_service),
        )

        clear_atom_label_for(view, 1)
        clear_atom_label_for(view, 99)
        prompt_atom_label_for(view, 2)

        atom_label_service.add_or_update_atom_label.assert_called_once_with(1, "C", show_carbon=False)
        atom_label_service.prompt_atom_label.assert_called_once_with(2)

    def test_refresh_hover_from_cursor_and_export_xyz_cover_guard_and_error_paths(self) -> None:
        refresh_hover_from_cursor_for(SimpleNamespace())

        template_view = SimpleNamespace(
            insert_state=CanvasInsertState(template_active=True),
            services=SimpleNamespace(
                tools=object(),
                hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            ),
        )
        refresh_hover_from_cursor_for(
            template_view,
            clear_hover_highlight=template_view.services.hover_scene_service.clear_hover_highlight,
        )
        template_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

        viewport = SimpleNamespace(
            mapFromGlobal=mock.Mock(return_value=QPointF(4.0, 5.0)),
            rect=lambda: SimpleNamespace(contains=lambda _pos: True),
        )
        inside_view = SimpleNamespace(
            insert_state=CanvasInsertState(),
            viewport=lambda: viewport,
            mapToScene=mock.Mock(return_value=QPointF(7.0, 8.0)),
            services=SimpleNamespace(
                tools=object(),
                hover_interaction_service=SimpleNamespace(update_hover_highlight=mock.Mock()),
                hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            ),
        )
        with mock.patch("ui.canvas_hover_refresh.QCursor.pos", return_value=QPointF(1.0, 2.0)):
            refresh_hover_from_cursor_for(
                inside_view,
                update_hover_highlight=inside_view.services.hover_interaction_service.update_hover_highlight,
                clear_hover_highlight=inside_view.services.hover_scene_service.clear_hover_highlight,
            )
        inside_view.services.hover_interaction_service.update_hover_highlight.assert_called_once_with(QPointF(7.0, 8.0))
        inside_view.services.hover_scene_service.clear_hover_highlight.assert_not_called()

        outside_view = SimpleNamespace(
            insert_state=CanvasInsertState(),
            viewport=lambda: SimpleNamespace(
                mapFromGlobal=mock.Mock(return_value=QPointF(9.0, 10.0)),
                rect=lambda: SimpleNamespace(contains=lambda _pos: False),
            ),
            mapToScene=mock.Mock(),
            services=SimpleNamespace(
                tools=object(),
                hover_interaction_service=SimpleNamespace(update_hover_highlight=mock.Mock()),
                hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            ),
        )
        with mock.patch("ui.canvas_hover_refresh.QCursor.pos", return_value=QPointF(3.0, 4.0)):
            refresh_hover_from_cursor_for(
                outside_view,
                update_hover_highlight=outside_view.services.hover_interaction_service.update_hover_highlight,
                clear_hover_highlight=outside_view.services.hover_scene_service.clear_hover_highlight,
            )
        outside_view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()
        outside_view.services.hover_interaction_service.update_hover_highlight.assert_not_called()

        error_model = MoleculeModel()
        error_model.add_atom("C", 0.0, 0.0)
        error_view = SimpleNamespace(
            model=error_model,
            scene=lambda: SimpleNamespace(selectedItems=lambda: []),
            rdkit=SimpleNamespace(
                model_to_xyz_block=mock.Mock(return_value=None),
                last_error="RDKit export failed",
            ),
            services=SimpleNamespace(history_service=SimpleNamespace(push=mock.Mock())),
        )
        with self.assertRaisesRegex(ValueError, "RDKit export failed"):
            CanvasDocumentSessionService(
                error_view,
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
                graph_service=_document_graph_service(),
            ).export_xyz("/tmp/unused.xyz")

        error_view.rdkit.last_error = None
        with self.assertRaisesRegex(ValueError, "Failed to export 3D XYZ."):
            CanvasDocumentSessionService(
                error_view,
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
                graph_service=_document_graph_service(),
            ).export_xyz("/tmp/unused.xyz")

    def test_tool_change_callback_runs_from_tool_mode_controller(self) -> None:
        callback = mock.Mock()
        view = SimpleNamespace(
            insert_state=SimpleNamespace(template_active=True, smiles_active=False),
            services=SimpleNamespace(
                tools=SimpleNamespace(set_active=mock.Mock()),
                insert_controller=SimpleNamespace(
                    cancel_template_insert=mock.Mock(),
                    cancel_smiles_insert=mock.Mock(),
                ),
                hover_scene_service=SimpleNamespace(clear_hover_highlight=mock.Mock()),
            ),
            refresh_selection_outline=mock.Mock(),
            callback_state=CanvasCallbackState(tool_change=callback),
        )
        view.services.tool_mode_controller = CanvasToolModeController(
            view,
            insert_controller=view.services.insert_controller,
            hover_refresh=view.services.hover_scene_service.clear_hover_highlight,
            set_active_tool=view.services.tools.set_active,
        )

        canvas_services_for(view).tool_mode_controller.set_tool("bond")

        callback.assert_called_once_with()
        view.services.hover_scene_service.clear_hover_highlight.assert_called_once_with()

    def test_structure_build_wrappers_delegate(self) -> None:
        structure_build_service = mock.Mock()
        structure_build_service.add_bond_between_points.return_value = (8, 9)
        structure_build_service.benzene_ring_points.return_value = ([QPointF(6.0, 7.0)], [(1, 0.0, 0.0)])
        view = SimpleNamespace(
            services=SimpleNamespace(structure_build_service=structure_build_service),
            tool_settings_state=CanvasToolSettingsState(
                active_bond_style="double",
                active_bond_order=2,
            ),
        )

        add_bond_between_points_for(view, QPointF(0.0, 0.0), QPointF(1.0, 0.0))
        self.assertEqual(
            structure_build_service.benzene_ring_points(QPointF(2.0, 3.0), attach_atom_id=1, attach_bond_id=2),
            ([QPointF(6.0, 7.0)], [(1, 0.0, 0.0)]),
        )
        sprout_bond_from_atom_for(view, 4, style="double", order=2, cyclic=True)
        sprout_benzene_from_atom_for(view, 6)
        sprout_acetyl_from_atom_for(view, 8)
        sprout_regular_ring_from_atom_for(view, 5, 6)
        fuse_benzene_to_bond_for(view, 3)
        fuse_regular_ring_to_bond_for(view, 7, 5)
        fuse_chair_to_bond_for(view, 9, mirrored=True)
        add_benzene_ring_for(view, QPointF(3.0, 4.0), attach_atom_id=1, attach_bond_id=2, before_smiles_input="before")

        structure_build_service.add_bond_between_points.assert_called_once_with(
            QPointF(0.0, 0.0),
            QPointF(1.0, 0.0),
            "double",
            2,
        )
        structure_build_service.benzene_ring_points.assert_called_once_with(
            QPointF(2.0, 3.0),
            attach_atom_id=1,
            attach_bond_id=2,
        )
        structure_build_service.sprout_bond_from_atom.assert_called_once_with(4, style="double", order=2, cyclic=True)
        structure_build_service.sprout_benzene_from_atom.assert_called_once_with(6)
        structure_build_service.sprout_acetyl_from_atom.assert_called_once_with(8)
        structure_build_service.sprout_regular_ring_from_atom.assert_called_once_with(5, 6)
        structure_build_service.fuse_benzene_to_bond.assert_called_once_with(3)
        structure_build_service.fuse_regular_ring_to_bond.assert_called_once_with(7, 5)
        structure_build_service.fuse_chair_to_bond.assert_called_once_with(9, mirrored=True)
        structure_build_service.add_benzene_ring.assert_called_once_with(
            QPointF(3.0, 4.0),
            attach_atom_id=1,
            attach_bond_id=2,
            before_smiles_input="before",
        )

    def test_benzene_preview_access_helpers_delegate_to_service(self) -> None:
        benzene_preview_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(benzene_preview_service=benzene_preview_service))

        clear_benzene_preview_for(view)
        render_benzene_preview_for(view, QPointF(2.0, 3.0), attach_atom_id=1, attach_bond_id=2)

        benzene_preview_service.clear_preview.assert_called_once_with()
        benzene_preview_service.render_preview.assert_called_once_with(
            QPointF(2.0, 3.0),
            attach_atom_id=1,
            attach_bond_id=2,
        )

    def test_benzene_preview_access_uses_service_only(self) -> None:
        benzene_preview_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(benzene_preview_service=benzene_preview_service))

        clear_benzene_preview_for(view)
        render_benzene_preview_for(view, QPointF(2.0, 3.0), attach_atom_id=1, attach_bond_id=2)

        benzene_preview_service.clear_preview.assert_called_once_with()
        benzene_preview_service.render_preview.assert_called_once_with(
            QPointF(2.0, 3.0),
            attach_atom_id=1,
            attach_bond_id=2,
        )

    def test_bond_hover_preview_wrappers_delegate(self) -> None:
        bond_hover_preview_service = mock.Mock()
        bond = object()
        view = SimpleNamespace(services=SimpleNamespace(bond_hover_preview_service=bond_hover_preview_service))

        add_bond_style_hover_preview_for(view, bond)
        add_bond_tool_hover_preview_for(view, 3, QPointF(4.0, 5.0))

        bond_hover_preview_service.add_bond_style_hover_preview.assert_called_once_with(bond)
        bond_hover_preview_service.add_bond_tool_hover_preview.assert_called_once_with(3, QPointF(4.0, 5.0))

    def test_mark_hover_preview_wrapper_delegates(self) -> None:
        mark_hover_preview_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(mark_hover_preview_service=mark_hover_preview_service))

        add_mark_hover_preview_for(view, QPointF(6.0, 7.0))

        mark_hover_preview_service.add_mark_hover_preview.assert_called_once_with(QPointF(6.0, 7.0))

    def test_hover_scene_wrappers_delegate(self) -> None:
        hover_scene_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(hover_scene_service=hover_scene_service))

        clear_hover_highlight_for(view)
        add_atom_hover_indicator_for(view, 3)
        add_bond_hover_indicator_for(view, 4)
        add_hover_preview_items_for(view, ["preview"])

        hover_scene_service.clear_hover_highlight.assert_called_once_with()
        hover_scene_service.add_atom_hover_indicator.assert_called_once_with(3)
        hover_scene_service.add_bond_hover_indicator.assert_called_once_with(4)
        hover_scene_service.add_hover_preview_items.assert_called_once_with(["preview"])

    def test_hover_interaction_wrapper_delegates(self) -> None:
        hover_interaction_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(hover_interaction_service=hover_interaction_service))

        update_hover_highlight_for(view, QPointF(8.0, 9.0))

        hover_interaction_service.update_hover_highlight.assert_called_once_with(QPointF(8.0, 9.0))

    def test_hover_interaction_wrappers_prefer_services_over_legacy_fallbacks(self) -> None:
        hover_scene_service = mock.Mock()
        mark_hover_preview_service = mock.Mock()
        bond_hover_preview_service = mock.Mock()
        hover_interaction_service = mock.Mock()
        view = SimpleNamespace(
            services=SimpleNamespace(
                hover_scene_service=hover_scene_service,
                mark_hover_preview_service=mark_hover_preview_service,
                bond_hover_preview_service=bond_hover_preview_service,
                hover_interaction_service=hover_interaction_service,
            ),
        )
        bond = object()

        add_atom_hover_indicator_for(view, 3)
        add_bond_hover_indicator_for(view, 4)
        add_mark_hover_preview_for(view, QPointF(5.0, 6.0))
        add_bond_tool_hover_preview_for(view, 7, QPointF(8.0, 9.0))
        add_bond_style_hover_preview_for(view, bond)
        update_hover_highlight_for(view, QPointF(10.0, 11.0))

        hover_scene_service.add_atom_hover_indicator.assert_called_once_with(3)
        hover_scene_service.add_bond_hover_indicator.assert_called_once_with(4)
        mark_hover_preview_service.add_mark_hover_preview.assert_called_once_with(QPointF(5.0, 6.0))
        bond_hover_preview_service.add_bond_tool_hover_preview.assert_called_once_with(7, QPointF(8.0, 9.0))
        bond_hover_preview_service.add_bond_style_hover_preview.assert_called_once_with(bond)
        hover_interaction_service.update_hover_highlight.assert_called_once_with(QPointF(10.0, 11.0))

    def test_selection_controller_public_api_delegates(self) -> None:
        selection_controller = mock.Mock()
        hit = SimpleNamespace(kind="atom", id=7)
        item = object()
        view = SimpleNamespace(services=SimpleNamespace(selection_controller=selection_controller))

        selection_controller.structure_hit_from_item.return_value = (hit, (1, 2), [3, 4])
        selection_controller.structure_item_for_hit.return_value = "item"

        self.assertEqual(selection_controller.structure_hit_from_item(item), (hit, (1, 2), [3, 4]))
        self.assertEqual(selection_controller.structure_item_for_hit(hit), "item")
        select_note_for(view, item, additive=True)
        toggle_note_selection_for(view, item)
        clear_note_selection_for(view)
        update_note_selection_box_for(view, item)
        refresh_selection_outline_for(view)
        shift_selection_outlines_for(view, 1.5, -2.0)

        selection_controller.structure_hit_from_item.assert_called_once_with(item)
        selection_controller.structure_item_for_hit.assert_called_once_with(hit)
        selection_controller.select_note.assert_called_once_with(item, additive=True)
        selection_controller.toggle_note_selection.assert_called_once_with(item)
        selection_controller.clear_note_selection.assert_called_once_with()
        selection_controller.update_note_selection_box.assert_called_once_with(item)
        selection_controller.update_selection_outline.assert_called_once_with()
        selection_controller.shift_selection_outlines.assert_called_once_with(1.5, -2.0)

    def test_handle_overlay_access_delegates(self) -> None:
        handle_overlay_service = mock.Mock()
        item = object()
        view = SimpleNamespace(services=SimpleNamespace(handle_overlay_service=handle_overlay_service))

        clear_handles_for(view)
        show_orbital_handles_for(view, item)
        show_curved_handles_for(view, item)

        handle_overlay_service.clear_handles.assert_called_once_with()
        handle_overlay_service.show_orbital_handles.assert_called_once_with(item)
        handle_overlay_service.show_curved_handles.assert_called_once_with(item)

    def test_handle_mutation_access_delegates_to_service(self) -> None:
        mutation_service = mock.Mock()
        item = object()
        view = SimpleNamespace(services=SimpleNamespace(handle_mutation_service=mutation_service))

        update_orbital_scale_for(view, item, QPointF(3.0, 4.0))
        update_orbital_rotate_for(view, item, QPointF(5.0, 6.0))
        update_curved_control_for(view, item, QPointF(7.0, 8.0))
        update_curved_endpoint_for(view, item, QPointF(9.0, 10.0), "start")

        mutation_service.update_orbital_scale.assert_called_once_with(item, QPointF(3.0, 4.0))
        mutation_service.update_orbital_rotate.assert_called_once_with(item, QPointF(5.0, 6.0))
        mutation_service.update_curved_control.assert_called_once_with(item, QPointF(7.0, 8.0))
        mutation_service.update_curved_endpoint.assert_called_once_with(item, QPointF(9.0, 10.0), "start")

    def test_handle_mutation_access_prefers_service_over_legacy_fallbacks(self) -> None:
        mutation_service = mock.Mock()
        item = object()
        view = SimpleNamespace(services=SimpleNamespace(handle_mutation_service=mutation_service))

        update_orbital_scale_for(view, item, QPointF(3.0, 4.0))
        update_orbital_rotate_for(view, item, QPointF(5.0, 6.0))
        update_curved_control_for(view, item, QPointF(7.0, 8.0))
        update_curved_endpoint_for(view, item, QPointF(9.0, 10.0), "start")

        mutation_service.update_orbital_scale.assert_called_once_with(item, QPointF(3.0, 4.0))
        mutation_service.update_orbital_rotate.assert_called_once_with(item, QPointF(5.0, 6.0))
        mutation_service.update_curved_control.assert_called_once_with(item, QPointF(7.0, 8.0))
        mutation_service.update_curved_endpoint.assert_called_once_with(item, QPointF(9.0, 10.0), "start")

    def test_curved_arrow_path_wrapper_delegates(self) -> None:
        curved_arrow_path_service = mock.Mock()
        item = object()
        view = SimpleNamespace(services=SimpleNamespace(curved_arrow_path_service=curved_arrow_path_service))

        set_curved_arrow_path_for(
            view,
            item,
            start=QPointF(0.0, 0.0),
            end=QPointF(10.0, 0.0),
            control=QPointF(5.0, 4.0),
            double=False,
        )

        curved_arrow_path_service.set_curved_arrow_path.assert_called_once_with(
            item,
            QPointF(0.0, 0.0),
            QPointF(10.0, 0.0),
            QPointF(5.0, 4.0),
            False,
        )

    def test_scene_decoration_wrappers_delegate(self) -> None:
        decoration_service = mock.Mock()
        decoration_service.add_mark.return_value = "mark"
        decoration_service.add_arrow.return_value = "arrow"
        decoration_service.add_ts_bracket.return_value = "ts"
        decoration_service.add_orbital.return_value = "orbital"
        view = SimpleNamespace(services=SimpleNamespace(scene_decoration_service=decoration_service))

        self.assertEqual(
            add_mark_for(
                view,
                QPointF(1.0, 2.0),
                kind="plus",
                atom_id=5,
                offset=QPointF(0.5, -0.5),
                record=False,
            ),
            "mark",
        )
        self.assertEqual(
            add_arrow_for(view, QPointF(0.0, 0.0), QPointF(4.0, 5.0), "reaction"),
            "arrow",
        )
        self.assertEqual(
            add_ts_bracket_for(view, QRectF(QPointF(0.0, 0.0), QPointF(3.0, 6.0))),
            "ts",
        )
        self.assertEqual(add_orbital_for(view, QPointF(9.0, 8.0)), "orbital")

        decoration_service.add_mark.assert_called_once_with(
            QPointF(1.0, 2.0),
            kind="plus",
            atom_id=5,
            offset=QPointF(0.5, -0.5),
            record=False,
        )
        decoration_service.add_arrow.assert_called_once_with(
            QPointF(0.0, 0.0),
            QPointF(4.0, 5.0),
            "reaction",
        )
        decoration_service.add_ts_bracket.assert_called_once_with(
            QRectF(QPointF(0.0, 0.0), QPointF(3.0, 6.0)),
        )
        decoration_service.add_orbital.assert_called_once_with(QPointF(9.0, 8.0))

    def test_scene_decoration_build_wrappers_delegate(self) -> None:
        build_service = mock.Mock()
        arrow_item = object()
        ts_item = object()
        orbital_items = [object()]
        path = QPainterPath()
        rect = QRectF(1.0, 2.0, 3.0, 4.0)
        view = SimpleNamespace(services=SimpleNamespace(scene_decoration_build_service=build_service))

        build_service.preview_arrow.return_value = arrow_item
        build_service.build_arrow_item.return_value = arrow_item
        build_service.build_single_head_arrow.return_value = arrow_item
        build_service.build_double_head_arrow.return_value = arrow_item
        build_service.build_dotted_arrow.return_value = arrow_item
        build_service.build_curved_arrow.return_value = arrow_item
        build_service.build_inhibition_arrow.return_value = arrow_item
        build_service.build_equilibrium_item.return_value = arrow_item
        build_service.ts_bracket_rect_from_points.return_value = rect
        build_service.ts_bracket_stroke_width.return_value = 2.5
        build_service.ts_bracket_path.return_value = path
        build_service.build_ts_bracket_item.return_value = ts_item
        build_service.preview_ts_bracket.return_value = ts_item
        build_service.build_orbital_items.return_value = orbital_items

        self.assertIs(preview_arrow_for(view, QPointF(1.0, 2.0), QPointF(3.0, 4.0), "reaction"), arrow_item)
        self.assertIs(build_arrow_item_for(view, QPointF(5.0, 6.0), QPointF(7.0, 8.0), "dotted"), arrow_item)
        self.assertIs(build_service.build_single_head_arrow(QPointF(9.0, 10.0), QPointF(11.0, 12.0)), arrow_item)
        self.assertIs(build_service.build_double_head_arrow(QPointF(13.0, 14.0), QPointF(15.0, 16.0)), arrow_item)
        self.assertIs(build_service.build_dotted_arrow(QPointF(17.0, 18.0), QPointF(19.0, 20.0)), arrow_item)
        self.assertIs(build_service.build_curved_arrow(QPointF(21.0, 22.0), QPointF(23.0, 24.0), True), arrow_item)
        self.assertIs(build_service.build_inhibition_arrow(QPointF(25.0, 26.0), QPointF(27.0, 28.0)), arrow_item)
        self.assertIs(build_service.build_equilibrium_item(QPointF(29.0, 30.0), QPointF(31.0, 32.0)), arrow_item)
        add_arrow_head_for(view, path, QPointF(33.0, 34.0), QPointF(35.0, 36.0), False)
        self.assertEqual(build_service.ts_bracket_rect_from_points(QPointF(37.0, 38.0), QPointF(39.0, 40.0)), rect)
        self.assertEqual(build_service.ts_bracket_stroke_width(), 2.5)
        self.assertEqual(ts_bracket_path_for(view, rect), path)
        self.assertIs(build_ts_bracket_item_for(view, rect), ts_item)
        self.assertIs(preview_ts_bracket_for(view, QPointF(41.0, 42.0), QPointF(43.0, 44.0)), ts_item)
        self.assertEqual(build_orbital_items_for(view, QPointF(45.0, 46.0), "sp2"), orbital_items)

        build_service.preview_arrow.assert_called_once_with(QPointF(1.0, 2.0), QPointF(3.0, 4.0), "reaction")
        build_service.build_arrow_item.assert_called_once_with(QPointF(5.0, 6.0), QPointF(7.0, 8.0), "dotted")
        build_service.build_single_head_arrow.assert_called_once_with(QPointF(9.0, 10.0), QPointF(11.0, 12.0))
        build_service.build_double_head_arrow.assert_called_once_with(QPointF(13.0, 14.0), QPointF(15.0, 16.0))
        build_service.build_dotted_arrow.assert_called_once_with(QPointF(17.0, 18.0), QPointF(19.0, 20.0))
        build_service.build_curved_arrow.assert_called_once_with(QPointF(21.0, 22.0), QPointF(23.0, 24.0), True)
        build_service.build_inhibition_arrow.assert_called_once_with(QPointF(25.0, 26.0), QPointF(27.0, 28.0))
        build_service.build_equilibrium_item.assert_called_once_with(QPointF(29.0, 30.0), QPointF(31.0, 32.0))
        build_service.add_arrow_head.assert_called_once_with(path, QPointF(33.0, 34.0), QPointF(35.0, 36.0), False)
        build_service.ts_bracket_rect_from_points.assert_called_once_with(QPointF(37.0, 38.0), QPointF(39.0, 40.0))
        build_service.ts_bracket_stroke_width.assert_called_once_with()
        build_service.ts_bracket_path.assert_called_once_with(rect)
        build_service.build_ts_bracket_item.assert_called_once_with(rect)
        build_service.preview_ts_bracket.assert_called_once_with(QPointF(41.0, 42.0), QPointF(43.0, 44.0))
        build_service.build_orbital_items.assert_called_once_with(QPointF(45.0, 46.0), "sp2")

    def test_fragment_template_access_uses_recorded_build_helper(self) -> None:
        template_builder = SimpleNamespace(
            add_regular_ring_template=mock.Mock(),
            add_hetero_ring_template=mock.Mock(),
            add_fused_benzenes=mock.Mock(),
            add_crown_ether=mock.Mock(),
        )
        structure_build_service = SimpleNamespace(
            run_recorded_build=mock.Mock(side_effect=lambda action, **kwargs: action()),
            template_builder=template_builder,
        )
        view = SimpleNamespace(services=SimpleNamespace(structure_build_service=structure_build_service))

        for template_key in (
            "cyclopropane",
            "cyclobutane",
            "cyclopentane",
            "pyridine",
            "pyrimidine",
            "imidazole",
            "pyrrole",
            "furan",
            "thiophene",
            "naphthalene",
            "anthracene",
            "phenanthrene",
            "pyranose",
            "furanose",
            "crown_12_4",
            "crown_15_5",
            "crown_18_6",
        ):
            add_structure_template_for(view, template_key)

        self.assertEqual(structure_build_service.run_recorded_build.call_count, 17)
        self.assertEqual(
            template_builder.add_regular_ring_template.call_args_list,
            [mock.call(3), mock.call(4), mock.call(5)],
        )
        self.assertEqual(
            template_builder.add_hetero_ring_template.call_args_list,
            [
                mock.call(6, ["C", "C", "C", "C", "C", "N"]),
                mock.call(6, ["N", "C", "N", "C", "C", "C"]),
                mock.call(5, ["C", "N", "C", "N", "C"]),
                mock.call(5, ["N", "C", "C", "C", "C"]),
                mock.call(5, ["O", "C", "C", "C", "C"]),
                mock.call(5, ["S", "C", "C", "C", "C"]),
                mock.call(6, ["O", "C", "C", "C", "C", "C"]),
                mock.call(5, ["O", "C", "C", "C", "C"]),
            ],
        )
        self.assertEqual(
            template_builder.add_fused_benzenes.call_args_list,
            [mock.call(2, mode="linear"), mock.call(3, mode="linear"), mock.call(3, mode="angled")],
        )
        self.assertEqual(
            template_builder.add_crown_ether.call_args_list,
            [mock.call(12, 4), mock.call(15, 5), mock.call(18, 6)],
        )

    def test_add_benzene_template_uses_viewport_scene_center(self) -> None:
        center = QPointF(12.0, 13.0)
        structure_build_service = mock.Mock()
        view = SimpleNamespace(
            services=SimpleNamespace(structure_build_service=structure_build_service),
            viewport=lambda: SimpleNamespace(rect=lambda: SimpleNamespace(center=lambda: QPointF(2.0, 3.0))),
            mapToScene=mock.Mock(return_value=center),
        )

        add_benzene_template_for(view)

        view.mapToScene.assert_called_once()
        structure_build_service.add_benzene_ring.assert_called_once_with(center)

    def test_service_backed_fragment_template_access_delegates(self) -> None:
        structure_build_service = mock.Mock()
        template_builder = structure_build_service.template_builder
        view = SimpleNamespace(services=SimpleNamespace(structure_build_service=structure_build_service))

        for template_key in (
            "cyclohexane_chair",
            "cyclohexane_boat",
            "indole",
            "quinoline",
            "isoquinoline",
            "benzimidazole",
            "phenyl",
            "benzyl",
            "vinyl",
            "allyl",
            "carboxyl",
            "nitro",
            "sulfonyl",
            "carbonyl",
            "tbu",
            "ipr",
            "me",
            "et",
            "peptide_2",
        ):
            add_structure_template_for(view, template_key)

        for method_name in (
            "add_cyclohexane_chair",
            "add_cyclohexane_boat",
            "add_indole",
            "add_quinoline",
            "add_isoquinoline",
            "add_benzimidazole",
            "add_phenyl",
            "add_benzyl",
            "add_vinyl",
            "add_allyl",
            "add_carboxyl",
            "add_nitro",
            "add_sulfonyl",
            "add_carbonyl",
            "add_tbu",
            "add_ipr",
            "add_me",
            "add_et",
            "add_peptide_2",
        ):
            getattr(template_builder, method_name).assert_called_once_with()

    def test_insert_controller_public_api_methods_are_callable(self) -> None:
        insert_controller = mock.Mock()
        state = object()
        request = object()
        resolvers = object()
        preview_snapshot = object()
        pairs = [(1.0, 2.0)]

        insert_controller.insert_session_state.return_value = state
        insert_controller.template_insert_request.return_value = request
        insert_controller.template_point_resolvers.return_value = resolvers
        insert_controller.resolve_ring_points_for_template.return_value = pairs
        insert_controller.resolve_regular_ring_points_for_template_bond.return_value = pairs
        insert_controller.resolve_chair_points_for_template.return_value = pairs
        insert_controller.resolve_boat_points_for_template.return_value = pairs
        insert_controller.resolve_template_points_for_template_bond.return_value = pairs
        insert_controller.smiles_preview_snapshot.return_value = preview_snapshot
        insert_controller.bond_merge_seed.return_value = [(1, 2.0, 3.0)]

        self.assertIs(insert_controller.insert_session_state(), state)
        insert_controller.apply_insert_session_state(state)
        insert_controller.load_smiles("CC")
        insert_controller.begin_smiles_insert("CO")
        insert_controller.begin_ring_template_insert(6, "chair")
        insert_controller.cancel_smiles_insert()
        insert_controller.commit_smiles_insert(QPointF(4.0, 5.0))
        insert_controller.clear_smiles_preview()
        self.assertIs(insert_controller.smiles_preview_snapshot(), preview_snapshot)
        insert_controller.render_smiles_preview(QPointF(6.0, 7.0))
        insert_controller.cancel_template_insert()
        self.assertIs(insert_controller.template_insert_request(QPointF(8.0, 9.0)), request)
        self.assertIs(insert_controller.template_point_resolvers(), resolvers)
        self.assertEqual(insert_controller.resolve_ring_points_for_template((1.0, 2.0), 6, 12.0), pairs)
        self.assertEqual(insert_controller.resolve_regular_ring_points_for_template_bond(6, 3, (4.0, 5.0)), pairs)
        self.assertEqual(insert_controller.resolve_chair_points_for_template((0.0, 0.0)), pairs)
        self.assertEqual(insert_controller.resolve_boat_points_for_template((0.0, 0.0)), pairs)
        self.assertEqual(
            insert_controller.resolve_template_points_for_template_bond([(0.0, 0.0)], 4, (2.0, 3.0)),
            pairs,
        )
        self.assertEqual(insert_controller.bond_merge_seed(7), [(1, 2.0, 3.0)])
        insert_controller.commit_template_insert(QPointF(10.0, 11.0))
        insert_controller.clear_template_preview()
        insert_controller.render_template_preview(QPointF(12.0, 13.0))

        insert_controller.insert_session_state.assert_called_once_with()
        insert_controller.apply_insert_session_state.assert_called_once_with(state)
        insert_controller.load_smiles.assert_called_once_with("CC")
        insert_controller.begin_smiles_insert.assert_called_once_with("CO")
        insert_controller.begin_ring_template_insert.assert_called_once_with(6, "chair")
        insert_controller.cancel_smiles_insert.assert_called_once_with()
        insert_controller.commit_smiles_insert.assert_called_once_with(QPointF(4.0, 5.0))
        insert_controller.clear_smiles_preview.assert_called_once_with()
        insert_controller.smiles_preview_snapshot.assert_called_once_with()
        insert_controller.render_smiles_preview.assert_called_once_with(QPointF(6.0, 7.0))
        insert_controller.cancel_template_insert.assert_called_once_with()
        insert_controller.template_insert_request.assert_called_once_with(QPointF(8.0, 9.0))
        insert_controller.template_point_resolvers.assert_called_once_with()
        insert_controller.resolve_ring_points_for_template.assert_called_once_with((1.0, 2.0), 6, 12.0)
        insert_controller.resolve_regular_ring_points_for_template_bond.assert_called_once_with(6, 3, (4.0, 5.0))
        insert_controller.resolve_chair_points_for_template.assert_called_once_with((0.0, 0.0))
        insert_controller.resolve_boat_points_for_template.assert_called_once_with((0.0, 0.0))
        insert_controller.resolve_template_points_for_template_bond.assert_called_once_with([(0.0, 0.0)], 4, (2.0, 3.0))
        insert_controller.bond_merge_seed.assert_called_once_with(7)
        insert_controller.commit_template_insert.assert_called_once_with(QPointF(10.0, 11.0))
        insert_controller.clear_template_preview.assert_called_once_with()
        insert_controller.render_template_preview.assert_called_once_with(QPointF(12.0, 13.0))

    def test_canvas_bond_mutation_access_delegates_to_service(self) -> None:
        bond_mutation_service = mock.Mock()
        bond_state = {"a": 1, "b": 2, "order": 2}
        view = SimpleNamespace(services=SimpleNamespace(canvas_bond_mutation_service=bond_mutation_service))

        bond_mutation_service.add_bond.return_value = 7

        self.assertEqual(add_bond_for(view, 1, 2, order=2), 7)
        restore_bond_from_state_for_history(view, 4, bond_state)
        remove_bond_for_history(view, 5)
        trim_bonds_for_history(view, 6)

        bond_mutation_service.add_bond.assert_called_once_with(1, 2, 2)
        bond_mutation_service.restore_bond_from_state.assert_called_once_with(4, bond_state)
        bond_mutation_service.remove_bond_by_id.assert_called_once_with(5)
        bond_mutation_service.trim_bonds_to_length.assert_called_once_with(6)

    def test_set_curved_arrow_path_builds_path_and_arrow_heads(self) -> None:
        path_item = QGraphicsPathItem()
        build_service = SimpleNamespace(add_arrow_head=mock.Mock())
        view = SimpleNamespace(
            services=SimpleNamespace(
                scene_decoration_build_service=build_service,
            )
        )
        view.services.curved_arrow_path_service = CurvedArrowPathService(view)

        set_curved_arrow_path_for(
            view,
            path_item,
            start=QPointF(0.0, 0.0),
            end=QPointF(10.0, 0.0),
            control=QPointF(5.0, 4.0),
            double=True,
        )

        self.assertFalse(path_item.path().isEmpty())
        self.assertEqual(build_service.add_arrow_head.call_count, 2)

    def test_atom_label_history_wrappers_delegate_to_service(self) -> None:
        atom_label_service = mock.Mock()
        atom_item = object()
        atom_label_service.atom_item_for_id.return_value = atom_item
        view = SimpleNamespace(services=SimpleNamespace(atom_label_service=atom_label_service))

        self.assertIs(atom_item_for_id_for(view, 5), atom_item)
        atom_label_service.record_label_change(
            5,
            "C",
            False,
            "before",
            [7],
            {"atom_states": {7: {"element": "C"}}},
        )
        atom_label_service.restore_atom_item_interaction(
            5,
            atom_item,
            was_selected=True,
            refresh_hover=False,
        )

        atom_label_service.atom_item_for_id.assert_called_once_with(5)
        atom_label_service.record_label_change.assert_called_once_with(
            5,
            "C",
            False,
            "before",
            [7],
            {"atom_states": {7: {"element": "C"}}},
        )
        atom_label_service.restore_atom_item_interaction.assert_called_once_with(
            5,
            atom_item,
            was_selected=True,
            refresh_hover=False,
        )

    def test_history_recording_wrappers_delegate_to_service(self) -> None:
        history_recording_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(canvas_history_recording_service=history_recording_service))

        record_additions_for(
            view,
            before_next_atom_id=1,
            before_bond_count=2,
            before_smiles_input="before",
            added_scene_items=["note"],
        )
        record_bond_update_for(
            view,
            3,
            {"order": 1},
            {"order": 2},
            "before",
            "after",
        )

        history_recording_service.record_additions.assert_called_once_with(
            before_next_atom_id=1,
            before_bond_count=2,
            before_smiles_input="before",
            added_scene_items=["note"],
        )
        history_recording_service.record_bond_update.assert_called_once_with(
            3,
            {"order": 1},
            {"order": 2},
            "before",
            "after",
        )

    def test_bond_mutation_access_delegates_to_public_api(self) -> None:
        bond_mutation_service = mock.Mock()
        bond_mutation_service.add_bond.return_value = 9
        mutation_view = SimpleNamespace(services=SimpleNamespace(canvas_bond_mutation_service=bond_mutation_service))

        self.assertEqual(add_bond_for(mutation_view, 1, 2, order=3), 9)
        restore_bond_from_state_for_history(
            mutation_view,
            4,
            {"a": 2, "b": 3, "order": 2, "style": "double", "color": "#334455"},
        )
        remove_bond_for_history(mutation_view, 5)
        trim_bonds_for_history(mutation_view, 6)

        bond_mutation_service.add_bond.assert_called_once_with(1, 2, 3)
        bond_mutation_service.restore_bond_from_state.assert_called_once_with(
            4,
            {"a": 2, "b": 3, "order": 2, "style": "double", "color": "#334455"},
        )
        bond_mutation_service.remove_bond_by_id.assert_called_once_with(5)
        bond_mutation_service.trim_bonds_to_length.assert_called_once_with(6)

    def test_atom_state_dict_and_atom_mutation_access_delegate_to_public_api(self) -> None:
        label_item = mock.Mock()
        state_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 2.0, color="#111111")}),
        )
        set_atom_items_for(state_view, {1: label_item})
        self.assertEqual(
            atom_state_dict_for(state_view, 1),
            {
                "element": "C",
                "x": 1.0,
                "y": 2.0,
                "color": "#111111",
                "explicit_label": True,
            },
        )
        self.assertEqual(atom_state_dict_for(state_view, 99), {})

        atom_mutation_service = mock.Mock()
        atom_mutation_service.add_atom.return_value = 7
        mutation_view = SimpleNamespace(services=SimpleNamespace(canvas_atom_mutation_service=atom_mutation_service))

        self.assertEqual(add_atom_for(mutation_view, "N", 1.5, -2.5), 7)
        remove_atom_for_history(mutation_view, 1, remove_marks=False)
        restore_atom_from_state_for_history(
            mutation_view,
            4,
            {"element": "C", "x": 3.0, "y": 4.0, "color": "#00ff00", "explicit_label": True},
        )
        apply_atom_color_for_history(mutation_view, 7, QColor("#aabbcc"))

        atom_mutation_service.add_atom.assert_called_once_with("N", 1.5, -2.5)
        atom_mutation_service.remove_atom_only.assert_called_once_with(1, remove_marks=False)
        atom_mutation_service.restore_atom_from_state.assert_called_once_with(
            4,
            {"element": "C", "x": 3.0, "y": 4.0, "color": "#00ff00", "explicit_label": True},
        )
        atom_mutation_service.apply_atom_color.assert_called_once_with(7, QColor("#aabbcc"))

    def test_color_mutation_service_accessor_delegates_to_public_api(self) -> None:
        color_service = mock.Mock()
        ring_item = object()
        color = QColor("#336699")
        view = SimpleNamespace(services=SimpleNamespace(canvas_color_mutation_service=color_service))

        canvas_services_for(view).canvas_color_mutation_service.apply_color_to_item(ring_item, color)
        canvas_services_for(view).canvas_color_mutation_service.apply_ring_fill_color(ring_item, color, alpha=0.5)

        color_service.apply_color_to_item.assert_called_once_with(ring_item, color)
        color_service.apply_ring_fill_color.assert_called_once_with(ring_item, color, alpha=0.5)

    def test_pick_radius_and_nearest_hit_helpers_cover_missing_and_success_paths(self) -> None:
        radius_view = SimpleNamespace(
            renderer=SimpleNamespace(style=SimpleNamespace(bond_line_width=1.0, bond_length_px=20.0))
        )
        self.assertEqual(atom_pick_radius_for(radius_view), 6.4)

    def test_style_and_text_setting_helpers_clamp_values_and_apply_presets(self) -> None:
        note_controller = SimpleNamespace(apply_text_style_to_selected=mock.Mock())
        style_view = SimpleNamespace(
            tool_settings_state=CanvasToolSettingsState(atom_symbol="C"),
            selection_style_state=SelectionStyleState(
                color=QColor("#000000"),
                stroke_delta=0.6,
            ),
            text_style_state=CanvasTextStyleState(
                text_font_family="Helvetica",
                text_font_size=11,
                text_font_weight=QFont.Weight.Normal,
                text_italic=False,
                text_color=QColor("#222222"),
                text_alignment=Qt.AlignmentFlag.AlignLeft,
                text_line_spacing=1.0,
                note_box_enabled=False,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.3,
                note_border_enabled=False,
                note_border_color=QColor("#111111"),
                note_border_width=1.0,
                note_padding=4.0,
            ),
            renderer=SimpleNamespace(style=SimpleNamespace(font_size_pt=12, atom_color="#123456")),
            refresh_selection_outline=mock.Mock(),
            services=SimpleNamespace(
                note_controller=note_controller,
                tools=SimpleNamespace(set_active=mock.Mock()),
            ),
        )
        style_view.services.selection_controller = SimpleNamespace(
            update_selection_outline=style_view.refresh_selection_outline
        )

        style_controller = CanvasStyleController(style_view, note_controller=note_controller)
        tool_mode_controller = CanvasToolModeController(
            style_view,
            set_active_tool=style_view.services.tools.set_active,
        )
        text_style = text_style_state_for(style_view)

        tool_mode_controller.set_curved_symmetry(True)
        self.assertTrue(tool_mode_controller.get_curved_symmetry())
        style_controller.set_selection_color(QColor("#abcdef"))
        self.assertEqual(style_view.selection_style_state.color.name(), "#abcdef")
        style_controller.set_selection_color(QColor())
        self.assertEqual(style_view.selection_style_state.color.name(), "#abcdef")
        style_controller.set_selection_stroke_delta(-5.0)
        self.assertEqual(style_controller.get_selection_stroke_delta(), 0.1)

        tool_mode_controller.set_orbital_snap_enabled(True)
        self.assertTrue(tool_mode_controller.get_orbital_snap_enabled())
        tool_mode_controller.set_orbital_snap_step(0)
        self.assertEqual(tool_mode_controller.get_orbital_snap_step(), 1)

        style_controller.set_text_font(QFont("Courier New", 14))
        self.assertEqual(text_style.text_font_family, "Courier New")
        style_controller.set_text_size(2)
        self.assertEqual(style_controller.get_text_size(), 6)
        style_controller.set_text_weight(150)
        self.assertEqual(style_controller.get_text_weight(), 99)
        style_controller.set_text_italic(True)
        self.assertTrue(text_style.text_italic)
        style_controller.set_text_color(QColor("#ff00aa"))
        self.assertEqual(text_style.text_color.name(), "#ff00aa")
        style_controller.set_text_color(QColor())
        self.assertEqual(text_style.text_color.name(), "#ff00aa")
        font = style_controller.get_text_font()
        self.assertEqual(font.family(), "Courier New")
        self.assertEqual(font.pointSize(), 6)

        style_controller.apply_text_preset_acs()
        self.assertEqual(text_style.text_font_family, "Arial")
        self.assertEqual(text_style.text_font_size, 12)
        self.assertEqual(text_style.text_color.name(), "#123456")
        self.assertFalse(text_style.note_box_enabled)
        self.assertFalse(text_style.note_border_enabled)

        style_controller.apply_text_preset_paper_thin()
        self.assertEqual(text_style.text_font_size, 11)
        self.assertAlmostEqual(text_style.text_line_spacing, 1.05)
        self.assertEqual(text_style.text_color.name(), "#222222")

        style_controller.apply_text_preset_paper_bold()
        self.assertEqual(text_style.text_font_size, 14)
        self.assertTrue(text_style.note_box_enabled)
        self.assertTrue(text_style.note_border_enabled)
        self.assertEqual(text_style.note_box_color.name(), "#ffffff")
        self.assertEqual(text_style.note_border_color.name(), "#111111")
        self.assertEqual(text_style.note_padding, 8.0)

        style_controller.set_text_alignment("center")
        self.assertEqual(text_style.text_alignment, Qt.AlignmentFlag.AlignHCenter)
        style_controller.set_text_alignment("bad")
        self.assertEqual(text_style.text_alignment, Qt.AlignmentFlag.AlignHCenter)
        style_controller.set_text_line_spacing(0.2)
        self.assertEqual(text_style.text_line_spacing, 0.8)
        tool_mode_controller.set_atom_symbol(" N ")
        self.assertEqual(tool_mode_controller.get_atom_symbol(), "N")
        style_controller.set_note_box_enabled(False)
        self.assertFalse(text_style.note_box_enabled)
        style_controller.set_note_box_color(QColor("#00ff00"))
        self.assertEqual(text_style.note_box_color.name(), "#00ff00")
        style_controller.set_note_box_color(QColor())
        self.assertEqual(text_style.note_box_color.name(), "#00ff00")
        style_controller.set_note_box_alpha(3.0)
        self.assertEqual(style_controller.get_note_box_alpha(), 1.0)
        style_controller.set_note_border_enabled(False)
        self.assertFalse(text_style.note_border_enabled)
        style_controller.set_note_border_color(QColor("#445566"))
        self.assertEqual(text_style.note_border_color.name(), "#445566")
        style_controller.set_note_border_color(QColor())
        self.assertEqual(text_style.note_border_color.name(), "#445566")
        style_controller.set_note_border_width(0.1)
        self.assertEqual(text_style.note_border_width, 0.5)
        style_controller.set_note_padding(1.0)
        self.assertEqual(text_style.note_padding, 2.0)
        tool_mode_controller.set_snap_angle_step(22)
        self.assertEqual(tool_settings_state_for(style_view).snap_angle_step, 22)
        style_view.services.tools.set_active.assert_called_with("bond")
        style_view.refresh_selection_outline.assert_called_once_with()
        self.assertGreaterEqual(note_controller.apply_text_style_to_selected.call_count, 14)

    def test_note_selection_and_text_style_helpers_update_boxes_and_focus(self) -> None:
        scene = QGraphicsScene()
        item = QGraphicsTextItem("Mechanism")
        scene.addItem(item)

        note_view = SimpleNamespace(
            text_style_state=CanvasTextStyleState(
                note_padding=6.0,
                note_box_enabled=True,
                note_border_enabled=True,
                note_box_color=QColor("#ffffff"),
                note_box_alpha=0.4,
                note_border_color=QColor("#111111"),
                note_border_width=1.2,
                text_font_family="Arial",
                text_font_size=13,
                text_font_weight=QFont.Weight.DemiBold,
                text_italic=True,
                text_color=QColor("#334455"),
                text_alignment=Qt.AlignmentFlag.AlignRight,
                text_line_spacing=1.25,
            ),
            selection_style_state=SelectionStyleState(
                color=QColor("#1f5eff"),
                stroke_delta=0.8,
            ),
            scene=lambda: scene,
            setFocus=mock.Mock(),
            services=SimpleNamespace(history_service=SimpleNamespace(push=mock.Mock())),
        )
        set_scene_item_collection_for(note_view, "selected_notes", [])
        note_view.clear_note_selection = lambda: clear_note_selection_for(note_view)
        note_view.select_note = lambda target, additive=False: select_note_for(note_view, target, additive=additive)
        selection_controller = _selection_controller_for(note_view)
        note_controller = CanvasNoteController(note_view)
        note_view.services = SimpleNamespace(
            selection_controller=selection_controller,
            note_controller=note_controller,
        )

        select_note_for(note_view, item, additive=False)
        self.assertEqual(selected_notes_for(note_view), [item])
        selection_box = item.data(21)
        self.assertIsNotNone(selection_box)
        self.assertTrue(selection_box.isVisible())

        canvas_services_for(note_view).note_controller.apply_text_style_to_selected()
        box = item.data(20)
        self.assertIsNotNone(box)
        self.assertTrue(box.isVisible())
        self.assertEqual(item.defaultTextColor().name(), "#334455")
        self.assertTrue(item.font().italic())
        self.assertEqual(item.font().pointSize(), 13)

        canvas_services_for(note_view).note_controller.update_text_note(item, "Updated")
        self.assertEqual(item.toPlainText(), "Updated")

        canvas_services_for(note_view).note_controller.begin_note_edit(item)
        self.assertIn(item, selected_notes_for(note_view))
        note_view.setFocus.assert_called()
        self.assertIs(scene.focusItem(), item)
        self.assertNotEqual(item.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)

        toggle_note_selection_for(note_view, item)
        self.assertEqual(selected_notes_for(note_view), [])
        self.assertFalse(item.data(21).isVisible())

        select_note_for(note_view, item, additive=False)
        clear_note_selection_for(note_view)
        self.assertEqual(selected_notes_for(note_view), [])
        self.assertFalse(item.data(21).isVisible())

        set_text_style_for(note_view, "note_box_enabled", False)
        set_text_style_for(note_view, "note_border_enabled", False)
        update_note_box_for(note_view, item)
        self.assertFalse(item.data(20).isVisible())

    def test_find_bond_near_uses_hit_testing_service(self) -> None:
        service = SimpleNamespace(
            find_bond_near=mock.Mock(return_value=4),
        )
        view = SimpleNamespace(services=SimpleNamespace(hit_testing_service=service))
        pos = QPointF(3.0, 4.0)

        self.assertEqual(view.services.hit_testing_service.find_bond_near(pos, 7.0), 4)

        service.find_bond_near.assert_called_once_with(pos, 7.0)

    def test_selection_and_copy_helpers_cover_transform_copy_and_mark_fallback(self) -> None:
        scene_token = object()
        selected_note = _FakeItem("note", scene_token=scene_token)
        transform_scene = _FakeScene(
            [
                _FakeItem("atom", data1=1, scene_token=scene_token),
                _FakeItem("handle", scene_token=scene_token),
                _FakeItem("note_box", scene_token=scene_token),
                selected_note,
            ]
        )
        selected_note._scene_token = transform_scene
        transform_view = SimpleNamespace(
            scene=lambda: transform_scene,
        )
        set_scene_item_collection_for(
            transform_view,
            "selected_notes",
            [selected_note, _FakeItem("note", scene_token=object())],
        )
        transformed_items = selected_items_for_transform_for(transform_view)
        self.assertEqual([item.data(0) for item in transformed_items], ["atom", "note"])

        polygon = QPolygonF(
            [
                QPointF(-1.0, -1.0),
                QPointF(3.0, -1.0),
                QPointF(3.0, 3.0),
                QPointF(-1.0, 3.0),
            ]
        )
        selection_scene = _FakeScene(
            [
                _FakeItem("atom", data1=1, scene_token=scene_token),
                _FakeItem("bond", data1=7, scene_token=scene_token),
                _FakeItem("ring", data2=[2, "bad", 99], scene_token=scene_token),
                _FakeItem("ring", scene_token=scene_token, polygon=polygon),
            ]
        )
        selection_view = SimpleNamespace(
            scene=lambda: selection_scene,
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 2.0, 0.0),
                    3: Atom("N", 1.0, 1.0),
                    4: Atom("F", 5.0, 5.0),
                }
            ),
        )
        atom_ids, bond_ids = selected_ids_for(selection_view)
        self.assertEqual(atom_ids, {1, 2, 3})
        self.assertEqual(bond_ids, {7})

        chemical_scene = _FakeScene([_FakeItem("mark", data1={"atom_id": 4}, scene_token=scene_token)])
        chemical_view = SimpleNamespace(
            scene=lambda: chemical_scene,
            model=SimpleNamespace(atoms={4: Atom("Cl", 0.0, 0.0)}),
        )
        self.assertEqual(selected_chemical_ids_for(chemical_view), ({4}, set()))

        bond_child = _FakeItem("bond_child", scene_token=scene_token)
        bond_graphic = _FakeItem("bond_graphic", scene_token=scene_token, children=[bond_child])
        extra_child = _FakeItem("arrow_head", scene_token=scene_token)
        generic_item = _FakeItem("arrow", scene_token=scene_token, children=[extra_child])
        note_select = _FakeItem("note_select", scene_token=scene_token)
        copy_scene = _FakeScene(
            [
                _FakeItem("bond", data1=5, scene_token=scene_token),
                generic_item,
                note_select,
            ]
        )
        note = _FakeItem("note", scene_token=scene_token)
        note._scene_token = copy_scene
        copy_view = SimpleNamespace(
            scene=lambda: copy_scene,
        )
        set_scene_item_collection_for(copy_view, "selected_notes", [note, _FakeItem("note", scene_token=object())])
        set_bond_items_for(copy_view, {5: [bond_graphic]})
        copied_items = selection_items_for_copy_for(copy_view)
        self.assertEqual(
            [item.data(0) for item in copied_items],
            ["bond_graphic", "bond_child", "arrow", "arrow_head", "note"],
        )

    def test_set_atom_positions_updates_geometry_marks_and_selection(self) -> None:
        label_item = object()
        dot_item = mock.Mock()
        mark_with_offset = _FakeItem("mark", data1={"dx": 1.5, "dy": -2.0})
        mark_without_offset = _FakeItem("mark", data1={})
        view = SimpleNamespace(
            model=SimpleNamespace(
                atoms={
                    1: Atom("C", 0.0, 0.0),
                    2: Atom("O", 5.0, 5.0),
                    3: Atom("N", 9.0, 9.0),
                }
            ),
            atom_coords_3d_state=CanvasAtomCoords3DState(
                atom_coords_3d={1: (0.0, 0.0, 1.0), 3: (9.0, 9.0, 3.0)}
            ),
            mark_registry=CanvasMarkRegistry({1: [mark_with_offset, mark_without_offset]}),
            services=SimpleNamespace(
                atom_label_service=SimpleNamespace(position_label=mock.Mock()),
                scene_decoration_build_service=SimpleNamespace(set_mark_center=mock.Mock()),
                move_controller=SimpleNamespace(redraw_bonds_for_atoms=mock.Mock()),
                canvas_ring_fill_scene_service=SimpleNamespace(update_ring_fills_for_atoms=mock.Mock()),
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
            ),
            refresh_selection_outline=mock.Mock(),
        )
        set_atom_items_for(view, {1: label_item})
        set_atom_dots_for(view, {1: dot_item})
        view.services.selection_controller = SimpleNamespace(update_selection_outline=view.refresh_selection_outline)

        set_atom_positions_for_history(
            view,
            positions={1: (2.0, 3.0), 99: (0.0, 0.0)},
            coords_3d={2: (7.0, 8.0, 9.0)},
        )

        self.assertEqual((view.model.atoms[1].x, view.model.atoms[1].y), (2.0, 3.0))
        self.assertEqual(atom_coords_3d_for(view)[1], (2.0, 3.0, 1.0))
        self.assertEqual(atom_coords_3d_for(view)[2], (7.0, 8.0, 9.0))
        view.services.atom_label_service.position_label.assert_called_once_with(label_item, 2.0, 3.0)
        dot_item.setPos.assert_called_once_with(2.0, 3.0)
        set_mark_center = view.services.scene_decoration_build_service.set_mark_center
        self.assertEqual(
            set_mark_center.call_args_list,
            [
                mock.call(mark_with_offset, QPointF(3.5, 1.0)),
                mock.call(mark_without_offset, QPointF(2.0, 3.0)),
            ],
        )
        view.services.move_controller.redraw_bonds_for_atoms.assert_called_once_with({1, 2})
        view.services.canvas_ring_fill_scene_service.update_ring_fills_for_atoms.assert_called_once_with({1, 2})
        view.services.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()
        view.refresh_selection_outline.assert_called_once_with()

        quiet_view = SimpleNamespace(
            model=SimpleNamespace(atoms={}),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            mark_registry=CanvasMarkRegistry(),
            services=SimpleNamespace(
                atom_label_service=SimpleNamespace(position_label=mock.Mock()),
                scene_decoration_build_service=SimpleNamespace(set_mark_center=mock.Mock()),
                move_controller=SimpleNamespace(redraw_bonds_for_atoms=mock.Mock()),
                canvas_ring_fill_scene_service=SimpleNamespace(update_ring_fills_for_atoms=mock.Mock()),
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
            ),
            refresh_selection_outline=mock.Mock(),
        )
        set_atom_items_for(quiet_view, {})
        set_atom_dots_for(quiet_view, {})
        set_atom_positions_for_history(quiet_view, positions={}, coords_3d=None)
        quiet_view.services.hit_testing_service.mark_spatial_index_dirty.assert_not_called()

        noop_view = SimpleNamespace(
            model=SimpleNamespace(atoms={1: Atom("C", 1.0, 1.0)}),
            atom_coords_3d_state=CanvasAtomCoords3DState(),
            mark_registry=CanvasMarkRegistry(),
            services=SimpleNamespace(
                atom_label_service=SimpleNamespace(position_label=mock.Mock()),
                scene_decoration_build_service=SimpleNamespace(set_mark_center=mock.Mock()),
                move_controller=SimpleNamespace(redraw_bonds_for_atoms=mock.Mock()),
                canvas_ring_fill_scene_service=SimpleNamespace(update_ring_fills_for_atoms=mock.Mock()),
                hit_testing_service=SimpleNamespace(mark_spatial_index_dirty=mock.Mock()),
            ),
            refresh_selection_outline=mock.Mock(),
        )
        set_atom_items_for(noop_view, {})
        set_atom_dots_for(noop_view, {})
        set_atom_positions_for_history(
            noop_view,
            positions={99: (3.0, 4.0)},
            coords_3d={98: (5.0, 6.0, 7.0)},
            update_selection=False,
        )
        noop_view.services.move_controller.redraw_bonds_for_atoms.assert_not_called()
        noop_view.services.canvas_ring_fill_scene_service.update_ring_fills_for_atoms.assert_not_called()
        noop_view.services.hit_testing_service.mark_spatial_index_dirty.assert_called_once_with()
        noop_view.refresh_selection_outline.assert_not_called()

    def test_ring_fill_access_helpers_delegate_to_scene_service(self) -> None:
        scene_service = mock.Mock()
        ring_item = object()
        view = SimpleNamespace(services=SimpleNamespace(canvas_ring_fill_scene_service=scene_service))

        scene_service.create_ring_fill_item.return_value = ring_item

        update_ring_fills_for_atoms_for(view, {1, 2, 3})
        rotate_ring_fills_3d_for(view, {1, 2, 3}, (4.0, 5.0, 6.0), 0.1, 0.2, 1.5)
        rotate_ring_fills_for(view, {1, 2, 3}, QPointF(7.0, 8.0), 0.3)
        self.assertIs(
            create_ring_fill_item_for(
                view,
                [QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(1.0, 1.5)],
                [1, 2, 3],
            ),
            ring_item,
        )

        scene_service.update_ring_fills_for_atoms.assert_called_once_with({1, 2, 3})
        scene_service.rotate_ring_fills_3d.assert_called_once_with({1, 2, 3}, (4.0, 5.0, 6.0), 0.1, 0.2, 1.5)
        scene_service.rotate_ring_fills.assert_called_once_with({1, 2, 3}, QPointF(7.0, 8.0), 0.3)
        scene_service.create_ring_fill_item.assert_called_once_with(
            [QPointF(0.0, 0.0), QPointF(2.0, 0.0), QPointF(1.0, 1.5)],
            [1, 2, 3],
        )

    def test_select_structure_for_item_selects_atom_bond_ring_and_scene_items(self) -> None:
        atom_item = _FakeItem("atom", data1=1)
        atom_item_2 = _FakeItem("atom", data1=2)
        bond_item = _FakeItem("bond", data1=0)
        bond_graphic = _FakeItem("bond")
        ring_item = _FakeItem("ring", data2=[1, 2])
        note_item = _FakeItem("note")
        selection_scene = _FakeScene([atom_item, bond_item, ring_item, note_item])
        expand_connected_atoms = mock.Mock(return_value={1, 2})
        view = SimpleNamespace(
            scene=lambda: selection_scene,
            model=SimpleNamespace(
                atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)},
                bonds=[Bond(1, 2, 1)],
            ),
            services=SimpleNamespace(canvas_graph_service=SimpleNamespace(expand_connected_atoms=expand_connected_atoms)),
            refresh_selection_outline=mock.Mock(),
        )
        set_scene_item_collection_for(view, "ring_items", [ring_item])
        set_atom_items_for(view, {1: atom_item, 2: atom_item_2})
        set_atom_dots_for(view, {})
        set_bond_items_for(view, {0: [bond_graphic]})
        selection_controller = _selection_controller_for(view)
        selection_controller.update_selection_outline = mock.Mock()
        view.services.selection_controller = selection_controller

        self.assertTrue(selection_controller.select_structure_for_item(atom_item))
        self.assertEqual(selection_scene.clear_selection_calls, 1)
        self.assertTrue(atom_item.isSelected())
        self.assertTrue(atom_item_2.isSelected())
        self.assertTrue(bond_graphic.isSelected())
        self.assertTrue(ring_item.isSelected())
        selection_controller.update_selection_outline.assert_called_once_with()

        selection_scene.clear_selection_calls = 0
        selection_controller.update_selection_outline.reset_mock()
        self.assertTrue(selection_controller.select_structure_for_item(bond_item))
        self.assertEqual(selection_scene.clear_selection_calls, 1)
        expand_connected_atoms.assert_called_with({1, 2})

        ring_only = _FakeItem("ring", data2=[1, 2])
        ring_scene = _FakeScene([ring_only])
        ring_view = SimpleNamespace(
            scene=lambda: ring_scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 2.0, 0.0)}, bonds=[]),
            services=SimpleNamespace(
                canvas_graph_service=SimpleNamespace(expand_connected_atoms=mock.Mock(return_value={1, 2}))
            ),
            refresh_selection_outline=mock.Mock(),
        )
        set_scene_item_collection_for(ring_view, "ring_items", [ring_only])
        set_atom_items_for(ring_view, {1: _FakeItem("atom", data1=1), 2: _FakeItem("atom", data1=2)})
        set_atom_dots_for(ring_view, {})
        set_bond_items_for(ring_view, {})
        ring_controller = _selection_controller_for(ring_view)
        ring_controller.update_selection_outline = mock.Mock()
        ring_view.services.selection_controller = ring_controller
        self.assertTrue(ring_controller.select_structure_for_item(ring_only))
        self.assertTrue(ring_only.isSelected())

        note_scene = _FakeScene([note_item])
        note_view = SimpleNamespace(
            scene=lambda: note_scene,
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(canvas_graph_service=SimpleNamespace(expand_connected_atoms=mock.Mock())),
            refresh_selection_outline=mock.Mock(),
        )
        set_scene_item_collection_for(note_view, "ring_items", [])
        set_atom_items_for(note_view, {})
        set_atom_dots_for(note_view, {})
        set_bond_items_for(note_view, {})
        note_controller = _selection_controller_for(note_view)
        note_controller.update_selection_outline = mock.Mock()
        note_view.services.selection_controller = note_controller
        self.assertTrue(note_controller.select_structure_for_item(note_item))
        self.assertEqual(note_scene.clear_selection_calls, 1)
        self.assertTrue(note_item.isSelected())
        note_controller.update_selection_outline.assert_not_called()

        invalid_atom = _FakeItem("atom", data1="bad")
        invalid_view = SimpleNamespace(
            scene=lambda: _FakeScene([invalid_atom]),
            model=SimpleNamespace(atoms={}, bonds=[]),
            services=SimpleNamespace(
                canvas_graph_service=SimpleNamespace(expand_connected_atoms=mock.Mock(return_value=set()))
            ),
            refresh_selection_outline=mock.Mock(),
        )
        set_scene_item_collection_for(invalid_view, "ring_items", [])
        set_atom_items_for(invalid_view, {})
        set_atom_dots_for(invalid_view, {})
        set_bond_items_for(invalid_view, {})
        invalid_controller = _selection_controller_for(invalid_view)
        invalid_view.services.selection_controller = invalid_controller
        self.assertFalse(invalid_controller.select_structure_for_item(invalid_atom))
        self.assertFalse(invalid_controller.select_structure_for_item(None))

    def test_apply_color_and_fill_helpers_cover_bond_atom_ring_and_commands(self) -> None:
        scene = QGraphicsScene()

        bond_item = QGraphicsPathItem()
        bond_item.setData(0, "bond")
        bond_item.setData(1, 0)
        scene.addItem(bond_item)
        bond_pushes = []
        bond_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(bonds=[Bond(1, 2, 1, color="#000000")]),
            smiles_input_state=CanvasSmilesInputState(last_smiles_input="smiles"),
            _bond_state_dict=lambda bond: {
                "a": bond.a,
                "b": bond.b,
                "order": bond.order,
                "style": bond.style,
                "color": bond.color,
            },
            services=SimpleNamespace(history_service=SimpleNamespace(push=bond_pushes.append)),
        )
        set_bond_items_for(bond_view, {0: [bond_item]})
        bond_view.services.canvas_color_mutation_service = _color_service_for(bond_view)
        canvas_services_for(bond_view).canvas_color_mutation_service.apply_color_to_item(
            bond_item,
            QColor("#ff0000"),
        )
        self.assertEqual(bond_view.model.bonds[0].color, "#ff0000")
        self.assertEqual(bond_item.pen().color().name(), "#ff0000")
        self.assertIsInstance(bond_pushes.pop(), UpdateBondCommand)

        atom_item = QGraphicsTextItem("O")
        atom_item.setData(0, "atom")
        atom_item.setData(1, 7)
        scene.addItem(atom_item)
        dot_item = mock.Mock()
        atom_pushes = []
        atom_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={7: Atom("O", 0.0, 0.0, color="#101010")}),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=atom_pushes.append),
                atom_label_service=SimpleNamespace(implicit_carbon_dot_brush=mock.Mock(return_value="dot-brush"))
            ),
        )
        set_atom_items_for(atom_view, {7: atom_item})
        set_atom_dots_for(atom_view, {7: dot_item})
        atom_view.services.canvas_color_mutation_service = _color_service_for(atom_view)
        canvas_services_for(atom_view).canvas_color_mutation_service.apply_color_to_item(
            atom_item,
            QColor("#00aa00"),
        )
        self.assertEqual(atom_view.model.atoms[7].color, "#00aa00")
        self.assertEqual(atom_item.defaultTextColor().name(), "#00aa00")
        dot_item.setBrush.assert_called_once_with("dot-brush")
        self.assertIsInstance(atom_pushes.pop(), UpdateAtomColorCommand)

        ring_item = QGraphicsPolygonItem(
            QPolygonF([QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(0.0, 1.0)])
        )
        ring_item.setData(0, "ring")
        ring_item.setData(2, [1, 2])
        scene.addItem(ring_item)
        recurse_view = SimpleNamespace(
            scene=lambda: scene,
            model=SimpleNamespace(atoms={1: Atom("C", 0.0, 0.0), 2: Atom("O", 1.0, 0.0)}),
            services=SimpleNamespace(
                history_service=SimpleNamespace(push=mock.Mock()),
            ),
        )
        graph_service = SimpleNamespace(bond_sets_for_atoms=mock.Mock(return_value=({3}, set())))
        set_atom_items_for(recurse_view, {1: object()})
        set_atom_dots_for(recurse_view, {2: object()})
        set_bond_items_for(recurse_view, {3: [object()]})
        recurse_service = _color_service_for(recurse_view, graph_service=graph_service)
        recurse_service.apply_color_to_item = mock.Mock()
        recurse_service._apply_ring_structure_color(ring_item, QColor("#336699"))
        graph_service.bond_sets_for_atoms.assert_called_once_with({1, 2})
        self.assertEqual(
            recurse_service.apply_color_to_item.call_args_list,
            [
                mock.call(atom_items_for(recurse_view)[1], QColor("#336699")),
                mock.call(atom_dots_for(recurse_view)[2], QColor("#336699")),
                mock.call(bond_items_for(recurse_view)[3][0], QColor("#336699")),
            ],
        )

        fill_pushes = []
        fill_view = SimpleNamespace(
            services=SimpleNamespace(history_service=SimpleNamespace(push=fill_pushes.append)),
        )
        fill_view.services.canvas_color_mutation_service = _color_service_for(fill_view)
        canvas_services_for(fill_view).canvas_color_mutation_service.apply_ring_fill_color(
            ring_item,
            QColor("#123456"),
            alpha=2.0,
        )
        self.assertAlmostEqual(ring_item.brush().color().alphaF(), 1.0)
        self.assertIsInstance(fill_pushes.pop(), UpdateSceneItemCommand)

        canvas_services_for(atom_view).canvas_color_mutation_service.apply_color_to_item(None, QColor("#ffffff"))
        canvas_services_for(fill_view).canvas_color_mutation_service.apply_ring_fill_color(None, QColor("#ffffff"))

    def test_clear_scene_access_delegates_to_reset_service(self) -> None:
        reset_service = mock.Mock()
        view = SimpleNamespace(services=SimpleNamespace(canvas_scene_reset_service=reset_service))

        clear_scene_for(view)

        reset_service.clear_scene.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
