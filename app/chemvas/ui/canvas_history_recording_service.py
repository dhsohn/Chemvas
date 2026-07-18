from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from types import MemberDescriptorType
from typing import Any, cast

from chemvas.core.history import (
    AddAtomsCommand,
    AddBondCommand,
    CompositeCommand,
    HistoryCommand,
    UpdateBondCommand,
)
from chemvas.domain.transactions import HistoryAuthoritySnapshot
from chemvas.ui.atom_coords_access import atom_coords_3d_for
from chemvas.ui.canvas_model_access import (
    atom_for_id,
    bond_count_for,
    bond_for_id,
    next_atom_id_for,
)
from chemvas.ui.canvas_smiles_input_state import last_smiles_input_for
from chemvas.ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
)
from chemvas.ui.history_commands import AddSceneItemsCommand
from chemvas.ui.history_push_failure_recovery import (
    RecordingHistoryPolicySnapshot,
    _verify_history_and_policy_authority,
    recover_failed_recording_push,
)
from chemvas.ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from chemvas.ui.transactions.history_command import HistoryCommandSnapshot

_MISSING_RAW_HISTORY_ROOT = object()


@dataclass(frozen=True, slots=True)
class _CallbackFreeHistoryAliasPort:
    """Identity-only canvas/history alias captured without custom accessors."""

    label: str
    owner: object
    owner_namespace: dict | None
    name: str
    value: object
    slot_descriptor: MemberDescriptorType | None = None

    @classmethod
    def capture(
        cls,
        owner: object,
        name: str,
        *,
        label: str,
    ) -> _CallbackFreeHistoryAliasPort | None:
        try:
            namespace = object.__getattribute__(owner, "__dict__")
        except (AttributeError, TypeError):
            namespace = None
        # Public canvas/service aliases can be properties implemented by an
        # extension.  ``object.__getattribute__`` still invokes those
        # descriptors, so it is not callback-free and can mutate history
        # before its raw items are frozen. Prefer the exact public storage,
        # then a conventional private backing field. Dataclass ``slots`` are
        # safe when read through their captured built-in member descriptor.
        for storage_name in (name, f"_{name}"):
            if isinstance(namespace, dict) and storage_name in namespace:
                return cls(
                    label,
                    owner,
                    namespace,
                    storage_name,
                    dict.__getitem__(namespace, storage_name),
                )
            descriptor = inspect.getattr_static(
                owner,
                storage_name,
                _MISSING_RAW_HISTORY_ROOT,
            )
            if type(descriptor) is not MemberDescriptorType:
                continue
            try:
                value = descriptor.__get__(owner, type(owner))
            except AttributeError:
                continue
            return cls(
                label,
                owner,
                None,
                storage_name,
                value,
                descriptor,
            )
        return None

    def _current(self) -> object:
        if self.owner_namespace is not None:
            return dict.get(
                self.owner_namespace,
                self.name,
                _MISSING_RAW_HISTORY_ROOT,
            )
        descriptor = self.slot_descriptor
        if descriptor is None:
            return _MISSING_RAW_HISTORY_ROOT
        if (
            inspect.getattr_static(
                self.owner,
                self.name,
                _MISSING_RAW_HISTORY_ROOT,
            )
            is not descriptor
        ):
            return _MISSING_RAW_HISTORY_ROOT
        try:
            return descriptor.__get__(self.owner, type(self.owner))
        except AttributeError:
            return _MISSING_RAW_HISTORY_ROOT

    def verify(self) -> None:
        if self._current() is not self.value:
            raise RuntimeError(f"{self.label} identity changed")

    def restore(self) -> None:
        if self.owner_namespace is not None:
            dict.__setitem__(self.owner_namespace, self.name, self.value)
            return
        descriptor = self.slot_descriptor
        if descriptor is None:
            raise RuntimeError(f"{self.label} has no callback-free restore port")
        descriptor.__set__(self.owner, self.value)


