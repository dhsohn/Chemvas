from __future__ import annotations

import gc
import os
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QRectF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
)

from chemvas.core.history import RestoreOutcome
from chemvas.domain.document import Atom, MoleculeModel
from chemvas.ui.canvas_hover_state import hover_state_for
from chemvas.ui.canvas_lifecycle import schedule_canvas_deletion_for
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_scene_items_state import note_items_for, selected_notes_for
from chemvas.ui.canvas_smiles_input_state import (
    last_smiles_input_for,
    set_last_smiles_input_for,
)
from chemvas.ui.canvas_view import CanvasView
from chemvas.ui.input_view_access import set_scene_rect_for
from chemvas.ui.insert_mode_logic import InsertSessionState
from chemvas.ui.insert_smiles_service import (
    InsertSmilesService,
)
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_style_state import selection_style_state_for
from tests.canvas_factory import build_canvas_view
from tests.test_insert_controller import _FakeCanvas


def _session_state(canvas: _FakeCanvas) -> InsertSessionState:
    center = canvas.insert_state.smiles_preview_center
    return InsertSessionState(
        template_active=canvas.insert_state.template_active,
        template_ring_size=canvas.insert_state.template_ring_size,
        template_ring_style=canvas.insert_state.template_ring_style,
        smiles_active=canvas.insert_state.smiles_active,
        smiles_text=canvas.insert_state.smiles_preview_smiles,
        smiles_center=None if center is None else (center.x(), center.y()),
    )


def _apply_state(canvas: _FakeCanvas, state: InsertSessionState) -> None:
    canvas.insert_state.template_active = state.template_active
    canvas.insert_state.template_ring_size = state.template_ring_size
    canvas.insert_state.template_ring_style = state.template_ring_style
    canvas.insert_state.smiles_active = state.smiles_active
    canvas.insert_state.smiles_preview_smiles = state.smiles_text
    canvas.insert_state.smiles_preview_center = (
        None if state.smiles_center is None else QPointF(*state.smiles_center)
    )


def _service_for(canvas: _FakeCanvas, **overrides) -> InsertSmilesService:
    return InsertSmilesService(
        canvas,
        insert_state=canvas.insert_state,
        insert_commit_service=overrides.pop("insert_commit_service", mock.Mock()),
        graph_service=canvas.services.graph_service,
        structure_build_service=canvas.services.structure.structure_build_service,
        history_service=canvas.services.history_service,
        session_state=lambda: _session_state(canvas),
        apply_session_state=lambda state: _apply_state(canvas, state),
        cancel_template_insert=overrides.pop("cancel_template_insert", mock.Mock()),
        cancel_smiles_insert=overrides.pop("cancel_smiles_insert", None),
        clear_smiles_preview=overrides.pop("clear_smiles_preview", None),
        render_smiles_preview=overrides.pop("render_smiles_preview", None),
    )


