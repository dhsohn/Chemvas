from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from core.document_state import model_bond_pairs, ring_atom_ids_form_cycle
from core.history import (
    CompositeCommand,
    DeleteAtomsCommand,
    DeleteBondCommand,
    HistoryCommand,
)
from PyQt6 import sip
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem

from ui.atom_coords_access import atom_coords_3d_for
from ui.canvas_callback_state import CanvasCallbackState, callback_state_for
from ui.canvas_delete_transaction import (
    CanvasDeleteTransactionSnapshot,
    canvas_delete_transaction,
)
from ui.canvas_group_state import (
    CanvasSceneGroup,
    group_ids_for_members_for,
    group_state_for,
    remove_group_for,
    restore_group_for,
)
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import (
    atom_for_id,
    bonds_for,
    model_for,
    next_atom_id_for,
)
from ui.canvas_scene_items_state import ring_items_for
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.handle_overlay_access import clear_handles_for
from ui.history_commands import DeleteSceneItemsCommand, UngroupSceneItemsCommand
from ui.scene_delete_apply_logic import apply_delete_selection_plan
from ui.scene_delete_logic import build_delete_selection_plan, classify_delete_selection
from ui.scene_item_access import remove_scene_item as remove_scene_item_helper
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    mark_state_dict_for,
    ring_state_dict_for,
    scene_item_state_for,
)
from ui.scene_single_item_mutation_logic import (
    delete_atom_with_history,
    delete_bond_with_history,
    delete_ring_with_history,
)
from ui.selection_collection_access import selected_scene_items_for
from ui.selection_info_state import selection_info_state_for
from ui.selection_service_access import refresh_selection_outline_for

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


_DELETED_RING_ITEM = object()
_MISSING_OBSERVER_PORT = object()


class _RingDataItem(Protocol):
    def data(self, role: int) -> object: ...


def _ring_atom_ids(item: _RingDataItem) -> object:
    try:
        return item.data(2)
    except RuntimeError:
        if isinstance(item, QGraphicsItem) and sip.isdeleted(item):
            return _DELETED_RING_ITEM
        raise


def _class_attribute(target: object, name: str) -> object:
    for owner in type(target).__mro__:
        namespace = vars(owner)
        if name in namespace:
            return namespace[name]
    return _MISSING_OBSERVER_PORT