@dataclass(frozen=True, slots=True)
class _CallbackFreeHistoryAliases:
    ports: tuple[_CallbackFreeHistoryAliasPort, ...]

    @classmethod
    def capture(
        cls,
        canvas: object | None,
        history: object,
        state: object,
    ) -> _CallbackFreeHistoryAliases:
        if canvas is None:
            return cls(())
        ports: list[_CallbackFreeHistoryAliasPort] = []

        def expected_port(
            owner: object,
            name: str,
            expected: object,
            *,
            label: str,
        ) -> _CallbackFreeHistoryAliasPort | None:
            port = _CallbackFreeHistoryAliasPort.capture(
                owner,
                name,
                label=label,
            )
            if port is not None and port.value is not expected:
                raise RuntimeError(f"{label} differed at history capture")
            return port

        bound_to_canvas = False
        for root_name in ("runtime_state", "services"):
            root_port = _CallbackFreeHistoryAliasPort.capture(
                canvas,
                root_name,
                label=f"canvas {root_name} root",
            )
            if root_port is None or root_port.value is None:
                continue
            nested: list[_CallbackFreeHistoryAliasPort] = []
            service_port = _CallbackFreeHistoryAliasPort.capture(
                root_port.value,
                "history_service",
                label=f"canvas {root_name} history service alias",
            )
            # A caller may intentionally inject an alternate history service
            # without installing it on the canvas. Only aliases already bound
            # to this publication are part of its authority.
            if service_port is None or service_port.value is not history:
                continue
            nested.append(service_port)
            bound_to_canvas = True
            if root_name == "runtime_state":
                state_port = expected_port(
                    root_port.value,
                    "history_state",
                    state,
                    label="canvas runtime_state history state alias",
                )
                if state_port is not None:
                    nested.append(state_port)
            if nested:
                ports.append(root_port)
                ports.extend(nested)

        canvas_port = _CallbackFreeHistoryAliasPort.capture(
            history,
            "canvas",
            label="history service canvas alias",
        )
        if canvas_port is not None:
            if canvas_port.value is not canvas:
                raise RuntimeError(
                    "history service canvas alias differed at history capture"
                )
            ports.append(canvas_port)
            bound_to_canvas = True

        direct_service = _CallbackFreeHistoryAliasPort.capture(
            canvas,
            "history_service",
            label="canvas history service alias",
        )
        if direct_service is not None and direct_service.value is history:
            ports.append(direct_service)
            bound_to_canvas = True

        if bound_to_canvas:
            direct_state = expected_port(
                canvas,
                "history_state",
                state,
                label="canvas history state alias",
            )
            if direct_state is not None:
                ports.append(direct_state)
        authority = cls(tuple(ports))
        authority.verify()
        return authority

    def verify(self) -> None:
        for ports in (self.ports, tuple(reversed(self.ports))):
            for port in ports:
                port.verify()

    def restore(self) -> None:
        errors: list[BaseException] = []
        for ports in (self.ports, tuple(reversed(self.ports))):
            try:
                for port in ports:
                    port.restore()
                self.verify()
            except BaseException as error:
                errors.append(error)
                continue
            return
        raise BaseExceptionGroup("history alias restore failed", errors)