def _dispose_canvas(canvas: CanvasView) -> None:
    schedule_canvas_deletion_for(canvas)
    QCoreApplication.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _live_canvas_load_snapshot(
    canvas: CanvasView, service: InsertSmilesService
) -> dict:
    original_model = canvas.model
    atom_id = original_model.add_atom("N", 12.0, 34.0)
    original_atom = original_model.atoms[atom_id]
    set_last_smiles_input_for(canvas, "old-smiles")
    note = canvas.services.interaction.note_controller.create_text_note(
        QPointF(18.0, 27.0),
        "original note",
    )
    note.setSelected(True)
    canvas.services.selection.selection_controller.select_note(note)

    scene = canvas.scene()

    def add_preview_item(x: float) -> QGraphicsRectItem:
        item = QGraphicsRectItem(QRectF(x, 0.0, 5.0, 5.0))
        scene.addItem(item)
        return item

    insert_state = service.insert_state
    smiles_bond_item = add_preview_item(100.0)
    smiles_atom_item = add_preview_item(110.0)
    template_line_item = add_preview_item(120.0)
    template_dot_item = add_preview_item(130.0)
    insert_state.smiles_active = True
    insert_state.smiles_preview_model = MoleculeModel(atoms={7: Atom("O", 1.0, 2.0)})
    insert_state.smiles_preview_items = [smiles_bond_item, smiles_atom_item]
    insert_state.smiles_preview_bond_items = {3: [smiles_bond_item]}
    insert_state.smiles_preview_atom_items = {7: smiles_atom_item}
    insert_state.smiles_preview_center = QPointF(1.5, 2.5)
    insert_state.smiles_preview_smiles = "preview-smiles"
    insert_state.template_active = True
    insert_state.template_ring_size = 5
    insert_state.template_ring_style = "chair"
    insert_state.template_preview_items = [template_line_item, template_dot_item]
    insert_state.template_preview_lines = [template_line_item]
    insert_state.template_preview_dots = [template_dot_item]

    hover_state = hover_state_for(canvas)
    hover_item = add_preview_item(150.0)
    hover_state.style = "bond"
    hover_state.items = [hover_item]
    hover_state.atom_id = atom_id
    hover_state.bond_id = 9

    rotation = rotation_state_for(canvas)
    rotation.base_coords = {atom_id: (12.0, 34.0, 5.0)}
    rotation.axis_bond_id = 8
    rotation.axis_atoms = (atom_id, 11)
    rotation.total_angle = 27.0
    rotation.mode = "free"
    rotation.free_angle_x = 3.0
    rotation.free_angle_y = 4.0
    rotation.base_bond_length = 37.0
    rotation.atom_ids = {atom_id, 11}
    rotation.center_3d = (1.0, 2.0, 3.0)
    rotation.projection_center_3d = (4.0, 5.0, 6.0)
    rotation.projection_anchor_2d = (7.0, 8.0)
    rotation.start_projection_center_3d = (9.0, 10.0, 11.0)
    rotation.start_projection_anchor_2d = (12.0, 13.0)
    rotation.start_positions = {atom_id: (12.0, 34.0)}
    rotation.start_coords_3d = {atom_id: (12.0, 34.0, 5.0)}
    rotation.coord_atom_ids = {atom_id}
    rotation.selection_ids = ({atom_id}, {8})

    canvas.renderer.set_bond_length(37.0)
    transform = QTransform()
    transform.rotate(17.0)
    transform.scale(1.25, 0.85)
    canvas.setTransform(transform)
    set_scene_rect_for(canvas, QRectF(-321.0, -222.0, 987.0, 765.0))

    history_state = service.history.state
    history_command = object()
    redo_command = object()
    history_state.history.append(history_command)
    history_state.redo_stack.append(redo_command)

    return {
        "model": original_model,
        "atom_id": atom_id,
        "atom": original_atom,
        "note": note,
        "note_items": note_items_for(canvas),
        "selected_notes": selected_notes_for(canvas),
        "scene_items": tuple(canvas.scene().items()),
        "scene_rect": QRectF(canvas.scene().sceneRect()),
        "view_rect": QRectF(canvas.sceneRect()),
        "view_transform": QTransform(canvas.transform()),
        "renderer_style": canvas.renderer.style,
        "history": history_state.history,
        "history_command": history_command,
        "redo": history_state.redo_stack,
        "redo_command": redo_command,
        "scene_signals_blocked": canvas.scene().signalsBlocked(),
        "insert_state": insert_state,
        "insert_containers": {
            name: (getattr(insert_state, name), getattr(insert_state, name).copy())
            for name in (
                "smiles_preview_items",
                "smiles_preview_bond_items",
                "smiles_preview_atom_items",
                "template_preview_items",
                "template_preview_lines",
                "template_preview_dots",
            )
        },
        "insert_values": {
            name: getattr(insert_state, name)
            for name in (
                "smiles_active",
                "smiles_preview_model",
                "smiles_preview_center",
                "smiles_preview_smiles",
                "template_active",
                "template_ring_size",
                "template_ring_style",
            )
        },
        "hover_state": hover_state,
        "hover_items": (hover_state.items, list(hover_state.items)),
        "hover_values": (hover_state.style, hover_state.atom_id, hover_state.bond_id),
        "rotation_state": rotation,
        "rotation_containers": {
            name: (getattr(rotation, name), getattr(rotation, name).copy())
            for name in (
                "base_coords",
                "atom_ids",
                "start_positions",
                "start_coords_3d",
                "coord_atom_ids",
            )
        },
        "rotation_values": {
            name: getattr(rotation, name)
            for name in (
                "axis_bond_id",
                "axis_atoms",
                "total_angle",
                "mode",
                "free_angle_x",
                "free_angle_y",
                "base_bond_length",
                "center_3d",
                "projection_center_3d",
                "projection_anchor_2d",
                "start_projection_center_3d",
                "start_projection_anchor_2d",
                "selection_ids",
            )
        },
    }