@dataclass(frozen=True, slots=True)
class _ObserverPort:
    name: str
    value: Callable[[], None] | None
    getter: Callable[[], object]
    setter: Callable[[object], object]

    @classmethod
    def capture(cls, target: object, name: str) -> _ObserverPort:
        static_value = inspect.getattr_static(
            target,
            name,
            _MISSING_OBSERVER_PORT,
        )
        if static_value is _MISSING_OBSERVER_PORT:
            raise AttributeError(f"delete observer state has no {name!r} port")
        class_value = _class_attribute(target, name)
        descriptor_getter = (
            inspect.getattr_static(
                type(class_value),
                "__get__",
                _MISSING_OBSERVER_PORT,
            )
            if class_value is not _MISSING_OBSERVER_PORT
            else _MISSING_OBSERVER_PORT
        )
        descriptor_setter = (
            inspect.getattr_static(
                type(class_value),
                "__set__",
                _MISSING_OBSERVER_PORT,
            )
            if class_value is not _MISSING_OBSERVER_PORT
            else _MISSING_OBSERVER_PORT
        )
        get_value: Callable[[], object]
        set_value: Callable[[object], object]
        if (
            static_value is class_value
            and callable(descriptor_getter)
            and callable(descriptor_setter)
        ):

            def descriptor_get_value(
                _getter=descriptor_getter,
                _descriptor=class_value,
                _target=target,
            ) -> object:
                return _getter(_descriptor, _target, type(_target))

            def descriptor_set_value(
                value: object,
                _setter=descriptor_setter,
                _descriptor=class_value,
                _target=target,
            ) -> object:
                return _setter(_descriptor, _target, value)

            get_value = descriptor_get_value
            set_value = descriptor_set_value

        else:
            getattribute = inspect.getattr_static(
                type(target),
                "__getattribute__",
            )
            setattribute = inspect.getattr_static(
                type(target),
                "__setattr__",
            )

            def attribute_get_value(
                _getattribute=getattribute,
                _target=target,
                _name=name,
            ) -> object:
                return _getattribute(_target, _name)

            def attribute_set_value(
                value: object,
                _setattribute=setattribute,
                _target=target,
                _name=name,
            ) -> object:
                return _setattribute(_target, _name, value)

            get_value = attribute_get_value
            set_value = attribute_set_value

        value = get_value()
        if value is not None and not callable(value):
            raise TypeError(f"delete observer port {name!r} is not callable")
        return cls(
            name=name,
            value=value,
            getter=get_value,
            setter=set_value,
        )

    def set_verified(
        self,
        value: Callable[[], None] | None,
    ) -> tuple[list[BaseException], bool]:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                self.setter(value)
                if self.getter() is not value:
                    raise RuntimeError(
                        f"delete observer setter for {self.name} was a no-op"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return errors, True
        return errors, False


@dataclass(slots=True)
class SceneDeleteTransactionSession:
    """One explicit savepoint spanning a delete-tool pointer gesture."""

    controller: SceneDeleteController
    snapshot: CanvasDeleteTransactionSnapshot
    bond_endpoints: dict[int, tuple[int, int]]
    atom_bond_ids: dict[int, set[int]]
    live_atom_ids: set[int]
    bond_pair_counts: dict[tuple[int, int], int]
    live_bond_pairs: set[tuple[int, int]]
    group_members_by_id: dict[int, tuple[set[int], set[int]]]
    group_ids_by_atom: dict[int, set[int]]
    group_ids_by_item: dict[int, set[int]]
    ring_items_by_id: dict[int, object]
    ring_order_by_id: dict[int, int]
    ring_dependencies_by_id: dict[
        int,
        tuple[set[int], set[tuple[int, int]]],
    ]
    ring_ids_by_atom: dict[int, set[int]]
    ring_ids_by_bond_pair: dict[tuple[int, int], set[int]]
    pending_broken_ring_ids: set[int]
    observer_state: CanvasCallbackState
    observer_ports: tuple[_ObserverPort, _ObserverPort]
    selection_group_callback: Callable[[], None] | None
    selection_outline_callback: Callable[[], None] | None
    selection_info_callback: Callable[[str, str], object] | None
    selection_info_cache: tuple[str, str] | None
    observers_suspended: bool = False
    mutated: bool = False
    active: bool = True
    selection_info_published: bool = False

    def _require_active(self) -> None:
        if not self.active:
            raise RuntimeError("Delete transaction session is no longer active")

    def _set_observer_ports(
        self,
        group_callback: Callable[[], None] | None,
        outline_callback: Callable[[], None] | None,
        *,
        phase: str,
        suspended: bool,
    ) -> tuple[list[tuple[str, BaseException]], bool]:
        errors: list[tuple[str, BaseException]] = []
        all_ports_set = True
        desired = {
            "scene_selection_group": group_callback,
            "scene_selection_outline": outline_callback,
        }
        for port in self.observer_ports:
            failures, restored = port.set_verified(desired[port.name])
            if not restored:
                all_ports_set = False
            errors.extend(
                (f"{phase} {port.name}", setter_error)
                for setter_error in failures
            )
        if all_ports_set:
            self.observers_suspended = suspended
        return errors, all_ports_set

    @classmethod
    def _raise_observer_errors(
        cls,
        errors: list[tuple[str, BaseException]],
    ) -> None:
        if not errors:
            return
        _, primary_error = errors[0]
        cls._add_observer_error_notes(primary_error, errors[1:])
        raise primary_error

    def _try_suspend_observers(
        self,
    ) -> tuple[list[tuple[str, BaseException]], bool]:
        return self._set_observer_ports(
            None,
            None,
            phase="suspending",
            suspended=True,
        )

    def _suspend_observers(self) -> None:
        errors, _suspended = self._try_suspend_observers()
        self._raise_observer_errors(errors)

    def _try_restore_observer_ports(
        self,
    ) -> tuple[list[tuple[str, BaseException]], bool]:
        return self._set_observer_ports(
            self.selection_group_callback,
            self.selection_outline_callback,
            phase="restoring",
            suspended=False,
        )

    def _restore_observer_ports(self) -> None:
        errors, _restored = self._try_restore_observer_ports()
        self._raise_observer_errors(errors)

    @staticmethod
    def _add_observer_error_notes(
        primary_error: BaseException,
        observer_errors: list[tuple[str, BaseException]],
    ) -> None:
        for phase, observer_error in observer_errors:
            try:
                primary_error.add_note(
                    "Delete gesture observer synchronization also failed during "
                    f"{phase}: {type(observer_error).__name__}: {observer_error}"
                )
            except BaseException:
                # Observer diagnostics cannot replace cancellation/termination.
                continue

    def _resume_and_sync_observers(self) -> list[tuple[str, BaseException]]:
        """Publish one final selection update without recursive intermediate work."""

        errors: list[tuple[str, BaseException]] = []
        # Keep both routed callbacks muted while the group callback expands a
        # selection.  Its nested Qt selectionChanged emissions must not rebuild
        # the outline once per member; the outline callback below sees the one
        # final, fully expanded state.
        suspension_errors, _suspended = self._try_suspend_observers()
        errors.extend(suspension_errors)
        try:
            if not suspension_errors:
                for phase, callback in (
                    ("group selection", self.selection_group_callback),
                    ("selection outline", self.selection_outline_callback),
                ):
                    if not callable(callback):
                        continue
                    try:
                        callback()
                    except BaseException as observer_error:
                        errors.append((phase, observer_error))
        finally:
            restore_errors, _restored = self._try_restore_observer_ports()
            errors.extend(restore_errors)
        return errors

    def _restore_absolute_snapshot(self) -> tuple[bool, list[BaseException]]:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                result = self.snapshot.restore_with_result()
            except BaseException as restore_error:
                errors.append(restore_error)
                continue
            errors.extend(result.errors)
            if result.authoritative:
                return True, errors
        return False, errors

    def _publish_restored_selection_info(
        self,
    ) -> tuple[list[BaseException], bool]:
        """Republish the exact cached pre-gesture status without rebuilding UI."""

        if self.selection_info_published:
            return [], False
        self.selection_info_published = True
        callback = self.selection_info_callback
        cache = self.selection_info_cache
        if callback is None or cache is None:
            return [], False
        try:
            formula_text, mass_text = cache
            callback(formula_text, mass_text)
        except BaseException as observer_error:
            return [observer_error], True
        return [], True

    def _observer_ports_are_exact(self) -> tuple[bool, list[BaseException]]:
        errors: list[BaseException] = []
        exact = True
        for port in self.observer_ports:
            try:
                if port.getter() is not port.value:
                    raise RuntimeError(
                        "delete rollback did not restore observer port "
                        f"{port.name}"
                    )
            except BaseException as error:
                errors.append(error)
                exact = False
        return exact, errors

    def _reassert_after_selection_info_publication(
        self,
    ) -> tuple[bool, list[BaseException]]:
        """Make the pre-gesture snapshot final without publishing again."""

        errors: list[BaseException] = []
        for _attempt in range(2):
            attempt_errors: list[BaseException] = []
            observer_errors, observer_ports_restored = (
                self._try_restore_observer_ports()
            )
            attempt_errors.extend(error for _phase, error in observer_errors)
            observer_ports_exact, observer_verify_errors = (
                self._observer_ports_are_exact()
            )
            attempt_errors.extend(observer_verify_errors)
            try:
                attempt_errors.extend(
                    self.snapshot._verify_exact_authorities()
                )
            except BaseException as verify_error:
                attempt_errors.append(verify_error)
            if (
                not attempt_errors
                and observer_ports_restored
                and observer_ports_exact
            ):
                return True, []

            errors.extend(attempt_errors)
            attempt_errors = []
            try:
                pass_errors, secondary_errors = (
                    self.snapshot._silent_authority_pass()
                )
            except BaseException as restore_error:
                attempt_errors.append(restore_error)
                secondary_errors = []
            else:
                attempt_errors.extend(pass_errors)
            errors.extend(secondary_errors)

            observer_ports_exact, observer_verify_errors = (
                self._observer_ports_are_exact()
            )
            attempt_errors.extend(observer_verify_errors)
            try:
                # Observer-port setters/getters are also untrusted. Verify the
                # complete canvas snapshot after them so a callback cannot
                # mutate model, scene, history, selection, or raw graphics and
                # still let the session publish rollback completion.
                attempt_errors.extend(
                    self.snapshot._verify_exact_authorities()
                )
            except BaseException as verify_error:
                attempt_errors.append(verify_error)

            if (
                not attempt_errors
                and observer_ports_restored
                and observer_ports_exact
            ):
                return True, []
            errors.extend(attempt_errors)
        return False, errors

    def delete_atom(self, atom_id: int) -> HistoryCommand | None:
        self._require_active()
        if not isinstance(atom_id, int) or not self.controller._has_atom(atom_id):
            return None
        removed_groups = self._take_groups(atom_ids={atom_id})
        candidate_ring_ids = set(self.pending_broken_ring_ids)
        candidate_ring_ids.update(self.ring_ids_by_atom.get(atom_id, ()))
        bond_ids = set(self.atom_bond_ids.get(atom_id, ()))
        removed_endpoints, removed_pairs = self._forget_bonds(bond_ids)
        for pair in removed_pairs:
            candidate_ring_ids.update(self.ring_ids_by_bond_pair.get(pair, ()))
        atom_was_live = atom_id in self.live_atom_ids
        self.live_atom_ids.discard(atom_id)
        removed_ring_items: list = []
        command = self.controller._delete_atom(
            atom_id,
            record=False,
            bond_ids=bond_ids,
            ring_atom_ids=self.live_atom_ids,
            ring_bond_pairs=self.live_bond_pairs,
            removed_groups=removed_groups,
            ring_items=self._ring_items(candidate_ring_ids),
            remove_groups_for_ring_items=self._take_groups_for_items,
            removed_ring_items=removed_ring_items,
        )
        if command is None:
            if atom_was_live:
                self.live_atom_ids.add(atom_id)
            self._restore_bonds(removed_endpoints)
            self._restore_groups(removed_groups)
            return None
        self.atom_bond_ids.pop(atom_id, None)
        self._forget_ring_items(removed_ring_items)
        self.mutated = True
        return command

    def delete_bond(self, bond_id: int) -> HistoryCommand | None:
        self._require_active()
        candidate_ring_ids = set(self.pending_broken_ring_ids)
        removed_endpoints, removed_pairs = self._forget_bonds((bond_id,))
        for pair in removed_pairs:
            candidate_ring_ids.update(self.ring_ids_by_bond_pair.get(pair, ()))
        removed_ring_items: list = []
        command = self.controller._delete_bond(
            bond_id,
            record=False,
            ring_atom_ids=self.live_atom_ids,
            ring_bond_pairs=self.live_bond_pairs,
            ring_items=self._ring_items(candidate_ring_ids),
            remove_groups_for_ring_items=self._take_groups_for_items,
            removed_ring_items=removed_ring_items,
        )
        if command is None:
            self._restore_bonds(removed_endpoints)
        else:
            self._forget_ring_items(removed_ring_items)
            self.mutated = True
        return command

    def delete_ring(self, item: QGraphicsPolygonItem) -> HistoryCommand | None:
        self._require_active()
        removed_groups = self._take_groups(items=[item])
        command = self.controller._delete_ring(
            item,
            record=False,
            removed_groups=removed_groups,
        )
        if command is not None:
            self._forget_ring_items([item])
            self.mutated = True
        else:
            self._restore_groups(removed_groups)
        return command

    def delete_scene_item(self, item, state: dict) -> HistoryCommand:
        self._require_active()
        removed_groups = self._take_groups(items=[item])
        command = self.controller._delete_scene_item_in_tool_session(
            item,
            state,
            removed_groups=removed_groups,
        )
        self.mutated = True
        return command

    def commit(self, command: HistoryCommand | None = None) -> None:
        self._require_active()
        if command is not None:
            self.controller._push_history(command)
        if not self.mutated:
            observer_errors, _restored = self._try_restore_observer_ports()
            self._raise_observer_errors(observer_errors)
            self.snapshot.release()
            self.active = False
            return
        observer_errors = self._resume_and_sync_observers()
        if observer_errors:
            _, primary_error = observer_errors[0]
            self._add_observer_error_notes(primary_error, observer_errors[1:])
            raise primary_error
        self.snapshot.release()
        self.active = False

    def rollback(self) -> list[BaseException]:
        self._require_active()
        errors: list[BaseException] = []
        suspension_errors, _suspended = self._try_suspend_observers()
        errors.extend(
            error
            for _phase, error in suspension_errors
        )
        authoritative, restore_errors = self._restore_absolute_snapshot()
        errors.extend(restore_errors)
        if authoritative:
            # The absolute snapshot already restored the exact outline objects,
            # stacking, group state, and selection.  Re-running the outline/group
            # mutators would replace those exact objects (and could expand a
            # deliberately partial pre-gesture selection).  Only the external
            # selection-info observer needs one final publication.
            publication_errors, published_now = (
                self._publish_restored_selection_info()
            )
            errors.extend(publication_errors)
            if published_now:
                authoritative, final_errors = (
                    self._reassert_after_selection_info_publication()
                )
                errors.extend(final_errors)
                observer_ports_restored = authoritative
            else:
                observer_restore_errors, observer_ports_restored = (
                    self._try_restore_observer_ports()
                )
                errors.extend(
                    error for _phase, error in observer_restore_errors
                )
        else:
            observer_restore_errors, observer_ports_restored = (
                self._try_restore_observer_ports()
            )
            errors.extend(error for _phase, error in observer_restore_errors)
        if authoritative and observer_ports_restored:
            self.active = False
        return errors

    @staticmethod
    def _bond_pair(atom_a: int, atom_b: int) -> tuple[int, int]:
        return (atom_a, atom_b) if atom_a < atom_b else (atom_b, atom_a)

    def _forget_bonds(
        self,
        bond_ids,
    ) -> tuple[dict[int, tuple[int, int]], set[tuple[int, int]]]:
        removed_endpoints: dict[int, tuple[int, int]] = {}
        removed_pairs: set[tuple[int, int]] = set()
        for bond_id in bond_ids:
            endpoints = self.bond_endpoints.pop(bond_id, None)
            if endpoints is None:
                continue
            removed_endpoints[bond_id] = endpoints
            atom_a, atom_b = endpoints
            self.atom_bond_ids.get(atom_a, set()).discard(bond_id)
            self.atom_bond_ids.get(atom_b, set()).discard(bond_id)
            if atom_a == atom_b:
                continue
            pair = self._bond_pair(atom_a, atom_b)
            count = self.bond_pair_counts.get(pair, 0) - 1
            if count > 0:
                self.bond_pair_counts[pair] = count
            else:
                self.bond_pair_counts.pop(pair, None)
                self.live_bond_pairs.discard(pair)
                removed_pairs.add(pair)
        return removed_endpoints, removed_pairs

    def _restore_bonds(self, endpoints_by_id: dict[int, tuple[int, int]]) -> None:
        for bond_id, (atom_a, atom_b) in endpoints_by_id.items():
            self.bond_endpoints[bond_id] = (atom_a, atom_b)
            self.atom_bond_ids.setdefault(atom_a, set()).add(bond_id)
            self.atom_bond_ids.setdefault(atom_b, set()).add(bond_id)
            if atom_a == atom_b:
                continue
            pair = self._bond_pair(atom_a, atom_b)
            self.bond_pair_counts[pair] = self.bond_pair_counts.get(pair, 0) + 1
            self.live_bond_pairs.add(pair)

    def _take_groups(
        self,
        *,
        atom_ids: set[int] | None = None,
        items: list | None = None,
    ) -> list[tuple[int, CanvasSceneGroup]]:
        group_ids: set[int] = set()
        for atom_id in atom_ids or ():
            group_ids.update(self.group_ids_by_atom.get(atom_id, ()))
        for item in items or ():
            group_ids.update(self.group_ids_by_item.get(id(item), ()))
        removed: list[tuple[int, CanvasSceneGroup]] = []
        for group_id in sorted(group_ids):
            group = remove_group_for(self.controller.canvas, group_id)
            self._forget_group(group_id)
            if group is not None:
                removed.append((group_id, group))
        return removed

    def _take_groups_for_items(self, items: list) -> list[tuple[int, CanvasSceneGroup]]:
        return self._take_groups(items=items)

    def _forget_group(self, group_id: int) -> None:
        members = self.group_members_by_id.pop(group_id, None)
        if members is None:
            return
        atom_ids, item_ids = members
        for atom_id in atom_ids:
            indexed = self.group_ids_by_atom.get(atom_id)
            if indexed is not None:
                indexed.discard(group_id)
                if not indexed:
                    self.group_ids_by_atom.pop(atom_id, None)
        for item_id in item_ids:
            indexed = self.group_ids_by_item.get(item_id)
            if indexed is not None:
                indexed.discard(group_id)
                if not indexed:
                    self.group_ids_by_item.pop(item_id, None)

    def _index_group(self, group_id: int, group: CanvasSceneGroup) -> None:
        atom_ids = set(group.atom_ids)
        item_ids = {id(item) for item in group.items}
        self.group_members_by_id[group_id] = (atom_ids, item_ids)
        for atom_id in atom_ids:
            self.group_ids_by_atom.setdefault(atom_id, set()).add(group_id)
        for item_id in item_ids:
            self.group_ids_by_item.setdefault(item_id, set()).add(group_id)

    def _restore_groups(self, removed: list[tuple[int, CanvasSceneGroup]]) -> None:
        for group_id, group in removed:
            restore_group_for(self.controller.canvas, group_id, group)
            self._index_group(group_id, group)

    def _ring_items(self, ring_ids: set[int]) -> list:
        return [
            self.ring_items_by_id[ring_id]
            for ring_id in sorted(
                ring_ids,
                key=lambda candidate: self.ring_order_by_id.get(candidate, 0),
            )
            if ring_id in self.ring_items_by_id
        ]

    def _forget_ring_items(self, items: list) -> None:
        for item in items:
            ring_id = id(item)
            dependencies = self.ring_dependencies_by_id.pop(ring_id, None)
            self.pending_broken_ring_ids.discard(ring_id)
            self.ring_items_by_id.pop(ring_id, None)
            self.ring_order_by_id.pop(ring_id, None)
            if dependencies is None:
                continue
            atom_ids, bond_pairs = dependencies
            for atom_id in atom_ids:
                indexed = self.ring_ids_by_atom.get(atom_id)
                if indexed is not None:
                    indexed.discard(ring_id)
                    if not indexed:
                        self.ring_ids_by_atom.pop(atom_id, None)
            for pair in bond_pairs:
                indexed = self.ring_ids_by_bond_pair.get(pair)
                if indexed is not None:
                    indexed.discard(ring_id)
                    if not indexed:
                        self.ring_ids_by_bond_pair.pop(pair, None)


class SceneDeleteController:
    def __init__(
        self,
        canvas: CanvasView,
        *,
        move_controller=None,
        atom_mutation_service=None,
        bond_mutation_service=None,
        style_controller=None,
        history_service=None,
    ) -> None:
        self.canvas = canvas
        self.move_controller = move_controller
        self.atom_mutation_service = atom_mutation_service
        self.bond_mutation_service = bond_mutation_service
        self.style_controller = style_controller
        self.history = history_service
        self.marks = mark_registry_for(canvas)

    @property
    def _bonds(self):
        return bonds_for(self.canvas)

    @property
    def _next_atom_id(self) -> int:
        return next_atom_id_for(self.canvas)

    def _has_atom(self, atom_id: int) -> bool:
        return atom_for_id(self.canvas, atom_id) is not None

    def _redraw_connected_bonds(self, atom_id: int, skip_bond_id: int | None = None) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(atom_id, skip_bond_id=skip_bond_id)

    def _mark_state(self, item) -> dict:
        return mark_state_dict_for(self.canvas, item)

    def _bond_state(self, bond) -> dict:
        return bond_state_dict(bond)

    def _atom_state(self, atom_id: int) -> dict:
        return atom_state_dict_for(self.canvas, atom_id)

    def _scene_item_state(self, item) -> dict:
        return scene_item_state_for(self.canvas, item)

    def _ring_state(self, item) -> dict:
        return ring_state_dict_for(self.canvas, item)

    def _atom_mutation_service(self):
        if self.atom_mutation_service is None:
            msg = "SceneDeleteController requires atom_mutation_service"
            raise RuntimeError(msg)
        return self.atom_mutation_service

    def _bond_mutation_service(self):
        if self.bond_mutation_service is None:
            msg = "SceneDeleteController requires bond_mutation_service"
            raise RuntimeError(msg)
        return self.bond_mutation_service

    def _style_controller(self):
        if self.style_controller is None:
            msg = "SceneDeleteController requires style_controller"
            raise RuntimeError(msg)
        return self.style_controller

    def _remove_bond(self, bond_id: int) -> None:
        self._bond_mutation_service().remove_bond_by_id(bond_id)

    def _remove_atom(self, atom_id: int, remove_marks: bool = True) -> None:
        self._atom_mutation_service().remove_atom_only(atom_id, remove_marks=remove_marks)

    def _remove_scene_item(self, item) -> None:
        remove_scene_item_helper(self.canvas, item)

    def _push_history(self, command: HistoryCommand) -> None:
        self.history.push(command)

    def _remove_overlapping_groups(
        self,
        *,
        atom_ids: set[int] | None = None,
        items: list | None = None,
    ) -> list[tuple[int, CanvasSceneGroup]]:
        group_ids = group_ids_for_members_for(
            self.canvas,
            atom_ids or set(),
            items or [],
        )
        removed: list[tuple[int, CanvasSceneGroup]] = []
        for group_id in sorted(group_ids):
            group = remove_group_for(self.canvas, group_id)
            if group is not None:
                removed.append((group_id, group))
        return removed

    @staticmethod
    def _with_group_cleanup(
        command: HistoryCommand,
        removed_groups: list[tuple[int, CanvasSceneGroup]],
    ) -> HistoryCommand:
        if not removed_groups:
            return command
        group_command = UngroupSceneItemsCommand(removed=removed_groups)
        if isinstance(command, CompositeCommand):
            return CompositeCommand([group_command, *command.commands])
        return CompositeCommand([group_command, command])

    def _delete_broken_ring_fills(
        self,
        *,
        removed_groups: list[tuple[int, CanvasSceneGroup]] | None = None,
        atom_ids: set[int] | None = None,
        bond_pairs: set[tuple[int, int]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_items=None,
        removed_ring_items: list | None = None,
    ) -> DeleteSceneItemsCommand | None:
        candidates = (
            list(ring_items_for(self.canvas))
            if ring_items is None
            else list(ring_items)
        )
        if not candidates:
            return None
        if atom_ids is None or bond_pairs is None:
            model = model_for(self.canvas)
            atom_ids = set(model.atoms)
            bond_pairs = model_bond_pairs(model)
        broken_items = []
        broken_states = []
        for item in candidates:
            ring_atom_ids = _ring_atom_ids(item)
            if ring_atom_ids is _DELETED_RING_ITEM:
                continue
            if (
                isinstance(ring_atom_ids, list)
                and all(type(atom_id) is int for atom_id in ring_atom_ids)
                and ring_atom_ids_form_cycle(ring_atom_ids, atom_ids, bond_pairs)
            ):
                continue
            broken_items.append(item)
            broken_states.append(self._ring_state(item))
        if not broken_items:
            return None
        if removed_groups is not None:
            if remove_groups_for_items is None:
                removed_groups.extend(
                    self._remove_overlapping_groups(items=broken_items)
                )
            else:
                removed_groups.extend(remove_groups_for_items(broken_items))
        command = DeleteSceneItemsCommand(item_states=broken_states, items=broken_items)
        for item in broken_items:
            self._remove_scene_item(item)
        if removed_ring_items is not None:
            removed_ring_items.extend(broken_items)
        return command

    def _with_broken_ring_cleanup(
        self,
        command: HistoryCommand,
        *,
        removed_groups: list[tuple[int, CanvasSceneGroup]],
        atom_ids: set[int] | None = None,
        bond_pairs: set[tuple[int, int]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_items=None,
        removed_ring_items: list | None = None,
    ) -> HistoryCommand:
        ring_command = self._delete_broken_ring_fills(
            removed_groups=removed_groups,
            atom_ids=atom_ids,
            bond_pairs=bond_pairs,
            ring_items=ring_items,
            remove_groups_for_items=remove_groups_for_items,
            removed_ring_items=removed_ring_items,
        )
        if ring_command is None:
            return command
        if isinstance(command, CompositeCommand):
            return CompositeCommand([ring_command, *command.commands])
        return CompositeCommand([ring_command, command])

    def begin_delete_tool_session(self) -> SceneDeleteTransactionSession:
        bond_endpoints: dict[int, tuple[int, int]] = {}
        atom_bond_ids: dict[int, set[int]] = {}
        bond_pair_counts: dict[tuple[int, int], int] = {}
        model = model_for(self.canvas)
        live_atom_ids = set(model.atoms)
        for bond_id, bond in enumerate(self._bonds):
            if bond is None:
                continue
            bond_endpoints[bond_id] = (bond.a, bond.b)
            atom_bond_ids.setdefault(bond.a, set()).add(bond_id)
            atom_bond_ids.setdefault(bond.b, set()).add(bond_id)
            if bond.a != bond.b:
                pair = SceneDeleteTransactionSession._bond_pair(bond.a, bond.b)
                bond_pair_counts[pair] = bond_pair_counts.get(pair, 0) + 1

        group_members_by_id: dict[int, tuple[set[int], set[int]]] = {}
        group_ids_by_atom: dict[int, set[int]] = {}
        group_ids_by_item: dict[int, set[int]] = {}
        for group_id, group in group_state_for(self.canvas).groups.items():
            atom_ids = set(group.atom_ids)
            item_ids = {id(item) for item in group.items}
            group_members_by_id[group_id] = (atom_ids, item_ids)
            for atom_id in atom_ids:
                group_ids_by_atom.setdefault(atom_id, set()).add(group_id)
            for item_id in item_ids:
                group_ids_by_item.setdefault(item_id, set()).add(group_id)

        live_bond_pairs = set(bond_pair_counts)
        ring_items_by_id: dict[int, object] = {}
        ring_order_by_id: dict[int, int] = {}
        ring_dependencies_by_id: dict[
            int,
            tuple[set[int], set[tuple[int, int]]],
        ] = {}
        ring_ids_by_atom: dict[int, set[int]] = {}
        ring_ids_by_bond_pair: dict[tuple[int, int], set[int]] = {}
        pending_broken_ring_ids: set[int] = set()
        for order, item in enumerate(ring_items_for(self.canvas)):
            raw_atom_ids = _ring_atom_ids(item)
            if raw_atom_ids is _DELETED_RING_ITEM:
                continue
            ring_id = id(item)
            ring_items_by_id[ring_id] = item
            ring_order_by_id[ring_id] = order
            if not (
                isinstance(raw_atom_ids, list)
                and all(type(atom_id) is int for atom_id in raw_atom_ids)
                and ring_atom_ids_form_cycle(
                    raw_atom_ids,
                    live_atom_ids,
                    live_bond_pairs,
                )
            ):
                ring_dependencies_by_id[ring_id] = (set(), set())
                pending_broken_ring_ids.add(ring_id)
                continue
            atom_ids = set(raw_atom_ids)
            bond_pairs = {
                SceneDeleteTransactionSession._bond_pair(atom_a, atom_b)
                for atom_a, atom_b in zip(
                    raw_atom_ids,
                    [*raw_atom_ids[1:], raw_atom_ids[0]],
                    strict=True,
                )
            }
            ring_dependencies_by_id[ring_id] = (atom_ids, bond_pairs)
            for atom_id in atom_ids:
                ring_ids_by_atom.setdefault(atom_id, set()).add(ring_id)
            for pair in bond_pairs:
                ring_ids_by_bond_pair.setdefault(pair, set()).add(ring_id)

        # Read both callback values exactly once before the scene-rect guard is
        # opened. A live getter failure must not strand a guarded snapshot.
        observer_state = callback_state_for(self.canvas)
        observer_ports = (
            _ObserverPort.capture(observer_state, "scene_selection_group"),
            _ObserverPort.capture(observer_state, "scene_selection_outline"),
        )
        selection_group_callback = observer_ports[0].value
        selection_outline_callback = observer_ports[1].value
        selection_info_state = selection_info_state_for(self.canvas)
        selection_info_callback_value = selection_info_state.callback
        selection_info_cache_value = selection_info_state.cache
        selection_info_callback = (
            selection_info_callback_value
            if callable(selection_info_callback_value)
            else None
        )
        selection_info_cache = (
            (str(selection_info_cache_value[0]), str(selection_info_cache_value[1]))
            if isinstance(selection_info_cache_value, tuple)
            and len(selection_info_cache_value) == 2
            else None
        )
        snapshot = CanvasDeleteTransactionSnapshot.capture(
            self.canvas,
            history_service=self.history,
            guard_scene_rect=True,
        )
        session = SceneDeleteTransactionSession(
            controller=self,
            snapshot=snapshot,
            bond_endpoints=bond_endpoints,
            atom_bond_ids=atom_bond_ids,
            live_atom_ids=live_atom_ids,
            bond_pair_counts=bond_pair_counts,
            live_bond_pairs=live_bond_pairs,
            group_members_by_id=group_members_by_id,
            group_ids_by_atom=group_ids_by_atom,
            group_ids_by_item=group_ids_by_item,
            ring_items_by_id=ring_items_by_id,
            ring_order_by_id=ring_order_by_id,
            ring_dependencies_by_id=ring_dependencies_by_id,
            ring_ids_by_atom=ring_ids_by_atom,
            ring_ids_by_bond_pair=ring_ids_by_bond_pair,
            pending_broken_ring_ids=pending_broken_ring_ids,
            observer_state=observer_state,
            observer_ports=observer_ports,
            selection_group_callback=selection_group_callback,
            selection_outline_callback=selection_outline_callback,
            selection_info_callback=selection_info_callback,
            selection_info_cache=selection_info_cache,
        )
        try:
            session._suspend_observers()
        except BaseException as original_error:
            cleanup_errors: list[tuple[str, BaseException]] = []
            authoritative, restore_errors = session._restore_absolute_snapshot()
            cleanup_errors.extend(
                ("restoring the guarded delete snapshot", error)
                for error in restore_errors
            )
            observer_restore_errors, _observer_ports_restored = (
                session._try_restore_observer_ports()
            )
            cleanup_errors.extend(observer_restore_errors)
            if not authoritative:
                try:
                    snapshot.release()
                except BaseException as release_error:
                    cleanup_errors.append(
                        ("releasing the failed delete guard", release_error)
                    )
            session.active = False
            session._add_observer_error_notes(original_error, cleanup_errors)
            raise
        return session

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_atom(atom_id, record=record)

    def _delete_atom(
        self,
        atom_id: int,
        *,
        record: bool,
        bond_ids=None,
        ring_atom_ids: set[int] | None = None,
        ring_bond_pairs: set[tuple[int, int]] | None = None,
        removed_groups: list[tuple[int, CanvasSceneGroup]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_ring_items=None,
        removed_ring_items: list | None = None,
    ) -> HistoryCommand | None:
        if not isinstance(atom_id, int) or not self._has_atom(atom_id):
            return None
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(atom_ids={atom_id})
        before_smiles_input = last_smiles_input_for(self.canvas)
        command = delete_atom_with_history(
            atom_id,
            bonds=self._bonds,
            marks_by_atom=self.marks.by_atom,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            mark_state_getter=self._mark_state,
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
            atom_state_getter=self._atom_state,
            next_atom_id_getter=lambda: self._next_atom_id,
            remove_atom_only=self._remove_atom,
            atom_coords_3d_getter=lambda atom_id: atom_coords_3d_for(self.canvas).get(atom_id),
            bond_ids=bond_ids,
        )
        command = self._with_broken_ring_cleanup(
            command,
            removed_groups=removed_groups,
            atom_ids=ring_atom_ids,
            bond_pairs=ring_bond_pairs,
            ring_items=ring_items,
            remove_groups_for_items=remove_groups_for_ring_items,
            removed_ring_items=removed_ring_items,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def delete_bond(self, bond_id: int, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_bond(bond_id, record=record)

    def _delete_bond(
        self,
        bond_id: int,
        *,
        record: bool,
        ring_atom_ids: set[int] | None = None,
        ring_bond_pairs: set[tuple[int, int]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_ring_items=None,
        removed_ring_items: list | None = None,
    ) -> HistoryCommand | None:
        if not isinstance(bond_id, int):
            return None
        removed_groups: list[tuple[int, CanvasSceneGroup]] = []
        before_smiles_input = last_smiles_input_for(self.canvas)
        bond_command = delete_bond_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
        )
        if bond_command is None:
            return None
        command = self._with_broken_ring_cleanup(
            bond_command,
            removed_groups=removed_groups,
            atom_ids=ring_atom_ids,
            bond_pairs=ring_bond_pairs,
            ring_items=ring_items,
            remove_groups_for_items=remove_groups_for_ring_items,
            removed_ring_items=removed_ring_items,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def delete_ring(self, item: QGraphicsPolygonItem, record: bool = True) -> HistoryCommand | None:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_ring(item, record=record)

    def _delete_ring(
        self,
        item: QGraphicsPolygonItem,
        *,
        record: bool,
        removed_groups: list[tuple[int, CanvasSceneGroup]] | None = None,
    ) -> HistoryCommand | None:
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(items=[item])
        command: HistoryCommand = delete_ring_with_history(
            item,
            ring_state_getter=self._ring_state,
            remove_scene_item=self._remove_scene_item,
        )
        command = self._with_group_cleanup(command, removed_groups)
        if record:
            self._push_history(command)
        return command

    def _delete_scene_item_in_tool_session(
        self,
        item,
        state: dict,
        *,
        removed_groups: list[tuple[int, CanvasSceneGroup]] | None = None,
    ) -> HistoryCommand:
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(items=[item])
        command: HistoryCommand = DeleteSceneItemsCommand(
            item_states=[state],
            items=[item],
        )
        self._remove_scene_item(item)
        return self._with_group_cleanup(command, removed_groups)

    def delete_selected_items(self) -> bool:
        with canvas_delete_transaction(self.canvas, history_service=self.history):
            return self._delete_selected_items()

    def _selection_delete_cleanup_errors(self) -> list[tuple[str, BaseException]]:
        errors: list[tuple[str, BaseException]] = []
        actions = (
            (
                "selection-outline resume",
                lambda: self._style_controller().suspend_selection_outline(False),
            ),
            (
                "selection-outline refresh",
                lambda: refresh_selection_outline_for(self.canvas),
            ),
        )
        for phase, action in actions:
            try:
                action()
            except BaseException as exc:
                errors.append((phase, exc))
        return errors

    @staticmethod
    def _add_cleanup_error_notes(
        primary_error: BaseException,
        cleanup_errors: list[tuple[str, BaseException]],
    ) -> None:
        for phase, cleanup_error in cleanup_errors:
            try:
                primary_error.add_note(
                    "Delete selection cleanup also failed during "
                    f"{phase}: {type(cleanup_error).__name__}: {cleanup_error}"
                )
            except BaseException:
                # Cleanup diagnostics cannot replace cancellation/termination.
                continue

    def _delete_selected_items(self) -> bool:
        items = selected_scene_items_for(self.canvas, excluded_kinds={"handle", "note_box", "note_select"})
        if not items:
            return False
        self._style_controller().suspend_selection_outline(True)
        body_error: BaseException | None = None
        try:
            selection = classify_delete_selection(items)
            plan = build_delete_selection_plan(
                selection,
                bonds=self._bonds,
                marks_by_atom=self.marks.by_atom,
                mark_state_getter=self._mark_state,
            )

            if plan.single_bond_id is not None:
                self._delete_bond(plan.single_bond_id, record=True)
                return True

            removed_groups = self._remove_overlapping_groups(
                atom_ids=set(plan.atom_ids),
                items=plan.scene_items,
            )
            before_smiles_input = last_smiles_input_for(self.canvas)
            if plan.clear_smiles_input:
                clear_last_smiles_input_for(self.canvas)
            commands = apply_delete_selection_plan(
                plan,
                bonds=self._bonds,
                before_smiles_input=before_smiles_input,
                current_smiles_input_getter=lambda: last_smiles_input_for(self.canvas),
                bond_state_getter=self._bond_state,
                remove_bond_by_id=self._remove_bond,
                redraw_connected_bonds=self._redraw_connected_bonds,
                atom_state_getter=self._atom_state,
                next_atom_id_getter=lambda: self._next_atom_id,
                remove_atom_only=self._remove_atom,
                scene_item_state_getter=self._scene_item_state,
                remove_scene_item=self._remove_scene_item,
                clear_handles=lambda: clear_handles_for(self.canvas),
                atom_coords_3d_getter=lambda atom_id: atom_coords_3d_for(self.canvas).get(atom_id),
            )

            if any(isinstance(command, (DeleteAtomsCommand, DeleteBondCommand)) for command in commands):
                ring_command = self._delete_broken_ring_fills(
                    removed_groups=removed_groups,
                )
                if ring_command is not None:
                    commands.insert(0, ring_command)

            if not commands:
                return False
            command = commands[0] if len(commands) == 1 else CompositeCommand(commands)
            command = self._with_group_cleanup(command, removed_groups)
            self._push_history(command)
            return True
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            cleanup_errors = self._selection_delete_cleanup_errors()
            if body_error is not None:
                self._add_cleanup_error_notes(body_error, cleanup_errors)
            elif cleanup_errors:
                _, primary_error = cleanup_errors[0]
                self._add_cleanup_error_notes(primary_error, cleanup_errors[1:])
                raise primary_error


__all__ = ["SceneDeleteController", "SceneDeleteTransactionSession"]
