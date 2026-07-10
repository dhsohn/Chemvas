from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from ui.canvas_state_lookup import canvas_state_object
from ui.history_commands import (
    _atom_primitive_graphics_snapshots,
    _restore_bond_primitive_graphics_snapshots,
    _restore_scene_runtime_snapshot,
    _scene_runtime_snapshot,
    _SceneRuntimeSnapshot,
)

_DELETE_MUTATED_RUNTIME_FIELDS = (
    "graph_state",
    "atom_coords_3d_state",
    "atom_graphics_state",
    "bond_graphics_state",
    "mark_registry",
    "spatial_index_state",
    "handle_state",
    "selection_style_state",
    "selection_outline_state",
    "selection_info_state",
    "scene_items_state",
    "group_state",
    "smiles_input_state",
    "history_state",
)


@dataclass(slots=True)
class _ContainerState:
    target: object
    kind: str
    contents: tuple


class _ContainerGraphSnapshot:
    """Preserve mutable container identities, including nested graph sets."""

    def __init__(self) -> None:
        self._states: dict[int, _ContainerState] = {}
        self._visited_immutable: set[int] = set()

    def capture(self, value: object) -> None:
        if isinstance(value, dict):
            if id(value) in self._states:
                return
            contents = tuple(value.items())
            self._states[id(value)] = _ContainerState(value, "dict", contents)
            for key, item in contents:
                self.capture(key)
                self.capture(item)
            return
        if isinstance(value, list):
            if id(value) in self._states:
                return
            contents = tuple(value)
            self._states[id(value)] = _ContainerState(value, "list", contents)
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, set):
            if id(value) in self._states:
                return
            contents = tuple(value)
            self._states[id(value)] = _ContainerState(value, "set", contents)
            for item in contents:
                self.capture(item)
            return
        if isinstance(value, tuple):
            if id(value) in self._visited_immutable:
                return
            self._visited_immutable.add(id(value))
            for item in value:
                self.capture(item)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for state in self._states.values():
            try:
                if state.kind == "dict":
                    target = state.target
                    assert isinstance(target, dict)
                    target.clear()
                    target.update(state.contents)
                elif state.kind == "list":
                    target = state.target
                    assert isinstance(target, list)
                    target[:] = state.contents
                else:
                    target = state.target
                    assert isinstance(target, set)
                    target.clear()
                    target.update(state.contents)
            except BaseException as exc:  # keep restoring independent state
                errors.append(exc)
        return errors


@dataclass(slots=True)
class _ObjectStateSnapshot:
    target: object
    attributes: dict[str, object]

    @classmethod
    def capture(
        cls,
        target: object,
        containers: _ContainerGraphSnapshot,
        *,
        names: tuple[str, ...] | None = None,
    ) -> _ObjectStateSnapshot | None:
        if names is None:
            if is_dataclass(target) and not isinstance(target, type):
                names = tuple(field.name for field in fields(target))
            else:
                namespace = getattr(target, "__dict__", None)
                if not isinstance(namespace, dict):
                    return None
                names = tuple(namespace)
        attributes = {
            name: getattr(target, name)
            for name in names
            if hasattr(target, name)
        }
        if not attributes:
            return None
        for value in attributes.values():
            containers.capture(value)
        return cls(target=target, attributes=attributes)

    def restore(self) -> list[BaseException]:
        errors: list[BaseException] = []
        for name, value in self.attributes.items():
            try:
                setattr(self.target, name, value)
            except BaseException as exc:
                errors.append(exc)
        return errors


