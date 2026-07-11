from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from core.document_state import deserialize_model_state
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMessageBox

from ui.benzene_preview_access import clear_benzene_preview_for
from ui.bond_graphics_access import parallel_bond_segments_for
from ui.canvas_atom_graphics_state import clear_atom_graphics_for
from ui.canvas_bond_graphics_state import clear_bond_graphics_for
from ui.canvas_document_state import (
    restore_document_groups,
    restore_document_post_model_items,
    restore_document_pre_model_items,
    restore_document_projection_state,
    snapshot_canvas_document_state,
)
from ui.canvas_insert_state import CanvasInsertState
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import next_atom_id_for, set_model_for
from ui.canvas_scene_items_state import clear_scene_item_collections_for
from ui.canvas_scene_reset_access import clear_scene_for
from ui.canvas_smiles_input_state import set_last_smiles_input_for
from ui.canvas_window_access import notify_error_for
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
    restore_history_transaction_for_history,
)
from ui.history_restore_retry import restore_history_snapshot_with_retry
from ui.input_view_access import viewport_center_scene_pos_for
from ui.insert_commit_service import InsertCommitService
from ui.insert_mode_logic import InsertSessionState
from ui.insert_mode_logic import begin_smiles_insert as begin_smiles_insert_state
from ui.insert_mode_logic import cancel_smiles_insert as cancel_smiles_insert_state
from ui.insert_smiles_transaction import SmilesLoadTransactionBuilder
from ui.preview_scene_access import (
    apply_smiles_preview_geometry_for as apply_smiles_preview_geometry_helper,
)
from ui.preview_scene_access import (
    clear_smiles_preview_for as clear_smiles_preview_helper,
)
from ui.preview_scene_renderer import (
    smiles_preview_snapshot as smiles_preview_snapshot_helper,
)
from ui.rdkit_adapter_access import rdkit_last_error_for, smiles_to_2d_for
from ui.renderer_style_access import (
    bond_length_px_for,
    bond_line_width_for,
    bond_pen_for,
)
from ui.scene_decoration_access import add_mark_for_atom_for
from ui.scene_item_access import clear_canvas_scene, remove_scene_item
from ui.scene_signal_blocking import blocked_scene_signals
from ui.smiles_insert_logic import (
    SmilesPreviewResolvers,
    annotation_mark_direction,
    annotation_mark_kinds,
    normalized_atom_annotation,
    plan_smiles_commit,
    plan_smiles_preview_update,
    smiles_preview_center,
)

MAX_SMILES_INPUT_LENGTH = 1024
_MISSING_DETACH_PORT = object()
_UNKNOWN_HISTORY_ENABLED = object()


