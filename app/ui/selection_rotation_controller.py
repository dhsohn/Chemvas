from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF

from ui.atom_coords_access import (
    atom_coords_3d_for,
    current_atom_coords_3d_for,
)
from ui.canvas_model_access import atom_for_id, atoms_for, bond_for_id, bonds_for
from ui.canvas_rotation_state import rotation_state_for
from ui.history_command_snapshot import HistoryCommandSnapshot
from ui.history_stack_snapshot import HistoryStackSnapshot
from ui.selection_collection_access import selected_ids_for
from ui.selection_rotation_access import (
    apply_projected_atom_positions_for,
    average_bond_length_for_atoms_for,
    flatten_planar_fragments_for,
    rotate_point_around_axis_for,
    unproject_scene_point_3d_for,
    update_ring_fills_for_atoms_for,
)
from ui.selection_rotation_geometry import (
    axis_rotated_coords,
    dominant_axis_angle_from_drag,
    rigid_rotated_coords,
    rigid_rotation_angles_from_drag,
)
from ui.selection_rotation_history import build_selection_rotation_command
from ui.selection_rotation_preview_transaction import (
    _RotationPreviewAuthority,
    capture_rotation_preview_authority,
    run_rotation_preview_update,
)
from ui.selection_rotation_session import begin_selection_rotation_session
from ui.selection_scene_access import scene_selected_items_for
from ui.selection_service_access import refresh_selection_outline_for
from ui.selection_style_access import (
    emit_selection_info_for,
    restore_selection_from_ids_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


_MISSING_HISTORY_POLICY = object()


@dataclass(frozen=True, slots=True)
class _HistoryPolicyPort:
    name: str
    present: bool
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]
    deleter: Callable[[], object] | None

    @staticmethod
    def _values_match(actual: object, expected: object) -> bool:
        if actual is expected:
            return True
        if type(actual) is not type(expected):
            return False
        return bool(actual == expected)

    def matches(self, expected: object) -> bool:
        return self._values_match(self.getter(), expected)

    def apply_once(self) -> None:
        if self.matches(self.value):
            return
        if self.present:
            self.setter(self.value)
            return
        if self.deleter is None:
            raise RuntimeError(
                f"rotation history policy {self.name!r} cannot be removed"
            )
        self.deleter()

    def verify(self, expected: object) -> None:
        if not self.matches(expected):
            raise RuntimeError(f"rotation history policy {self.name!r} changed")


@dataclass(frozen=True, slots=True)
class HistoryCheckpoint:
    history_items: tuple[object, ...]
    redo_items: tuple[object, ...]
    enabled: object
    limit: object


@dataclass(slots=True)
class _RotationTransactionToken:
    history_service: object
    begin_bound: bool
    history_push: Callable[[object], object] | None = None
    history_stacks: HistoryStackSnapshot | None = None
    begin_history_checkpoint: HistoryCheckpoint | None = None
    history_policy_ports: tuple[_HistoryPolicyPort, ...] = ()
    preview: _RotationPreviewAuthority | None = None


@dataclass(frozen=True, slots=True)
class _RotationFinalizationAuthority:
    """Immutable capture-bound ports used across finalization callbacks."""

    history_service: object
    history_push: Callable[[object], object]
    history_stacks: HistoryStackSnapshot
    begin_history_checkpoint: HistoryCheckpoint
    history_policy_ports: tuple[_HistoryPolicyPort, ...]
    preview: _RotationPreviewAuthority


