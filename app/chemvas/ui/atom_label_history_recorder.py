from __future__ import annotations

import inspect
from dataclasses import dataclass
from types import MemberDescriptorType
from typing import cast

from chemvas.core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
    UpdateBondCommand,
)
from chemvas.ui.canvas_history_recording_service import (
    CallbackFreeHistoryBaseline,
    CanvasHistoryRecordingService,
)
from chemvas.ui.canvas_model_access import bond_for_id, next_atom_id_for
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from chemvas.ui.history_commands import ChangeAtomLabelCommand
from chemvas.ui.history_push_failure_recovery import recover_failed_recording_push
from chemvas.ui.scene_item_state import bond_state_dict
from chemvas.ui.transactions.history_command import HistoryCommandSnapshot

_MISSING_HISTORY_STATE = object()


def _release_failed_label_history_snapshot(
    canvas,
    snapshot: object | None,
    original_error: BaseException,
) -> None:
    try:
        release_history_transaction_for_history(canvas, snapshot)
    except BaseException as release_error:
        try:
            original_error.add_note(
                "Atom-label history snapshot release also encountered "
                f"{type(release_error).__name__}: {release_error}"
            )
        except BaseException:
            return


def _recover_failed_label_history_transaction(
    canvas,
    command: HistoryCommand,
    original_error: BaseException,
    *,
    phase: str,
    command_snapshot: HistoryCommandSnapshot | None,
    after_runtime_snapshot: object | None,
) -> None:
    """Release first, then make the frozen runtime/inverse the final writer.

    Snapshot release can cross scene-rect/view callbacks.  Retrying release
    after recovery would let one of those callbacks contaminate the restored
    canvas as the final writer, so finish every release attempt before
    reasserting the exact after-runtime and applying the command inverse.
    """

    _release_failed_label_history_snapshot(
        canvas,
        after_runtime_snapshot,
        original_error,
    )
    recover_failed_recording_push(
        canvas,
        command,
        None,
        original_error,
        phase=phase,
        command_snapshot=command_snapshot,
        after_runtime_snapshot=after_runtime_snapshot,
    )


def _restore_lightweight_publication_after_failure(
    publication: _LightweightHistoryPublication | None,
    original_error: BaseException,
) -> None:
    if publication is None:
        return
    try:
        publication.restore_baseline()
    except BaseException as restore_error:
        try:
            original_error.add_note(
                "Atom-label lightweight publication restore also encountered "
                f"{type(restore_error).__name__}: {restore_error}"
            )
        except BaseException:
            return


@dataclass(frozen=True, slots=True)
class _LightweightPublicationPort:
    owner: object
    name: str
    namespace: dict | None
    descriptor: MemberDescriptorType | None
    present: bool
    value: object

    def current(self) -> object:
        if self.namespace is not None:
            return dict.get(
                self.namespace,
                self.name,
                _MISSING_HISTORY_STATE,
            )
        descriptor = self.descriptor
        if descriptor is None:
            return _MISSING_HISTORY_STATE
        try:
            return descriptor.__get__(self.owner, type(self.owner))
        except AttributeError:
            return _MISSING_HISTORY_STATE

    def restore(self) -> None:
        if self.namespace is not None:
            if self.present:
                dict.__setitem__(self.namespace, self.name, self.value)
            else:
                self.namespace.pop(self.name, None)
            return
        descriptor = self.descriptor
        if descriptor is None:
            raise RuntimeError(
                "lightweight history publication has no raw restore port"
            )
        if self.present:
            descriptor.__set__(self.owner, self.value)
            return
        try:
            descriptor.__delete__(self.owner)
        except AttributeError:
            return

    def is_exact(self) -> bool:
        current = self.current()
        if not self.present:
            return current is _MISSING_HISTORY_STATE
        return current is self.value


