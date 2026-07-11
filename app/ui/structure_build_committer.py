from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF

from ui.atom_label_access import add_or_update_atom_label, atom_label_service
from ui.canvas_model_access import atom_for_id, atoms_for, bonds_for
from ui.canvas_ring_fill_scene_access import create_ring_fill_item_for
from ui.canvas_scene_items_state import (
    SCENE_ITEM_COLLECTION_ATTRS,
    ring_items_for,
    scene_item_collection_for,
)
from ui.canvas_smiles_input_state import (
    clear_last_smiles_input_for,
    last_smiles_input_for,
)
from ui.graph_algorithms import find_rings
from ui.graph_index_operations import first_matching_bond_id
from ui.history_canvas_access import (
    capture_history_transaction_for_history,
    release_history_transaction_for_history,
    restore_history_transaction_for_history,
    verify_history_transaction_for_history,
)
from ui.history_restore_retry import restore_history_snapshot_with_retry
from ui.insert_commit_rollback import (
    SmilesInputRestoreAuthority,
    capture_smiles_input_restore_authority,
)
from ui.renderer_style_access import bond_length_px_for
from ui.scene_item_access import (
    attach_scene_item,
    refresh_bond_geometry_for_ring_item,
    remove_item_from_canvas_scene,
    remove_scene_item,
)
from ui.structure_insert_access import (
    add_insert_atom_for,
    add_insert_bond_for,
    add_insert_bond_graphics_for,
    ensure_insert_carbon_dot_for,
    insert_atom_for_id,
    insert_bond_count_for,
    insert_bond_for_id,
    insert_next_atom_id_for,
    new_insert_bond_ids_from,
    record_insert_additions_for,
    rollback_insert_mutation_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


def _add_build_rollback_note(
    original_error: BaseException,
    cleanup_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"{phase}: {cleanup_error!r}")
    except BaseException:
        return


@dataclass(slots=True)
class StructureBuildHistorySnapshot:
    before_smiles_input: str | None
    before_next_atom_id: int
    before_bond_count: int
    before_scene_items: dict[str, tuple[Any, ...]]
    exact_transaction: Any
    smiles_authority: SmilesInputRestoreAuthority


class StructureBuildCommitter:
    def __init__(self, canvas: CanvasView) -> None:
        self.canvas = canvas

    def begin_recorded_change(
        self,
        *,
        before_smiles_input: str | None = None,
    ) -> StructureBuildHistorySnapshot:
        if before_smiles_input is None:
            before_smiles_input = last_smiles_input_for(self.canvas)
        services = getattr(self.canvas, "services", None)
        history_service = getattr(services, "history_service", None)
        smiles_authority = capture_smiles_input_restore_authority(self.canvas)
        before_next_atom_id = insert_next_atom_id_for(self.canvas)
        before_bond_count = insert_bond_count_for(self.canvas)
        before_scene_items = self._scene_item_snapshot()
        try:
            # Exact capture crosses live extension getters (for example the
            # renderer style).  Keep the capture itself inside the raw
            # model/scene/SMILES baseline: a getter can poison one of those
            # roots before terminating, even though the build body has not run.
            exact_transaction = capture_history_transaction_for_history(
                self.canvas,
                history_service=history_service,
            )
        except BaseException as error:
            capture_baseline = StructureBuildHistorySnapshot(
                before_smiles_input=before_smiles_input,
                before_next_atom_id=before_next_atom_id,
                before_bond_count=before_bond_count,
                before_scene_items=before_scene_items,
                exact_transaction=None,
                smiles_authority=smiles_authority,
            )
            cleanup_errors: list[BaseException] = []
            try:
                cleanup_errors.extend(self._remove_new_scene_items(capture_baseline))
            except BaseException as scene_cleanup_error:
                cleanup_errors.append(scene_cleanup_error)
            try:
                rollback_insert_mutation_for(
                    self.canvas,
                    before_next_atom_id=before_next_atom_id,
                    before_bond_count=before_bond_count,
                )
            except BaseException as model_cleanup_error:
                cleanup_errors.append(model_cleanup_error)
            smiles_result = smiles_authority.restore(before_smiles_input)
            cleanup_errors.extend(smiles_result.errors)
            if not smiles_result.authoritative and not smiles_result.errors:
                cleanup_errors.append(
                    RuntimeError("build capture SMILES restore was non-authoritative")
                )
            for recorded_cleanup_error in cleanup_errors:
                _add_build_rollback_note(
                    error,
                    recorded_cleanup_error,
                    phase="Build capture rollback also failed",
                )
            raise

        snapshot = StructureBuildHistorySnapshot(
            before_smiles_input=before_smiles_input,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
            before_scene_items=before_scene_items,
            exact_transaction=exact_transaction,
            smiles_authority=smiles_authority,
        )
        try:
            clear_last_smiles_input_for(self.canvas)
        except BaseException as error:
            restore_result = restore_history_snapshot_with_retry(
                lambda: restore_history_transaction_for_history(
                    self.canvas,
                    snapshot.exact_transaction,
                ),
                description="build initialization transaction",
            )
            for caught_rollback_error in restore_result.errors:
                _add_build_rollback_note(
                    error,
                    caught_rollback_error,
                    phase="Build initialization rollback also failed",
                )
            raise
        return snapshot

    def record_additions(
        self,
        snapshot: StructureBuildHistorySnapshot,
        *,
        added_scene_items: list | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "before_next_atom_id": snapshot.before_next_atom_id,
            "before_bond_count": snapshot.before_bond_count,
            "before_smiles_input": snapshot.before_smiles_input,
        }
        merged_scene_items = self._merged_added_scene_items(snapshot, added_scene_items)
        if merged_scene_items is not None:
            kwargs["added_scene_items"] = merged_scene_items
        published_transaction = capture_history_transaction_for_history(
            self.canvas,
            history_service=None,
            guard_scene_rect=False,
        )
        try:
            record_insert_additions_for(self.canvas, **kwargs)
            verify_history_transaction_for_history(
                self.canvas,
                published_transaction,
            )
        except BaseException as error:
            try:
                release_history_transaction_for_history(
                    self.canvas,
                    published_transaction,
                )
            except BaseException as cleanup_error:
                _add_build_rollback_note(
                    error,
                    cleanup_error,
                    phase="Build publication snapshot release also failed",
                )
            raise
        else:
            release_history_transaction_for_history(
                self.canvas,
                published_transaction,
            )
        self.release_recorded_change(snapshot)

    def release_recorded_change(
        self,
        snapshot: StructureBuildHistorySnapshot,
    ) -> None:
        release_history_transaction_for_history(
            self.canvas,
            snapshot.exact_transaction,
        )

    def abort_recorded_change(
        self,
        snapshot: StructureBuildHistorySnapshot,
        *,
        original_error: BaseException | None = None,
    ) -> None:
        """Best-effort rollback for a recorded build.

        Scene cleanup, model rollback, and SMILES restoration are independent
        phases. A failure in one phase must not prevent the later phases from
        running. When this is called while handling the mutation's original
        exception, cleanup failures are attached as notes and the caller can
        re-raise that original exception unchanged.
        """

        cleanup_errors: list[BaseException] = []
        try:
            cleanup_errors.extend(self._remove_new_scene_items(snapshot))
        except BaseException as error:
            cleanup_errors.append(error)
        try:
            rollback_insert_mutation_for(
                self.canvas,
                before_next_atom_id=snapshot.before_next_atom_id,
                before_bond_count=snapshot.before_bond_count,
            )
        except BaseException as error:
            cleanup_errors.append(error)
        restore_result = restore_history_snapshot_with_retry(
            lambda: restore_history_transaction_for_history(
                self.canvas,
                snapshot.exact_transaction,
            ),
            description="recorded build transaction",
        )
        if original_error is not None or not restore_result.authoritative:
            cleanup_errors.extend(restore_result.errors)
        # ``before_smiles_input`` may intentionally differ from the live value
        # captured by the exact UI snapshot (callers can supply an explicit
        # logical predecessor). Apply that contract after the raw restore.
        smiles_result = snapshot.smiles_authority.restore(snapshot.before_smiles_input)
        cleanup_errors.extend(smiles_result.errors)
        if not smiles_result.authoritative and not smiles_result.errors:
            cleanup_errors.append(
                RuntimeError("recorded build SMILES restore was non-authoritative")
            )

        if not cleanup_errors:
            return
        if original_error is not None:
            for cleanup_error in cleanup_errors:
                _add_build_rollback_note(
                    original_error,
                    cleanup_error,
                    phase="Rollback cleanup also failed",
                )
            return
        first_error, *additional_errors = cleanup_errors
        for cleanup_error in additional_errors:
            _add_build_rollback_note(
                first_error,
                cleanup_error,
                phase="Additional rollback cleanup failure",
            )
        raise first_error

    def _scene_item_snapshot(self) -> dict[str, tuple[Any, ...]]:
        return {
            name: tuple(scene_item_collection_for(self.canvas, name))
            for name in SCENE_ITEM_COLLECTION_ATTRS
        }

    def _new_scene_items_since(
        self, snapshot: StructureBuildHistorySnapshot
    ) -> list[Any]:
        items: list[Any] = []
        seen_ids: set[int] = set()
        before_ids = {
            id(item)
            for collection in snapshot.before_scene_items.values()
            for item in collection
        }
        for name in SCENE_ITEM_COLLECTION_ATTRS:
            for item in scene_item_collection_for(self.canvas, name):
                item_id = id(item)
                if item_id in before_ids or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                items.append(item)
        return items

    def _merged_added_scene_items(
        self,
        snapshot: StructureBuildHistorySnapshot,
        added_scene_items: list | None,
    ) -> list | None:
        merged: list[Any] = []
        seen_ids: set[int] = set()
        for item in [
            *(added_scene_items or []),
            *self._new_scene_items_since(snapshot),
        ]:
            item_id = id(item)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(item)
        if added_scene_items is None and not merged:
            return None
        return merged

    def _remove_new_scene_items(
        self, snapshot: StructureBuildHistorySnapshot
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        services = getattr(self.canvas, "services", None)
        scene_item_controller = getattr(services, "scene_item_controller", None)
        canonical_remove = getattr(scene_item_controller, "remove_scene_item", None)
        for item in reversed(self._new_scene_items_since(snapshot)):
            if callable(canonical_remove):
                try:
                    remove_scene_item(self.canvas, item)
                except BaseException as error:
                    errors.append(error)
                else:
                    continue
            # A lifecycle callback can raise before or after doing only part of
            # the detach. Finish the basic registry/scene cleanup directly so a
            # failed history record does not leave an orphan ring over a model
            # that is about to be rolled back.
            for name in SCENE_ITEM_COLLECTION_ATTRS:
                try:
                    collection = scene_item_collection_for(self.canvas, name)
                    if item in collection:
                        collection.remove(item)
                except BaseException as fallback_error:
                    errors.append(fallback_error)
            scene_method = getattr(self.canvas, "scene", None)
            try:
                scene = scene_method() if callable(scene_method) else None
            except BaseException as fallback_error:
                errors.append(fallback_error)
                scene = None
            if callable(getattr(scene, "removeItem", None)):
                try:
                    remove_item_from_canvas_scene(self.canvas, item)
                except BaseException as fallback_error:
                    errors.append(fallback_error)
            data_method = getattr(item, "data", None)
            try:
                kind = data_method(0) if callable(data_method) else None
            except BaseException as fallback_error:
                errors.append(fallback_error)
                kind = None
            if kind == "ring":
                # Ring fills clip/offset their bound bond graphics. Whether
                # lifecycle removal failed before detach or during its own
                # refresh, retry while the model graph still exists.
                try:
                    refresh_bond_geometry_for_ring_item(self.canvas, item)
                except BaseException as fallback_error:
                    errors.append(fallback_error)
        return errors

    def add_bond_graphics(self, bond_id: int) -> None:
        add_insert_bond_graphics_for(self.canvas, bond_id)

    def add_atom(self, element: str, x: float, y: float) -> int:
        return add_insert_atom_for(self.canvas, element, x, y)

    def add_bond(
        self, a_id: int, b_id: int, order: int = 1, *, style: str = "single"
    ) -> int:
        bond_id = add_insert_bond_for(self.canvas, a_id, b_id, order)
        bond = insert_bond_for_id(self.canvas, bond_id)
        if bond is not None:
            bond.style = style
        return bond_id

    def bond_id_between(self, a_id: int, b_id: int) -> int | None:
        return first_matching_bond_id(bonds_for(self.canvas), a_id, b_id)

    def add_bond_graphics_range(self, start_bond_id: int) -> None:
        for bond_id in new_insert_bond_ids_from(self.canvas, start_bond_id):
            self.add_bond_graphics(bond_id)

    def add_atom_label(
        self,
        atom_id: int,
        element: str,
        *,
        record: bool = True,
        show_carbon: bool = False,
    ) -> None:
        kwargs = {"record": record}
        if show_carbon:
            kwargs["show_carbon"] = True
        atom_label_service(self.canvas).add_or_update_atom_label(
            atom_id, element, **kwargs
        )

    def label_non_carbon_atoms(self, atom_ids: list[int], elements: list[str]) -> None:
        for atom_id, element in zip(atom_ids, elements, strict=False):
            if element != "C":
                atom = insert_atom_for_id(self.canvas, atom_id)
                if atom is None:
                    continue
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    record=False,
                )

    def add_atom_with_merge(self, point: QPointF, element: str, merge: list) -> int:
        tol = bond_length_px_for(self.canvas) * 0.2
        for entry in merge:
            atom_id, x, y = entry
            if abs(point.x() - x) < tol and abs(point.y() - y) < tol:
                return atom_id
        atom_id = self.add_atom(element, point.x(), point.y())
        merge.append((atom_id, point.x(), point.y()))
        return atom_id

    def add_ring_from_points(
        self,
        points,
        elements: list[str] | None = None,
        merge: list | None = None,
        bond_orders: list[int] | None = None,
    ) -> list[int]:
        if merge is None:
            merge = []
        atom_ids = []
        for idx, point in enumerate(points):
            element = elements[idx] if elements else "C"
            atom_ids.append(self.add_atom_with_merge(point, element, merge))
        resolved_bond_orders = self.resolved_ring_bond_orders(atom_ids, bond_orders)
        bonds_start = insert_bond_count_for(self.canvas)
        for index in range(len(atom_ids)):
            order = resolved_bond_orders[index]
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            if self.bond_id_between(a_id, b_id) is not None:
                continue
            self.add_bond(a_id, b_id, order)
        self.add_bond_graphics_range(bonds_start)
        self.label_non_carbon_atoms(atom_ids, elements or ["C"] * len(atom_ids))
        self.add_ring_fill(points, atom_ids)
        return atom_ids

    def add_ring_fill(self, points, atom_ids: list[int]):
        if len(points) < 3:
            return None
        ring_item = create_ring_fill_item_for(self.canvas, list(points), list(atom_ids))
        attach_scene_item(self.canvas, ring_item)
        return ring_item

    def resolved_ring_bond_orders(
        self, atom_ids: list[int], bond_orders: list[int] | None
    ) -> list[int]:
        if not bond_orders:
            return [1] * len(atom_ids)
        resolved = [
            bond_orders[index] if index < len(bond_orders) else 1
            for index in range(len(atom_ids))
        ]
        if not self._is_alternating_single_double_pattern(resolved):
            return resolved
        inverted = [1 if order == 2 else 2 for order in resolved]
        valid_candidates = [
            (
                self._projected_ring_double_bond_count(atom_ids, candidate),
                index,
                candidate,
            )
            for index, candidate in enumerate((resolved, inverted))
            if self._max_projected_bond_order_sum(atom_ids, candidate) <= 4
        ]
        exact_benzene_candidates = [
            candidate for candidate in valid_candidates if candidate[0] == 3
        ]
        if exact_benzene_candidates:
            return min(exact_benzene_candidates, key=lambda candidate: candidate[1])[2]
        under_benzene_candidates = [
            candidate for candidate in valid_candidates if candidate[0] < 3
        ]
        if under_benzene_candidates:
            return max(
                under_benzene_candidates,
                key=lambda candidate: (candidate[0], -candidate[1]),
            )[2]
        if valid_candidates:
            return min(
                valid_candidates, key=lambda candidate: (candidate[0], candidate[1])
            )[2]
        return resolved

    @staticmethod
    def _is_alternating_single_double_pattern(bond_orders: list[int]) -> bool:
        return all(order in (1, 2) for order in bond_orders) and all(
            bond_orders[index] != bond_orders[(index + 1) % len(bond_orders)]
            for index in range(len(bond_orders))
        )

    def _max_projected_bond_order_sum(
        self, atom_ids: list[int], bond_orders: list[int]
    ) -> int:
        sums = {atom_id: 0 for atom_id in atom_ids}
        for bond in bonds_for(self.canvas):
            if bond is None:
                continue
            if bond.a in sums:
                sums[bond.a] += max(1, int(bond.order or 1))
            if bond.b in sums:
                sums[bond.b] += max(1, int(bond.order or 1))
        for index, order in enumerate(bond_orders):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            if self.bond_id_between(a_id, b_id) is not None:
                continue
            sums[a_id] += order
            sums[b_id] += order
        return max(sums.values(), default=0)

    def _projected_ring_double_bond_count(
        self, atom_ids: list[int], bond_orders: list[int]
    ) -> int:
        double_count = 0
        for index, order in enumerate(bond_orders):
            a_id = atom_ids[index]
            b_id = atom_ids[(index + 1) % len(atom_ids)]
            existing_bond = insert_bond_for_id(
                self.canvas, self.bond_id_between(a_id, b_id)
            )
            if existing_bond is not None:
                if existing_bond.order >= 2:
                    double_count += 1
            elif order == 2:
                double_count += 1
        return double_count

    def add_linear_chain(
        self, points: list[QPointF], elements: list[str], bonds: list[int]
    ) -> list[int]:
        atom_ids = []
        for point, element in zip(points, elements, strict=False):
            atom_ids.append(self.add_atom(element, point.x(), point.y()))
        bonds_start = insert_bond_count_for(self.canvas)
        for index, order in enumerate(bonds):
            self.add_bond(atom_ids[index], atom_ids[index + 1], order)
        self.add_bond_graphics_range(bonds_start)
        self.label_non_carbon_atoms(atom_ids, elements)
        return atom_ids

    def ensure_ring_fills_for_model(self) -> list:
        rings = find_rings(bonds_for(self.canvas))
        if not rings:
            return []
        existing: set[frozenset[int]] = set()
        for ring_item in ring_items_for(self.canvas):
            ring_atom_ids = ring_item.data(2)
            if isinstance(ring_atom_ids, list):
                existing.add(frozenset(a for a in ring_atom_ids if isinstance(a, int)))
        created: list = []
        for ring in rings:
            if frozenset(ring) in existing:
                continue
            points = []
            for atom_id in ring:
                atom = atom_for_id(self.canvas, atom_id)
                if atom is None:
                    break
                points.append(QPointF(atom.x, atom.y))
            if len(points) != len(ring) or len(points) < 3:
                continue
            item = create_ring_fill_item_for(self.canvas, points, list(ring))
            attach_scene_item(self.canvas, item)
            created.append(item)
        return created

    def render_model(self) -> None:
        for bond_id, bond in enumerate(bonds_for(self.canvas)):
            if bond is None:
                continue
            self.add_bond_graphics(bond_id)

        for atom_id, atom in atoms_for(self.canvas).items():
            if atom.element == "C":
                if atom.explicit_label:
                    add_or_update_atom_label(
                        self.canvas,
                        atom_id,
                        atom.element,
                        clear_smiles=False,
                        record=False,
                        show_carbon=True,
                    )
                else:
                    ensure_insert_carbon_dot_for(self.canvas, atom_id)
            else:
                add_or_update_atom_label(
                    self.canvas,
                    atom_id,
                    atom.element,
                    clear_smiles=False,
                    record=False,
                )


__all__ = ["StructureBuildCommitter", "StructureBuildHistorySnapshot"]