@dataclass(slots=True)
class CanvasDeleteTransactionSnapshot:
    canvas: Any
    canvas_model: object
    history_service: object | None
    containers: _ContainerGraphSnapshot
    objects: tuple[_ObjectStateSnapshot, ...]
    scene_runtime: _SceneRuntimeSnapshot
    atom_primitive_graphics: tuple[Any, ...]
    scene: Any | None
    focus_item: object | None
    scene_rect: object | None

    @classmethod
    def capture(
        cls,
        canvas,
        *,
        history_service=None,
    ) -> CanvasDeleteTransactionSnapshot:
        containers = _ContainerGraphSnapshot()
        objects: list[_ObjectStateSnapshot] = []
        seen: set[int] = set()

        def append(target: object | None, *, names: tuple[str, ...] | None = None) -> None:
            if target is None or id(target) in seen:
                return
            snapshot = _ObjectStateSnapshot.capture(
                target,
                containers,
                names=names,
            )
            if snapshot is None:
                return
            seen.add(id(target))
            objects.append(snapshot)

        model = getattr(canvas, "model", None)
        append(
            model,
            names=("atoms", "bonds", "next_atom_id", "atom_annotations"),
        )
        for name in _DELETE_MUTATED_RUNTIME_FIELDS:
            append(canvas_state_object(canvas, name))
        group_state = canvas_state_object(canvas, "group_state")
        groups = getattr(group_state, "groups", None)
        if isinstance(groups, dict):
            for group in groups.values():
                append(group)
        append(getattr(history_service, "state", None))

        # Lightweight test canvases use this list as their history stack.
        # Capturing it also makes a mutate-then-raise fake push transactional.
        append(canvas, names=("pushed_commands",))

        scene_runtime = _scene_runtime_snapshot(canvas)
        scene = getattr(scene_runtime, "scene", None)
        focus_item = None
        scene_rect = None
        if scene is not None:
            focus_item_getter = getattr(scene, "focusItem", None)
            if callable(focus_item_getter):
                focus_item = focus_item_getter()
            scene_rect_getter = getattr(scene, "sceneRect", None)
            if callable(scene_rect_getter):
                scene_rect = scene_rect_getter()

        return cls(
            canvas=canvas,
            canvas_model=model,
            history_service=history_service,
            containers=containers,
            objects=tuple(objects),
            scene_runtime=scene_runtime,
            atom_primitive_graphics=_atom_primitive_graphics_snapshots(canvas),
            scene=scene,
            focus_item=focus_item,
            scene_rect=scene_rect,
        )

    def restore(self) -> list[BaseException]:
        errors = self.containers.restore()
        for snapshot in self.objects:
            errors.extend(snapshot.restore())

        try:
            self.canvas.model = self.canvas_model
        except BaseException as exc:
            errors.append(exc)

        try:
            _restore_scene_runtime_snapshot(self.scene_runtime)
        except BaseException as exc:
            errors.append(exc)

        if self.scene is not None:
            if self.scene_rect is not None:
                try:
                    self.scene.setSceneRect(self.scene_rect)
                except BaseException as exc:
                    errors.append(exc)
            set_focus_item = getattr(self.scene, "setFocusItem", None)
            if callable(set_focus_item):
                try:
                    set_focus_item(self.focus_item)
                except BaseException as exc:
                    errors.append(exc)

        # Ring removal can refresh surviving bond primitives in place. The
        # restored model, ring collection, and original graphics mappings are
        # now live again, so refresh those same item objects canonically.
        try:
            renderer = getattr(self.canvas, "bond_renderer", None)
            update_bond_geometry = getattr(renderer, "update_bond_geometry", None)
            bonds = getattr(self.canvas_model, "bonds", ())
            if callable(update_bond_geometry):
                for bond_id, bond in enumerate(bonds):
                    if bond is None:
                        continue
                    try:
                        update_bond_geometry(bond_id)
                    except BaseException as exc:
                        errors.append(exc)
        finally:
            # A renderer callback may mutate a primitive before raising, and
            # the same callback may fail persistently during rollback. Keep the
            # canonical refresh as a best-effort repair for dependent geometry,
            # but make the exact pre-transaction raw graphics savepoint the
            # final authority so rollback itself cannot leave a partial line,
            # path, polygon, transform, or style mutation behind.
            errors.extend(
                _restore_bond_primitive_graphics_snapshots(
                    self.scene_runtime.bond_primitive_graphics
                )
            )
            errors.extend(
                _restore_bond_primitive_graphics_snapshots(
                    self.atom_primitive_graphics
                )
            )
        notify_history_change = getattr(self.history_service, "notify_change", None)
        if callable(notify_history_change):
            try:
                notify_history_change()
            except BaseException as exc:
                errors.append(exc)
        return errors


@contextmanager
def canvas_delete_transaction(
    canvas,
    *,
    history_service=None,
) -> Iterator[None]:
    snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history_service,
    )
    try:
        yield
    except BaseException as original_error:
        try:
            rollback_errors = snapshot.restore()
        except BaseException as caught_rollback_error:
            rollback_errors = [caught_rollback_error]
        for secondary_error in rollback_errors:
            add_note = getattr(original_error, "add_note", None)
            if callable(add_note):
                add_note(
                    "Delete rollback also encountered "
                    f"{type(secondary_error).__name__}: {secondary_error}"
                )
        raise


__all__ = [
    "CanvasDeleteTransactionSnapshot",
    "canvas_delete_transaction",
]