class _LightweightHistoryPublication:
    """Expected fake-canvas publication excluded from runtime verification."""

    def __init__(
        self,
        commands: list | None,
        items: tuple[object, ...],
        ports: tuple[_LightweightPublicationPort, ...],
    ) -> None:
        self.commands = commands
        self.items = items
        self.ports = ports

    @classmethod
    def capture(
        cls,
        canvas,
        history: object,
    ) -> _LightweightHistoryPublication | None:
        ports: list[_LightweightPublicationPort] = []

        def capture_owner(owner: object, names: tuple[str, ...]) -> None:
            try:
                namespace_value = object.__getattribute__(owner, "__dict__")
            except (AttributeError, TypeError):
                namespace = None
            else:
                namespace = (
                    namespace_value if isinstance(namespace_value, dict) else None
                )
            if namespace is not None:
                for name in names:
                    present = name in namespace
                    value = (
                        dict.__getitem__(namespace, name)
                        if present
                        else _MISSING_HISTORY_STATE
                    )
                    ports.append(
                        _LightweightPublicationPort(
                            owner,
                            name,
                            namespace,
                            None,
                            present,
                            value,
                        )
                    )

            seen_descriptors: set[int] = set()
            for owner_type in type(owner).__mro__:
                for name in names:
                    descriptor = owner_type.__dict__.get(name)
                    if (
                        type(descriptor) is not MemberDescriptorType
                        or id(descriptor) in seen_descriptors
                    ):
                        continue
                    seen_descriptors.add(id(descriptor))
                    member = cast(MemberDescriptorType, descriptor)
                    try:
                        value = member.__get__(owner, type(owner))
                    except AttributeError:
                        present = False
                        value = _MISSING_HISTORY_STATE
                    else:
                        present = True
                    ports.append(
                        _LightweightPublicationPort(
                            owner,
                            name,
                            None,
                            member,
                            present,
                            value,
                        )
                    )

        capture_owner(canvas, ("pushed_commands",))
        capture_owner(
            history,
            ("pushed_commands", "_pushed_commands", "commands", "_commands"),
        )
        by_identity = {
            id(port.value): port.value
            for port in ports
            if port.present and isinstance(port.value, list)
        }
        if len(by_identity) > 1:
            raise RuntimeError(
                "ambiguous lightweight history publication list authorities"
            )
        if not ports:
            return None
        commands = cast(list, next(iter(by_identity.values()))) if by_identity else None
        authority = cls(
            commands,
            tuple(list.__iter__(commands)) if commands is not None else (),
            tuple(ports),
        )
        authority.verify_baseline()
        return authority

    @staticmethod
    def _same_items(actual: tuple[object, ...], expected: tuple[object, ...]) -> bool:
        return len(actual) == len(expected) and all(
            item is expected_item
            for item, expected_item in zip(actual, expected, strict=True)
        )

    def verify_baseline(self) -> None:
        if any(not port.is_exact() for port in self.ports):
            raise RuntimeError("lightweight history publication root changed")
        if self.commands is not None and not self._same_items(
            tuple(list.__iter__(self.commands)),
            self.items,
        ):
            raise RuntimeError("lightweight history publication changed early")

    def verify_published(self, command: HistoryCommand) -> None:
        if any(not port.is_exact() for port in self.ports):
            raise RuntimeError("lightweight history publication root changed")
        if self.commands is None:
            raise RuntimeError(
                "enabled stateless atom-label history has no exact "
                "publication authority"
            )
        expected = (*self.items, command)
        if not self._same_items(tuple(list.__iter__(self.commands)), expected):
            raise RuntimeError("lightweight history publication was not exact")

    def restore_baseline(self) -> None:
        for ports in (self.ports, tuple(reversed(self.ports))):
            for port in ports:
                port.restore()
            if self.commands is not None:
                list.__setitem__(self.commands, slice(None), self.items)
            try:
                self.verify_baseline()
            except BaseException:
                continue
            return
        raise RuntimeError("lightweight history publication could not be restored")

    def verify_runtime_after_publication(
        self,
        command: HistoryCommand,
        runtime_verify,
    ) -> tuple[BaseException, ...]:
        # An enabled lightweight service has no stack snapshot, so this raw
        # list is its only publication authority.  A truthy/implicit push
        # result cannot substitute for proving that the exact command was
        # appended once.
        self.verify_published(command)
        assert self.commands is not None
        try:
            list.__setitem__(self.commands, slice(None), self.items)
            return tuple(runtime_verify())
        finally:
            list.__setitem__(self.commands, slice(None), (*self.items, command))
            self.verify_published(command)


