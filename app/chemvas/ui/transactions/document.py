from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, cast

from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.bond_renderer_access import bond_renderer_for
from chemvas.ui.renderer_style_access import renderer_for
from chemvas.ui.transactions.object_graph_snapshot import (
    ContainerGraphSnapshot as _ContainerGraphSnapshot,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    ObjectStateSnapshot as _ObjectStateSnapshot,
)
from chemvas.ui.transactions.object_graph_snapshot import (
    SceneItemExactSnapshot as _SceneItemExactSnapshot,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    scene_rect_is_automatic,
)
from chemvas.ui.transactions.scene_runtime import (
    SceneRuntimeSnapshot,
    capture_atom_primitive_graphics,
    capture_scene_runtime,
    restore_primitive_graphics,
    restore_scene_runtime,
    verify_scene_runtime_identity,
)

_MISSING_RENDERER_STYLE = object()


def _collect_restore_errors(
    operation,
    destination: list[BaseException],
) -> None:
    try:
        result = operation()
    except Exception as exc:
        destination.append(exc)
        return
    destination.extend(result)


def _add_delete_rollback_note(
    original_error: BaseException,
    secondary_error: BaseException,
) -> None:
    original_error.add_note(
        "Delete rollback also encountered "
        f"{type(secondary_error).__name__}: {secondary_error}"
    )


@dataclass(frozen=True)
class MoveGestureScope:
    """The mutation footprint of a pure-move drag gesture.

    A selection move mutates only atom coordinates, their 3D coordinates,
    the runtime state objects, and the positions/geometry/data of a closed
    set of scene items (atom labels/dots, marks, incident bond items,
    affected ring polygons, independently moved selection items, active
    handles, and selection outlines). Capturing a savepoint restricted to
    that footprint keeps the fail-closed restore exact for everything the
    gesture can touch while skipping the per-item snapshots of the rest of
    the document. Gestures whose footprint is not closed (handle drags,
    direct item drags that redraw bonds) must keep the whole-document
    capture by passing no scope.
    """

    atom_ids: frozenset[int]
    bond_ids: frozenset[int]
    scene_items: tuple[Any, ...]


def _capture_optional_attribute(
    target: object,
    name: str,
    *,
    default: object = None,
) -> object:
    return getattr(target, name, default)


def _capture_canvas_state_object(canvas, name: str) -> object | None:
    runtime_state = _capture_optional_attribute(canvas, "runtime_state")
    if runtime_state is not None:
        state = _capture_optional_attribute(runtime_state, name)
        if state is not None:
            return state
    return _capture_optional_attribute(canvas, name)


_DELETE_MUTATED_RUNTIME_FIELDS = (
    "graph_state",
    "atom_coords_3d_state",
    "atom_graphics_state",
    "bond_graphics_state",
    "mark_registry",
    "spatial_index_state",
    "handle_state",
    "hover_preview_state",
    "selection_style_state",
    "selection_outline_state",
    "selection_info_state",
    "scene_items_state",
    "group_state",
    "scene_clipboard_state",
    "insert_state",
    "rotation_state",
    "smiles_input_state",
    "history_state",
)


def _delete_scene_for_capture(canvas) -> object | None:
    scene_method = _capture_optional_attribute(canvas, "scene")
    if not callable(scene_method):
        return None
    return scene_method()


def _delete_scene_items_for_capture(
    scene: object | None,
) -> tuple[object, ...]:
    if scene is None:
        return ()
    items = _capture_optional_attribute(scene, "items")
    if not callable(items):
        return ()
    return tuple(items())