@dataclass(frozen=True, slots=True)
class CallbackFreeHistoryBaseline:
    """Raw pre-publication history roots captured without descriptor callbacks."""

    service_namespace: dict
    service_state_key: str
    state_namespace: dict
    state: object
    state_history_key: str
    state_redo_key: str
    history: list
    redo_stack: list
    history_items: tuple[object, ...]
    redo_items: tuple[object, ...]
    policy_values: tuple[tuple[str, str | None, object], ...]
    aliases: _CallbackFreeHistoryAliases

    @classmethod
    def capture(
        cls,
        service: object | None,
        *,
        canvas: object | None = None,
    ) -> CallbackFreeHistoryBaseline | None:
        if service is None:
            return None
        try:
            service_namespace = object.__getattribute__(service, "__dict__")
        except (AttributeError, TypeError):
            return None
        if not isinstance(service_namespace, dict):
            return None

        # The production service stores ``state`` directly, while compatible
        # descriptor-backed services commonly expose a property over ``_state``.
        # Inspect every raw candidate before invoking any live state getter. A
        # direct decoy plus a distinct backing state (or public/private stack
        # pairs on one state) is ambiguous and therefore cannot be used as a
        # transaction authority.
        candidates: list[tuple[str, object, dict, str, str, list, list]] = []
        for key, candidate in tuple(dict.items(service_namespace)):
            try:
                candidate_namespace = object.__getattribute__(candidate, "__dict__")
            except (AttributeError, TypeError):
                continue
            if not isinstance(candidate_namespace, dict):
                continue
            history_roots = tuple(
                (name, value)
                for name in ("history", "_history")
                if isinstance(
                    value := dict.get(
                        candidate_namespace,
                        name,
                        _MISSING_RAW_HISTORY_ROOT,
                    ),
                    list,
                )
            )
            redo_roots = tuple(
                (name, value)
                for name in ("redo_stack", "_redo_stack")
                if isinstance(
                    value := dict.get(
                        candidate_namespace,
                        name,
                        _MISSING_RAW_HISTORY_ROOT,
                    ),
                    list,
                )
            )
            for state_history_key, history in history_roots:
                for state_redo_key, redo_stack in redo_roots:
                    if history is redo_stack:
                        continue
                    candidates.append(
                        (
                            key,
                            candidate,
                            candidate_namespace,
                            state_history_key,
                            state_redo_key,
                            history,
                            redo_stack,
                        )
                    )
        if not candidates:
            return None

        candidate_groups: dict[
            tuple[int, int, int],
            list[tuple[str, object, dict, str, str, list, list]],
        ] = {}
        for candidate in candidates:
            _key, state, _namespace, _history_key, _redo_key, history, redo = candidate
            candidate_groups.setdefault(
                (id(state), id(history), id(redo)),
                [],
            ).append(candidate)
        if len(candidate_groups) != 1:
            raise RuntimeError("ambiguous callback-free history stack backings")

        equivalent_candidates = next(iter(candidate_groups.values()))
        # Prefer the conventional public keys when several raw aliases all bind
        # the same state and built-in list roots.
        equivalent_candidates.sort(
            key=lambda value: (
                value[0] != "state",
                value[3] != "history",
                value[4] != "redo_stack",
            )
        )
        (
            service_state_key,
            state,
            state_namespace,
            state_history_key,
            state_redo_key,
            history,
            redo_stack,
        ) = equivalent_candidates[0]
        # Freeze raw stacks and policy before resolving any canvas/service
        # aliases. Alias capture must never be allowed to redefine the
        # transaction baseline, even if a future alias port regresses and
        # crosses a callback boundary.
        history_items = tuple(list.__iter__(history))
        redo_items = tuple(list.__iter__(redo_stack))
        policy_values: list[tuple[str, str | None, object]] = []
        for public_name in ("enabled", "limit"):
            roots = tuple(
                (
                    candidate_name,
                    dict.__getitem__(state_namespace, candidate_name),
                )
                for candidate_name in (public_name, f"_{public_name}")
                if candidate_name in state_namespace
            )
            if len(roots) > 1:
                raise RuntimeError(
                    "ambiguous callback-free history policy backing for "
                    f"{public_name!r}"
                )
            if roots:
                storage_name, value = roots[0]
                policy_values.append((public_name, storage_name, value))
            else:
                policy_values.append((public_name, None, _MISSING_RAW_HISTORY_ROOT))
        raw_baseline = cls(
            service_namespace=service_namespace,
            service_state_key=service_state_key,
            state_namespace=state_namespace,
            state=state,
            state_history_key=state_history_key,
            state_redo_key=state_redo_key,
            history=history,
            redo_stack=redo_stack,
            history_items=history_items,
            redo_items=redo_items,
            policy_values=tuple(policy_values),
            aliases=_CallbackFreeHistoryAliases(()),
        )
        baseline = raw_baseline
        try:
            aliases = _CallbackFreeHistoryAliases.capture(canvas, service, state)
            baseline = cls(
                service_namespace=service_namespace,
                service_state_key=service_state_key,
                state_namespace=state_namespace,
                state=state,
                state_history_key=state_history_key,
                state_redo_key=state_redo_key,
                history=history,
                redo_stack=redo_stack,
                history_items=history_items,
                redo_items=redo_items,
                policy_values=tuple(policy_values),
                aliases=aliases,
            )
            baseline.verify()
        except BaseException as original_error:
            try:
                baseline.restore()
            except BaseException as restore_error:
                try:
                    original_error.add_note(
                        "Callback-free history baseline capture restore also "
                        "failed with "
                        f"{type(restore_error).__name__}: {restore_error}"
                    )
                except BaseException:
                    pass
            raise
        return baseline

    @staticmethod
    def _same_items(actual: tuple[object, ...], expected: tuple[object, ...]) -> bool:
        return len(actual) == len(expected) and all(
            item is expected_item
            for item, expected_item in zip(actual, expected, strict=True)
        )

    def _verify_expected_items(
        self,
        *,
        history_items: tuple[object, ...],
        redo_items: tuple[object, ...],
    ) -> None:
        self.aliases.verify()
        if dict.get(self.service_namespace, self.service_state_key) is not self.state:
            raise RuntimeError("raw history service state identity changed")
        if dict.get(self.state_namespace, self.state_history_key) is not self.history:
            raise RuntimeError("raw history-list identity changed")
        if dict.get(self.state_namespace, self.state_redo_key) is not self.redo_stack:
            raise RuntimeError("raw redo-list identity changed")
        if not self._same_items(
            tuple(list.__iter__(self.history)),
            history_items,
        ):
            raise RuntimeError("raw history stack contents changed")
        if not self._same_items(
            tuple(list.__iter__(self.redo_stack)),
            redo_items,
        ):
            raise RuntimeError("raw redo stack contents changed")
        for public_name, storage_name, expected in self.policy_values:
            roots = tuple(
                (
                    candidate_name,
                    dict.__getitem__(self.state_namespace, candidate_name),
                )
                for candidate_name in (public_name, f"_{public_name}")
                if candidate_name in self.state_namespace
            )
            if storage_name is None:
                exact = not roots
            else:
                exact = (
                    len(roots) == 1
                    and roots[0][0] == storage_name
                    and (
                        roots[0][1] is expected
                        or (
                            type(roots[0][1]) is type(expected)
                            and roots[0][1] == expected
                        )
                    )
                )
            if not exact:
                raise RuntimeError(f"raw history policy {public_name!r} changed")
        self.aliases.verify()

    def verify(self) -> None:
        self._verify_expected_items(
            history_items=self.history_items,
            redo_items=self.redo_items,
        )

    def bind_snapshot(
        self,
        history_snapshot: HistoryAuthoritySnapshot,
        policy_snapshot: RecordingHistoryPolicySnapshot | None,
    ) -> None:
        """Bind live snapshot ports to the callback-free backing authority."""

        if history_snapshot.state is not self.state:
            raise RuntimeError(
                "live history state did not match its callback-free backing"
            )
        if history_snapshot.history is not self.history:
            raise RuntimeError(
                "live history stack did not match its callback-free backing"
            )
        if history_snapshot.redo_stack is not self.redo_stack:
            raise RuntimeError(
                "live redo stack did not match its callback-free backing"
            )
        raw_policies = {
            public_name: expected
            for public_name, storage_name, expected in self.policy_values
            if storage_name is not None
            and inspect.getattr_static(
                self.state,
                public_name,
                _MISSING_RAW_HISTORY_ROOT,
            )
            is not _MISSING_RAW_HISTORY_ROOT
        }
        live_policies = (
            {port.name: port.value for port in policy_snapshot.ports}
            if policy_snapshot is not None
            else {}
        )
        if raw_policies.keys() != live_policies.keys():
            raise RuntimeError(
                "live history policy ports did not match callback-free backing"
            )
        for name, expected in raw_policies.items():
            actual = live_policies[name]
            if actual is expected:
                continue
            if type(actual) is not type(expected) or actual != expected:
                raise RuntimeError(
                    f"live history policy {name!r} did not match callback-free backing"
                )
        self.verify()

    def verify_published_commands(
        self,
        publications: tuple[tuple[HistoryCommand, bool], ...],
    ) -> None:
        expected_history = list(self.history_items)
        expected_redo = self.redo_items
        policy_values = {
            public_name: expected
            for public_name, storage_name, expected in self.policy_values
            if storage_name is not None
        }
        limit = policy_values.get("limit")
        for command, accepted in publications:
            if not accepted:
                continue
            expected_history.append(command)
            expected_redo = ()
            if type(limit) is int and len(expected_history) > limit:
                expected_history.pop(0)
        self._verify_expected_items(
            history_items=tuple(expected_history),
            redo_items=expected_redo,
        )

    def restore(self) -> None:
        self.aliases.restore()
        dict.__setitem__(
            self.service_namespace,
            self.service_state_key,
            self.state,
        )
        dict.__setitem__(
            self.state_namespace,
            self.state_history_key,
            self.history,
        )
        dict.__setitem__(
            self.state_namespace,
            self.state_redo_key,
            self.redo_stack,
        )
        list.__setitem__(self.history, slice(None), self.history_items)
        list.__setitem__(self.redo_stack, slice(None), self.redo_items)
        for public_name, storage_name, value in self.policy_values:
            for candidate_name in (public_name, f"_{public_name}"):
                if candidate_name == storage_name:
                    dict.__setitem__(self.state_namespace, candidate_name, value)
                else:
                    self.state_namespace.pop(candidate_name, None)
        self.aliases.restore()
        self.verify()


