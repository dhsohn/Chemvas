"""Attach-time ports and the registration savepoint for scene items.

Attaching an item touches several owners in sequence: the kind's collection
list, the mark registry, item flags, the scene itself, and the automatic
scene-rect guard. A mid-sequence failure must not leave a half-registered
item, so the snapshot records the pre-attach registration state and the
rollback removes the item and re-pins every owner. The scene-rect guard
always opens last (after every other fallible read) and is handed the
item's bounding rect on release so sequential attaches stay linear.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsTextItem

from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_scene_items_state import scene_items_state_for
from chemvas.ui.scene_item_access import item_is_unavailable_for_scene_operation
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot

ARROW_KINDS = frozenset(
    {
        "arrow",
        "equilibrium",
        "resonance",
        "curved_single",
        "curved_double",
        "inhibit",
        "dotted",
    }
)

_KIND_COLLECTION = {
    "ring": "ring_items",
    "mark": "mark_items",
    "note": "note_items",
    "ts_bracket": "ts_bracket_items",
    "shape": "shape_items",
    "orbital": "orbital_items",
    **{kind: "arrow_items" for kind in ARROW_KINDS},
}


def _add_attach_rollback_note(
    original_error: BaseException | None,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    if original_error is None:
        raise rollback_error
    try:
        original_error.add_note(
            f"Scene-item attach recovery also failed while {phase}: "
            f"{type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        return


def _optional_callable(target, name: str):
    candidate = getattr(target, name, None)
    return candidate if callable(candidate) else None


@dataclass(frozen=True, slots=True)
class SceneItemAttachPorts:
    """Bound scene/item ports captured once per attach operation."""

    scene: Any
    item: Any
    item_scene_available: bool
    initial_item_scene: Any
    item_kind: object
    item_flags: object
    text_interaction_flags: object
    item_scene_getter: Callable[[], object] | None
    item_data_getter: Callable[[int], object] | None
    item_flags_getter: Callable[[], object] | None
    item_flags_setter: Callable[[object], object] | None
    text_flags_getter: Callable[[], object] | None
    text_flags_setter: Callable[[object], object] | None
    scene_add_item: Callable[[object], object] | None
    scene_remove_item: Callable[[object], object] | None
    scene_rect_getter: Callable[[], object] | None
    scene_rect_setter: Callable[[QRectF], object] | None
    scene_items_bounding_rect_getter: Callable[[], object] | None
    scene_bounding_rect_getter: Callable[[], object] | None
    focus_item_getter: Callable[[], object] | None
    focus_item_setter: Callable[[object], object] | None
    requires_authoritative_scene_bounds: bool

    @classmethod
    def _unavailable(cls, scene, item) -> SceneItemAttachPorts:
        return cls(
            scene=scene,
            item=item,
            item_scene_available=False,
            initial_item_scene=None,
            item_kind=None,
            item_flags=None,
            text_interaction_flags=None,
            item_scene_getter=None,
            item_data_getter=None,
            item_flags_getter=None,
            item_flags_setter=None,
            text_flags_getter=None,
            text_flags_setter=None,
            scene_add_item=None,
            scene_remove_item=None,
            scene_rect_getter=None,
            scene_rect_setter=None,
            scene_items_bounding_rect_getter=None,
            scene_bounding_rect_getter=None,
            focus_item_getter=None,
            focus_item_setter=None,
            requires_authoritative_scene_bounds=False,
        )

    @classmethod
    def capture(cls, scene, item) -> SceneItemAttachPorts:
        if item_is_unavailable_for_scene_operation(item):
            return cls._unavailable(scene, item)
        item_scene_getter = _optional_callable(item, "scene")
        try:
            initial_item_scene = (
                item_scene_getter() if item_scene_getter is not None else None
            )
        except RuntimeError:
            if item_is_unavailable_for_scene_operation(item):
                return cls._unavailable(scene, item)
            raise
        if initial_item_scene is not None and initial_item_scene is not scene:
            raise RuntimeError("scene item is already attached to a different scene")

        item_data_getter = _optional_callable(item, "data")
        item_kind = item_data_getter(0) if item_data_getter is not None else None
        item_flags_getter = _optional_callable(item, "flags")
        item_flags_setter = _optional_callable(item, "setFlags")
        item_flags = item_flags_getter() if item_flags_getter is not None else None
        text_flags_getter = (
            _optional_callable(item, "textInteractionFlags")
            if isinstance(item, QGraphicsTextItem)
            or hasattr(item, "setTextInteractionFlags")
            else None
        )
        text_flags_setter = _optional_callable(item, "setTextInteractionFlags")
        text_interaction_flags = (
            text_flags_getter() if text_flags_getter is not None else None
        )
        scene_add_item = _optional_callable(scene, "addItem")
        scene_remove_item = _optional_callable(scene, "removeItem")
        scene_rect_getter = _optional_callable(scene, "sceneRect")
        scene_rect_setter = _optional_callable(scene, "setSceneRect")
        scene_items_bounding_rect_getter = _optional_callable(
            scene,
            "itemsBoundingRect",
        )
        scene_bounding_rect_getter = _optional_callable(item, "sceneBoundingRect")
        focus_item_getter = _optional_callable(scene, "focusItem")
        focus_item_setter = _optional_callable(scene, "setFocusItem")

        mutation_ports = (
            scene_add_item,
            scene_remove_item,
            scene_rect_getter,
            scene_rect_setter,
            focus_item_setter,
        )
        requires_authoritative_scene_bounds = any(
            callable(port) and not inspect.isbuiltin(port) for port in mutation_ports
        )
        return cls(
            scene=scene,
            item=item,
            item_scene_available=True,
            initial_item_scene=initial_item_scene,
            item_kind=item_kind,
            item_flags=item_flags,
            text_interaction_flags=text_interaction_flags,
            item_scene_getter=item_scene_getter,
            item_data_getter=item_data_getter,
            item_flags_getter=item_flags_getter,
            item_flags_setter=item_flags_setter,
            text_flags_getter=text_flags_getter,
            text_flags_setter=text_flags_setter,
            scene_add_item=scene_add_item,
            scene_remove_item=scene_remove_item,
            scene_rect_getter=scene_rect_getter,
            scene_rect_setter=scene_rect_setter,
            scene_items_bounding_rect_getter=scene_items_bounding_rect_getter,
            scene_bounding_rect_getter=scene_bounding_rect_getter,
            focus_item_getter=focus_item_getter,
            focus_item_setter=focus_item_setter,
            requires_authoritative_scene_bounds=requires_authoritative_scene_bounds,
        )

    def item_can_be_added(self) -> bool:
        return (
            self.scene is not None
            and self.item_scene_available
            and (
                self.item_scene_getter is None
                or self.initial_item_scene is not self.scene
            )
        )

    def item_kind_for_attach(self) -> object:
        if self.item_data_getter is None:
            raise RuntimeError("scene item attach requires a data getter")
        return self.item_kind

    def validate_attachment_contract(
        self,
        *,
        require_text_interaction: bool = False,
    ) -> None:
        if self.scene is None:
            raise RuntimeError("scene item attach requires a scene")
        if self.scene_add_item is None or self.scene_remove_item is None:
            raise RuntimeError("scene item attach requires add/remove ports")
        if self.item_scene_getter is None:
            raise RuntimeError("scene item attach requires an item scene getter")
        if self.item_flags_getter is None or self.item_flags_setter is None:
            raise RuntimeError("scene item attach requires item flag ports")
        if require_text_interaction and (
            self.text_flags_getter is None or self.text_flags_setter is None
        ):
            raise RuntimeError("scene item attach requires text-interaction flag ports")

    def apply_selectable(self) -> None:
        if self.item_flags_setter is None or self.item_flags is None:
            raise RuntimeError("scene item attach requires item flag ports")
        try:
            self.item_flags_setter(
                cast(Any, self.item_flags)
                | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            )
        except TypeError as error:
            raise RuntimeError(
                "scene item attach captured invalid item flags"
            ) from error

    def apply_text_interaction_flags(self, expected) -> None:
        if self.text_flags_setter is None:
            raise RuntimeError("scene item attach requires text-interaction flag ports")
        self.text_flags_setter(expected)

    def add_item(self, item) -> None:
        self.validate_attachment_contract()
        add_port = self.scene_add_item
        assert add_port is not None
        result = add_port(item)
        if result is False:
            raise RuntimeError("scene item-add port reported failure")
        scene_getter = (
            self.item_scene_getter
            if item is self.item
            else _optional_callable(item, "scene")
        )
        if scene_getter is not None and scene_getter() is not self.scene:
            raise RuntimeError("scene item-add port did not attach the item")

    def remove_item(self, item) -> bool:
        if self.scene is None or self.scene_remove_item is None:
            return False
        scene_getter = (
            self.item_scene_getter
            if item is self.item
            else _optional_callable(item, "scene")
        )
        if scene_getter is not None and scene_getter() is not self.scene:
            return False
        result = self.scene_remove_item(item)
        if result is False:
            raise RuntimeError("scene item-remove port reported failure")
        return True


_UNSET = object()


@dataclass(slots=True)
class SceneItemAttachSnapshot:
    """Pre-attach registration savepoint for one scene item."""

    canvas: Any
    item: Any
    scene: Any
    attach_ports: SceneItemAttachPorts | None
    kind: object
    collection_owner: Any
    collection_name: str | None
    collection: list | None
    mark_registry: Any
    mark_mapping: dict | None
    mark_atom_id: int | None
    mark_entry_existed: bool
    mark_list: list | None
    item_flags: object
    text_interaction_flags: object
    focus_item: object
    scene_rect_snapshot: SceneRectSnapshot | None
    recovery_errors: list[BaseException] = field(default_factory=list)

    @classmethod
    def capture(
        cls,
        canvas,
        item,
        *,
        scene=_UNSET,
        attach_ports: SceneItemAttachPorts | None = None,
    ) -> SceneItemAttachSnapshot:
        if scene is _UNSET:
            scene_getter = _optional_callable(canvas, "scene")
            scene = scene_getter() if scene_getter is not None else None
        if attach_ports is None:
            attach_ports = SceneItemAttachPorts.capture(scene, item)
        kind = attach_ports.item_kind_for_attach()

        collection_owner = scene_items_state_for(canvas)
        collection_name = _KIND_COLLECTION.get(kind) if isinstance(kind, str) else None
        collection = None
        if collection_name is not None:
            candidate = getattr(collection_owner, collection_name, None)
            collection = candidate if isinstance(candidate, list) else None

        mark_registry = None
        mark_mapping: dict | None = None
        mark_atom_id: int | None = None
        mark_entry_existed = False
        mark_list: list | None = None
        if kind == "mark":
            mark_registry = mark_registry_for(canvas)
            candidate_mapping = getattr(mark_registry, "by_atom", None)
            mark_mapping = (
                candidate_mapping if isinstance(candidate_mapping, dict) else None
            )
            metadata = (
                attach_ports.item_data_getter(1)
                if attach_ports.item_data_getter is not None
                else None
            )
            candidate_atom_id = (
                cast(dict, metadata).get("atom_id")
                if isinstance(metadata, dict)
                else None
            )
            if isinstance(candidate_atom_id, int):
                mark_atom_id = candidate_atom_id
            if mark_mapping is not None and mark_atom_id is not None:
                mark_entry_existed = mark_atom_id in mark_mapping
                candidate_list = mark_mapping.get(mark_atom_id)
                mark_list = (
                    list(candidate_list) if isinstance(candidate_list, list) else None
                )

        focus_item = (
            attach_ports.focus_item_getter()
            if attach_ports.focus_item_getter is not None
            else None
        )

        # The growth guard opens last, after every other fallible read, so a
        # failed capture never strands a pinned guard rect.
        scene_rect_snapshot = (
            SceneRectSnapshot.capture(
                scene,
                scene_rect_getter=attach_ports.scene_rect_getter,
                set_scene_rect_setter=attach_ports.scene_rect_setter,
                scene_items_bounding_rect_getter=(
                    attach_ports.scene_items_bounding_rect_getter
                ),
                incremental_tracking=(
                    not attach_ports.requires_authoritative_scene_bounds
                ),
            )
            if scene is not None
            else None
        )
        return cls(
            canvas=canvas,
            item=item,
            scene=scene,
            attach_ports=attach_ports,
            kind=kind,
            collection_owner=collection_owner,
            collection_name=collection_name,
            collection=collection,
            mark_registry=mark_registry,
            mark_mapping=mark_mapping,
            mark_atom_id=mark_atom_id,
            mark_entry_existed=mark_entry_existed,
            mark_list=mark_list,
            item_flags=attach_ports.item_flags,
            text_interaction_flags=attach_ports.text_interaction_flags,
            focus_item=focus_item,
            scene_rect_snapshot=scene_rect_snapshot,
        )

    def _restore_lightweight_registration(
        self,
        original_error: BaseException | None,
        *,
        phase: str,
    ) -> None:
        def step(description: str, operation: Callable[[], object]) -> None:
            try:
                operation()
            except BaseException as rollback_error:
                _add_attach_rollback_note(
                    original_error,
                    rollback_error,
                    phase=f"{description} after {phase}",
                )

        collection_name = self.collection_name
        collection = self.collection
        if collection_name is not None:

            def clean_replacement_collection() -> None:
                current = getattr(self.collection_owner, collection_name, None)
                if isinstance(current, list) and current is not collection:
                    current[:] = [entry for entry in current if entry is not self.item]

            step("cleaning a replaced collection", clean_replacement_collection)
            if collection is not None:
                bound_collection = collection

                def remove_from_collection() -> None:
                    bound_collection[:] = [
                        entry for entry in bound_collection if entry is not self.item
                    ]

                step("removing the item registration", remove_from_collection)

                def repin_collection() -> None:
                    setattr(self.collection_owner, collection_name, bound_collection)

                step("re-pinning the collection", repin_collection)

        mark_mapping = self.mark_mapping
        mark_atom_id = self.mark_atom_id
        if mark_mapping is not None and mark_atom_id is not None:
            bound_mapping = mark_mapping
            bound_atom_id = mark_atom_id

            def restore_mark_entry() -> None:
                if self.mark_entry_existed and self.mark_list is not None:
                    restored = [
                        entry for entry in self.mark_list if entry is not self.item
                    ]
                    live = bound_mapping.get(bound_atom_id)
                    if isinstance(live, list):
                        # Services hold references to the per-atom list;
                        # restore its contents in place.
                        live[:] = restored
                        bound_mapping[bound_atom_id] = live
                    else:
                        bound_mapping[bound_atom_id] = restored
                else:
                    bound_mapping.pop(bound_atom_id, None)

            step("restoring the mark registry entry", restore_mark_entry)

            def repin_mark_mapping() -> None:
                if self.mark_registry is not None:
                    self.mark_registry.by_atom = bound_mapping

            step("re-pinning the mark registry", repin_mark_mapping)

    def restore(
        self,
        original_error: BaseException | None = None,
        *,
        phase: str = "a failed scene-item attach",
        restore_scene_rect: bool = True,
    ) -> None:
        ports = self.attach_ports

        def step(description: str, operation: Callable[[], object]) -> None:
            try:
                operation()
            except BaseException as rollback_error:
                _add_attach_rollback_note(
                    original_error,
                    rollback_error,
                    phase=f"{description} after {phase}",
                )

        if ports is not None:
            step("detaching the item", lambda: ports.remove_item(self.item))
            flags_setter = ports.item_flags_setter
            if flags_setter is not None and self.item_flags is not None:
                step(
                    "restoring the item flags",
                    lambda: flags_setter(self.item_flags),
                )
            text_setter = ports.text_flags_setter
            if text_setter is not None and self.text_interaction_flags is not None:
                step(
                    "restoring the text-interaction flags",
                    lambda: text_setter(self.text_interaction_flags),
                )
        self._restore_lightweight_registration(original_error, phase=phase)
        focus_setter = ports.focus_item_setter if ports is not None else None
        if focus_setter is not None:
            step(
                "restoring the scene focus",
                lambda: focus_setter(self.focus_item),
            )
        if restore_scene_rect:
            self.restore_scene_rect(original_error, phase=phase)

    def restore_scene_rect(
        self,
        original_error: BaseException | None = None,
        *,
        phase: str = "a failed scene-item attach",
    ) -> None:
        snapshot = self.scene_rect_snapshot
        if snapshot is None:
            return
        try:
            if snapshot.active:
                snapshot.restore()
            else:
                snapshot.reassert()
        except BaseException as rollback_error:
            _add_attach_rollback_note(
                original_error,
                rollback_error,
                phase=f"restoring the scene rect after {phase}",
            )

    def release(self) -> None:
        snapshot = self.scene_rect_snapshot
        if snapshot is None:
            return
        ports = self.attach_ports
        if not snapshot.automatic or ports is None:
            snapshot.release()
            return
        bounds_getter = ports.scene_bounding_rect_getter
        expanded_rect = bounds_getter() if callable(bounds_getter) else None
        release_kwargs: dict = {
            "expansion_key": self.item,
            "expansion_owner_scene_getter": ports.item_scene_getter,
        }
        if ports.requires_authoritative_scene_bounds:
            release_kwargs["authoritative_scene_bounds_getter"] = (
                ports.scene_items_bounding_rect_getter
            )
        snapshot.release(expanded_rect, **release_kwargs)


__all__ = ["SceneItemAttachPorts", "SceneItemAttachSnapshot"]