def _assert_live_canvas_load_snapshot(
    canvas: CanvasView, service: InsertSmilesService, state: dict
) -> None:
    note = state["note"]
    assert not sip.isdeleted(note)
    assert note.scene() is canvas.scene()
    assert canvas.model is state["model"]
    assert canvas.model.atoms[state["atom_id"]] is state["atom"]
    assert last_smiles_input_for(canvas) == "old-smiles"

    assert note_items_for(canvas) is state["note_items"]
    assert note_items_for(canvas) == [note]
    assert selected_notes_for(canvas) is state["selected_notes"]
    assert selected_notes_for(canvas) == [note]
    assert note.isSelected()
    current_scene_items = tuple(canvas.scene().items())
    assert len(current_scene_items) == len(state["scene_items"])
    assert all(
        current is original
        for current, original in zip(
            current_scene_items, state["scene_items"], strict=True
        )
    )

    history_state = service.history.state
    assert history_state.history is state["history"]
    assert history_state.history == [state["history_command"]]
    assert history_state.redo_stack is state["redo"]
    assert history_state.redo_stack == [state["redo_command"]]
    assert canvas.renderer.style is state["renderer_style"]
    assert canvas.scene().sceneRect() == state["scene_rect"]
    assert canvas.sceneRect() == state["view_rect"]
    assert canvas.transform() == state["view_transform"]
    assert canvas.scene().signalsBlocked() is state["scene_signals_blocked"]

    insert_state = service.insert_state
    assert insert_state is state["insert_state"]
    for name, (original_container, original_contents) in state[
        "insert_containers"
    ].items():
        assert getattr(insert_state, name) is original_container
        assert getattr(insert_state, name) == original_contents
    for name, original_value in state["insert_values"].items():
        assert getattr(insert_state, name) is original_value

    hover_state = hover_state_for(canvas)
    assert hover_state is state["hover_state"]
    original_hover_items, original_hover_contents = state["hover_items"]
    assert hover_state.items is original_hover_items
    assert hover_state.items == original_hover_contents
    assert (hover_state.style, hover_state.atom_id, hover_state.bond_id) == state[
        "hover_values"
    ]

    rotation = rotation_state_for(canvas)
    assert rotation is state["rotation_state"]
    for name, (original_container, original_contents) in state[
        "rotation_containers"
    ].items():
        assert getattr(rotation, name) is original_container
        assert getattr(rotation, name) == original_contents
    for name, original_value in state["rotation_values"].items():
        assert getattr(rotation, name) == original_value


class _DetachProbeItem:
    def __init__(self, scene, *, parent_error: BaseException | None = None) -> None:
        self._scene = scene
        self._parent_error = parent_error

    def parentItem(self):
        if self._parent_error is not None:
            raise self._parent_error
        return None

    def scene(self):
        return self._scene