@dataclass(slots=True)
class _CallbackFreeHistorySnapshotService:
    """Direct state port used when ``state`` is exposed only by ``__getattr__``."""

    state: object
    notify_change: Callable[[], object] | None


def _capture_recording_history_snapshot(
    history: object,
    raw_baseline: CallbackFreeHistoryBaseline | None,
) -> HistoryAuthoritySnapshot | None:
    if (
        raw_baseline is None
        or inspect.getattr_static(
            history,
            "state",
            _MISSING_RAW_HISTORY_ROOT,
        )
        is not _MISSING_RAW_HISTORY_ROOT
    ):
        return HistoryAuthoritySnapshot.capture(history)

    # A dynamic ``__getattr__`` state remains compatible when its raw backing is
    # unambiguous. Bind that one live lookup to the callback-free state and use a
    # direct adapter for all later root restores/verifications. The original
    # service still owns the actual push operation.
    dynamic_history = cast(Any, history)
    live_state = dynamic_history.state
    if live_state is not raw_baseline.state:
        raise RuntimeError(
            "dynamic history state did not match its callback-free backing"
        )
    try:
        notify_change = dynamic_history.notify_change
    except AttributeError:
        if (
            inspect.getattr_static(
                history,
                "notify_change",
                _MISSING_RAW_HISTORY_ROOT,
            )
            is not _MISSING_RAW_HISTORY_ROOT
        ):
            raise
        notify_change = None
    raw_baseline.verify()
    return HistoryAuthoritySnapshot.capture(
        _CallbackFreeHistorySnapshotService(
            state=raw_baseline.state,
            notify_change=(notify_change if callable(notify_change) else None),
        )
    )


