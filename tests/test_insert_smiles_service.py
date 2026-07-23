from __future__ import annotations

import gc
import os
import weakref
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from chemvas.core.history import HistoryTransactionRestoreResult
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
    _detach_top_level_scene_items_before_clear,
)
from chemvas.ui.selection_info_state import selection_info_state_for
from chemvas.ui.selection_style_state import selection_style_state_for
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QPointF, QRectF
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsRectItem,
    QGraphicsScene,
)

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


class _BrokenAddNoteInterrupt(KeyboardInterrupt):
    def add_note(self, _note: str) -> None:
        raise SystemExit("add_note failed")


def test_smiles_detach_propagates_live_descriptor_attribute_error_before_mutation() -> (
    None
):
    class BrokenSceneCanvas:
        @property
        def scene(self):
            raise AttributeError("live canvas scene descriptor failed")

    with pytest.raises(AttributeError, match="scene descriptor failed"):
        _detach_top_level_scene_items_before_clear(BrokenSceneCanvas())

    scene = _DetachProbeScene([], remove_result=None)

    class BrokenParentDescriptorItem(_DetachProbeItem):
        @property
        def parentItem(self):
            raise AttributeError("live parent descriptor failed")

    item = BrokenParentDescriptorItem(scene)
    scene._items.append(item)
    canvas = mock.Mock()
    canvas.scene.return_value = scene

    with pytest.raises(AttributeError, match="parent descriptor failed"):
        _detach_top_level_scene_items_before_clear(canvas)

    assert scene.remove_calls == []


@pytest.mark.parametrize("restore_path", ["detach", "document"])
@pytest.mark.parametrize("second_authoritative", [True, False])
def test_smiles_exact_rollback_retries_and_reports_authority(
    restore_path: str,
    second_authoritative: bool,
) -> None:
    canvas = _FakeCanvas()
    service = _service_for(canvas)
    primary = KeyboardInterrupt(f"{restore_path} failed")
    first_error = SystemExit("first exact restore failed")
    results = iter(
        (
            HistoryTransactionRestoreResult(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(first_error,),
            ),
            HistoryTransactionRestoreResult(
                authoritative=second_authoritative,
                fallback_to_inverse=False,
            ),
        )
    )

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.restore_history_transaction_for_history",
            side_effect=lambda *_args: next(results),
        ) as restore,
        mock.patch(
            "chemvas.ui.insert_smiles_service.deserialize_model_state",
            return_value=MoleculeModel(),
        ),
    ):
        if restore_path == "detach":
            service._restore_exact_transaction_after_failed_detach(
                object(),
                original_error=primary,
            )
        else:
            service._restore_document_state_after_failed_load(
                {"model": {}},
                [],
                exact_transaction=object(),
                original_error=primary,
            )

    assert restore.call_count == 2
    notes = "\n".join(getattr(primary, "__notes__", ()))
    assert "first exact restore failed" in notes
    if second_authoritative:
        assert "remained non-authoritative" not in notes
    else:
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


def test_load_smiles_next_atom_id_exit_precedes_exact_scene_guard() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    scene = QGraphicsScene()
    scene.addRect(QRectF(0.0, 0.0, 10.0, 10.0))
    canvas = _FakeCanvas()
    canvas._scene = scene
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch.object(
            service.transaction_builder, "capture", return_value=object()
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.next_atom_id_for",
            side_effect=SystemExit("next atom id capture terminated"),
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            side_effect=lambda *_args, **_kwargs: SceneRectSnapshot.capture(scene),
        ) as capture,
        pytest.raises(SystemExit, match="next atom id capture terminated"),
    ):
        service.load_smiles("C")

    capture.assert_not_called()
    tracker = getattr(scene, "_chemvas_scene_rect_tracker", None)
    assert tracker is None or tracker.depth == 0
    far = scene.addRect(QRectF(10_000.0, 0.0, 10.0, 10.0))
    assert scene.sceneRect().right() > 10_000.0
    scene.removeItem(far)


@pytest.mark.parametrize("enabled_port", [True, None], ids=["enabled", "unknown"])
def test_load_smiles_false_history_push_rolls_back_when_not_explicitly_disabled(
    enabled_port: bool | None,
) -> None:
    canvas = _FakeCanvas()
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)
    push = mock.Mock(return_value=False)
    service.history = (
        type(
            "EnabledHistory",
            (),
            {"push": push, "is_enabled": lambda self: enabled_port},
        )()
        if enabled_port is not None
        else type("UnknownHistory", (), {"push": push})()
    )
    command = object()
    exact_transaction = object()
    service.transaction_builder.capture = mock.Mock(return_value=object())
    service.transaction_builder.build_command = mock.Mock(return_value=command)

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            return_value=exact_transaction,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.release_history_transaction_for_history"
        ) as release,
        mock.patch(
            "chemvas.ui.insert_smiles_service._detach_top_level_scene_items_before_clear"
        ),
        mock.patch("chemvas.ui.insert_smiles_service.clear_scene_for"),
        mock.patch("chemvas.ui.insert_smiles_service.next_atom_id_for", return_value=0),
        mock.patch("chemvas.ui.insert_smiles_service.set_model_for"),
        mock.patch("chemvas.ui.insert_smiles_service.set_last_smiles_input_for"),
        mock.patch.object(
            service,
            "_restore_document_state_after_failed_load",
        ) as restore,
        pytest.raises(RuntimeError, match="push was rejected"),
    ):
        service.load_smiles("C")

    push.assert_called_once_with(command)
    release.assert_not_called()
    restore.assert_called_once()
    assert restore.call_args.kwargs["exact_transaction"] is exact_transaction
    assert isinstance(restore.call_args.kwargs["original_error"], RuntimeError)


