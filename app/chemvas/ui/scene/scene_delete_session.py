"""Transaction session for the delete tool: staged atom, bond, ring and group removals with exact rollback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from PyQt6 import sip
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPolygonItem

from chemvas.domain.document.groups import SceneGroup
from chemvas.domain.transactions import add_recovery_error_note
from chemvas.ui.canvas.canvas_group_state import (
    group_state_for,
    remove_group_for,
    restore_group_for,
)
from chemvas.ui.canvas.canvas_scene_items_state import (
    require_scene_record_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.core.history import (
        HistoryCommand,
    )
    from chemvas.ui.canvas.canvas_callback_state import (
        CanvasCallbackState,
    )
    from chemvas.ui.scene.scene_delete_controller import SceneDeleteController
    from chemvas.ui.transactions.document import (
        DocumentSavepoint,
    )


_DELETED_RING_ITEM = object()


def _shrink_group_members(
    canvas,
    group_id: int,
    *,
    atom_ids: set[int],
    item_ids: set[int],
) -> SceneGroup | None:
    """Replace the remaining membership, retaining the original Undo object."""
    groups = group_state_for(canvas).groups
    original = groups.get(group_id)
    if original is None:
        return None
    remaining = SceneGroup(
        original.atom_ids - atom_ids,
        [item for item in original.item_ids if item not in item_ids],
    )
    if remaining.atom_ids or remaining.item_ids:
        restore_group_for(canvas, group_id, remaining)
    else:
        remove_group_for(canvas, group_id)
    return original


class _RingDataItem(Protocol):
    def data(self, role: int) -> object: ...


def _ring_atom_ids(item: _RingDataItem) -> object:
    try:
        return item.data(2)
    except RuntimeError:
        if isinstance(item, QGraphicsItem) and sip.isdeleted(item):
            return _DELETED_RING_ITEM
        raise


@dataclass(frozen=True)
class _ObserverPort:
    target: object
    name: str
    value: Callable[[], None] | None

    @classmethod
    def capture(cls, target: object, name: str) -> _ObserverPort:
        value = getattr(target, name)
        if value is not None and not callable(value):
            raise TypeError(f"delete observer port {name!r} is not callable")
        return cls(target=target, name=name, value=value)

    def set_verified(
        self,
        value: Callable[[], None] | None,
    ) -> tuple[list[BaseException], bool]:
        try:
            setattr(self.target, self.name, value)
            if getattr(self.target, self.name) is not value:
                raise RuntimeError(
                    f"delete observer setter for {self.name} was a no-op"
                )
        except Exception as error:
            return [error], False
        return [], True


@dataclass(slots=True, kw_only=True)
class SceneDeleteTransactionSession:
    """One explicit savepoint spanning a delete-tool pointer gesture."""

    controller: SceneDeleteController
    snapshot: DocumentSavepoint
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
                (f"{phase} the {port.name} observer port", setter_error)
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
        for phase, observer_error in errors[1:]:
            add_recovery_error_note(primary_error, observer_error, phase=phase)
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
                    (
                        "publishing the group selection observer update",
                        self.selection_group_callback,
                    ),
                    (
                        "publishing the selection outline observer update",
                        self.selection_outline_callback,
                    ),
                ):
                    if not callable(callback):
                        continue
                    try:
                        callback()
                    except Exception as observer_error:
                        errors.append((phase, observer_error))
        finally:
            restore_errors, _restored = self._try_restore_observer_ports()
            errors.extend(restore_errors)
        return errors

    def _restore_absolute_snapshot(self) -> tuple[bool, list[BaseException]]:
        try:
            result = self.snapshot.restore()
        except Exception as restore_error:
            return False, [restore_error]
        return result.authoritative, list(result.errors)

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
        except Exception as observer_error:
            return [observer_error], True
        return [], True

    def delete_atom(self, atom_id: int) -> HistoryCommand | None:
        self._require_active()
        if not isinstance(atom_id, int) or not self.controller._has_atom(atom_id):
            return None
        removed_groups = self._take_groups(
            atom_ids={atom_id},
            items=list(self.controller.marks.by_atom.get(atom_id, ())),
        )
        candidate_ring_ids = set(self.pending_broken_ring_ids)
        candidate_ring_ids.update(self.ring_ids_by_atom.get(atom_id, ()))
        bond_ids = set(self.atom_bond_ids.get(atom_id, ()))
        removed_endpoints, removed_pairs = self._forget_bonds(bond_ids)
        for pair in removed_pairs:
            candidate_ring_ids.update(self.ring_ids_by_bond_pair.get(pair, ()))
        atom_was_live = atom_id in self.live_atom_ids
        self.live_atom_ids.discard(atom_id)
        removed_ring_items: list = []
        removed_atom_ids: list[int] = []
        command = self.controller._delete_atom(
            atom_id,
            record=False,
            bond_ids=bond_ids,
            ring_atom_ids=self.live_atom_ids,
            ring_bond_pairs=self.live_bond_pairs,
            removed_groups=removed_groups,
            ring_items=self._ring_items(candidate_ring_ids),
            remove_groups_for_ring_items=self._take_groups_for_items,
            remove_groups_for_atoms=self._take_groups_for_atoms,
            removed_ring_items=removed_ring_items,
            removed_atom_ids=removed_atom_ids,
        )
        if command is None:
            if atom_was_live:
                self.live_atom_ids.add(atom_id)
            self._restore_bonds(removed_endpoints)
            self._restore_groups(removed_groups)
            return None
        self.atom_bond_ids.pop(atom_id, None)
        for orphan_atom_id in removed_atom_ids:
            self.live_atom_ids.discard(orphan_atom_id)
            self.atom_bond_ids.pop(orphan_atom_id, None)
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
        removed_atom_ids: list[int] = []
        command = self.controller._delete_bond(
            bond_id,
            record=False,
            ring_atom_ids=self.live_atom_ids,
            ring_bond_pairs=self.live_bond_pairs,
            ring_items=self._ring_items(candidate_ring_ids),
            remove_groups_for_ring_items=self._take_groups_for_items,
            remove_groups_for_atoms=self._take_groups_for_atoms,
            removed_ring_items=removed_ring_items,
            removed_atom_ids=removed_atom_ids,
        )
        if command is None:
            self._restore_bonds(removed_endpoints)
        else:
            for atom_id in removed_atom_ids:
                self.live_atom_ids.discard(atom_id)
                self.atom_bond_ids.pop(atom_id, None)
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
            for phase, observer_error in observer_errors[1:]:
                add_recovery_error_note(primary_error, observer_error, phase=phase)
            raise primary_error
        self.snapshot.release()
        self.active = False

    def rollback(self) -> list[BaseException]:
        self._require_active()
        errors: list[BaseException] = []
        suspension_errors, _suspended = self._try_suspend_observers()
        errors.extend(error for _phase, error in suspension_errors)
        authoritative, restore_errors = self._restore_absolute_snapshot()
        errors.extend(restore_errors)
        if authoritative:
            # The absolute snapshot already restored the exact outline objects,
            # stacking, group state, and selection.  Re-running the outline/group
            # mutators would replace those exact objects (and could expand a
            # deliberately partial pre-gesture selection).  Only the external
            # selection-info observer needs one final publication.
            publication_errors, _published_now = self._publish_restored_selection_info()
            errors.extend(publication_errors)
            observer_restore_errors, observer_ports_restored = (
                self._try_restore_observer_ports()
            )
            errors.extend(error for _phase, error in observer_restore_errors)
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
    ) -> list[tuple[int, SceneGroup]]:
        group_ids: set[int] = set()
        for atom_id in atom_ids or ():
            group_ids.update(self.group_ids_by_atom.get(atom_id, ()))
        for item in items or ():
            group_ids.update(
                self.group_ids_by_item.get(require_scene_record_id(item), ())
            )
        removed: list[tuple[int, SceneGroup]] = []
        deleted_atoms = atom_ids or set()
        deleted_items = {require_scene_record_id(item) for item in items or ()}
        for group_id in sorted(group_ids):
            group = _shrink_group_members(
                self.controller.canvas,
                group_id,
                atom_ids=deleted_atoms,
                item_ids=deleted_items,
            )
            if group is not None:
                removed.append((group_id, group))
            if group_id not in group_state_for(self.controller.canvas).groups:
                self._forget_group(group_id)
                continue
            # Keep the surviving group discoverable on subsequent erase hits.
            # Update only removed reverse-index entries, not every survivor.
            member_atoms, member_items = self.group_members_by_id[group_id]
            for members, deleted, reverse in (
                (member_atoms, deleted_atoms, self.group_ids_by_atom),
                (member_items, deleted_items, self.group_ids_by_item),
            ):
                for member in deleted & members:
                    indexed = reverse.get(member)
                    if indexed is not None:
                        indexed.discard(group_id)
                        if not indexed:
                            reverse.pop(member, None)
                members.difference_update(deleted)
        return removed

    def _take_groups_for_items(self, items: list) -> list[tuple[int, SceneGroup]]:
        return self._take_groups(items=items)

    def _take_groups_for_atoms(
        self, atom_ids: set[int]
    ) -> list[tuple[int, SceneGroup]]:
        return self._take_groups(atom_ids=atom_ids)

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

    def _index_group(self, group_id: int, group: SceneGroup) -> None:
        atom_ids = set(group.atom_ids)
        item_ids = set(group.item_ids)
        self.group_members_by_id[group_id] = (atom_ids, item_ids)
        for atom_id in atom_ids:
            self.group_ids_by_atom.setdefault(atom_id, set()).add(group_id)
        for item_id in item_ids:
            self.group_ids_by_item.setdefault(item_id, set()).add(group_id)

    def _restore_groups(self, removed: list[tuple[int, SceneGroup]]) -> None:
        for group_id, group in removed:
            restore_group_for(self.controller.canvas, group_id, group)
            self._forget_group(group_id)
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


__all__ = [
    "SceneDeleteTransactionSession",
]
