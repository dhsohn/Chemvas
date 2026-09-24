"""Restore a captured scene runtime snapshot exactly, or apply atomic scene mutations against one."""

from __future__ import annotations

from functools import partial
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

from chemvas.domain.transactions import add_recovery_error_note, run_rollback_step
from chemvas.ui.scene.scene_item_access import (
    create_scene_item_from_state as _create_scene_item_from_state,
)
from chemvas.ui.scene.scene_item_access import (
    remove_scene_item as _remove_scene_item,
)
from chemvas.ui.scene.scene_item_access import (
    restore_scene_item as _restore_scene_item,
)
from chemvas.ui.transactions.scene_rect import (
    SceneRectSnapshot,
    capture_scene_rect_snapshot,
    release_scene_rect_snapshot,
    restore_scene_rect_snapshot,
)
from chemvas.ui.transactions.scene_runtime import (
    _SCENE_STACKING_FLAG_MASK,
    _UNAVAILABLE_ITEM_VALUE,
    SceneRuntimeSnapshot,
    _CollectionAttributeSnapshot,
    _MarkRegistrySnapshot,
    _new_top_level_scene_items,
    _run_absolute_restore_step,
    _run_suppressed_restore_step,
    _scene_item_membership,
    _SceneItemTopologySnapshot,
    _snapshot_attribute,
    _VisibilitySnapshot,
    capture_scene_runtime,
    restore_primitive_graphics,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import (
        QGraphicsItem,
    )


def _item_parent(item, *, strict: bool = False):
    parent_method = _snapshot_attribute(item, "parentItem")
    if not callable(parent_method):
        return None
    try:
        return parent_method()
    except RuntimeError:
        if strict:
            raise
        return None


def _verify_scene_membership(
    scene,
    item,
    *,
    attached: bool,
) -> None:
    scene_method = _snapshot_attribute(item, "scene")
    if not callable(scene_method):
        return
    try:
        actual = scene_method() is scene
    except RuntimeError as error:
        raise RuntimeError("failed to verify restored scene-item membership") from error
    if actual is not attached:
        action = "attach" if attached else "detach"
        raise RuntimeError(f"scene restore failed to {action} an item")


def _direct_scene_remove(scene, item) -> None:
    remove_item = _snapshot_attribute(scene, "removeItem")
    if callable(remove_item):
        try:
            result = remove_item(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not remove an item") from error
        if result is False:
            raise RuntimeError("scene restore remove operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=False,
        )
        return
    detach = _snapshot_attribute(scene, "detach")
    if callable(detach):
        try:
            result = detach(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not detach an item") from error
        if result is False:
            raise RuntimeError("scene restore detach operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=False,
        )
        return
    raise RuntimeError("scene does not provide a direct item-removal operation")


def _direct_scene_add(scene, item) -> None:
    add_item = _snapshot_attribute(scene, "addItem")
    if callable(add_item):
        try:
            result = add_item(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not add an item") from error
        if result is False:
            raise RuntimeError("scene restore add operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=True,
        )
        return
    attach = _snapshot_attribute(scene, "attach")
    if callable(attach):
        try:
            result = attach(item)
        except RuntimeError as error:
            raise RuntimeError("scene restore could not attach an item") from error
        if result is False:
            raise RuntimeError("scene restore attach operation reported failure")
        _verify_scene_membership(
            scene,
            item,
            attached=True,
        )
        return
    raise RuntimeError("scene does not provide a direct item-add operation")


def _item_is_attached_to_scene(
    scene,
    item,
    *,
    strict: bool = False,
) -> bool:
    scene_method = _snapshot_attribute(item, "scene")
    if not callable(scene_method):
        return False
    try:
        return scene_method() is scene
    except RuntimeError:
        if strict:
            raise
        return False


def _topology_depths(
    topology_states: list[_SceneItemTopologySnapshot],
) -> dict[int, int]:
    """Resolve every captured parent depth once and reject parent cycles."""

    states_by_item_id = {id(state.item): state for state in topology_states}
    depths: dict[int, int] = {}
    for start in topology_states:
        start_id = id(start.item)
        if start_id in depths:
            continue
        path: list[_SceneItemTopologySnapshot] = []
        positions: dict[int, int] = {}
        current: _SceneItemTopologySnapshot | None = start
        base_depth = -1
        while current is not None:
            item_id = id(current.item)
            if item_id in depths:
                base_depth = depths[item_id]
                break
            if item_id in positions:
                raise RuntimeError("scene runtime snapshot contains a parent cycle")
            positions[item_id] = len(path)
            path.append(current)
            current = states_by_item_id.get(id(current.parent))
        while path:
            resolved = path.pop()
            base_depth += 1
            depths[id(resolved.item)] = base_depth
    return depths


def _restore_scene_parent_topology(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    depths = _topology_depths(topology_states)
    ordered_states = sorted(
        topology_states,
        key=lambda state: depths[id(state.item)],
    )
    for state in ordered_states:
        getter = state.parent_getter
        if getter is None:
            continue
        try:
            if getter() is state.parent:
                continue
            setter = state.parent_setter
            if setter is None:
                raise RuntimeError(
                    "scene restore cannot repair a read-only item parent"
                )
            setter(state.parent)
            if getter() is not state.parent:
                raise RuntimeError(
                    "scene restore did not restore an item's exact parent identity"
                )
        except Exception as restore_error:
            errors.append(restore_error)


def _restore_scene_z_values(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    for state in topology_states:
        getter = state.z_getter
        expected = state.z_value
        if getter is None or expected is None:
            continue
        try:
            if float(cast("Any", getter())) == expected:
                continue
            setter = state.z_setter
            if setter is None:
                raise RuntimeError(
                    "scene restore cannot repair a read-only item z value"
                )
            setter(expected)
            if float(cast("Any", getter())) != expected:
                raise RuntimeError(
                    "scene restore did not restore an item's exact z value"
                )
        except Exception as restore_error:
            errors.append(restore_error)


def _restore_scene_stacking_flags(
    topology_states: list[_SceneItemTopologySnapshot],
    *,
    errors: list[BaseException],
) -> None:
    for state in topology_states:
        getter = state.flags_getter
        setter = state.flags_setter
        expected = state.stacking_flags
        if getter is None or setter is None or expected is None:
            continue
        try:
            current = cast("QGraphicsItem.GraphicsItemFlag", getter())
            if current & _SCENE_STACKING_FLAG_MASK == expected:
                continue
            restored = (current & ~_SCENE_STACKING_FLAG_MASK) | expected
            setter(restored)
            actual = cast("QGraphicsItem.GraphicsItemFlag", getter())
            if actual & _SCENE_STACKING_FLAG_MASK != expected:
                raise RuntimeError(
                    "scene restore did not restore an item's stacking flags"
                )
        except Exception as restore_error:
            errors.append(restore_error)


def _verify_scene_item_topology(
    topology_states: list[_SceneItemTopologySnapshot],
) -> None:
    for state in topology_states:
        parent_getter = state.parent_getter
        if parent_getter is not None and parent_getter() is not state.parent:
            raise RuntimeError(
                "scene restore did not preserve an item's exact parent identity"
            )
        z_getter = state.z_getter
        if (
            z_getter is not None
            and state.z_value is not None
            and float(cast("Any", z_getter())) != state.z_value
        ):
            raise RuntimeError("scene restore did not preserve an item's exact z value")
        flags_getter = state.flags_getter
        if flags_getter is not None and state.stacking_flags is not None:
            actual_flags = cast(
                "QGraphicsItem.GraphicsItemFlag",
                flags_getter(),
            )
            if actual_flags & _SCENE_STACKING_FLAG_MASK != state.stacking_flags:
                raise RuntimeError(
                    "scene restore did not preserve an item's stacking flags"
                )


def _restore_scene_stacking(
    snapshot: SceneRuntimeSnapshot,
    *,
    errors: list[BaseException],
) -> None:
    expected_items = snapshot.scene_items
    items_getter = snapshot.scene_items_getter
    if expected_items is not None and items_getter is not None:
        try:
            current_items = list(items_getter())
            if len(current_items) == len(expected_items) and all(
                current is expected
                for current, expected in zip(
                    current_items,
                    expected_items,
                    strict=True,
                )
            ):
                return
        except Exception as error:
            errors.append(error)
            return
    sibling_groups: dict[
        tuple[int, float],
        list[_SceneItemTopologySnapshot],
    ] = {}
    for state in snapshot.topology_states:
        z_value = state.z_value
        if z_value is None:
            continue
        sibling_groups.setdefault((id(state.parent), z_value), []).append(state)
    for siblings in sibling_groups.values():
        for higher, lower in pairwise(siblings):
            stack_before = lower.stack_before
            if not callable(stack_before):
                continue
            _run_suppressed_restore_step(
                None,
                "restoring scene-item stacking",
                partial(stack_before, higher.item),
                errors=errors,
            )


def _restore_scene_contents(
    snapshot: SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None = None,
    errors: list[BaseException] | None = None,
) -> None:
    scene = snapshot.scene
    before = snapshot.scene_items
    if scene is None or before is None:
        return
    current_items_method = snapshot.scene_items_getter
    if not callable(current_items_method):
        if errors is not None:
            errors.append(RuntimeError("scene restore cannot read current items"))
        return
    if errors is not None:
        current = _run_absolute_restore_step(
            original_error,
            "reading current scene contents",
            lambda: list(current_items_method()),
            default=None,
            errors=errors,
        )
        if current is None:
            return
    elif original_error is None:
        try:
            current = list(current_items_method())
        except RuntimeError:
            return
    else:
        current = run_rollback_step(
            original_error,
            "reading current scene contents",
            lambda: list(current_items_method()),
            default=None,
        )
        if current is None:
            return

    try:
        _restore_scene_signal_state(
            snapshot,
            True,
            phase="blocking scene signals for restore",
            original_error=original_error,
            errors=errors,
        )
        before_ids = {id(item) for item in before}
        topology_by_item_id = {
            id(state.item): state for state in snapshot.topology_states
        }
        added = [item for item in current if id(item) not in before_ids]
        added_ids = {id(item) for item in added}
        for item in added:
            parent = _run_absolute_restore_step(
                original_error,
                "reading a newly added item's parent",
                partial(_item_parent, item, strict=errors is not None),
                errors=errors,
            )
            if parent is not None and id(parent) in added_ids:
                continue
            _run_absolute_restore_step(
                original_error,
                "removing an item absent from the scene snapshot",
                partial(
                    _direct_scene_remove,
                    scene,
                    item,
                ),
                default=False,
                errors=errors,
            )

        # Add roots before their children. Reverse the scene's top-to-bottom order
        # because newly added equal-z siblings stack above existing siblings.
        for item in reversed(before):
            attached = _run_absolute_restore_step(
                original_error,
                "reading scene-item membership",
                partial(
                    _item_is_attached_to_scene,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )
            if attached:
                continue
            topology_state = topology_by_item_id.get(id(item))
            parent = (
                topology_state.parent
                if topology_state is not None
                else _run_absolute_restore_step(
                    original_error,
                    "reading a snapshot item's parent",
                    partial(_item_parent, item, strict=errors is not None),
                    errors=errors,
                )
            )
            if parent is not None and id(parent) in before_ids:
                continue
            _run_absolute_restore_step(
                original_error,
                "reattaching a snapshot scene-item root",
                partial(
                    _direct_scene_add,
                    scene,
                    item,
                ),
                default=False,
                errors=errors,
            )
        for item in reversed(before):
            attached = _run_absolute_restore_step(
                original_error,
                "reading scene-item membership",
                partial(
                    _item_is_attached_to_scene,
                    scene,
                    item,
                    strict=errors is not None,
                ),
                default=False,
                errors=errors,
            )
            if not attached:
                _run_absolute_restore_step(
                    original_error,
                    "reattaching a snapshot scene item",
                    partial(
                        _direct_scene_add,
                        scene,
                        item,
                    ),
                    default=False,
                    errors=errors,
                )

        _restore_scene_focus(
            snapshot,
            original_error=original_error,
            errors=errors,
        )
        _restore_scene_order_and_selection(
            snapshot,
            current_items_method,
            original_error=original_error,
            errors=errors,
        )
    finally:
        if snapshot.scene_signals_blocked is not None:
            _restore_scene_signal_state(
                snapshot,
                snapshot.scene_signals_blocked,
                phase="restoring the scene signal-blocking state",
                original_error=original_error,
                errors=errors,
            )


def _restore_scene_signal_state(
    snapshot: SceneRuntimeSnapshot,
    blocked: bool,
    *,
    phase: str,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
) -> None:
    getter = snapshot.scene_signals_blocked_getter
    setter = snapshot.scene_block_signals_setter
    if getter is None or setter is None:
        return

    def restore_once() -> None:
        setter(blocked)
        if bool(getter()) is not blocked:
            raise RuntimeError(
                "scene signal-blocking setter did not restore the requested state"
            )

    try:
        restore_once()
    except Exception as restore_error:
        if errors is not None:
            errors.append(restore_error)
        elif original_error is not None:
            add_recovery_error_note(
                original_error,
                restore_error,
                phase=phase,
            )
        else:
            raise
    else:
        return


def _restore_expected_scene_membership(
    snapshot: SceneRuntimeSnapshot,
    *,
    errors: list[BaseException],
) -> None:
    scene = snapshot.scene
    expected_items = snapshot.scene_items
    if scene is None or expected_items is None:
        return
    expected_ids = {id(item) for item in expected_items}
    topology_by_item_id = {id(state.item): state for state in snapshot.topology_states}

    def attach_if_missing(item: object) -> None:
        try:
            if _item_is_attached_to_scene(scene, item, strict=True):
                return
            _direct_scene_add(scene, item)
        except Exception as restore_error:
            errors.append(restore_error)

    for item in reversed(expected_items):
        state = topology_by_item_id.get(id(item))
        if state is not None and state.parent is not None:
            if id(state.parent) in expected_ids:
                continue
        attach_if_missing(item)
    for item in reversed(expected_items):
        attach_if_missing(item)


def _restore_scene_order_and_selection(
    snapshot: SceneRuntimeSnapshot,
    current_items_method: Callable[[], Any],
    *,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
) -> None:
    expected_items = snapshot.scene_items
    if expected_items is None:
        return

    failures: list[BaseException] = []
    # Stacking flags can synchronously change selection. Restore them before
    # selection so the latter remains the final writer for that dependency.
    _restore_scene_stacking_flags(
        snapshot.topology_states,
        errors=failures,
    )
    # A selected item's setter may synchronously select a peer. Apply the
    # captured-false states last so those callbacks cannot repollute the
    # final selection set. ``sorted`` is stable, preserving scene order
    # within each state group.
    ordered_selection_states = sorted(
        snapshot.selected_states,
        key=lambda selection: not selection.selected,
    )
    for selection in ordered_selection_states:
        try:
            if not _item_is_attached_to_scene(
                snapshot.scene,
                selection.item,
                strict=True,
            ):
                raise RuntimeError(
                    "scene selection target is not attached after restore"
                )
            selection.setter(selection.selected)
            if bool(selection.getter()) != selection.selected:
                raise RuntimeError(
                    "scene restore did not restore an item's selection state"
                )
        except Exception as restore_error:
            failures.append(restore_error)
    # Keep topology as the final writer after selection.
    _restore_scene_parent_topology(
        snapshot.topology_states,
        errors=failures,
    )
    _restore_expected_scene_membership(
        snapshot,
        errors=failures,
    )
    _restore_scene_z_values(
        snapshot.topology_states,
        errors=failures,
    )
    _restore_scene_stacking(
        snapshot,
        errors=failures,
    )
    try:
        _verify_scene_item_topology(snapshot.topology_states)
        for selection in snapshot.selected_states:
            if bool(selection.getter()) != selection.selected:
                raise RuntimeError(
                    "scene topology restore changed an item's selection state"
                )
        current_items = list(current_items_method())
        if len(current_items) != len(expected_items) or any(
            current is not expected
            for current, expected in zip(
                current_items,
                expected_items,
                strict=True,
            )
        ):
            raise RuntimeError(
                "scene restore did not restore the exact ordered item identity"
            )
    except Exception as restore_error:
        failures.append(restore_error)

    if not failures:
        return

    if errors is not None:
        errors.extend(failures)
        return
    if original_error is not None:
        for failure in failures:
            add_recovery_error_note(
                original_error,
                failure,
                phase="restoring scene order and selection",
            )
        return
    raise failures[0]


def _restore_scene_focus(
    snapshot: SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None,
    errors: list[BaseException] | None,
) -> None:
    getter = snapshot.focus_item_getter
    setter = snapshot.focus_item_setter
    if getter is None or setter is None:
        return

    def restore_once() -> None:
        focus_item = snapshot.focus_item
        if focus_item is not None and not _item_is_attached_to_scene(
            snapshot.scene,
            focus_item,
            strict=True,
        ):
            raise RuntimeError("scene focus target is not attached after restore")
        setter(focus_item)
        if getter() is not focus_item:
            raise RuntimeError("scene restore did not restore the focus item")

    try:
        restore_once()
    except Exception as restore_error:
        if errors is not None:
            errors.append(restore_error)
        elif original_error is not None:
            add_recovery_error_note(
                original_error,
                restore_error,
                phase="restoring the scene focus item",
            )
        else:
            raise
    else:
        return


def verify_scene_runtime_identity(snapshot: SceneRuntimeSnapshot) -> None:
    signals_getter = snapshot.scene_signals_blocked_getter
    if signals_getter is not None and snapshot.scene_signals_blocked is not None:
        if bool(signals_getter()) != snapshot.scene_signals_blocked:
            raise RuntimeError(
                "final scene restore did not preserve the signal-blocking state"
            )

    focus_getter = snapshot.focus_item_getter
    if focus_getter is not None and focus_getter() is not snapshot.focus_item:
        raise RuntimeError("final scene restore did not preserve focus identity")

    for selection in snapshot.selected_states:
        if bool(selection.getter()) != selection.selected:
            raise RuntimeError(
                "final scene restore did not preserve an item's selection state"
            )

    _verify_scene_item_topology(snapshot.topology_states)

    expected_items = snapshot.scene_items
    items_getter = snapshot.scene_items_getter
    if expected_items is None:
        return
    if items_getter is None:
        raise RuntimeError("final scene restore cannot read scene items")
    current_items = list(items_getter())
    if len(current_items) != len(expected_items) or any(
        current is not expected
        for current, expected in zip(
            current_items,
            expected_items,
            strict=True,
        )
    ):
        raise RuntimeError(
            "final scene restore did not preserve exact ordered item identity"
        )


def _restore_collection_attribute(snapshot: _CollectionAttributeSnapshot) -> None:
    if isinstance(snapshot.collection_object, dict):
        snapshot.collection_object.clear()
        snapshot.collection_object.update(cast("dict", snapshot.contents))
    else:
        snapshot.collection_object[:] = snapshot.contents
    setattr(snapshot.owner, snapshot.attribute, snapshot.collection_object)


def _restore_mark_registry(snapshot: _MarkRegistrySnapshot) -> None:
    snapshot.mapping_object.clear()
    for key, value, contents in snapshot.entries:
        if isinstance(value, list) and contents is not None:
            value[:] = contents
        snapshot.mapping_object[key] = value
    snapshot.registry.by_atom = snapshot.mapping_object


def _restore_visibility(snapshot: _VisibilitySnapshot) -> None:
    for method_name, value in (
        ("setRect", snapshot.rect),
        ("setPen", snapshot.pen),
        ("setBrush", snapshot.brush),
    ):
        if value is _UNAVAILABLE_ITEM_VALUE:
            continue
        method = _snapshot_attribute(snapshot.item, method_name)
        if callable(method):
            method(value)
    set_visible = _snapshot_attribute(snapshot.item, "setVisible")
    if callable(set_visible):
        set_visible(snapshot.visible)


def restore_scene_runtime(
    snapshot: SceneRuntimeSnapshot,
    *,
    original_error: BaseException | None = None,
    collect_errors: bool = False,
    defer_scene_identity_errors: bool = False,
) -> list[BaseException]:
    errors: list[BaseException] | None = [] if collect_errors else None
    scene_errors = [] if collect_errors and defer_scene_identity_errors else errors
    try:
        _run_absolute_restore_step(
            original_error,
            "restoring absolute scene contents",
            lambda: _restore_scene_contents(
                snapshot,
                original_error=original_error,
                errors=scene_errors,
            ),
            errors=scene_errors,
        )
        for collection_snapshot in snapshot.collection_attributes:
            _run_suppressed_restore_step(
                original_error,
                f"restoring runtime collection {collection_snapshot.attribute}",
                partial(_restore_collection_attribute, collection_snapshot),
                errors=errors,
            )
        mark_registry = snapshot.mark_registry
        if mark_registry is not None:
            _run_suppressed_restore_step(
                original_error,
                "restoring the mark registry",
                partial(_restore_mark_registry, mark_registry),
                errors=errors,
            )
        for visibility_snapshot in snapshot.visibility_states:
            _run_suppressed_restore_step(
                original_error,
                "restoring selection-overlay visibility",
                partial(_restore_visibility, visibility_snapshot),
                errors=errors,
            )
        if snapshot.handle_state is not None:
            _run_suppressed_restore_step(
                original_error,
                "restoring the active handle target",
                lambda: setattr(
                    snapshot.handle_state, "target", snapshot.handle_target
                ),
                errors=errors,
            )
        if snapshot.selection_info_state is not None:
            for attribute, value in snapshot.selection_info_values.items():
                _run_suppressed_restore_step(
                    original_error,
                    f"restoring selection-info field {attribute}",
                    partial(
                        setattr,
                        snapshot.selection_info_state,
                        attribute,
                        value,
                    ),
                    errors=errors,
                )
    finally:
        # Ring attach/remove callbacks refresh surviving bond primitives in
        # place and can fail after a partial mutation. The exact raw graphics
        # savepoint must be the final restore phase, including when lifecycle
        # compensation itself invokes the same persistently failing callback.
        primitive_errors = _run_absolute_restore_step(
            original_error,
            "restoring raw bond primitives",
            lambda: restore_primitive_graphics(snapshot.bond_primitive_graphics),
            default=[],
            errors=errors,
        )
        if errors is not None:
            errors.extend(primitive_errors)
        elif original_error is not None:
            for primitive_error in primitive_errors:
                add_recovery_error_note(
                    original_error,
                    primitive_error,
                    phase="restoring a raw bond primitive",
                )
    return errors or []


def _restore_scene_item_memberships(
    canvas,
    attempted: list[tuple[object, bool | None]],
    *,
    unknown_was_attached: bool,
    original_error: BaseException,
) -> None:
    desired_memberships = [
        (
            item,
            unknown_was_attached if was_attached is None else was_attached,
        )
        for item, was_attached in attempted
    ]
    # Remove newly attached items in reverse mutation order, then reattach
    # removed items in their original order so equal-z scene stacking is not
    # reversed by the compensation itself.
    for item, should_be_attached in reversed(desired_memberships):
        if should_be_attached:
            continue
        run_rollback_step(
            original_error,
            "removing a newly attached scene item",
            partial(_remove_scene_item, canvas, item),
        )
    for item, should_be_attached in desired_memberships:
        if not should_be_attached:
            continue
        run_rollback_step(
            original_error,
            "reattaching a removed scene item",
            partial(_restore_scene_item, canvas, item),
        )


def restore_absolute_snapshots(
    runtime_snapshot: SceneRuntimeSnapshot,
    scene_rect_snapshot: SceneRectSnapshot | None,
    original_error: BaseException,
) -> None:
    """The shared rollback tail: absolute scene/runtime snapshot, then rect."""

    run_rollback_step(
        original_error,
        "restoring the absolute scene/runtime snapshot",
        partial(
            restore_scene_runtime,
            runtime_snapshot,
            original_error=original_error,
        ),
    )
    restore_scene_rect_snapshot(scene_rect_snapshot, original_error)


def mutate_existing_scene_items_atomically(
    canvas,
    items: list,
    operation: Callable[[Any, Any], None],
    *,
    unknown_was_attached: bool,
    after_mutation: Callable[[], None] | None = None,
) -> None:
    runtime_snapshot = capture_scene_runtime(canvas)
    snapshots = [
        (item, _scene_item_membership(canvas, item))
        for item in items
        if item is not None
    ]
    attempted: list[tuple[object, bool | None]] = []
    scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        for snapshot in snapshots:
            attempted.append(snapshot)
            operation(canvas, snapshot[0])
        if after_mutation is not None:
            after_mutation()
        release_scene_rect_snapshot(scene_rect_snapshot)
    except Exception as original_error:
        _restore_scene_item_memberships(
            canvas,
            attempted,
            unknown_was_attached=unknown_was_attached,
            original_error=original_error,
        )
        restore_absolute_snapshots(
            runtime_snapshot, scene_rect_snapshot, original_error
        )
        raise


def create_scene_items_atomically(canvas, states: list[dict], items: list) -> None:
    original_items = list(items)
    runtime_snapshot = capture_scene_runtime(canvas)
    scene_before = (
        list(runtime_snapshot.scene_items)
        if runtime_snapshot.scene_items is not None
        else None
    )
    created: list = []
    scene_rect_snapshot = capture_scene_rect_snapshot(runtime_snapshot.scene)
    try:
        for state in states:
            item = _create_scene_item_from_state(canvas, state)
            items.append(item)
            if item is not None:
                created.append(item)
        release_scene_rect_snapshot(scene_rect_snapshot)
    except Exception as original_error:
        created.extend(
            run_rollback_step(
                original_error,
                "discovering partially created scene items",
                lambda: _new_top_level_scene_items(canvas, scene_before),
                default=[],
            )
        )
        seen: set[int] = set()
        for item in reversed(created):
            if id(item) in seen:
                continue
            seen.add(id(item))
            run_rollback_step(
                original_error,
                "removing a partially created scene item",
                partial(_remove_scene_item, canvas, item),
            )
        items[:] = original_items
        restore_absolute_snapshots(
            runtime_snapshot, scene_rect_snapshot, original_error
        )
        raise


__all__ = [
    "create_scene_items_atomically",
    "mutate_existing_scene_items_atomically",
    "restore_absolute_snapshots",
    "restore_scene_runtime",
    "verify_scene_runtime_identity",
]
