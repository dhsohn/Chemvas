from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, cast

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.core.model_commands import (
    DeleteAtomsCommand,
    DeleteBondCommand,
)
from chemvas.domain.document import (
    broken_ring_fill_indices,
    model_bond_pairs,
    orphaned_atom_ids,
    ring_fill_is_intact,
)
from chemvas.domain.transactions import add_recovery_error_note
from chemvas.ui.annotations.materialize import restore_ring_projections
from chemvas.ui.annotations.state import (
    atom_state_dict_for,
    bond_state_dict,
    mark_state_dict_for,
    ring_state_dict_for,
    scene_item_state_for,
)
from chemvas.ui.canvas.canvas_group_state import group_ids_for_members_for
from chemvas.ui.canvas.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas.canvas_model_access import atom_for_id
from chemvas.ui.canvas.canvas_scene_items_state import (
    require_scene_record_id,
    ring_items_for,
    scene_item_collection_for,
)
from chemvas.ui.canvas.canvas_smiles_input_state import clear_last_smiles_input_for
from chemvas.ui.history.history_commands import (
    DeleteSceneItemsCommand,
    GroupSceneItemsCommand,
    UngroupSceneItemsCommand,
)
from chemvas.ui.molecule.atom_label_access import atom_has_visible_label_for
from chemvas.ui.scene.scene_delete_apply_logic import apply_delete_selection_plan
from chemvas.ui.scene.scene_delete_plan import (
    build_delete_selection_plan,
    classify_delete_selection,
)
from chemvas.ui.scene.scene_delete_session import (
    _DELETED_RING_ITEM,
    SceneDeleteTransactionSession,
    _ObserverPort,
    _ring_atom_ids,
    _shrink_group_members,
)
from chemvas.ui.scene.scene_item_access import (
    remove_scene_item as remove_scene_item_helper,
)
from chemvas.ui.scene.scene_single_item_mutation_logic import (
    delete_atom_with_history,
    delete_bond_with_history,
    delete_ring_with_history,
)
from chemvas.ui.selection.selection_queries import selected_scene_items_for
from chemvas.ui.transactions.document import (
    DocumentSavepoint,
    document_transaction,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsPolygonItem

    from chemvas.domain.document.groups import SceneGroup
    from chemvas.ui.canvas.canvas_view import CanvasView


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
        return self.canvas.model.bonds

    @property
    def _next_atom_id(self) -> int:
        return int(self.canvas.model.next_atom_id)

    def _has_atom(self, atom_id: int) -> bool:
        return atom_for_id(self.canvas, atom_id) is not None

    def _redraw_connected_bonds(
        self, atom_id: int, skip_bond_id: int | None = None
    ) -> None:
        if self.move_controller is not None:
            self.move_controller.redraw_connected_bonds(
                atom_id, skip_bond_id=skip_bond_id
            )

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
        self._atom_mutation_service().remove_atom_only(
            atom_id, remove_marks=remove_marks
        )

    def _remove_scene_item(self, item) -> None:
        remove_scene_item_helper(self.canvas, item)

    def _push_history(self, command: HistoryCommand) -> None:
        if self.history.push(command) is False and self.history.is_enabled():
            raise RuntimeError("Delete history push did not commit")

    def _remove_overlapping_groups(
        self,
        *,
        atom_ids: set[int] | None = None,
        items: list | None = None,
    ) -> list[tuple[int, SceneGroup]]:
        group_ids = group_ids_for_members_for(
            self.canvas,
            atom_ids or set(),
            items or [],
        )
        removed: list[tuple[int, SceneGroup]] = []
        for group_id in sorted(group_ids):
            group = _shrink_group_members(
                self.canvas,
                group_id,
                atom_ids=atom_ids or set(),
                item_ids={require_scene_record_id(item) for item in items or ()},
            )
            if group is not None:
                removed.append((group_id, group))
        return removed

    def _with_group_cleanup(
        self,
        command: HistoryCommand,
        removed_groups: list[tuple[int, SceneGroup]],
    ) -> HistoryCommand:
        if not removed_groups:
            return command
        # Atom removal, orphan cleanup and broken ring cleanup may shrink the
        # same group repeatedly in one command. Undo needs the *first* object.
        originals: dict[int, SceneGroup] = {}
        for group_id, group in removed_groups:
            originals.setdefault(group_id, group)
        groups = self.canvas.runtime_state.group_state.groups
        group_commands: list[HistoryCommand] = []
        for group_id, original in originals.items():
            remaining = groups.get(group_id)
            if remaining is None:
                group_commands.append(UngroupSceneItemsCommand([(group_id, original)]))
            else:
                group_commands.append(
                    GroupSceneItemsCommand(
                        atom_ids=set(remaining.atom_ids),
                        item_ids=list(remaining.item_ids),
                        absorbed=[(group_id, original)],
                        group_id=group_id,
                    )
                )
        if isinstance(command, CompositeCommand):
            return CompositeCommand([*group_commands, *command.commands])
        return CompositeCommand([*group_commands, command])

    def _ring_items_with_projections(self) -> list:
        items = ring_items_for(self.canvas)
        if len(items) < len(scene_item_collection_for(self.canvas, "ring_items")):
            return restore_ring_projections(self.canvas.render_context)
        return items

    def _delete_broken_ring_fills(
        self,
        *,
        removed_groups: list[tuple[int, SceneGroup]] | None = None,
        atom_ids: set[int] | None = None,
        bond_pairs: set[tuple[int, int]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_items=None,
        removed_ring_items: list | None = None,
    ) -> DeleteSceneItemsCommand | None:
        candidates = (
            self._ring_items_with_projections()
            if ring_items is None
            else list(ring_items)
        )
        if not candidates:
            return None
        if atom_ids is None or bond_pairs is None:
            model = self.canvas.model
            atom_ids = set(model.atoms)
            bond_pairs = model_bond_pairs(model)
        live_items = [
            item
            for item in candidates
            if _ring_atom_ids(item) is not _DELETED_RING_ITEM
        ]
        broken_items = [
            live_items[index]
            for index in broken_ring_fill_indices(
                [_ring_atom_ids(item) for item in live_items],
                atom_ids=atom_ids,
                bond_pairs=bond_pairs,
            )
        ]
        broken_states = [self._ring_state(item) for item in broken_items]
        if not broken_items:
            return None
        if removed_groups is not None:
            if remove_groups_for_items is None:
                removed_groups.extend(
                    self._remove_overlapping_groups(items=broken_items)
                )
            else:
                removed_groups.extend(remove_groups_for_items(broken_items))
        command = DeleteSceneItemsCommand.capture(
            self.history.operations, broken_states, broken_items
        )
        for item in broken_items:
            self._remove_scene_item(item)
        if removed_ring_items is not None:
            removed_ring_items.extend(broken_items)
        return command

    def _with_broken_ring_cleanup(
        self,
        command: HistoryCommand,
        *,
        removed_groups: list[tuple[int, SceneGroup]],
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
        model = self.canvas.model
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
        for group_id, group in self.canvas.runtime_state.group_state.groups.items():
            atom_ids = set(group.atom_ids)
            item_ids = set(group.item_ids)
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

        # Read both callback values exactly once before the scene-rect guard is
        # opened. A live getter failure must not strand a guarded snapshot.
        observer_state = self.canvas.runtime_state.callback_state
        observer_ports = (
            _ObserverPort.capture(observer_state, "scene_selection_group"),
            _ObserverPort.capture(observer_state, "scene_selection_outline"),
        )
        selection_group_callback = observer_ports[0].value
        selection_outline_callback = observer_ports[1].value
        selection_info_state = self.canvas.runtime_state.selection_info_state
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
        snapshot = DocumentSavepoint.capture(
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
            for order, item in enumerate(self._ring_items_with_projections()):
                raw_atom_ids = _ring_atom_ids(item)
                if raw_atom_ids is _DELETED_RING_ITEM:
                    continue
                ring_id = id(item)
                ring_items_by_id[ring_id] = item
                ring_order_by_id[ring_id] = order
                if not ring_fill_is_intact(
                    raw_atom_ids, atom_ids=live_atom_ids, bond_pairs=live_bond_pairs
                ):
                    ring_dependencies_by_id[ring_id] = (set(), set())
                    pending_broken_ring_ids.add(ring_id)
                    continue
                # The shared rule established the list-of-ints shape above.
                raw_atom_ids = cast("list[int]", raw_atom_ids)
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
        except Exception as original_error:
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
                except Exception as release_error:
                    cleanup_errors.append(
                        ("releasing the failed delete guard", release_error)
                    )
            session.active = False
            for phase, cleanup_error in cleanup_errors:
                add_recovery_error_note(original_error, cleanup_error, phase=phase)
            raise
        return session

    def delete_atom(self, atom_id: int, record: bool = True) -> HistoryCommand | None:
        with document_transaction(self.canvas, history_service=self.history):
            return self._delete_atom(atom_id, record=record)

    def _delete_atom(
        self,
        atom_id: int,
        *,
        record: bool,
        bond_ids=None,
        ring_atom_ids: set[int] | None = None,
        ring_bond_pairs: set[tuple[int, int]] | None = None,
        removed_groups: list[tuple[int, SceneGroup]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_ring_items=None,
        remove_groups_for_atoms=None,
        removed_ring_items: list | None = None,
        removed_atom_ids: list | None = None,
    ) -> HistoryCommand | None:
        if not isinstance(atom_id, int) or not self._has_atom(atom_id):
            return None
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(
                atom_ids={atom_id}, items=list(self.marks.by_atom.get(atom_id, ()))
            )
        before_smiles_input = (
            self.canvas.runtime_state.smiles_input_state.last_smiles_input
        )
        neighbor_atom_ids = self._neighbor_atom_ids(atom_id, bond_ids=bond_ids)
        command = self._atom_delete_command(
            atom_id,
            before_smiles_input=before_smiles_input,
            bond_ids=bond_ids,
        )
        # The tail from here matches `_delete_bond`'s apart from
        # `candidate_atom_ids`, and stays a copy on purpose: every other value
        # in it is a parameter of this method, so a shared helper has to take
        # twelve keywords and both call sites have to spell them out. Extracting
        # it was measured at 24 net lines added.
        command = self._with_orphan_cleanup(
            command,
            candidate_atom_ids=neighbor_atom_ids,
            before_smiles_input=before_smiles_input,
            removed_groups=removed_groups,
            remove_groups_for_atoms=remove_groups_for_atoms,
            removed_atom_ids=removed_atom_ids,
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
        with document_transaction(self.canvas, history_service=self.history):
            return self._delete_bond(bond_id, record=record)

    def _atom_delete_command(
        self,
        atom_id: int,
        *,
        before_smiles_input,
        bond_ids=None,
    ) -> HistoryCommand:
        return delete_atom_with_history(
            atom_id,
            bonds=self._bonds,
            marks_by_atom=self.marks.by_atom,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: (
                self.canvas.runtime_state.smiles_input_state.last_smiles_input
            ),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            mark_state_getter=self._mark_state,
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
            atom_state_getter=self._atom_state,
            next_atom_id_getter=lambda: self._next_atom_id,
            remove_atom_only=self._remove_atom,
            remove_scene_item=self._remove_scene_item,
            scene_delete_command_factory=partial(
                DeleteSceneItemsCommand.capture, self.history.operations
            ),
            atom_coords_3d_getter=lambda atom_id: (
                self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.get(
                    atom_id
                )
            ),
            bond_ids=bond_ids,
        )

    def _removable_orphaned_atom_ids(
        self, candidate_atom_ids: tuple[int, ...]
    ) -> list[int]:
        # The removed bond is already gone from the model here, so the shared
        # rule sees only surviving bonds. A label or an attached mark keeps the
        # atom visible on the sheet, so orphaning must not delete it.
        return list(
            orphaned_atom_ids(
                self._bonds,
                candidate_atom_ids=candidate_atom_ids,
                atom_exists=self._has_atom,
                keeps_visible=lambda atom_id: (
                    atom_has_visible_label_for(self.canvas, atom_id)
                    or bool(self.marks.by_atom.get(atom_id))
                ),
            )
        )

    def _neighbor_atom_ids(self, atom_id: int, *, bond_ids=None) -> tuple[int, ...]:
        bonds = self._bonds
        candidate_bond_ids = (
            range(len(bonds)) if bond_ids is None else sorted(set(bond_ids))
        )
        neighbors: dict[int, None] = {}
        for bond_id in candidate_bond_ids:
            if not (0 <= bond_id < len(bonds)):
                continue
            bond = bonds[bond_id]
            if bond is None or atom_id not in (bond.a, bond.b):
                continue
            other = bond.b if bond.a == atom_id else bond.a
            if other != atom_id:
                neighbors[other] = None
        return tuple(neighbors)

    def _with_orphan_cleanup(
        self,
        command: HistoryCommand,
        *,
        candidate_atom_ids: tuple[int, ...],
        before_smiles_input,
        removed_groups: list[tuple[int, SceneGroup]],
        remove_groups_for_atoms=None,
        removed_atom_ids: list | None = None,
    ) -> HistoryCommand:
        orphaned_atom_ids = self._removable_orphaned_atom_ids(candidate_atom_ids)
        if not orphaned_atom_ids:
            return command
        if remove_groups_for_atoms is None:
            removed_groups.extend(
                self._remove_overlapping_groups(atom_ids=set(orphaned_atom_ids))
            )
        else:
            removed_groups.extend(remove_groups_for_atoms(set(orphaned_atom_ids)))
        atom_commands = [
            self._atom_delete_command(
                atom_id,
                before_smiles_input=before_smiles_input,
                bond_ids=(),
            )
            for atom_id in orphaned_atom_ids
        ]
        # Session bookkeeping is synced by the caller through removed_atom_ids;
        # rings referencing an orphaned atom are already broken because all of
        # its bond pairs are gone.
        if removed_atom_ids is not None:
            removed_atom_ids.extend(orphaned_atom_ids)
        return CompositeCommand([command, *atom_commands])

    def _delete_bond(
        self,
        bond_id: int,
        *,
        record: bool,
        ring_atom_ids: set[int] | None = None,
        ring_bond_pairs: set[tuple[int, int]] | None = None,
        ring_items: list | None = None,
        remove_groups_for_ring_items=None,
        remove_groups_for_atoms=None,
        removed_ring_items: list | None = None,
        removed_atom_ids: list | None = None,
    ) -> HistoryCommand | None:
        if not isinstance(bond_id, int):
            return None
        removed_groups: list[tuple[int, SceneGroup]] = []
        before_smiles_input = (
            self.canvas.runtime_state.smiles_input_state.last_smiles_input
        )
        bonds = self._bonds
        bond = bonds[bond_id] if 0 <= bond_id < len(bonds) else None
        endpoint_atom_ids = (
            () if bond is None else tuple(dict.fromkeys((bond.a, bond.b)))
        )
        bond_command = delete_bond_with_history(
            bond_id,
            bonds=self._bonds,
            before_smiles_input=before_smiles_input,
            current_smiles_input_getter=lambda: (
                self.canvas.runtime_state.smiles_input_state.last_smiles_input
            ),
            clear_smiles_input=lambda: clear_last_smiles_input_for(self.canvas),
            bond_state_getter=self._bond_state,
            remove_bond_by_id=self._remove_bond,
            redraw_connected_bonds=self._redraw_connected_bonds,
        )
        if bond_command is None:
            return None
        # The tail from here matches `_delete_atom`'s apart from
        # `candidate_atom_ids`; see the note there for why it is not shared.
        command = self._with_orphan_cleanup(
            bond_command,
            candidate_atom_ids=endpoint_atom_ids,
            before_smiles_input=before_smiles_input,
            removed_groups=removed_groups,
            remove_groups_for_atoms=remove_groups_for_atoms,
            removed_atom_ids=removed_atom_ids,
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

    def delete_ring(
        self, item: QGraphicsPolygonItem, record: bool = True
    ) -> HistoryCommand | None:
        with document_transaction(self.canvas, history_service=self.history):
            return self._delete_ring(item, record=record)

    def _delete_ring(
        self,
        item: QGraphicsPolygonItem,
        *,
        record: bool,
        removed_groups: list[tuple[int, SceneGroup]] | None = None,
    ) -> HistoryCommand | None:
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(items=[item])
        command: HistoryCommand = delete_ring_with_history(
            item,
            ring_state_getter=self._ring_state,
            remove_scene_item=self._remove_scene_item,
            scene_delete_command_factory=partial(
                DeleteSceneItemsCommand.capture, self.history.operations
            ),
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
        removed_groups: list[tuple[int, SceneGroup]] | None = None,
    ) -> HistoryCommand:
        if removed_groups is None:
            removed_groups = self._remove_overlapping_groups(items=[item])
        command: HistoryCommand = DeleteSceneItemsCommand.capture(
            self.history.operations,
            item_states=[state],
            items=[item],
        )
        self._remove_scene_item(item)
        atom_id = state.get("atom_id") if state.get("kind") == "mark" else None
        if isinstance(atom_id, int):
            labels = self.canvas.services.canvas_mark_scene_service.reveal_unmarked_isolated_carbons(
                {atom_id}
            )
            if labels:
                command = CompositeCommand([command, *labels])
        return self._with_group_cleanup(command, removed_groups)

    def delete_selected_items(self) -> bool:
        with document_transaction(self.canvas, history_service=self.history):
            return self._delete_selected_items()

    def _selection_delete_cleanup_errors(self) -> list[tuple[str, BaseException]]:
        errors: list[tuple[str, BaseException]] = []
        actions = (
            (
                "resuming the selection outline after a delete",
                lambda: self._style_controller().suspend_selection_outline(False),
            ),
            (
                "refreshing the selection outline after a delete",
                lambda: self.canvas.services.selection.update_selection_outline(),
            ),
        )
        for phase, action in actions:
            try:
                action()
            except Exception as exc:
                errors.append((phase, exc))
        return errors

    def _delete_selected_items(self) -> bool:
        items = selected_scene_items_for(
            self.canvas, excluded_kinds={"handle", "note_box", "note_select"}
        )
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
                atom_has_visible_label=lambda atom_id: atom_has_visible_label_for(
                    self.canvas, atom_id
                ),
            )

            if plan.single_bond_id is not None:
                self._delete_bond(plan.single_bond_id, record=True)
                return True

            removed_groups = self._remove_overlapping_groups(
                atom_ids=set(plan.atom_ids),
                items=plan.scene_items,
            )
            before_smiles_input = (
                self.canvas.runtime_state.smiles_input_state.last_smiles_input
            )
            if plan.clear_smiles_input:
                clear_last_smiles_input_for(self.canvas)
            mark_owner_ids = {
                atom_id
                for item in plan.scene_items
                if item.data(0) == "mark"
                and isinstance(atom_id := (item.data(1) or {}).get("atom_id"), int)
            } - set(plan.atom_ids)
            commands = apply_delete_selection_plan(
                plan,
                bonds=self._bonds,
                before_smiles_input=before_smiles_input,
                current_smiles_input_getter=lambda: (
                    self.canvas.runtime_state.smiles_input_state.last_smiles_input
                ),
                bond_state_getter=self._bond_state,
                remove_bond_by_id=self._remove_bond,
                redraw_connected_bonds=self._redraw_connected_bonds,
                atom_state_getter=self._atom_state,
                next_atom_id_getter=lambda: self._next_atom_id,
                remove_atom_only=self._remove_atom,
                scene_item_state_getter=self._scene_item_state,
                remove_scene_item=self._remove_scene_item,
                clear_handles=lambda: (
                    self.canvas.services.handle_overlay_service.clear_handles()
                ),
                scene_delete_command_factory=partial(
                    DeleteSceneItemsCommand.capture, self.history.operations
                ),
                atom_coords_3d_getter=lambda atom_id: (
                    self.canvas.runtime_state.atom_coords_3d_state.atom_coords_3d.get(
                        atom_id
                    )
                ),
            )
            if mark_owner_ids:
                commands.extend(
                    self.canvas.services.canvas_mark_scene_service.reveal_unmarked_isolated_carbons(
                        mark_owner_ids
                    )
                )

            if any(
                isinstance(command, (DeleteAtomsCommand, DeleteBondCommand))
                for command in commands
            ):
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
        except Exception as exc:
            body_error = exc
            raise
        finally:
            cleanup_errors = self._selection_delete_cleanup_errors()
            if body_error is not None:
                for phase, cleanup_error in cleanup_errors:
                    add_recovery_error_note(body_error, cleanup_error, phase=phase)
            elif cleanup_errors:
                _, primary_error = cleanup_errors[0]
                for phase, cleanup_error in cleanup_errors[1:]:
                    add_recovery_error_note(primary_error, cleanup_error, phase=phase)
                raise primary_error


__all__ = ["SceneDeleteController", "SceneDeleteTransactionSession"]