class _DetachProbeScene:
    def __init__(self, items: list[_DetachProbeItem], *, remove_result) -> None:
        self._items = items
        self._remove_result = remove_result
        self._signals_blocked = False
        self.remove_calls: list[_DetachProbeItem] = []

    def items(self) -> list[_DetachProbeItem]:
        return list(self._items)

    def signalsBlocked(self) -> bool:
        return self._signals_blocked

    def blockSignals(self, blocked: bool) -> bool:
        previous = self._signals_blocked
        self._signals_blocked = blocked
        return previous

    def removeItem(self, item: _DetachProbeItem):
        self.remove_calls.append(item)
        return self._remove_result


def test_smiles_exact_rollback_runs_once_and_reports_failure() -> None:
    canvas = _FakeCanvas()
    service = _service_for(canvas)
    primary = RuntimeError("load failed")
    restore_error = ValueError("exact restore failed")
    result = RestoreOutcome(
        authoritative=False,
        fallback_to_inverse=False,
        errors=(restore_error,),
    )

    with mock.patch(
        "chemvas.ui.insert_smiles_service.restore_history_transaction_for_history",
        return_value=result,
    ) as restore:
        service._restore_exact_transaction_after_failed_load(
            object(),
            original_error=primary,
        )

    restore.assert_called_once()
    notes = "\n".join(getattr(primary, "__notes__", ()))
    assert "exact restore failed" in notes
    assert "remained non-authoritative" in notes


def test_insert_smiles_service_begin_smiles_insert_uses_callbacks_and_preview_state() -> (
    None
):
    canvas = _FakeCanvas()
    canvas.insert_state.template_active = True
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={
            0: Atom("C", 0.0, 0.0),
            1: Atom("O", 10.0, 0.0),
        }
    )
    cancel_template = mock.Mock()
    render_preview = mock.Mock()
    service = _service_for(
        canvas,
        cancel_template_insert=cancel_template,
        render_smiles_preview=render_preview,
    )

    service.begin_smiles_insert(" CO ")

    cancel_template.assert_called_once_with()
    assert canvas.insert_state.smiles_active
    assert canvas.insert_state.smiles_preview_smiles == "CO"
    assert (
        canvas.insert_state.smiles_preview_center.x(),
        canvas.insert_state.smiles_preview_center.y(),
    ) == (5.0, 0.0)
    assert (
        render_preview.call_args.args[0].x(),
        render_preview.call_args.args[0].y(),
    ) == (60.0, 40.0)


def test_insert_smiles_service_commit_uses_commit_service_and_cancel_callback() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_preview_smiles = "CO"
    canvas.insert_state.smiles_preview_center = QPointF(5.0, 0.0)
    canvas.insert_state.smiles_preview_model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    commit_service = mock.Mock()
    commit_service.apply_smiles_commit.return_value = True
    cancel_smiles = mock.Mock()
    service = _service_for(
        canvas, insert_commit_service=commit_service, cancel_smiles_insert=cancel_smiles
    )

    service.commit_smiles_insert(QPointF(40.0, 20.0))

    commit_service.apply_smiles_commit.assert_called_once()
    assert commit_service.apply_smiles_commit.call_args.kwargs == {
        "after_smiles_input": "CO"
    }
    cancel_smiles.assert_called_once_with()