def _capture_optional_detach_port(target: object, name: str) -> object:
    """Read one optional live port without hiding descriptor failures."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_DETACH_PORT)
            is not _MISSING_DETACH_PORT
        ):
            raise
        return _MISSING_DETACH_PORT


@dataclass(frozen=True, slots=True)
class _FrozenLoadHistoryEnabledAuthority:
    value: object
    getter: Callable[[], object] | None
    setter: Callable[[bool], object] | None

    @classmethod
    def capture(cls, history: object) -> _FrozenLoadHistoryEnabledAuthority:
        getter_value = _capture_optional_detach_port(history, "is_enabled")
        setter_value = _capture_optional_detach_port(history, "set_enabled")
        getter = getter_value if callable(getter_value) else None
        setter = setter_value if callable(setter_value) else None
        value = getter() if getter is not None else _UNKNOWN_HISTORY_ENABLED
        return cls(value=value, getter=getter, setter=setter)

    def restore(self, original_error: BaseException) -> bool:
        if self.getter is None or type(self.value) is not bool:
            return True
        try:
            if self.getter() is self.value:
                return True
            if self.setter is None:
                raise RuntimeError("SMILES history enabled policy has no restore port")
            self.setter(self.value)
            if self.getter() is not self.value:
                raise RuntimeError("SMILES history enabled policy was not restored")
        except BaseException as policy_error:
            _add_smiles_load_rollback_note(
                original_error,
                policy_error,
                phase="history policy",
            )
            return False
        return True


@dataclass(frozen=True, slots=True)
class _RootDetachPort:
    item: object
    scene_getter: Callable[[], object]


@dataclass(frozen=True, slots=True)
class _SceneDetachPorts:
    scene: object
    roots: tuple[_RootDetachPort, ...]
    remove_item: Callable[[object], object]
    block_signals: Callable[[bool], object] | None
    signals_blocked: Callable[[], object] | None


def _capture_scene_detach_ports(canvas) -> _SceneDetachPorts | None:
    """Capture the complete non-destructive detach authority before mutation."""

    scene_method = _capture_optional_detach_port(canvas, "scene")
    if scene_method is _MISSING_DETACH_PORT:
        return None
    if not callable(scene_method):
        raise RuntimeError("canvas scene accessor is not callable")
    scene = scene_method()
    if scene is None:
        return None

    items_method = _capture_optional_detach_port(scene, "items")
    if items_method is _MISSING_DETACH_PORT:
        return None
    if not callable(items_method):
        raise RuntimeError("scene items accessor is not callable")
    scene_items = tuple(items_method())

    roots: list[_RootDetachPort] = []
    for item in scene_items:
        parent_method = _capture_optional_detach_port(item, "parentItem")
        if parent_method is _MISSING_DETACH_PORT:
            parent = None
        elif callable(parent_method):
            parent = parent_method()
        else:
            raise RuntimeError("scene item parent accessor is not callable")
        if parent is not None:
            continue

        item_scene_method = _capture_optional_detach_port(item, "scene")
        if not callable(item_scene_method):
            raise RuntimeError("scene root does not expose a membership getter")
        if item_scene_method() is not scene:
            raise RuntimeError("scene root membership changed during detach capture")
        roots.append(
            _RootDetachPort(
                item=item,
                scene_getter=item_scene_method,
            )
        )

    if not roots:
        return None

    remove_item = _capture_optional_detach_port(scene, "removeItem")
    if not callable(remove_item):
        raise RuntimeError("scene does not support non-destructive item detach")

    block_signals = _capture_optional_detach_port(scene, "blockSignals")
    if block_signals is _MISSING_DETACH_PORT:
        bound_block_signals = None
    elif callable(block_signals):
        bound_block_signals = block_signals
    else:
        raise RuntimeError("scene signal-blocking setter is not callable")

    signals_blocked = _capture_optional_detach_port(scene, "signalsBlocked")
    if signals_blocked is _MISSING_DETACH_PORT:
        bound_signals_blocked = None
    elif callable(signals_blocked):
        bound_signals_blocked = signals_blocked
    else:
        raise RuntimeError("scene signal-blocking getter is not callable")

    return _SceneDetachPorts(
        scene=scene,
        roots=tuple(roots),
        remove_item=remove_item,
        block_signals=bound_block_signals,
        signals_blocked=bound_signals_blocked,
    )


def _add_smiles_load_rollback_note(
    original_error: BaseException,
    secondary_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"SMILES {phase} rollback also failed: {secondary_error!r}")
    except BaseException:
        return


def _detach_top_level_scene_items_before_clear(canvas) -> None:
    """Keep live Qt item identities outside a destructive scene clear.

    The exact history transaction already owns strong references to every
    scene item.  Detaching only the roots removes the whole parent/child tree
    from the scene without destroying its C++ objects, so an exact rollback
    can reattach those same wrappers.  The roots are collected completely
    before the first removal so a getter failure cannot leave a partial tree.
    """

    ports = _capture_scene_detach_ports(canvas)
    if ports is None or not ports.roots:
        return

    def detach_roots() -> None:
        for root in ports.roots:
            result = ports.remove_item(root.item)
            if result is False:
                raise RuntimeError("scene item detach operation reported failure")
            if root.scene_getter() is ports.scene:
                raise RuntimeError("scene item remained attached after detach")

    if ports.block_signals is not None:
        with blocked_scene_signals(
            ports.scene,
            block_signals=ports.block_signals,
            signals_blocked=ports.signals_blocked,
        ):
            detach_roots()
        return
    detach_roots()


class InsertSmilesService:
    def __init__(
        self,
        canvas,
        *,
        insert_state: CanvasInsertState,
        insert_commit_service: InsertCommitService,
        graph_service,
        structure_build_service,
        history_service,
        session_state: Callable[[], InsertSessionState],
        apply_session_state: Callable[[InsertSessionState], None],
        cancel_template_insert: Callable[[], None],
        cancel_smiles_insert=None,
        clear_smiles_preview=None,
        render_smiles_preview=None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state
        self.insert_commit_service = insert_commit_service
        self.graph_service = graph_service
        self.structure_build_service = structure_build_service
        self.history = history_service
        self._session_state = session_state
        self._apply_session_state = apply_session_state
        self._cancel_template_insert = cancel_template_insert
        self._cancel_smiles_insert_callback = cancel_smiles_insert
        self._clear_smiles_preview_callback = clear_smiles_preview
        self._render_smiles_preview_callback = render_smiles_preview
        self.transaction_builder = SmilesLoadTransactionBuilder(canvas)

    def _warn_smiles_error(self, message: str) -> None:
        if not notify_error_for(self.canvas, f"SMILES: {message}"):
            QMessageBox.warning(self.canvas, "SMILES Error", message)

    def _reject_oversized_smiles(self, smiles: str) -> bool:
        if len(smiles) <= MAX_SMILES_INPUT_LENGTH:
            return False
        self._warn_smiles_error(
            f"SMILES input is too long (maximum {MAX_SMILES_INPUT_LENGTH} characters)."
        )
        return True

    def load_smiles(self, smiles: str) -> None:
        smiles = smiles.strip()
        if not smiles:
            return
        if self._reject_oversized_smiles(smiles):
            return
        model = smiles_to_2d_for(
            self.canvas, smiles, scale=bond_length_px_for(self.canvas)
        )
        if model is None:
            self._warn_smiles_error(
                rdkit_last_error_for(self.canvas) or "Failed to render SMILES."
            )
            return
        if self.structure_build_service is None:
            raise RuntimeError("structure_build_service is required to load SMILES")
        document_snapshot = snapshot_canvas_document_state(self.canvas)
        snapshot = self.transaction_builder.capture()
        after_clear_next_atom_id = next_atom_id_for(self.canvas)
        added_scene_items: list[object] = []
        command = None
        document_mutation_started = False

        def build_load_command():
            if added_scene_items:
                return self.transaction_builder.build_command(
                    snapshot,
                    after_clear_next_atom_id=after_clear_next_atom_id,
                    after_smiles_input=smiles,
                    added_scene_items=added_scene_items,
                )
            return self.transaction_builder.build_command(
                snapshot,
                after_clear_next_atom_id=after_clear_next_atom_id,
                after_smiles_input=smiles,
            )

        exact_transaction = capture_history_transaction_for_history(
            self.canvas,
            history_service=self.history,
        )
        try:
            _detach_top_level_scene_items_before_clear(self.canvas)
            # From here onward clear_scene_for may mutate the document before
            # raising.  A detach failure above needs exact-only restoration:
            # running the legacy document rebuild while an original root is
            # still attached would destroy the wrapper we are preserving.
            document_mutation_started = True
            clear_scene_for(self.canvas)
            after_clear_next_atom_id = next_atom_id_for(self.canvas)
            set_model_for(self.canvas, model)
            self.graph_service.rebuild_bond_adjacency()
            set_last_smiles_input_for(self.canvas, smiles)
            self.structure_build_service.render_model()
            self._add_annotation_marks(model, added_scene_items)
            command = build_load_command()
            if command is not None:
                self._push_load_history_verified(command)
            release_history_transaction_for_history(
                self.canvas,
                exact_transaction,
            )
        except BaseException as error:
            if document_mutation_started:
                self._restore_document_state_after_failed_load(
                    document_snapshot,
                    added_scene_items,
                    exact_transaction=exact_transaction,
                    original_error=error,
                )
            else:
                self._restore_exact_transaction_after_failed_detach(
                    exact_transaction,
                    original_error=error,
                )
            raise

    def _push_load_history_verified(self, command: object) -> None:
        enabled_authority = _FrozenLoadHistoryEnabledAuthority.capture(self.history)
        try:
            result = self.history.push(command)
        except BaseException as original_error:
            enabled_authority.restore(original_error)
            raise
        if result is not False:
            return
        if enabled_authority.value is False:
            # Disabled history is an explicit policy: the loaded document is
            # valid but intentionally has no undo entry.
            disabled_result = RuntimeError(
                "SMILES history push returned False while explicitly disabled"
            )
            if not enabled_authority.restore(disabled_result):
                raise disabled_result
            return
        # False from an enabled or unknown history service is a rejected
        # publication.  Raising here keeps the exact transaction active so the
        # owning load failure path restores the original document and stacks.
        rejection = RuntimeError(
            "SMILES history push was rejected while history was enabled"
        )
        enabled_authority.restore(rejection)
        raise rejection

    def begin_smiles_insert(self, smiles: str) -> None:
        if self.insert_state.template_active:
            self._cancel_template_insert()
        clear_benzene_preview_for(self.canvas)
        smiles = smiles.strip()
        if not smiles:
            return
        if self._reject_oversized_smiles(smiles):
            return
        model = smiles_to_2d_for(
            self.canvas, smiles, scale=bond_length_px_for(self.canvas)
        )
        if model is None:
            self._warn_smiles_error(
                rdkit_last_error_for(self.canvas) or "Failed to render SMILES."
            )
            return
        self.insert_state.smiles_preview_model = model
        center_xy = smiles_preview_center(model)
        if center_xy is None:
            self.insert_state.smiles_preview_model = None
            return
        next_state = begin_smiles_insert_state(self._session_state(), smiles, center_xy)
        if next_state is None:
            self.insert_state.smiles_preview_model = None
            return
        self._apply_session_state(next_state)
        self._render_smiles_preview(viewport_center_scene_pos_for(self.canvas))

    def _render_smiles_preview(self, pos: QPointF) -> None:
        if self._render_smiles_preview_callback is not None:
            self._render_smiles_preview_callback(pos)
            return
        self.render_smiles_preview(pos)

    def cancel_smiles_insert(self) -> None:
        self.insert_state.smiles_preview_model = None
        next_state = cancel_smiles_insert_state(self._session_state())
        self._apply_session_state(next_state)

    def commit_smiles_insert(self, pos: QPointF) -> None:
        plan = plan_smiles_commit(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (
                self.insert_state.smiles_preview_center.x(),
                self.insert_state.smiles_preview_center.y(),
            ),
            (pos.x(), pos.y()),
        )
        if plan is None:
            self._cancel_smiles_insert()
            return
        if not self.insert_commit_service.apply_smiles_commit(
            plan,
            after_smiles_input=self.insert_state.smiles_preview_smiles,
        ):
            self._cancel_smiles_insert()
            return
        self._cancel_smiles_insert()

    def _cancel_smiles_insert(self) -> None:
        if self._cancel_smiles_insert_callback is not None:
            self._cancel_smiles_insert_callback()
            return
        self.cancel_smiles_insert()

    def clear_smiles_preview(self) -> None:
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = clear_smiles_preview_helper(
            self.canvas, self.insert_state.smiles_preview_items
        )

    def smiles_preview_snapshot(self):
        return smiles_preview_snapshot_helper(
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        )

    def render_smiles_preview(self, pos: QPointF) -> None:
        atom_radius = max(0.6, bond_line_width_for(self.canvas) * 0.6)
        preview_plan = plan_smiles_preview_update(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (
                self.insert_state.smiles_preview_center.x(),
                self.insert_state.smiles_preview_center.y(),
            ),
            (pos.x(), pos.y()),
            atom_radius,
            self.smiles_preview_snapshot(),
            SmilesPreviewResolvers(
                parallel_bond_segments=lambda *args: parallel_bond_segments_for(
                    self.canvas, *args
                )
            ),
        )
        if preview_plan.action == "clear" or preview_plan.geometry is None:
            self._clear_smiles_preview()
            return
        (
            self.insert_state.smiles_preview_items,
            self.insert_state.smiles_preview_bond_items,
            self.insert_state.smiles_preview_atom_items,
        ) = apply_smiles_preview_geometry_helper(
            self.canvas,
            preview_plan.geometry,
            base_pen=bond_pen_for(self.canvas),
            existing_items=self.insert_state.smiles_preview_items,
            existing_bond_items=self.insert_state.smiles_preview_bond_items,
            existing_atom_items=self.insert_state.smiles_preview_atom_items,
            action=preview_plan.action,
        )

    def _clear_smiles_preview(self) -> None:
        if self._clear_smiles_preview_callback is not None:
            self._clear_smiles_preview_callback()
            return
        self.clear_smiles_preview()

    def _add_annotation_marks(
        self, model, added: list[object] | None = None
    ) -> list[object]:
        if added is None:
            added = []
        atom_annotations = getattr(model, "atom_annotations", {})
        for atom_id, annotation in atom_annotations.items():
            atom = model.atoms.get(atom_id)
            if atom is None:
                continue
            annotation_values = normalized_atom_annotation(annotation)
            for index, kind in enumerate(annotation_mark_kinds(annotation_values)):
                direction_x, direction_y = annotation_mark_direction(index)
                item = add_mark_for_atom_for(
                    self.canvas,
                    atom_id,
                    QPointF(atom.x + direction_x, atom.y + direction_y),
                    kind=kind,
                    record=False,
                )
                if item is not None:
                    added.append(item)
        return added

    def _restore_document_state_after_failed_load(
        self,
        state: dict,
        added_scene_items: list[object],
        *,
        exact_transaction: object,
        original_error: BaseException,
    ) -> None:
        rollback_errors: list[BaseException] = []

        def run(operation: Callable[[], object]) -> None:
            try:
                operation()
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)

        for item in reversed(added_scene_items):
            run(partial(remove_scene_item, self.canvas, item))
        run(lambda: clear_scene_for(self.canvas))
        run(lambda: clear_canvas_scene(self.canvas))
        run(lambda: clear_scene_item_collections_for(self.canvas))
        run(lambda: mark_registry_for(self.canvas).clear())
        run(lambda: clear_atom_graphics_for(self.canvas))
        run(lambda: clear_bond_graphics_for(self.canvas))
        run(lambda: set_model_for(self.canvas, deserialize_model_state(state["model"])))
        run(
            lambda: set_last_smiles_input_for(
                self.canvas, state.get("last_smiles_input")
            )
        )
        run(self.graph_service.rebuild_bond_adjacency)
        run(lambda: restore_document_pre_model_items(self.canvas, state))
        run(lambda: restore_document_projection_state(self.canvas, state))
        run(self.structure_build_service.render_model)
        run(lambda: restore_document_post_model_items(self.canvas, state))
        run(lambda: restore_document_groups(self.canvas, state))
        restore_result = restore_history_snapshot_with_retry(
            lambda: restore_history_transaction_for_history(
                self.canvas,
                exact_transaction,
            ),
            description="SMILES document transaction",
        )
        rollback_errors.extend(restore_result.errors)
        if not restore_result.authoritative:
            rollback_errors.append(
                RuntimeError(
                    "SMILES document exact rollback remained non-authoritative"
                )
            )
        for secondary_error in rollback_errors:
            _add_smiles_load_rollback_note(
                original_error,
                secondary_error,
                phase="document",
            )

    def _restore_exact_transaction_after_failed_detach(
        self,
        exact_transaction: object,
        *,
        original_error: BaseException,
    ) -> None:
        restore_result = restore_history_snapshot_with_retry(
            lambda: restore_history_transaction_for_history(
                self.canvas,
                exact_transaction,
            ),
            description="SMILES detach transaction",
        )
        rollback_errors: tuple[BaseException, ...] = restore_result.errors
        if not restore_result.authoritative:
            rollback_errors = (
                *rollback_errors,
                RuntimeError("SMILES detach exact rollback remained non-authoritative"),
            )
        for secondary_error in rollback_errors:
            _add_smiles_load_rollback_note(
                original_error,
                secondary_error,
                phase="detach",
            )


__all__ = ["MAX_SMILES_INPUT_LENGTH", "InsertSmilesService"]