def _restore_callback_free_history_baseline(
    baseline: CallbackFreeHistoryBaseline | None,
    original_error: BaseException,
) -> None:
    if baseline is None:
        return
    try:
        baseline.restore()
    except BaseException as restore_error:
        try:
            original_error.add_note(
                "Callback-free history baseline restore also failed with "
                f"{type(restore_error).__name__}: {restore_error}"
            )
        except BaseException:
            return


def _frozen_recorded_after_verifier(
    canvas,
    command: HistoryCommand,
) -> Callable[[], None]:
    """Freeze a command's published payload before an untrusted history push.

    History observers receive the live command and canvas.  Comparing runtime
    with that same mutable command after publication lets an observer rewrite
    both sides and make a corrupt commit appear valid, so retain independent
    copies of every supported after-state first.
    """

    if isinstance(command, CompositeCommand):
        verifiers = tuple(
            _frozen_recorded_after_verifier(canvas, child)
            for child in tuple(command.commands)
        )

        def verify_composite() -> None:
            for verify in verifiers:
                verify()

        return verify_composite

    if isinstance(command, AddAtomsCommand):
        atom_states = copy.deepcopy(command.atom_states)
        after_next_atom_id = command.after_next_atom_id
        after_smiles_input = command.after_smiles_input
        atom_coords_3d = copy.deepcopy(command.atom_coords_3d)

        def verify_atoms() -> None:
            if next_atom_id_for(canvas) != after_next_atom_id:
                raise RuntimeError(
                    "recorded atom next-id changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded atom SMILES changed after history publication"
                )
            for atom_id, expected_state in atom_states.items():
                if (
                    atom_for_id(canvas, atom_id) is None
                    or atom_state_dict_for(canvas, atom_id) != expected_state
                ):
                    raise RuntimeError(
                        "recorded atom state changed after history publication"
                    )
            if atom_coords_3d is not None:
                live_coords = atom_coords_3d_for(canvas)
                if any(
                    live_coords.get(atom_id) != expected
                    for atom_id, expected in atom_coords_3d.items()
                ):
                    raise RuntimeError(
                        "recorded atom coordinates changed after history publication"
                    )

        return verify_atoms

    if isinstance(command, AddBondCommand):
        bond_id = command.bond_id
        bond_state = copy.deepcopy(command.bond_state)
        after_smiles_input = command.after_smiles_input

        def verify_bond_addition() -> None:
            bond = bond_for_id(canvas, bond_id)
            if bond is None or bond_state_dict(bond) != bond_state:
                raise RuntimeError(
                    "recorded bond state changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded bond SMILES changed after history publication"
                )

        return verify_bond_addition

    if isinstance(command, UpdateBondCommand):
        bond_id = command.bond_id
        after_state = copy.deepcopy(command.after_state)
        after_smiles_input = command.after_smiles_input

        def verify_bond_update() -> None:
            bond = bond_for_id(canvas, bond_id)
            if bond is None or bond_state_dict(bond) != after_state:
                raise RuntimeError(
                    "recorded bond update changed after history publication"
                )
            if last_smiles_input_for(canvas) != after_smiles_input:
                raise RuntimeError(
                    "recorded bond-update SMILES changed after history publication"
                )

        return verify_bond_update

    if isinstance(command, AddSceneItemsCommand):
        items = tuple(command.items)
        item_states = copy.deepcopy(command.item_states)

        def verify_scene_items() -> None:
            if len(items) != len(item_states):
                raise RuntimeError(
                    "recorded scene-item payload changed before publication"
                )
            for item, expected_state in zip(items, item_states, strict=True):
                if scene_item_state_for(canvas, item) != expected_state:
                    raise RuntimeError(
                        "recorded scene item changed after history publication"
                    )

        return verify_scene_items

    return lambda: None