class AtomLabelHistoryRecorder:
    def __init__(self, canvas, *, history_service) -> None:
        self.canvas = canvas
        self.history = history_service

    def _push_or_rollback(self, command: HistoryCommand) -> None:
        # A dynamic ``__getattr__`` state over ``_state`` must use the exact
        # stack/runtime publication path. Stateless lightweight services retain
        # their explicit ``is_enabled`` policy, but that live callback is
        # crossed only inside an exact after-runtime savepoint.
        static_state_is_missing = (
            inspect.getattr_static(
                self.history,
                "state",
                _MISSING_HISTORY_STATE,
            )
            is _MISSING_HISTORY_STATE
        )
        if static_state_is_missing:
            command_snapshot: HistoryCommandSnapshot | None = None
            lightweight_publication: _LightweightHistoryPublication | None = None
            try:
                lightweight_publication = _LightweightHistoryPublication.capture(
                    self.canvas,
                    self.history,
                )
                command_snapshot = HistoryCommandSnapshot.capture(command)
                raw_baseline = CallbackFreeHistoryBaseline.capture(
                    self.history,
                    canvas=self.canvas,
                )
            except BaseException as original_error:
                _restore_lightweight_publication_after_failure(
                    lightweight_publication,
                    original_error,
                )
                try:
                    recover_failed_recording_push(
                        self.canvas,
                        command,
                        None,
                        original_error,
                        phase="atom-label history routing",
                        command_snapshot=command_snapshot,
                    )
                finally:
                    _restore_lightweight_publication_after_failure(
                        lightweight_publication,
                        original_error,
                    )
                raise
            if raw_baseline is not None:
                CanvasHistoryRecordingService(
                    self.canvas,
                    history_service=self.history,
                ).push_history(command)
                return

            after_runtime_snapshot: object | None = None
            try:
                after_runtime_snapshot = capture_history_transaction_for_history(
                    self.canvas,
                    history_service=None,
                    guard_scene_rect=False,
                )
                runtime_verify = getattr(
                    after_runtime_snapshot,
                    "verify_exact",
                    None,
                )
                if not callable(runtime_verify):
                    raise RuntimeError(
                        "stateless atom-label history policy has no exact "
                        "runtime verifier"
                    )
                initial_runtime_errors = tuple(runtime_verify())
                if initial_runtime_errors:
                    raise BaseExceptionGroup(
                        "stateless atom-label history policy did not capture an "
                        "exact after-runtime",
                        list(initial_runtime_errors),
                    )
                if lightweight_publication is not None:
                    lightweight_publication.verify_baseline()
                history_enabled = bool(self.history.is_enabled())
                command_snapshot.verify()
                policy_runtime_errors = tuple(runtime_verify())
                if policy_runtime_errors:
                    raise BaseExceptionGroup(
                        "stateless atom-label history policy changed the canvas "
                        "runtime",
                        list(policy_runtime_errors),
                    )
                if lightweight_publication is not None:
                    lightweight_publication.verify_baseline()
                command_snapshot.verify()
            except BaseException as original_error:
                _restore_lightweight_publication_after_failure(
                    lightweight_publication,
                    original_error,
                )
                try:
                    _recover_failed_label_history_transaction(
                        self.canvas,
                        command,
                        original_error,
                        phase="atom-label stateless history policy",
                        command_snapshot=command_snapshot,
                        after_runtime_snapshot=after_runtime_snapshot,
                    )
                finally:
                    _restore_lightweight_publication_after_failure(
                        lightweight_publication,
                        original_error,
                    )
                raise
            if not history_enabled:
                try:
                    release_history_transaction_for_history(
                        self.canvas,
                        after_runtime_snapshot,
                    )
                    released_runtime_errors = tuple(runtime_verify())
                    if released_runtime_errors:
                        raise BaseExceptionGroup(
                            "stateless atom-label history policy release changed "
                            "the canvas runtime",
                            list(released_runtime_errors),
                        )
                    if lightweight_publication is not None:
                        lightweight_publication.verify_baseline()
                except BaseException as original_error:
                    _restore_lightweight_publication_after_failure(
                        lightweight_publication,
                        original_error,
                    )
                    try:
                        _recover_failed_label_history_transaction(
                            self.canvas,
                            command,
                            original_error,
                            phase="atom-label disabled history release",
                            command_snapshot=command_snapshot,
                            after_runtime_snapshot=after_runtime_snapshot,
                        )
                    finally:
                        _restore_lightweight_publication_after_failure(
                            lightweight_publication,
                            original_error,
                        )
                    raise
                return
            try:
                if (
                    lightweight_publication is None
                    or lightweight_publication.commands is None
                ):
                    raise RuntimeError(
                        "enabled stateless atom-label history has no exact "
                        "publication authority"
                    )
                push_result = self.history.push(command)
                if push_result is False:
                    raise RuntimeError(
                        "atom-label history push was rejected without a provable "
                        "disabled policy"
                    )
                command_snapshot.verify()
                push_runtime_errors = (
                    lightweight_publication.verify_runtime_after_publication(
                        command,
                        runtime_verify,
                    )
                    if lightweight_publication is not None
                    else tuple(runtime_verify())
                )
                if push_runtime_errors:
                    raise BaseExceptionGroup(
                        "stateless atom-label history push changed the canvas runtime",
                        list(push_runtime_errors),
                    )
                release_history_transaction_for_history(
                    self.canvas,
                    after_runtime_snapshot,
                )
                released_runtime_errors = (
                    lightweight_publication.verify_runtime_after_publication(
                        command,
                        runtime_verify,
                    )
                    if lightweight_publication is not None
                    else tuple(runtime_verify())
                )
                if released_runtime_errors:
                    raise BaseExceptionGroup(
                        "stateless atom-label history release changed the canvas runtime",
                        list(released_runtime_errors),
                    )
                command_snapshot.verify()
            except BaseException as original_error:
                _restore_lightweight_publication_after_failure(
                    lightweight_publication,
                    original_error,
                )
                try:
                    _recover_failed_label_history_transaction(
                        self.canvas,
                        command,
                        original_error,
                        phase="atom-label history recording",
                        command_snapshot=command_snapshot,
                        after_runtime_snapshot=after_runtime_snapshot,
                    )
                finally:
                    _restore_lightweight_publication_after_failure(
                        lightweight_publication,
                        original_error,
                    )
                raise
            return
        CanvasHistoryRecordingService(
            self.canvas,
            history_service=self.history,
        ).push_history(command)

    def record_label_change(
        self,
        atom_id: int,
        *,
        before_element: str,
        after_element: str,
        before_explicit_label: bool,
        after_explicit_label: bool,
        before_smiles_input: str | None,
        merge_ids: list[int],
        merge_info: dict,
    ) -> None:
        after_smiles_input = last_smiles_input_for(self.canvas)
        commands: list[HistoryCommand] = []
        if (
            before_element != after_element
            or before_explicit_label != after_explicit_label
            or before_smiles_input != after_smiles_input
        ):
            commands.append(
                ChangeAtomLabelCommand(
                    atom_id=atom_id,
                    before_element=before_element,
                    after_element=after_element,
                    before_explicit_label=before_explicit_label,
                    after_explicit_label=after_explicit_label,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                )
            )
        if merge_ids:
            commands.extend(
                self._merge_history_commands(
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                    merge_info=merge_info,
                )
            )
        if not commands:
            return
        if len(commands) == 1:
            self._push_or_rollback(commands[0])
            return
        self._push_or_rollback(CompositeCommand(commands))

    def _merge_history_commands(
        self,
        *,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
        merge_info: dict,
    ) -> list[HistoryCommand]:
        commands: list[HistoryCommand] = []
        bond_before_states = merge_info.get("bond_before_states", {})
        deleted_bond_ids = set(merge_info.get("deleted_bond_ids", []))
        for bond_id, before_state in bond_before_states.items():
            if bond_id in deleted_bond_ids:
                commands.append(
                    DeleteBondCommand(
                        bond_id=bond_id,
                        bond_state=before_state,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                    )
                )
                continue
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                continue
            after_state = bond_state_dict(bond)
            if before_state != after_state:
                commands.append(
                    UpdateBondCommand(
                        bond_id=bond_id,
                        before_state=before_state,
                        after_state=after_state,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=after_smiles_input,
                    )
                )
        atom_states = merge_info.get("atom_states", {})
        if atom_states:
            commands.append(
                DeleteAtomsCommand(
                    atom_states=atom_states,
                    mark_states=[],
                    before_next_atom_id=next_atom_id_for(self.canvas),
                    after_next_atom_id=next_atom_id_for(self.canvas),
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=after_smiles_input,
                    remove_marks=False,
                    atom_coords_3d=merge_info.get("atom_coords_3d") or None,
                )
            )
        return commands


__all__ = ["AtomLabelHistoryRecorder"]