def test_insert_smiles_service_render_preview_routes_clear_and_apply_paths() -> None:
    canvas = _FakeCanvas()
    canvas.insert_state.smiles_preview_model = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    canvas.insert_state.smiles_preview_center = QPointF(0.0, 0.0)
    clear_smiles_preview = mock.Mock()
    service = _service_for(canvas, clear_smiles_preview=clear_smiles_preview)

    with mock.patch(
        "chemvas.ui.insert_smiles_service.plan_smiles_preview_update",
        return_value=mock.Mock(action="clear", geometry=None),
    ):
        service.render_smiles_preview(QPointF(1.0, 2.0))

    clear_smiles_preview.assert_called_once_with()

    clear_smiles_preview.reset_mock()
    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.plan_smiles_preview_update",
            return_value=mock.Mock(action="update", geometry={"lines": 1}),
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.apply_smiles_preview_geometry_helper",
            return_value=(["items"], {0: ["bond"]}, {0: "atom"}),
        ) as apply_helper,
    ):
        service.render_smiles_preview(QPointF(3.0, 4.0))

    clear_smiles_preview.assert_not_called()
    apply_helper.assert_called_once()
    assert canvas.insert_state.smiles_preview_items == ["items"]
    assert canvas.insert_state.smiles_preview_bond_items == {0: ["bond"]}
    assert canvas.insert_state.smiles_preview_atom_items == {0: "atom"}


def test_load_smiles_clears_detached_highlight_and_pending_selection_info() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    try:
        service = canvas.services.structure.insert_controller.smiles_service
        old_highlight = QGraphicsRectItem(QRectF(0.0, 0.0, 10.0, 10.0))
        canvas.scene().addItem(old_highlight)

        selection_style = selection_style_state_for(canvas)
        selection_style.selected_items = [old_highlight]
        selection_style.suspend_outline = True
        selection_info = selection_info_state_for(canvas)
        selection_callback = mock.Mock()
        selection_info.callback = selection_callback
        selection_info.signature = (frozenset({7}), frozenset({8}))
        selection_info.pending_signature = (frozenset({7}), frozenset({8}))
        selection_info.cache = ("OLD", "999.99")
        selection_info.rdkit_warmup_pending = True

        idle_timer = canvas.runtime_state.rdkit_idle_timer
        idle_timer.start()
        assert idle_timer.isActive()
        replacement_model = MoleculeModel(atoms={0: Atom("C", 0.0, 0.0)})

        with mock.patch(
            "chemvas.ui.insert_smiles_service.smiles_to_2d_for",
            return_value=replacement_model,
        ):
            service.load_smiles("C")

        assert canvas.model is replacement_model
        assert old_highlight.scene() is None
        assert selection_style.selected_items == []
        assert not selection_style.suspend_outline
        assert selection_info.signature is None
        assert selection_info.pending_signature is None
        assert selection_info.cache == ("", "")
        assert not selection_info.rdkit_warmup_pending
        selection_callback.assert_called_once_with("", "")

        # Reset deliberately leaves timer lifecycle ownership with the bridge.
        # The cleared pending flag makes the very next tick a no-op that stops
        # polling, with no stale RDKit preload or formula computation.
        assert idle_timer.isActive()
        with (
            mock.patch("chemvas.ui.selection_info_access.preload_rdkit_for") as preload,
            mock.patch("chemvas.ui.selection_info_access.compute_props_for") as compute,
        ):
            canvas.runtime_state.rdkit_idle_warmup_bridge.warm_when_idle()
        preload.assert_not_called()
        compute.assert_not_called()
        assert not idle_timer.isActive()
    finally:
        _dispose_canvas(canvas)


def test_load_smiles_success_releases_detached_original_qt_wrappers() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = build_canvas_view()
    try:
        service = canvas.services.structure.insert_controller.smiles_service
        note = canvas.services.interaction.note_controller.create_text_note(
            QPointF(1.0, 2.0),
            "temporary original",
        )
        note_ref = weakref.ref(note)
        replacement_model = MoleculeModel(
            atoms={0: Atom("C", 0.0, 0.0)},
        )

        with mock.patch(
            "chemvas.ui.insert_smiles_service.smiles_to_2d_for",
            return_value=replacement_model,
        ):
            service.load_smiles("C")

        assert note.scene() is None
        assert not sip.isdeleted(note)
        assert note not in note_items_for(canvas)
        assert all(item is not note for item in canvas.scene().items())

        del note
        gc.collect()
        app.processEvents()
        gc.collect()
        assert note_ref() is None
    finally:
        _dispose_canvas(canvas)