def _verify_published_recording_history(
    history_snapshot: HistoryAuthoritySnapshot | None,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
    command: HistoryCommand,
    *,
    accepted: bool,
) -> None:
    if history_snapshot is None:
        return
    expected_history = list(history_snapshot.history_items)
    expected_redo = history_snapshot.redo_items
    if accepted:
        expected_history.append(command)
        expected_redo = ()
        limit = None
        if policy_snapshot is not None:
            limit = next(
                (port.value for port in policy_snapshot.ports if port.name == "limit"),
                None,
            )
        if type(limit) is int and len(expected_history) > limit:
            expected_history.pop(0)

    def verify_stacks() -> None:
        history_snapshot.verify_exact_items(
            history_items=tuple(expected_history),
            redo_items=expected_redo,
        )

    verify_stacks()
    if policy_snapshot is None:
        return
    policy_snapshot.verify()
    verify_stacks()
    policy_snapshot.verify(reverse=True)
    verify_stacks()


def _recording_push_accepted(
    result: object,
    policy_snapshot: RecordingHistoryPolicySnapshot | None,
) -> bool:
    if result is not False:
        return True
    enabled = (
        next(
            (port.value for port in policy_snapshot.ports if port.name == "enabled"),
            _MISSING_RAW_HISTORY_ROOT,
        )
        if policy_snapshot is not None
        else _MISSING_RAW_HISTORY_ROOT
    )
    if enabled is False:
        return False
    raise RuntimeError(
        "recording history push was rejected without an explicitly disabled policy"
    )