@dataclass(slots=True)
class DocumentSavepoint:
    canvas: Any
    canvas_model: object
    renderer: object | None
    renderer_style: object
    history_service: object | None
    containers: _ContainerGraphSnapshot
    objects: tuple[_ObjectStateSnapshot, ...]
    scene_runtime: SceneRuntimeSnapshot
    atom_primitive_graphics: tuple[Any, ...]
    scene_items: tuple[_SceneItemExactSnapshot, ...]
    scene: Any | None
    scene_rect_snapshot: SceneRectSnapshot | None
    scene_items_bounding_rect_getter: Any | None
    notify_history_change: Callable[[], object] | None
    move_scope: MoveGestureScope | None = None
    history_notification_published: bool = False
    active: bool = True

    @classmethod
    def capture(
        cls,
        canvas,
        *,
        history_service=None,
        guard_scene_rect: bool = False,
        move_scope: MoveGestureScope | None = None,
    ) -> DocumentSavepoint:
        containers = _ContainerGraphSnapshot()

        notify_history_change_value = _capture_optional_attribute(
            history_service,
            "notify_change",
        )
        notify_history_change = (
            notify_history_change_value
            if callable(notify_history_change_value)
            else None
        )

        objects: list[_ObjectStateSnapshot] = []
        snapshots_by_target: dict[int, _ObjectStateSnapshot] = {}

        def append(
            target: object | None,
            *,
            names: tuple[str, ...] | None = None,
        ) -> _ObjectStateSnapshot | None:
            if target is None:
                return None
            existing = snapshots_by_target.get(id(target))
            if existing is not None:
                return existing
            snapshot = _ObjectStateSnapshot.capture(
                target,
                containers,
                names=names,
            )
            if snapshot is None:
                return None
            snapshots_by_target[id(target)] = snapshot
            objects.append(snapshot)
            return snapshot

        model = _capture_optional_attribute(canvas, "model")
        try:
            renderer = renderer_for(canvas)
        except AttributeError:
            # Savepoints also support deliberately model-only/headless canvases.
            renderer = None
        renderer_style = (
            _capture_optional_attribute(
                renderer,
                "style",
                default=_MISSING_RENDERER_STYLE,
            )
            if renderer is not None
            else _MISSING_RENDERER_STYLE
        )
        append(
            model,
            names=("next_atom_id", "atom_annotations", "atoms", "bonds"),
        )
        atoms = _capture_optional_attribute(model, "atoms")
        if isinstance(atoms, dict):
            for atom_id, atom in tuple(atoms.items()):
                if move_scope is not None and atom_id not in move_scope.atom_ids:
                    continue
                append(atom)
        bonds = _capture_optional_attribute(model, "bonds")
        if isinstance(bonds, (list, tuple)):
            for bond_id, bond in enumerate(tuple(bonds)):
                if move_scope is not None and bond_id not in move_scope.bond_ids:
                    continue
                append(bond)

        runtime_states: dict[str, object | None] = {}
        for name in _DELETE_MUTATED_RUNTIME_FIELDS:
            # A publication checkpoint intentionally excludes history: pushing
            # the command is the expected delta being published, while the
            # caller verifies that delta with its independently captured
            # HistoryStackSnapshot/checkpoint. Including the runtime-owned
            # alias here would reject every successful push as a canvas
            # mutation even when ``history_service=None`` was explicitly
            # requested for that purpose.
            if name == "history_state" and history_service is None:
                runtime_states[name] = None
                continue
            state = _capture_canvas_state_object(canvas, name)
            runtime_states[name] = state
            append(state)
        groups = _capture_optional_attribute(
            runtime_states["group_state"],
            "groups",
        )
        if isinstance(groups, dict):
            for group in groups.values():
                append(group)
        append(_capture_optional_attribute(history_service, "state"))

        # Lightweight test canvases use this list as their history stack.
        # Capturing it also makes a mutate-then-raise fake push transactional.
        append(canvas, names=("pushed_commands",))

        object_snapshots = tuple(objects)

        scene_item_snapshots: list[_SceneItemExactSnapshot] = []
        scene_item_seen: set[int] = set()

        def capture_scene_item(scene_item: object) -> None:
            if scene_item is None or id(scene_item) in scene_item_seen:
                return
            scene_item_seen.add(id(scene_item))
            snapshot = _SceneItemExactSnapshot.capture(scene_item, containers)
            if snapshot is not None:
                scene_item_snapshots.append(snapshot)

        scene = _delete_scene_for_capture(canvas)
        if move_scope is None:
            for scene_item in _delete_scene_items_for_capture(scene):
                capture_scene_item(scene_item)

        scene_runtime = capture_scene_runtime(
            canvas,
            strict=True,
            detail_items=(None if move_scope is None else move_scope.scene_items),
            detail_bond_ids=(None if move_scope is None else move_scope.bond_ids),
        )
        if scene is None:
            scene = getattr(scene_runtime, "scene", None)
        if move_scope is None:
            for scene_item in scene_runtime.scene_items or ():
                capture_scene_item(scene_item)

            registered_ring_items = _capture_optional_attribute(
                runtime_states["scene_items_state"],
                "ring_items",
            )
            if isinstance(registered_ring_items, (list, tuple)):
                for scene_item in registered_ring_items:
                    capture_scene_item(scene_item)
        else:
            # The scope owner enumerated the gesture's mutation footprint;
            # exact per-item snapshots are restricted to it.
            for scene_item in move_scope.scene_items:
                capture_scene_item(scene_item)

        atom_primitive_graphics = capture_atom_primitive_graphics(
            canvas,
            strict=True,
            atom_ids=(None if move_scope is None else move_scope.atom_ids),
        )

        # The rect guard is the only mutation capture performs, so take it
        # last: every step above is a pure read and needs no unwind.
        scene_rect_snapshot: SceneRectSnapshot | None = None
        scene_items_bounding_rect_getter = None
        if scene is not None:
            items_bounding_rect = _capture_optional_attribute(
                scene,
                "itemsBoundingRect",
            )
            scene_items_bounding_rect_getter = (
                items_bounding_rect if callable(items_bounding_rect) else None
            )
            scene_rect_snapshot = SceneRectSnapshot.capture(
                scene,
                guard_growth=guard_scene_rect,
                scene_items_bounding_rect_getter=scene_items_bounding_rect_getter,
            )

        return cls(
            canvas=canvas,
            canvas_model=model,
            renderer=renderer,
            renderer_style=renderer_style,
            history_service=history_service,
            containers=containers,
            objects=object_snapshots,
            scene_runtime=scene_runtime,
            atom_primitive_graphics=atom_primitive_graphics,
            scene_items=tuple(scene_item_snapshots),
            scene=scene,
            scene_rect_snapshot=scene_rect_snapshot,
            scene_items_bounding_rect_getter=scene_items_bounding_rect_getter,
            notify_history_change=notify_history_change,
            move_scope=move_scope,
        )

    def verify(
        self,
        *,
        include_rect: bool = True,
    ) -> list[BaseException]:
        errors: list[BaseException] = []
        rect_snapshot = self.scene_rect_snapshot
        if include_rect and rect_snapshot is not None:
            try:
                if rect_snapshot.live_rect() != rect_snapshot.baseline_rect:
                    raise RuntimeError("delete rollback scene rect was re-mutated")
                if (
                    scene_rect_is_automatic(rect_snapshot.tracker.scene)
                    is not rect_snapshot.automatic
                ):
                    raise RuntimeError("delete rollback scene-rect mode was re-mutated")
                if rect_snapshot.tracker.depth != 0:
                    raise RuntimeError(
                        "delete rollback scene-rect guard remained active"
                    )
            except Exception as exc:
                errors.append(exc)
        errors.extend(self.containers.verify())
        for snapshot in self.objects:
            errors.extend(snapshot.verify())
        if self.canvas.model is not self.canvas_model:
            errors.append(
                RuntimeError("delete rollback canvas-model identity was re-mutated")
            )
        if self.renderer_style is not _MISSING_RENDERER_STYLE:
            try:
                if (
                    self.renderer is None
                    or cast(Any, self.renderer).style is not self.renderer_style
                ):
                    raise RuntimeError(
                        "document rollback renderer style was not restored"
                    )
            except Exception as exc:
                errors.append(exc)
        for scene_item in self.scene_items:
            errors.extend(scene_item.verify())
        try:
            verify_scene_runtime_identity(self.scene_runtime)
        except Exception as exc:
            errors.append(exc)
        return errors

    def _refresh_bond_geometry(
        self,
        secondary_errors: list[BaseException],
    ) -> None:
        # Ring removal can refresh surviving bond primitives in place. The
        # restored model, ring collection, and original graphics mappings are
        # now live again, so refresh those same item objects canonically.
        try:
            try:
                renderer = bond_renderer_for(self.canvas)
            except AttributeError:
                # A savepoint also supports model-only/headless canvases, where
                # there is no bond graphics collaborator to refresh.
                return
            bonds = (
                _capture_optional_attribute(self.canvas_model, "bonds", default=())
                or ()
            )
            for bond_id, bond in enumerate(cast(Any, bonds)):
                if bond is None:
                    continue
                if (
                    self.move_scope is not None
                    and bond_id not in self.move_scope.bond_ids
                ):
                    # A canonical redraw of a bond outside the gesture's
                    # footprint would be a terminal writer with no exact
                    # snapshot to stay authoritative over it — it must not
                    # rewrite graphics the gesture never touched (a prior
                    # drag legitimately leaves interior bond items translated
                    # via moveBy rather than in canonical form).
                    continue
                try:
                    renderer.update_bond_geometry(bond_id)
                except Exception as exc:
                    secondary_errors.append(exc)
        except Exception as exc:
            secondary_errors.append(exc)

    def _restore_raw_authorities(
        self,
        errors: list[BaseException],
        *,
        secondary_errors: list[BaseException] | None = None,
    ) -> None:
        _collect_restore_errors(self.containers.restore, errors)
        for snapshot in self.objects:
            _collect_restore_errors(snapshot.restore, errors)
        try:
            self.canvas.model = self.canvas_model
        except Exception as exc:
            errors.append(exc)
        try:
            errors.extend(
                restore_scene_runtime(
                    self.scene_runtime,
                    collect_errors=True,
                    defer_scene_identity_errors=True,
                )
            )
        except Exception as exc:
            errors.append(exc)
        if secondary_errors is not None:
            # Canonical redraw is a dependent repair between the model
            # restore and the final raw graphics authority: it recomputes
            # geometry that ring removal rewrote in place, and the exact
            # pre-transaction primitive snapshots below stay authoritative
            # over anything it produces.
            self._refresh_bond_geometry(secondary_errors)
        _collect_restore_errors(
            lambda: restore_primitive_graphics(
                self.atom_primitive_graphics,
            ),
            errors,
        )
        # Restore each captured scene item once after canonical redraw so its
        # exact primitive state is the final writer.
        for scene_item in self.scene_items:
            _collect_restore_errors(scene_item.restore, errors)
        if self.renderer_style is not _MISSING_RENDERER_STYLE:
            try:
                assert self.renderer is not None
                cast(Any, self.renderer).style = self.renderer_style
            except Exception as exc:
                errors.append(exc)

    def _restore_scene_rect_last(
        self,
        errors: list[BaseException],
    ) -> None:
        # Restore the rect only after every raw geometry authority has run:
        # the canonical redraw can transiently move a primitive far away, and
        # releasing the guard earlier would let Qt's cached automatic rect
        # keep that transient growth.
        rect_snapshot = self.scene_rect_snapshot
        if rect_snapshot is None:
            return
        try:
            if rect_snapshot.active:
                rect_snapshot.restore()
        except Exception as exc:
            errors.append(exc)

    def restore(self) -> RestoreOutcome:
        """Run the full absolute restore and classify its failures.

        Core model/container/scene/raw-graphics failures make the snapshot
        non-authoritative, but they do not make relative inverse commands
        safe: the full pass has already touched independent state. Canonical
        redraw and history notification failures are secondary once the raw
        savepoint has been restored.
        """

        if not self.active:
            return RestoreOutcome(
                authoritative=False,
                fallback_to_inverse=False,
                errors=(RuntimeError("Document savepoint has already been consumed"),),
            )
        self.active = False
        critical_errors: list[BaseException] = []
        secondary_errors: list[BaseException] = []

        self._restore_raw_authorities(
            critical_errors,
            secondary_errors=secondary_errors,
        )
        self._restore_scene_rect_last(critical_errors)
        critical_errors.extend(self.verify())

        notify_history_change = self.notify_history_change
        if (
            not critical_errors
            and callable(notify_history_change)
            and not self.history_notification_published
        ):
            # Consume publication before entering callback code: a callback
            # that raises is still one observable publication.
            self.history_notification_published = True
            try:
                notify_history_change()
            except Exception as exc:
                secondary_errors.append(exc)
        return RestoreOutcome(
            authoritative=not critical_errors,
            fallback_to_inverse=False,
            errors=tuple((*critical_errors, *secondary_errors)),
        )

    def release(self) -> None:
        if not self.active:
            return
        self.active = False
        if self.scene_rect_snapshot is None:
            return
        self.scene_rect_snapshot.release(
            authoritative_scene_bounds_getter=(
                self.scene_items_bounding_rect_getter
                if callable(self.scene_items_bounding_rect_getter)
                else None
            )
        )


@contextmanager
def document_transaction(
    canvas,
    *,
    history_service=None,
) -> Iterator[None]:
    snapshot = DocumentSavepoint.capture(
        canvas,
        history_service=history_service,
        guard_scene_rect=True,
    )
    try:
        yield
        snapshot.release()
    except Exception as original_error:
        rollback_errors: tuple[BaseException, ...]
        try:
            rollback_errors = snapshot.restore().errors
        except Exception as caught_rollback_error:
            rollback_errors = (caught_rollback_error,)
        for secondary_error in rollback_errors:
            _add_delete_rollback_note(original_error, secondary_error)
        raise


__all__ = [
    "DocumentSavepoint",
    "MoveGestureScope",
    "document_transaction",
]