def test_load_smiles_false_history_push_is_allowed_when_explicitly_disabled() -> None:
    canvas = _FakeCanvas()
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)
    push = mock.Mock(return_value=False)
    service.history = type(
        "DisabledHistory",
        (),
        {"push": push, "is_enabled": lambda self: False},
    )()
    command = object()
    exact_transaction = object()
    service.transaction_builder.capture = mock.Mock(return_value=object())
    service.transaction_builder.build_command = mock.Mock(return_value=command)

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            return_value=exact_transaction,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.release_history_transaction_for_history"
        ) as release,
        mock.patch(
            "chemvas.ui.insert_smiles_service._detach_top_level_scene_items_before_clear"
        ),
        mock.patch("chemvas.ui.insert_smiles_service.clear_scene_for"),
        mock.patch("chemvas.ui.insert_smiles_service.next_atom_id_for", return_value=0),
        mock.patch("chemvas.ui.insert_smiles_service.set_model_for"),
        mock.patch("chemvas.ui.insert_smiles_service.set_last_smiles_input_for"),
        mock.patch.object(
            service,
            "_restore_document_state_after_failed_load",
        ) as restore,
    ):
        service.load_smiles("C")

    push.assert_called_once_with(command)
    restore.assert_not_called()
    release.assert_called_once_with(canvas, exact_transaction)


def test_load_smiles_freezes_enabled_policy_before_rejected_push() -> None:
    canvas = _FakeCanvas()
    service = _service_for(canvas)

    class SelfDisablingHistory:
        def __init__(self) -> None:
            self.enabled = True

        def is_enabled(self) -> bool:
            return self.enabled

        def set_enabled(self, enabled: bool) -> None:
            self.enabled = enabled

        def push(self, _command) -> bool:
            self.enabled = False
            return False

    history = SelfDisablingHistory()
    service.history = history

    with pytest.raises(RuntimeError, match="push was rejected"):
        service._push_load_history_verified(object())

    assert history.enabled is True


@pytest.mark.parametrize(
    "remove_result", [None, False], ids=["no-op", "reported-failure"]
)
def test_load_smiles_aborts_before_destructive_clear_when_root_detach_does_not_complete(
    remove_result,
) -> None:
    canvas = _FakeCanvas()
    scene = _DetachProbeScene([], remove_result=remove_result)
    root = _DetachProbeItem(scene)
    scene._items.append(root)
    canvas._scene = scene
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)
    exact_transaction = object()
    restore_result = HistoryTransactionRestoreResult(authoritative=True)

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch.object(
            service.transaction_builder, "capture", return_value=object()
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            return_value=exact_transaction,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.restore_history_transaction_for_history",
            return_value=restore_result,
        ) as restore_exact,
        pytest.raises(RuntimeError, match="detach"),
    ):
        service.load_smiles("C")

    assert scene.remove_calls == [root]
    assert root.scene() is scene
    assert not scene.signalsBlocked()
    canvas.clear_scene.assert_not_called()
    restore_exact.assert_called_once_with(canvas, exact_transaction)


def test_load_smiles_collects_every_root_before_first_detach() -> None:
    canvas = _FakeCanvas()
    scene = _DetachProbeScene([], remove_result=None)
    first_root = _DetachProbeItem(scene)
    deleted_child = _DetachProbeItem(
        scene,
        parent_error=RuntimeError("deleted child parent lookup"),
    )
    scene._items.extend((first_root, deleted_child))
    canvas._scene = scene
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)
    exact_transaction = object()
    restore_result = HistoryTransactionRestoreResult(authoritative=True)

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch.object(
            service.transaction_builder, "capture", return_value=object()
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            return_value=exact_transaction,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.restore_history_transaction_for_history",
            return_value=restore_result,
        ) as restore_exact,
        pytest.raises(RuntimeError, match="deleted child parent lookup"),
    ):
        service.load_smiles("C")

    assert scene.remove_calls == []
    assert first_root.scene() is scene
    assert deleted_child.scene() is scene
    canvas.clear_scene.assert_not_called()
    restore_exact.assert_called_once_with(canvas, exact_transaction)