class CanvasHistoryRecordingService:
    def __init__(self, canvas, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service

    def push_history(self, command: HistoryCommand) -> None:
        self._push_history(command)

    def _push_history(self, command: HistoryCommand) -> None:
        raw_history_baseline: CallbackFreeHistoryBaseline | None = None
        history_snapshot: HistoryAuthoritySnapshot | None = None
        policy_snapshot: RecordingHistoryPolicySnapshot | None = None
        command_snapshot: HistoryCommandSnapshot | None = None
        after_runtime_snapshot: object | None = None
        publication_started = False
        try:
            command_snapshot = HistoryCommandSnapshot.capture(command)
            raw_history_baseline = CallbackFreeHistoryBaseline.capture(
                self.history,
                canvas=self.canvas,
            )
            # This savepoint is the exact already-mutated canvas authority.  A
            # subsequent history getter or observer may mutate unrelated
            # runtime. Capture it before crossing those live history ports.
            after_runtime_snapshot = capture_history_transaction_for_history(
                self.canvas,
                history_service=None,
                guard_scene_rect=False,
            )
            runtime_verify = getattr(after_runtime_snapshot, "verify_exact", None)
            if not callable(runtime_verify):
                raise RuntimeError(
                    "recorded history publication has no exact runtime verifier"
                )
            initial_runtime_errors = tuple(runtime_verify())
            if initial_runtime_errors:
                # Lightweight non-canvas test doubles historically expose only
                # a history port and cannot satisfy the production model/scene
                # transaction protocol. Keep their inverse-only compatibility;
                # a real canvas whose capture itself raises still fails closed.
                if getattr(self.canvas, "model", None) is not None:
                    raise BaseExceptionGroup(
                        "recorded history publication did not capture an exact "
                        "after-runtime",
                        list(initial_runtime_errors),
                    )
                release_history_transaction_for_history(
                    self.canvas,
                    after_runtime_snapshot,
                )
                after_runtime_snapshot = None
                runtime_verify = None

            if raw_history_baseline is not None:
                # Runtime capture is itself an extension boundary. It must not
                # redefine the pre-publication history baseline.
                raw_history_baseline.verify()

            verify_recorded_after = _frozen_recorded_after_verifier(
                self.canvas,
                command,
            )
            if raw_history_baseline is not None:
                raw_history_baseline.verify()

            history_snapshot = _capture_recording_history_snapshot(
                self.history,
                raw_history_baseline,
            )
            if history_snapshot is not None:
                if raw_history_baseline is None:
                    raise RuntimeError(
                        "recording history has mutable stacks but no callback-free "
                        "backing authority"
                    )
                policy_snapshot = RecordingHistoryPolicySnapshot.capture(
                    history_snapshot
                )
                _verify_history_and_policy_authority(
                    history_snapshot,
                    policy_snapshot,
                )
                raw_history_baseline.bind_snapshot(
                    history_snapshot,
                    policy_snapshot,
                )
            if callable(runtime_verify):
                history_capture_runtime_errors = tuple(runtime_verify())
                if history_capture_runtime_errors:
                    raise BaseExceptionGroup(
                        "recording history capture changed the canvas runtime",
                        list(history_capture_runtime_errors),
                    )
            if raw_history_baseline is not None:
                raw_history_baseline.verify()
            command_snapshot.verify()

            publication_started = True
            push_result = self.history.push(command)
            accepted = _recording_push_accepted(
                push_result,
                policy_snapshot,
            )
            command_snapshot.verify()
            _verify_published_recording_history(
                history_snapshot,
                policy_snapshot,
                command,
                accepted=accepted,
            )
            verify_recorded_after()
            if callable(runtime_verify):
                runtime_errors = tuple(runtime_verify())
                if runtime_errors:
                    raise BaseExceptionGroup(
                        "recorded canvas changed during history publication",
                        list(runtime_errors),
                    )
            command_snapshot.verify()

            # Releasing the runtime savepoint can cross scene-rect extension
            # ports. Do it before the final mutually bound close so release
            # cannot become the last writer over runtime or history.
            if after_runtime_snapshot is not None:
                release_history_transaction_for_history(
                    self.canvas,
                    after_runtime_snapshot,
                )

            # Final close order is deliberate: live history readers first,
            # exact runtime second, callback-free command payload third, and
            # raw expected stacks last. Nothing after the raw comparison can
            # invoke a live history getter.
            _verify_published_recording_history(
                history_snapshot,
                policy_snapshot,
                command,
                accepted=accepted,
            )
            verify_recorded_after()
            if callable(runtime_verify):
                closing_runtime_errors = tuple(runtime_verify())
                if closing_runtime_errors:
                    raise BaseExceptionGroup(
                        "recorded canvas changed during final history verification",
                        list(closing_runtime_errors),
                    )
            command_snapshot.verify()
            if raw_history_baseline is not None:
                raw_history_baseline.verify_published_commands(((command, accepted),))
        except BaseException as error:
            _restore_callback_free_history_baseline(raw_history_baseline, error)
            recover_failed_recording_push(
                self.canvas,
                command,
                history_snapshot if publication_started else None,
                error,
                phase="recorded canvas mutation",
                policy_snapshot=(policy_snapshot if publication_started else None),
                command_snapshot=command_snapshot,
                after_runtime_snapshot=after_runtime_snapshot,
            )
            _restore_callback_free_history_baseline(raw_history_baseline, error)
            raise

    def record_additions(
        self,
        before_next_atom_id: int,
        before_bond_count: int,
        before_smiles_input: str | None,
        added_scene_items: list | None = None,
    ) -> None:
        commands: list[HistoryCommand] = []
        after_next_atom_id = next_atom_id_for(self.canvas)
        if after_next_atom_id > before_next_atom_id:
            atom_states = {
                atom_id: atom_state_dict_for(self.canvas, atom_id)
                for atom_id in range(before_next_atom_id, after_next_atom_id)
                if atom_for_id(self.canvas, atom_id) is not None
            }
            if atom_states:
                stored_coords_3d = atom_coords_3d_for(self.canvas)
                atom_coords_3d = {
                    atom_id: stored_coords_3d[atom_id]
                    for atom_id in atom_states
                    if atom_id in stored_coords_3d
                }
                commands.append(
                    AddAtomsCommand(
                        atom_states=atom_states,
                        before_next_atom_id=before_next_atom_id,
                        after_next_atom_id=after_next_atom_id,
                        before_smiles_input=before_smiles_input,
                        after_smiles_input=last_smiles_input_for(self.canvas),
                        atom_coords_3d=atom_coords_3d or None,
                    )
                )
        for bond_id in range(before_bond_count, bond_count_for(self.canvas)):
            bond = bond_for_id(self.canvas, bond_id)
            if bond is None:
                continue
            bond_state = bond_state_dict(bond)
            commands.append(
                AddBondCommand(
                    bond_id=bond_id,
                    bond_state=bond_state,
                    previous_bond_count=bond_id,
                    before_smiles_input=before_smiles_input,
                    after_smiles_input=last_smiles_input_for(self.canvas),
                )
            )
        if added_scene_items:
            states = [
                scene_item_state_for(self.canvas, item)
                for item in added_scene_items
                if item is not None
            ]
            if states:
                commands.append(
                    AddSceneItemsCommand(
                        item_states=states, items=list(added_scene_items)
                    )
                )
        if not commands:
            return
        if len(commands) == 1:
            self._push_history(commands[0])
            return
        self._push_history(CompositeCommand(commands))

    def record_bond_update(
        self,
        bond_id: int,
        before_state: dict,
        after_state: dict,
        before_smiles_input: str | None,
        after_smiles_input: str | None,
    ) -> None:
        if before_state == after_state and before_smiles_input == after_smiles_input:
            return
        self._push_history(
            UpdateBondCommand(
                bond_id=bond_id,
                before_state=before_state,
                after_state=after_state,
                before_smiles_input=before_smiles_input,
                after_smiles_input=after_smiles_input,
            )
        )


__all__ = ["CanvasHistoryRecordingService"]