def _add_rotation_finalization_rollback_note(
    original_error: BaseException,
    cleanup_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Rotation finalization rollback also failed: {cleanup_error!r}")
    except BaseException:
        return


class SelectionRotationController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        graph_service,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.graph_service = graph_service
        self.rotation = rotation_state_for(canvas)
        self.history = history_service
        self._rotation_transaction: _RotationTransactionToken | None = None
        self._rotation_preview_authority: _RotationPreviewAuthority | None = None
        self._rotation_finalization_authority: _RotationFinalizationAuthority | None = (
            None
        )

    @staticmethod
    def _same_identity_sequence(
        actual: tuple[object, ...],
        expected: tuple[object, ...],
    ) -> bool:
        return len(actual) == len(expected) and all(
            item is expected_item
            for item, expected_item in zip(actual, expected, strict=False)
        )

    @staticmethod
    def _history_checkpoint_for(
        token: _RotationTransactionToken,
    ) -> HistoryCheckpoint | None:
        snapshot = token.history_stacks
        if snapshot is None:
            return None
        policies = {port.name: port.value for port in token.history_policy_ports}
        return HistoryCheckpoint(
            history_items=tuple(snapshot.history_port.iterate()),
            redo_items=tuple(snapshot.redo_port.iterate()),
            enabled=policies["enabled"],
            limit=policies["limit"],
        )

    @staticmethod
    def _capture_history_policy(token: _RotationTransactionToken) -> None:
        snapshot = token.history_stacks
        if snapshot is None:
            raise RuntimeError("rotation requires capture-bound history stacks")
        state = snapshot.state
        getattribute = inspect.getattr_static(
            type(state),
            "__getattribute__",
            _MISSING_HISTORY_POLICY,
        )
        setattribute = inspect.getattr_static(
            type(state),
            "__setattr__",
            _MISSING_HISTORY_POLICY,
        )
        delattribute = inspect.getattr_static(
            type(state),
            "__delattr__",
            _MISSING_HISTORY_POLICY,
        )
        if not callable(getattribute) or not callable(setattribute):
            raise RuntimeError("rotation history policy has incomplete bound ports")
        ports: list[_HistoryPolicyPort] = []
        for name in ("enabled", "limit"):
            present = (
                inspect.getattr_static(
                    state,
                    name,
                    _MISSING_HISTORY_POLICY,
                )
                is not _MISSING_HISTORY_POLICY
            )
            try:
                value = getattribute(state, name)
            except AttributeError:
                if present:
                    raise
                value = _MISSING_HISTORY_POLICY

            def get_value(
                _getattribute=getattribute,
                _state=state,
                _name=name,
                _present=present,
            ) -> object:
                try:
                    return _getattribute(_state, _name)
                except AttributeError:
                    if _present:
                        raise
                    return _MISSING_HISTORY_POLICY

            def set_value(
                policy_value: object,
                _setattribute=setattribute,
                _state=state,
                _name=name,
            ) -> object:
                return _setattribute(_state, _name, policy_value)

            def delete_value(
                _delattribute=delattribute,
                _state=state,
                _name=name,
            ) -> object:
                if not callable(_delattribute):
                    raise RuntimeError(
                        f"rotation history policy {_name!r} cannot be deleted"
                    )
                return _delattribute(_state, _name)

            ports.append(
                _HistoryPolicyPort(
                    name=name,
                    present=present,
                    value=value,
                    getter=get_value,
                    setter=set_value,
                    deleter=delete_value,
                )
            )
        token.history_policy_ports = tuple(ports)

    @staticmethod
    def _expected_history_checkpoint_after_push(
        authority: _RotationFinalizationAuthority,
        command: object,
    ) -> HistoryCheckpoint:
        checkpoint = authority.begin_history_checkpoint
        if checkpoint.enabled is not _MISSING_HISTORY_POLICY and not bool(
            checkpoint.enabled
        ):
            raise RuntimeError("selection rotation history was disabled at begin")
        history_items = [*checkpoint.history_items, command]
        limit = checkpoint.limit
        if isinstance(limit, int) and len(history_items) > limit:
            history_items.pop(0)
        return HistoryCheckpoint(
            history_items=tuple(history_items),
            redo_items=(),
            enabled=checkpoint.enabled,
            limit=checkpoint.limit,
        )

    def _verify_bound_history_authority(
        self,
        token: _RotationTransactionToken,
        *,
        checkpoint: HistoryCheckpoint | None,
    ) -> None:
        snapshot = token.history_stacks
        if snapshot is None:
            return
        snapshot.state_port.verify()
        if snapshot.history_port.getter() is not snapshot.history:
            raise RuntimeError("rotation history-list identity changed")
        if snapshot.redo_port.getter() is not snapshot.redo_stack:
            raise RuntimeError("rotation redo-list identity changed")
        if checkpoint is None:
            return
        actual_history = tuple(snapshot.history_port.iterate())
        actual_redo = tuple(snapshot.redo_port.iterate())
        expected_history = checkpoint.history_items
        expected_redo = checkpoint.redo_items
        if not self._same_identity_sequence(actual_history, expected_history):
            raise RuntimeError("rotation history contents changed outside commit")
        if not self._same_identity_sequence(actual_redo, expected_redo):
            raise RuntimeError("rotation redo contents changed outside commit")
        expected_policies = {
            "enabled": checkpoint.enabled,
            "limit": checkpoint.limit,
        }
        # Policy descriptors are untrusted readers too. Verify policies in both
        # directions and close on capture-bound roots/raw stacks after each
        # order, so the final policy getter cannot poison an earlier policy or
        # stack authority while returning its expected value.
        for ports in (
            token.history_policy_ports,
            tuple(reversed(token.history_policy_ports)),
        ):
            for port in ports:
                port.verify(expected_policies[port.name])
            snapshot.verify_exact_items(
                history_items=expected_history,
                redo_items=expected_redo,
            )

    @staticmethod
    def _restore_history_policy_once(
        policy_ports: tuple[_HistoryPolicyPort, ...],
        *,
        reverse: bool,
    ) -> tuple[BaseException, ...]:
        errors: list[BaseException] = []
        ports = tuple(reversed(policy_ports)) if reverse else policy_ports
        for port in ports:
            try:
                port.apply_once()
            except BaseException as error:
                errors.append(error)
        return tuple(errors)

    @staticmethod
    def _rollback_authority_is_exact(
        snapshot: HistoryStackSnapshot,
        policy_ports: tuple[_HistoryPolicyPort, ...],
    ) -> bool:
        try:
            snapshot.verify_exact_items()
            for ports in (policy_ports, tuple(reversed(policy_ports))):
                for port in ports:
                    port.verify(port.value)
                snapshot.verify_exact_items()
        except BaseException:
            return False
        return True

    @staticmethod
    def _finalization_authority_for(
        token: _RotationTransactionToken,
        *,
        preview: _RotationPreviewAuthority | None = None,
    ) -> _RotationFinalizationAuthority:
        history_push = token.history_push
        history_stacks = token.history_stacks
        checkpoint = token.begin_history_checkpoint
        bound_preview = token.preview if preview is None else preview
        if not callable(history_push):
            raise RuntimeError("Selection rotation lost its bound push port")
        if history_stacks is None or checkpoint is None:
            raise RuntimeError("Selection rotation lost its history authority")
        if bound_preview is None:
            raise RuntimeError("Selection rotation has no runtime authority")
        return _RotationFinalizationAuthority(
            history_service=token.history_service,
            history_push=history_push,
            history_stacks=history_stacks,
            begin_history_checkpoint=checkpoint,
            history_policy_ports=token.history_policy_ports,
            preview=bound_preview,
        )

    def _publish_finalization_authority(
        self,
        token: _RotationTransactionToken,
        preview: _RotationPreviewAuthority,
    ) -> _RotationFinalizationAuthority:
        authority = self._finalization_authority_for(token, preview=preview)
        self._rotation_finalization_authority = authority
        return authority

    def _verify_finalization_token(
        self,
        token: _RotationTransactionToken,
        authority: _RotationFinalizationAuthority,
    ) -> None:
        if token.history_service is not authority.history_service:
            raise RuntimeError("selection rotation token history owner changed")
        if token.history_push is not authority.history_push:
            raise RuntimeError("selection rotation token push port changed")
        if token.history_stacks is not authority.history_stacks:
            raise RuntimeError("selection rotation token stack authority changed")
        if token.begin_history_checkpoint is not authority.begin_history_checkpoint:
            raise RuntimeError("selection rotation token checkpoint changed")
        if token.history_policy_ports is not authority.history_policy_ports:
            raise RuntimeError("selection rotation token policy authority changed")
        if token.preview is not authority.preview:
            raise RuntimeError("selection rotation token preview authority changed")

    def _ensure_rotation_owner(
        self,
        token: _RotationTransactionToken,
        *,
        checkpoint: HistoryCheckpoint | None,
        phase: str,
        require_preview: bool = True,
    ) -> None:
        if self._rotation_transaction is not token:
            raise RuntimeError(f"selection rotation owner changed while {phase}")
        if self.history is not token.history_service:
            raise RuntimeError(
                f"selection rotation history owner changed while {phase}"
            )
        if require_preview:
            preview = token.preview
            if preview is None or self._rotation_preview_authority is not preview:
                raise RuntimeError(
                    f"selection rotation preview owner changed while {phase}"
                )
        self._verify_bound_history_authority(
            token,
            checkpoint=checkpoint,
        )

    def _reserve_rotation_transaction(
        self,
        *,
        begin_bound: bool,
    ) -> _RotationTransactionToken:
        if self._rotation_transaction is not None:
            raise RuntimeError("A selection rotation transaction is already active")
        history_service = self.history
        token = _RotationTransactionToken(
            history_service=history_service,
            begin_bound=begin_bound,
        )
        # Publish the reservation before reading any live history descriptor.
        # Re-entrant callbacks must not be able to start an unseen owner B.
        self._rotation_transaction = token
        try:
            history_push = getattr(history_service, "push", None)
            if not callable(history_push):
                raise AttributeError(
                    "Selection rotation requires a callable bound history push port"
                )
            token.history_push = history_push
            token.history_stacks = HistoryStackSnapshot.capture(history_service)
            if token.history_stacks is None:
                raise RuntimeError(
                    "Selection rotation requires exact mutable history stacks"
                )
            self._capture_history_policy(token)
            token.begin_history_checkpoint = self._history_checkpoint_for(token)
            self._ensure_rotation_owner(
                token,
                checkpoint=token.begin_history_checkpoint,
                phase="capturing its begin history authority",
                require_preview=False,
            )
        except BaseException:
            if self._rotation_transaction is token:
                self._rotation_transaction = None
            raise
        return token

    def _capture_rotation_preview_for_token(
        self,
        token: _RotationTransactionToken,
        atom_ids: set[int],
        *,
        core_state=None,
    ) -> _RotationPreviewAuthority:
        self._ensure_rotation_owner(
            token,
            checkpoint=token.begin_history_checkpoint,
            phase="capturing its preview authority",
            require_preview=False,
        )
        if self._rotation_preview_authority is not None:
            raise RuntimeError("A rotation preview authority is already active")
        preview = capture_rotation_preview_authority(
            self,
            atom_ids,
            core_state=core_state,
        )
        authority: _RotationFinalizationAuthority | None = None
        try:
            token.preview = preview
            self._rotation_preview_authority = preview
            authority = self._publish_finalization_authority(token, preview)
            self._ensure_rotation_owner(
                token,
                checkpoint=token.begin_history_checkpoint,
                phase="publishing its preview authority",
            )
        except BaseException as original_error:
            try:
                preview.restore(original_error)
            except BaseException as cleanup_error:
                _add_rotation_finalization_rollback_note(
                    original_error,
                    cleanup_error,
                )
            if self._rotation_preview_authority is preview:
                self._rotation_preview_authority = None
            if self._rotation_finalization_authority is authority:
                self._rotation_finalization_authority = None
            try:
                token_preview = token.preview
            except BaseException:
                token_preview = None
            if token_preview is preview:
                token.preview = None
            raise
        return preview

    def _require_rotation_transaction(self) -> _RotationTransactionToken:
        token = self._rotation_transaction
        if token is None:
            token = self._reserve_rotation_transaction(begin_bound=False)
        if token.preview is None:
            existing_preview = self._rotation_preview_authority
            if isinstance(existing_preview, _RotationPreviewAuthority):
                if (
                    existing_preview.controller is not self
                    or existing_preview.atom_ids != frozenset(self.rotation.atom_ids)
                ):
                    raise RuntimeError(
                        "Existing rotation preview has incompatible authority"
                    )
                token.preview = existing_preview
                self._publish_finalization_authority(token, existing_preview)
            else:
                self._capture_rotation_preview_for_token(
                    token,
                    set(self.rotation.atom_ids),
                )
        self._ensure_rotation_owner(
            token,
            checkpoint=token.begin_history_checkpoint,
            phase="requiring its transaction",
        )
        return token

    def _current_rotation_replacement_token(
        self,
        token: _RotationTransactionToken,
    ) -> _RotationTransactionToken | None:
        replacement = self._rotation_transaction
        if replacement is None or replacement is token:
            return None
        if not isinstance(replacement, _RotationTransactionToken):
            raise RuntimeError("replacement rotation owner is incomplete")
        return replacement

    def _reapply_rotation_replacement(
        self,
        token: _RotationTransactionToken,
        original_error: BaseException,
        *,
        preview_authoritative: bool,
        errors: list[BaseException],
    ) -> tuple[_RotationTransactionToken | None, bool]:
        """Make a callback-published owner B the final runtime writer."""

        try:
            replacement_token = self._current_rotation_replacement_token(token)
        except BaseException as replacement_error:
            errors.append(replacement_error)
            return None, False
        if replacement_token is None:
            return None, preview_authoritative
        replacement_preview = replacement_token.preview
        if replacement_preview is None:
            errors.append(RuntimeError("replacement rotation owner has no preview"))
            return replacement_token, False
        try:
            reapplied = replacement_preview.reapply_rolling(original_error)
        except BaseException as restore_error:
            errors.append(restore_error)
            return replacement_token, False
        return replacement_token, reapplied and preview_authoritative

    def _restore_rotation_transaction(
        self,
        token: _RotationTransactionToken,
        original_error: BaseException,
        *,
        authority: _RotationFinalizationAuthority,
    ) -> bool:
        preview = authority.preview
        history_snapshot = authority.history_stacks
        policy_ports = authority.history_policy_ports
        authoritative = False
        for attempt in range(2):
            pass_errors: list[BaseException] = []
            history_authoritative = history_snapshot is None
            preview_authoritative = preview is not None

            def restore_history(
                _attempt: int = attempt,
                _pass_errors: list[BaseException] = pass_errors,
            ) -> None:
                nonlocal history_authoritative
                if history_snapshot is None:
                    return
                try:
                    if _attempt == 0:
                        history_authoritative = history_snapshot.restore(
                            original_error,
                            phase="selection rotation transaction",
                        )
                    else:
                        history_authoritative = history_snapshot.restore_silently(
                            original_error,
                            phase="selection rotation transaction retry",
                        )
                except BaseException as restore_error:
                    _pass_errors.append(restore_error)
                    history_authoritative = False
                policy_errors = self._restore_history_policy_once(
                    policy_ports,
                    reverse=bool(_attempt),
                )
                if policy_errors:
                    _pass_errors.extend(policy_errors)
                    history_authoritative = False

            def restore_preview(
                _pass_errors: list[BaseException] = pass_errors,
            ) -> None:
                nonlocal preview_authoritative
                if preview is None:
                    preview_authoritative = False
                    return
                try:
                    preview_authoritative = preview.restore(original_error)
                except BaseException as restore_error:
                    _pass_errors.append(restore_error)
                    preview_authoritative = False

            if attempt == 0:
                # The history rollback observer is published at most once, then
                # preview is the final writer for the first global pass.
                restore_history()
                restore_preview()
            else:
                # Reverse the independent authorities silently on retry.
                restore_preview()
                restore_history()

            # ``history_snapshot.restore`` publishes its observer before its
            # silent history reassertion. That observer can retire A and create
            # B after this method began, so acquiring B only at method entry is
            # stale. Reacquire after both independent restore writers and make
            # B's rolling checkpoint final without consuming B's transaction.
            replacement_token, preview_authoritative = (
                self._reapply_rotation_replacement(
                    token,
                    original_error,
                    preview_authoritative=preview_authoritative,
                    errors=pass_errors,
                )
            )

            try:
                if not self._rollback_authority_is_exact(
                    history_snapshot,
                    policy_ports,
                ):
                    raise RuntimeError(
                        "rotation rollback history/config changed after preview restore"
                    )
            except BaseException as verify_error:
                pass_errors.append(verify_error)
                history_authoritative = False

            try:
                latest_replacement = self._current_rotation_replacement_token(token)
            except BaseException as replacement_error:
                pass_errors.append(replacement_error)
                latest_replacement = None
                preview_authoritative = False
            if latest_replacement is not replacement_token:
                replacement_token, preview_authoritative = (
                    self._reapply_rotation_replacement(
                        token,
                        original_error,
                        preview_authoritative=preview_authoritative,
                        errors=pass_errors,
                    )
                )
            target_preview = (
                replacement_token.preview
                if replacement_token is not None
                and replacement_token.preview is not None
                else preview
            )
            if target_preview is not None:
                try:
                    target_preview.verify_current_global()
                except BaseException as verify_error:
                    pass_errors.append(verify_error)
                    preview_authoritative = False

            # Scene/preview verification itself can execute Qt or user ports.
            # It therefore cannot be the final reader after history was
            # verified: re-check the bound stacks once more before accepting
            # the combined rollback authority.
            try:
                if not self._rollback_authority_is_exact(
                    history_snapshot,
                    policy_ports,
                ):
                    raise RuntimeError(
                        "rotation rollback history/config changed during preview verification"
                    )
            except BaseException as verify_error:
                pass_errors.append(verify_error)
                history_authoritative = False

            if history_authoritative and preview_authoritative:
                authoritative = True
                for recovered_error in pass_errors:
                    _add_rotation_finalization_rollback_note(
                        original_error,
                        recovered_error,
                    )
                break
            for pass_error in pass_errors:
                _add_rotation_finalization_rollback_note(
                    original_error,
                    pass_error,
                )

        if self._rotation_transaction is token:
            if self._rotation_preview_authority is preview:
                self._rotation_preview_authority = None
            if self._rotation_finalization_authority is authority:
                self._rotation_finalization_authority = None
            token.preview = None
            if not authoritative:
                try:
                    self.rotation.clear_session()
                except BaseException as cleanup_error:
                    _add_rotation_finalization_rollback_note(
                        original_error,
                        cleanup_error,
                    )
                self._rotation_transaction = None
            elif not token.begin_bound:
                # Compatibility sessions that were assembled directly in
                # tests have no real begin boundary. Retry by recapturing the
                # now-authoritative runtime and current history push port.
                self._rotation_transaction = None
            else:
                # Rebuild the retryable owner from the immutable authority; a
                # callback may have deleted/replaced any mutable token field.
                token.history_service = authority.history_service
                token.history_push = authority.history_push
                token.history_stacks = authority.history_stacks
                token.begin_history_checkpoint = authority.begin_history_checkpoint
                token.history_policy_ports = authority.history_policy_ports
        return authoritative

    def selected_ids(self):
        return selected_ids_for(self.canvas)

    def selected_scene_items(self):
        return scene_selected_items_for(self.canvas)

    @property
    def atoms(self):
        return atoms_for(self.canvas)

    @property
    def bonds(self):
        return bonds_for(self.canvas)

    def atom(self, atom_id: int):
        return atom_for_id(self.canvas, atom_id)

    def bond(self, bond_id: int):
        return bond_for_id(self.canvas, bond_id)

    def atom_positions(self, atom_ids: set[int]) -> dict[int, tuple[float, float]]:
        positions = {}
        for atom_id in atom_ids:
            atom = self.atom(atom_id)
            if atom is not None:
                positions[atom_id] = (atom.x, atom.y)
        return positions

    def axis_from_rotation_hint(
        self,
        axis_hint: int,
        rotation_atom_ids: set[int],
        *,
        press_pos: QPointF | None = None,
    ):
        return self.graph_service.axis_from_rotation_hint(
            axis_hint,
            rotation_atom_ids,
            press_pos=press_pos,
        )

    def current_atom_coords_3d(self, atom_id: int):
        return current_atom_coords_3d_for(self.canvas, atom_id)

    def flatten_planar_fragments(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> dict[int, tuple[float, float, float]]:
        return flatten_planar_fragments_for(
            self.canvas,
            atom_ids,
            coords,
            bond_in_cycle=self.graph_service.bond_in_cycle,
        )

    def average_bond_length_for_atoms(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> float | None:
        return average_bond_length_for_atoms_for(self.canvas, atom_ids, coords)

    def unproject_scene_point_3d(
        self,
        point: QPointF,
        z: float,
        *,
        center_3d: tuple[float, float, float],
        anchor_2d: tuple[float, float],
    ) -> tuple[float, float, float]:
        return unproject_scene_point_3d_for(
            self.canvas,
            point,
            z,
            center_3d=center_3d,
            anchor_2d=anchor_2d,
        )

    def apply_projected_atom_positions(
        self,
        atom_ids: set[int],
        coords: dict[int, tuple[float, float, float]],
    ) -> None:
        apply_projected_atom_positions_for(self.canvas, atom_ids, coords)

    def refresh_atom_geometry(self, atom_ids: set[int]) -> None:
        if self.move_controller is not None:
            update_geometries = getattr(
                self.move_controller,
                "update_bond_geometries_for_atoms",
                None,
            )
            if callable(update_geometries):
                # Rotation never changes bond topology.  Updating the existing
                # primitives in place preserves scene membership/stacking and
                # avoids allocate-remove-add churn on every pointer frame.
                update_geometries(atom_ids)
            else:
                self.move_controller.redraw_bonds_for_atoms(atom_ids)
        preview = self._rotation_preview_authority
        if isinstance(
            preview, _RotationPreviewAuthority
        ) and preview.atom_ids == frozenset(atom_ids):
            update_ring_fills_for_atoms_for(
                self.canvas,
                atom_ids,
                ring_items=preview.affected_ring_items,
            )
        else:
            update_ring_fills_for_atoms_for(self.canvas, atom_ids)
        refresh_selection_outline_for(self.canvas)

    def rotate_point_around_axis(self, coords, axis_start, axis_end, angle: float):
        return rotate_point_around_axis_for(
            self.canvas, coords, axis_start, axis_end, angle
        )

    def restore_selection_from_ids(
        self, atom_ids: set[int], bond_ids: set[int]
    ) -> None:
        restore_selection_from_ids_for(self.canvas, atom_ids, bond_ids)

    def emit_selection_info(self) -> None:
        emit_selection_info_for(self.canvas)

    def begin_selection_3d_rotation(
        self,
        axis_hint: int | None = None,
        press_pos: QPointF | None = None,
    ) -> bool:
        token = self._reserve_rotation_transaction(begin_bound=True)

        def publish_preview(begin_snapshot) -> None:
            self._capture_rotation_preview_for_token(
                token,
                set(self.rotation.atom_ids),
                core_state=begin_snapshot.exact_core,
            )

        try:
            rotating = begin_selection_rotation_session(
                self,
                self.rotation,
                axis_hint=axis_hint,
                press_pos=press_pos,
                on_session_started=publish_preview,
            )
        except BaseException:
            authority = self._rotation_finalization_authority
            published_preview = (
                authority.preview
                if authority is not None
                else self._rotation_preview_authority
            )
            if self._rotation_preview_authority is published_preview:
                self._rotation_preview_authority = None
            if authority is not None and authority.preview is published_preview:
                self._rotation_finalization_authority = None
            if self._rotation_transaction is token:
                self._rotation_transaction = None
            raise
        if rotating:
            return True
        authority = self._rotation_finalization_authority
        published_preview = (
            authority.preview
            if authority is not None
            else self._rotation_preview_authority
        )
        if self._rotation_preview_authority is published_preview:
            self._rotation_preview_authority = None
        if authority is not None and authority.preview is published_preview:
            self._rotation_finalization_authority = None
        if self._rotation_transaction is token:
            self._rotation_transaction = None
        return False

    def update_selection_3d_rotation(self, delta_x: float, delta_y: float) -> None:
        state = self.rotation
        if not state.atom_ids:
            return
        if state.mode == "rigid":
            angle_x, angle_y = rigid_rotation_angles_from_drag(delta_x, delta_y)
            if abs(angle_x) < 1e-9 and abs(angle_y) < 1e-9:
                return
            center = state.center_3d
            if center is None:
                return
            next_angle_x = state.free_angle_x + angle_x
            next_angle_y = state.free_angle_y + angle_y

            def update_rigid_preview() -> None:
                state.free_angle_x = next_angle_x
                state.free_angle_y = next_angle_y
                rotated_coords = rigid_rotated_coords(
                    state.atom_ids,
                    state.base_coords,
                    center,
                    angle_x=next_angle_x,
                    angle_y=next_angle_y,
                )
                self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
                self.refresh_atom_geometry(state.atom_ids)

            run_rotation_preview_update(
                self,
                set(state.atom_ids),
                update_rigid_preview,
            )
            return
        if state.axis_atoms is None:
            return
        angle_delta = dominant_axis_angle_from_drag(delta_x, delta_y)
        if abs(angle_delta) < 1e-9:
            return
        axis_a, axis_b = state.axis_atoms
        axis_start = state.base_coords.get(axis_a)
        axis_end = state.base_coords.get(axis_b)
        if axis_start is None or axis_end is None:
            return
        next_total_angle = state.total_angle + angle_delta

        def update_axis_preview() -> None:
            state.total_angle = next_total_angle
            rotated_coords = axis_rotated_coords(
                state.atom_ids,
                state.base_coords,
                axis_start,
                axis_end,
                next_total_angle,
                rotate_point=self.rotate_point_around_axis,
            )
            self.apply_projected_atom_positions(state.atom_ids, rotated_coords)
            self.refresh_atom_geometry(state.atom_ids)

        run_rotation_preview_update(
            self,
            set(state.atom_ids),
            update_axis_preview,
        )

    def end_selection_3d_rotation(self) -> None:
        token = self._rotation_transaction
        command_snapshot: HistoryCommandSnapshot | None = None
        # Acquire the controller-owned frozen authority before reading or
        # validating any mutable token field. A callback may have deleted those
        # fields after preview publication, but it cannot erase this local.
        authority = self._rotation_finalization_authority
        try:
            token = self._require_rotation_transaction()
            if authority is None:
                authority = self._rotation_finalization_authority
            if authority is None:
                raise RuntimeError(
                    "Selection rotation lost its published finalization authority"
                )
            preview = authority.preview
            self._verify_finalization_token(token, authority)
            self._ensure_rotation_owner(
                token,
                checkpoint=token.begin_history_checkpoint,
                phase="starting finalization",
            )
            state = self.rotation
            selection_ids = state.selection_ids
            rotated_atoms = set(state.atom_ids)
            before_positions = dict(state.start_positions)
            before_coords_3d = dict(state.start_coords_3d)
            before_projection_center_3d = state.start_projection_center_3d
            before_projection_anchor_2d = state.start_projection_anchor_2d
            current_coords_3d = atom_coords_3d_for(self.canvas)
            after_coords_3d = {
                atom_id: current_coords_3d[atom_id]
                for atom_id in state.coord_atom_ids
                if atom_id in current_coords_3d
            }
            after_projection_center_3d = state.projection_center_3d
            after_projection_anchor_2d = state.projection_anchor_2d
            after_positions = self.atom_positions(rotated_atoms)
            command = build_selection_rotation_command(
                before_positions=before_positions,
                after_positions=after_positions,
                before_coords_3d=before_coords_3d,
                after_coords_3d=after_coords_3d,
                before_projection_center_3d=before_projection_center_3d,
                after_projection_center_3d=after_projection_center_3d,
                before_projection_anchor_2d=before_projection_anchor_2d,
                after_projection_anchor_2d=after_projection_anchor_2d,
            )
            post_history_checkpoint = token.begin_history_checkpoint
            if command is not None:
                command_snapshot = HistoryCommandSnapshot.capture(command)
                history_push = authority.history_push
                push_result = history_push(command)
                if push_result is False:
                    raise RuntimeError(
                        "Selection rotation history push did not commit its command"
                    )
                post_history_checkpoint = self._expected_history_checkpoint_after_push(
                    authority, command
                )
                command_snapshot.verify()
            self._verify_finalization_token(token, authority)
            self._ensure_rotation_owner(
                token,
                checkpoint=post_history_checkpoint,
                phase="publishing its history command",
            )
            if selection_ids is not None:
                self.restore_selection_from_ids(*selection_ids)
                self._ensure_rotation_owner(
                    token,
                    checkpoint=post_history_checkpoint,
                    phase="restoring its selection",
                )
                self._verify_finalization_token(token, authority)
            self.emit_selection_info()
            self._ensure_rotation_owner(
                token,
                checkpoint=post_history_checkpoint,
                phase="emitting its selection information",
            )
            self._verify_finalization_token(token, authority)
            expected_final = preview.capture_final_publication()
            self._ensure_rotation_owner(
                token,
                checkpoint=post_history_checkpoint,
                phase="capturing its final selection publication",
            )
            self._verify_finalization_token(token, authority)
            preview.verify_current_global(expected_final)

            # Clear only after every fallible callback and bound owner/root
            # verification. A fail-after/no-op clear remains rollback-safe.
            state.clear_session()
            self._ensure_rotation_owner(
                token,
                checkpoint=post_history_checkpoint,
                phase="clearing its session",
            )
            self._verify_finalization_token(token, authority)
            if state.atom_ids or state.selection_ids is not None:
                raise RuntimeError("Selection rotation session did not clear")
            if command_snapshot is not None:
                # Selection/status and history policy verification are live
                # callback boundaries. Close successful publication on the
                # original command object and its frozen payload after all of
                # them, not only on the matching runtime preview.
                command_snapshot.verify()

            preview.release()
            # No external callback is invoked after release. These direct CAS
            # writes are therefore the final publication of a successful A.
            if self._rotation_transaction is not token:
                raise RuntimeError("Selection rotation owner changed before release")
            if self._rotation_preview_authority is not preview:
                raise RuntimeError("Selection rotation preview changed before release")
            if self._rotation_finalization_authority is not authority:
                raise RuntimeError(
                    "Selection rotation finalization authority changed before release"
                )
            self._rotation_preview_authority = None
            self._rotation_finalization_authority = None
            token.preview = None
            self._rotation_transaction = None
        except BaseException as error:
            if command_snapshot is not None:
                command_snapshot.restore()
            if token is not None and authority is not None:
                self._restore_rotation_transaction(
                    token,
                    error,
                    authority=authority,
                )
            raise


__all__ = ["SelectionRotationController"]