def test_load_smiles_detach_rollback_note_failure_preserves_primary_exception() -> None:
    canvas = _FakeCanvas()
    canvas.rdkit.smiles_to_2d.return_value = MoleculeModel(
        atoms={0: Atom("C", 0.0, 0.0)}
    )
    service = _service_for(canvas)
    exact_transaction = object()
    primary_error = _BrokenAddNoteInterrupt("detach interrupted")
    secondary_error = RuntimeError("exact restore failed")
    restore_result = HistoryTransactionRestoreResult(
        authoritative=True,
        errors=(secondary_error,),
    )

    with (
        mock.patch(
            "chemvas.ui.insert_smiles_service.snapshot_canvas_document_state",
            return_value={},
        ),
        mock.patch.object(
            service.transaction_builder, "capture", return_value=object()
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.capture_history_transaction_for_history",
            return_value=exact_transaction,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service._detach_top_level_scene_items_before_clear",
            side_effect=primary_error,
        ),
        mock.patch(
            "chemvas.ui.insert_smiles_service.restore_history_transaction_for_history",
            return_value=restore_result,
        ),
        pytest.raises(_BrokenAddNoteInterrupt) as caught,
    ):
        service.load_smiles("C")

    assert caught.value is primary_error
    canvas.clear_scene.assert_not_called()


@pytest.mark.parametrize(
    ("failure_stage", "failure_type"),
    [
        pytest.param("clear", KeyboardInterrupt, id="clear-keyboard-interrupt"),
        pytest.param("clear", SystemExit, id="clear-system-exit"),
        pytest.param("render", SystemExit, id="restore-render-system-exit"),
        pytest.param("push", KeyboardInterrupt, id="history-push-keyboard-interrupt"),
        pytest.param("release", SystemExit, id="exact-release-system-exit"),
    ],
)
def test_load_smiles_preserves_live_qt_document_identity_across_base_exceptions_and_retry(
    failure_stage: str,
    failure_type: type[BaseException],
) -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView()
    try:
        service = canvas.services.structure.insert_controller.smiles_service
        state = _live_canvas_load_snapshot(canvas, service)
        replacement_model = MoleculeModel(
            atoms={0: Atom("C", 0.0, 0.0)},
        )

        def fail() -> None:
            raise failure_type(f"{failure_stage} interrupted")

        if failure_stage == "clear":
            original_clear = (
                canvas.services.document.canvas_scene_reset_service.clear_scene
            )

            def clear_then_fail(_canvas) -> None:
                original_clear()
                fail()

            failure_patch = mock.patch(
                "chemvas.ui.insert_smiles_service.clear_scene_for",
                side_effect=clear_then_fail,
            )
        elif failure_stage == "render":
            original_render = service.structure_build_service.render_model

            def render_then_fail() -> None:
                original_render()
                fail()

            failure_patch = mock.patch.object(
                service.structure_build_service,
                "render_model",
                side_effect=render_then_fail,
            )
        elif failure_stage == "push":
            original_push = service.history.push

            def push_then_fail(command) -> None:
                original_push(command)
                fail()

            failure_patch = mock.patch.object(
                service.history,
                "push",
                side_effect=push_then_fail,
            )
        else:
            from chemvas.ui import insert_smiles_service as service_module

            original_release = service_module.release_history_transaction_for_history

            def release_then_fail(target_canvas, transaction) -> None:
                original_release(target_canvas, transaction)
                fail()

            failure_patch = mock.patch.object(
                service_module,
                "release_history_transaction_for_history",
                side_effect=release_then_fail,
            )

        with (
            mock.patch(
                "chemvas.ui.insert_smiles_service.smiles_to_2d_for",
                return_value=replacement_model,
            ),
            failure_patch,
            pytest.raises(failure_type, match=rf"{failure_stage} interrupted"),
        ):
            service.load_smiles("C")

        _assert_live_canvas_load_snapshot(canvas, service, state)

        retry_model = MoleculeModel(
            atoms={
                0: Atom("C", -10.0, 0.0),
                1: Atom("O", 10.0, 0.0),
            }
        )
        with mock.patch(
            "chemvas.ui.insert_smiles_service.smiles_to_2d_for",
            return_value=retry_model,
        ):
            service.load_smiles("CO")

        note = state["note"]
        assert canvas.model is retry_model
        assert last_smiles_input_for(canvas) == "CO"
        assert note.scene() is None
        assert note not in note_items_for(canvas)
        assert all(item is not note for item in canvas.scene().items())
        assert all(item.scene() is None for item in state["scene_items"])
        assert not service.insert_state.smiles_active
        assert service.insert_state.smiles_preview_items == []
        assert not service.insert_state.template_active
        assert service.insert_state.template_preview_items == []
        assert hover_state_for(canvas).items == []
        assert rotation_state_for(canvas).projection_center_3d is None
        assert rotation_state_for(canvas).projection_anchor_2d is None
        assert service.history.state.history is state["history"]
        assert service.history.state.history[0] is state["history_command"]
        assert len(service.history.state.history) == 2
        assert service.history.state.redo_stack is state["redo"]
        assert service.history.state.redo_stack == []
    finally:
        _dispose_canvas(canvas)


def test_load_smiles_clears_detached_highlight_and_pending_selection_info() -> None:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    canvas = CanvasView()
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
    canvas = CanvasView()
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
