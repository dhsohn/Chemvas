from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from ui.canvas_group_state import CanvasSceneGroup, group_state_for
from ui.history_commands import (
    AddSceneItemsCommand,
    ChangeAtomLabelCommand,
    DeleteSceneItemsCommand,
    GroupSceneItemsCommand,
    MoveItemsCommand,
    UngroupSceneItemsCommand,
    UpdateSceneItemCommand,
)


class _Scene:
    def __init__(self) -> None:
        self._items: list[_SceneItem] = []
        self._signals_blocked = False

    def attach(self, item: _SceneItem) -> None:
        if item not in self._items:
            self._items.append(item)
        item._scene = self

    def detach(self, item: _SceneItem) -> None:
        if item in self._items:
            self._items.remove(item)
        item._scene = None

    def items(self) -> list[_SceneItem]:
        return list(self._items)

    def addItem(self, item: _SceneItem) -> None:
        self.attach(item)

    def removeItem(self, item: _SceneItem) -> None:
        self.detach(item)

    def blockSignals(self, blocked: bool) -> bool:
        previous = self._signals_blocked
        self._signals_blocked = blocked
        return previous

    def selectedItems(self) -> list[_SceneItem]:
        return [item for item in self._items if item.isSelected()]


class _SceneItem:
    def __init__(self, name: str) -> None:
        self.name = name
        self._scene: _Scene | None = None
        self.x = 0.0
        self.y = 0.0
        self._selected = False
        self._visible = True

    def scene(self) -> _Scene | None:
        return self._scene

    def parentItem(self):
        return None

    def zValue(self) -> float:
        return 0.0

    def stackBefore(self, sibling: _SceneItem) -> None:
        if self._scene is None or sibling._scene is not self._scene:
            return
        items = self._scene._items
        items.remove(self)
        items.insert(items.index(sibling) + 1, self)

    def isSelected(self) -> bool:
        return self._selected

    def setSelected(self, selected: bool) -> None:
        self._selected = bool(selected)

    def isVisible(self) -> bool:
        return self._visible

    def setVisible(self, visible: bool) -> None:
        self._visible = bool(visible)


class _RawStateSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.metadata_x = 0.0

    def pos(self) -> float:
        return self.x

    def setPos(self, position: float) -> None:
        self.x = float(position)

    def data(self, index: int):
        if index == 1:
            return {"metadata_x": self.metadata_x}
        return None

    def setData(self, index: int, value) -> None:
        if index == 1:
            self.metadata_x = float(value["metadata_x"])


class _ModelBackedSceneItem(_SceneItem):
    def __init__(self, name: str, kind: str, item_id: int) -> None:
        super().__init__(name)
        self.kind = kind
        self.item_id = item_id

    def pos(self) -> float:
        return self.x

    def setPos(self, position: float) -> None:
        self.x = float(position)

    def data(self, index: int):
        if index == 0:
            return self.kind
        if index == 1:
            return self.item_id
        return None

    def setData(self, index: int, value) -> None:
        if index == 1:
            self.item_id = int(value)


class _VisualRectSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.rect_value = "before-rect"
        self.pen_value = "before-pen"
        self.brush_value = "before-brush"

    def data(self, index: int):
        return "note_select" if index == 0 else None

    def rect(self):
        return self.rect_value

    def setRect(self, value) -> None:
        self.rect_value = value

    def pen(self):
        return self.pen_value

    def setPen(self, value) -> None:
        self.pen_value = value

    def brush(self):
        return self.brush_value

    def setBrush(self, value) -> None:
        self.brush_value = value


class _StyledSceneItem(_SceneItem):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.pen_value = "highlight"
        self.original_pen = "normal"

    def pen(self):
        return self.pen_value

    def setPen(self, value) -> None:
        self.pen_value = value

    def data(self, index: int):
        return self.original_pen if index == 6 else None

    def setData(self, index: int, value) -> None:
        if index == 6:
            self.original_pen = value


class _Canvas:
    def __init__(self) -> None:
        self._scene = _Scene()

    def scene(self) -> _Scene:
        return self._scene


def _install_scene_runtime_state(canvas: _Canvas) -> None:
    canvas.scene_items_state = SimpleNamespace(
        selected_notes=[],
        ring_items=[],
        note_items=[],
        mark_items=[],
        arrow_items=[],
        ts_bracket_items=[],
        shape_items=[],
        orbital_items=[],
    )
    canvas.mark_registry = SimpleNamespace(by_atom={})
    canvas.handle_state = SimpleNamespace(active_handles=[], target=None)
    canvas.selection_style_state = SimpleNamespace(selected_items=[])
    canvas.selection_outline_state = SimpleNamespace(outlines=[])
    canvas.selection_info_state = SimpleNamespace(
        signature=(frozenset({1}), frozenset()),
        pending_signature=None,
        cache=("before", "selection"),
        rdkit_warmup_pending=False,
        last_interaction_time=1.0,
    )


def _restore_scene_item(canvas: _Canvas, item: _SceneItem) -> None:
    canvas.scene().attach(item)


def _remove_scene_item(canvas: _Canvas, item: _SceneItem) -> None:
    canvas.scene().detach(item)


def _persistent_outline_failure(canvas: _Canvas):
    old_outline = _SceneItem("old-outline")
    canvas.scene().attach(old_outline)
    outlines = [old_outline]
    canvas.selection_outline_state.outlines = outlines
    partial_outlines: list[_SceneItem] = []

    def refresh_then_fail(_canvas) -> None:
        for outline in list(canvas.selection_outline_state.outlines):
            canvas.scene().detach(outline)
        partial = _SceneItem(f"partial-{len(partial_outlines)}")
        partial_outlines.append(partial)
        canvas.scene().attach(partial)
        canvas.selection_outline_state.outlines = [partial]
        raise RuntimeError("persistent outline rebuild failure")

    return old_outline, outlines, partial_outlines, refresh_then_fail


def _assert_original_outline_restored(
    canvas: _Canvas,
    old_outline: _SceneItem,
    outlines: list[_SceneItem],
    partial_outlines: list[_SceneItem],
) -> None:
    assert canvas.selection_outline_state.outlines is outlines
    assert outlines == [old_outline]
    assert old_outline.scene() is canvas.scene()
    assert all(partial.scene() is None for partial in partial_outlines)


@pytest.mark.parametrize(
    ("command", "method_name", "starts_attached", "operation_name"),
    [
        (AddSceneItemsCommand([], []), "redo", False, "restore"),
        (AddSceneItemsCommand([], []), "undo", True, "remove"),
        (DeleteSceneItemsCommand([], []), "redo", True, "remove"),
        (DeleteSceneItemsCommand([], []), "undo", False, "restore"),
    ],
)
def test_existing_scene_item_commands_rollback_a_second_item_that_mutates_then_raises(
    command,
    method_name: str,
    starts_attached: bool,
    operation_name: str,
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    command.items[:] = items
    if starts_attached:
        for item in items:
            canvas.scene().attach(item)
    before = canvas.scene().items()
    failed = False

    def restore_with_failure(canvas_arg, item) -> None:
        nonlocal failed
        _restore_scene_item(canvas_arg, item)
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("restore failed after mutation")

    def remove_with_failure(canvas_arg, item) -> None:
        nonlocal failed
        _remove_scene_item(canvas_arg, item)
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("remove failed after mutation")

    patches = {
        "_restore_scene_item": restore_with_failure,
        "_remove_scene_item": remove_with_failure,
    }
    with mock.patch.multiple("ui.history_commands", **patches):
        with pytest.raises(RuntimeError, match=f"{operation_name} failed after mutation"):
            getattr(command, method_name)(canvas)

    assert canvas.scene().items() == before


@pytest.mark.parametrize(
    "command",
    [
        AddSceneItemsCommand([{"name": "first"}, {"name": "second", "fail": True}]),
        DeleteSceneItemsCommand([{"name": "first"}, {"name": "second", "fail": True}]),
    ],
)
def test_initial_scene_item_creation_rollback_finds_the_unreturned_failed_item(command) -> None:
    canvas = _Canvas()
    existing = _SceneItem("existing")
    canvas.scene().attach(existing)
    before = canvas.scene().items()

    def create_with_failure(canvas_arg, state):
        item = _SceneItem(state["name"])
        canvas_arg.scene().attach(item)
        if state.get("fail"):
            raise RuntimeError("create failed after mutation")
        return item

    method = command.redo if isinstance(command, AddSceneItemsCommand) else command.undo
    with (
        mock.patch("ui.history_commands._create_scene_item_from_state", side_effect=create_with_failure),
        mock.patch("ui.history_commands._remove_scene_item", side_effect=_remove_scene_item),
        pytest.raises(RuntimeError, match="create failed after mutation"),
    ):
        method(canvas)

    assert canvas.scene().items() == before
    assert command.items == []


def test_note_remove_failure_restores_collections_selection_and_container_identity() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    other = _SceneItem("other")
    note = _SceneItem("note")
    tail = _SceneItem("tail")
    for item in (other, note, tail):
        canvas.scene().attach(item)
    note.setSelected(True)

    note_items = [other, note]
    selected_notes = [note]
    selected_style_items = [note]
    outlines = [_SceneItem("outline")]
    canvas.scene_items_state.note_items = note_items
    canvas.scene_items_state.selected_notes = selected_notes
    canvas.selection_style_state.selected_items = selected_style_items
    canvas.selection_outline_state.outlines = outlines
    before_order = canvas.scene().items()
    before_info = vars(canvas.selection_info_state).copy()

    def remove_after_registration_mutation(_canvas, item) -> None:
        note_items.remove(item)
        selected_notes.remove(item)
        item.setSelected(False)
        canvas.selection_style_state.selected_items = []
        canvas.selection_outline_state.outlines = []
        canvas.selection_info_state.signature = None
        canvas.selection_info_state.cache = ("mutated", "selection")
        raise RuntimeError("note remove failed before detach")

    command = DeleteSceneItemsCommand([], [note])
    with (
        mock.patch("ui.history_commands._remove_scene_item", side_effect=remove_after_registration_mutation),
        mock.patch("ui.history_commands._restore_scene_item", side_effect=_restore_scene_item),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before_order
    assert note.isSelected()
    assert canvas.scene_items_state.note_items is note_items
    assert note_items == [other, note]
    assert canvas.scene_items_state.selected_notes is selected_notes
    assert selected_notes == [note]
    assert canvas.selection_style_state.selected_items is selected_style_items
    assert selected_style_items == [note]
    assert canvas.selection_outline_state.outlines is outlines
    assert vars(canvas.selection_info_state) == before_info


def test_note_remove_failure_restores_selection_child_visual_state() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    note = _SceneItem("note")
    selection_box = _VisualRectSceneItem("note-select")
    canvas.scene().attach(note)
    canvas.scene().attach(selection_box)
    selected_notes = [note]
    note_items = [note]
    canvas.scene_items_state.selected_notes = selected_notes
    canvas.scene_items_state.note_items = note_items

    def remove_after_selection_box_mutation(_canvas, item) -> None:
        selected_notes.remove(item)
        note_items.remove(item)
        selection_box.setVisible(False)
        selection_box.setRect("mutated-rect")
        selection_box.setPen("mutated-pen")
        selection_box.setBrush("mutated-brush")
        canvas.scene().detach(item)
        raise RuntimeError("note detach failed after hiding selection box")

    command = DeleteSceneItemsCommand([], [note])
    with (
        mock.patch("ui.history_commands._remove_scene_item", side_effect=remove_after_selection_box_mutation),
        mock.patch("ui.history_commands._restore_scene_item", side_effect=_restore_scene_item),
        pytest.raises(RuntimeError, match="after hiding selection box"),
    ):
        command.redo(canvas)

    assert canvas.scene_items_state.selected_notes is selected_notes
    assert selected_notes == [note]
    assert canvas.scene_items_state.note_items is note_items
    assert note_items == [note]
    assert selection_box.isVisible()
    assert selection_box.rect_value == "before-rect"
    assert selection_box.pen_value == "before-pen"
    assert selection_box.brush_value == "before-brush"
    assert canvas.scene().items() == [note, selection_box]


def test_mark_remove_failure_restores_registry_nested_lists_and_mapping_identity() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    mark = _SceneItem("mark")
    canvas.scene().attach(mark)
    mark_items = [mark]
    marks_for_atom = [mark]
    by_atom = {7: marks_for_atom}
    canvas.scene_items_state.mark_items = mark_items
    canvas.mark_registry.by_atom = by_atom

    def remove_after_registry_mutation(_canvas, item) -> None:
        mark_items.remove(item)
        marks_for_atom.remove(item)
        by_atom.pop(7)
        raise RuntimeError("mark remove failed before detach")

    command = AddSceneItemsCommand([], [mark])
    with (
        mock.patch("ui.history_commands._remove_scene_item", side_effect=remove_after_registry_mutation),
        mock.patch("ui.history_commands._restore_scene_item", side_effect=_restore_scene_item),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.undo(canvas)

    assert canvas.scene_items_state.mark_items is mark_items
    assert mark_items == [mark]
    assert canvas.mark_registry.by_atom is by_atom
    assert by_atom[7] is marks_for_atom
    assert marks_for_atom == [mark]
    assert mark.scene() is canvas.scene()


@pytest.mark.parametrize("collection_name", ["shape_items", "orbital_items"])
def test_handle_target_remove_failure_restores_handles_scene_order_and_container_identity(
    collection_name: str,
) -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    target = _StyledSceneItem("target")
    first_handle = _SceneItem("first-handle")
    second_handle = _SceneItem("second-handle")
    other = _SceneItem("other")
    for item in (target, first_handle, second_handle, other):
        canvas.scene().attach(item)
    target_collection = [target]
    setattr(canvas.scene_items_state, collection_name, target_collection)
    active_handles = [first_handle, second_handle]
    canvas.handle_state.active_handles = active_handles
    canvas.handle_state.target = target
    selected_style_items = [target]
    canvas.selection_style_state.selected_items = selected_style_items
    before_order = canvas.scene().items()

    def remove_after_handle_clear(_canvas, item) -> None:
        target_collection.remove(item)
        canvas.scene().detach(first_handle)
        canvas.scene().detach(second_handle)
        canvas.handle_state.active_handles = []
        canvas.handle_state.target = None
        target.pen_value = "normal"
        target.original_pen = None
        canvas.selection_style_state.selected_items = []
        raise RuntimeError("target remove failed before detach")

    command = DeleteSceneItemsCommand([], [target])
    with (
        mock.patch("ui.history_commands._remove_scene_item", side_effect=remove_after_handle_clear),
        mock.patch("ui.history_commands._restore_scene_item", side_effect=_restore_scene_item),
        pytest.raises(RuntimeError, match="before detach"),
    ):
        command.redo(canvas)

    assert canvas.scene().items() == before_order
    assert getattr(canvas.scene_items_state, collection_name) is target_collection
    assert target_collection == [target]
    assert canvas.handle_state.active_handles is active_handles
    assert active_handles == [first_handle, second_handle]
    assert canvas.handle_state.target is target
    assert canvas.selection_style_state.selected_items is selected_style_items
    assert selected_style_items == [target]
    assert target.pen_value == "highlight"
    assert target.original_pen == "normal"


@pytest.mark.parametrize(("method_name", "direction"), [("redo", 1.0), ("undo", -1.0)])
def test_move_items_command_rolls_back_a_second_item_that_mutates_then_raises(
    method_name: str,
    direction: float,
) -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for item in items:
        canvas.scene().attach(item)
    before = [(item.x, item.y) for item in items]
    failed = False

    def move_with_failure(_canvas, item, dx, dy, *, update_selection) -> None:
        nonlocal failed
        assert not update_selection
        item.x += dx
        item.y += dy
        if item is items[1] and dx == direction * 3.0 and not failed:
            failed = True
            raise RuntimeError("move failed after mutation")

    command = MoveItemsCommand(items, 3.0, 5.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="move failed after mutation"),
    ):
        getattr(command, method_name)(canvas)

    assert [(item.x, item.y) for item in items] == before


def test_move_items_command_restores_absolute_state_after_partial_field_mutation() -> None:
    canvas = _Canvas()
    items = [_SceneItem("first"), _SceneItem("second")]
    for index, item in enumerate(items):
        item.x = float(index)
        item.metadata_x = float(index)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "test", "x": item.x, "metadata_x": item.metadata_x}

    def apply_state(_canvas, item, state) -> None:
        item.x = state["x"]
        item.metadata_x = state["metadata_x"]

    def move_with_partial_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal failed
        assert not update_selection
        item.x += dx
        if item is items[1] and not failed:
            failed = True
            raise RuntimeError("move failed between geometry and metadata")
        item.metadata_x += dx

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch("ui.history_commands.scene_item_state_for", side_effect=snapshot_state),
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=apply_state),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_with_partial_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="between geometry and metadata"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


@pytest.mark.parametrize(
    ("kind", "item_id", "moved_atom_ids"),
    [
        ("atom", 7, (7,)),
        ("bond", 0, (7, 8)),
    ],
)
def test_move_model_backed_item_restores_absolute_model_and_3d_state_on_refresh_failure(
    kind: str,
    item_id: int,
    moved_atom_ids: tuple[int, ...],
) -> None:
    canvas = _Canvas()
    atoms = {
        7: SimpleNamespace(x=1.0, y=2.0),
        8: SimpleNamespace(x=5.0, y=6.0),
    }
    canvas.model = SimpleNamespace(
        atoms=atoms,
        bonds=[SimpleNamespace(a=7, b=8)],
    )
    coords_3d = {
        7: (1.0, 2.0, 3.0),
        8: (5.0, 6.0, 7.0),
    }
    canvas.atom_coords_3d_state = SimpleNamespace(atom_coords_3d=coords_3d)
    item = _ModelBackedSceneItem(kind, kind, item_id)
    canvas.scene().attach(item)
    before_positions = {atom_id: (atoms[atom_id].x, atoms[atom_id].y) for atom_id in moved_atom_ids}
    before_coords = {atom_id: coords_3d[atom_id] for atom_id in moved_atom_ids}

    def move_model_item(_canvas, current_item, dx, dy, *, update_selection) -> None:
        assert not update_selection
        current_item.x += dx
        for atom_id in moved_atom_ids:
            atoms[atom_id].x += dx
            atoms[atom_id].y += dy
            x, y, z = coords_3d[atom_id]
            coords_3d[atom_id] = (x + dx, y + dy, z)

    restore_calls: list[tuple[dict, dict | None]] = []

    def restore_model_state(_canvas, positions, *, update_selection, coords_3d=None) -> None:
        assert not update_selection
        restore_calls.append((dict(positions), dict(coords_3d) if coords_3d is not None else None))
        for atom_id, (x, y) in positions.items():
            atoms[atom_id].x = x
            atoms[atom_id].y = y
        if coords_3d is not None:
            canvas.atom_coords_3d_state.atom_coords_3d.update(coords_3d)

    command = MoveItemsCommand([item], 4.0, 9.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_model_item),
        mock.patch("ui.history_commands._set_atom_positions_for_history", side_effect=restore_model_state),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=RuntimeError("selection refresh failed"),
        ),
        pytest.raises(RuntimeError, match="selection refresh failed"),
    ):
        command.redo(canvas)

    assert item.x == 0.0
    assert {atom_id: (atoms[atom_id].x, atoms[atom_id].y) for atom_id in moved_atom_ids} == before_positions
    assert {atom_id: coords_3d[atom_id] for atom_id in moved_atom_ids} == before_coords
    assert restore_calls == [(before_positions, before_coords)]


def test_move_items_restores_exact_outline_runtime_after_persistent_refresh_failure() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    item = _SceneItem("moved")
    canvas.scene().attach(item)
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )

    def move_item(_canvas, target, dx, dy, *, update_selection) -> None:
        assert not update_selection
        target.x += dx
        target.y += dy

    command = MoveItemsCommand([item], 4.0, 9.0)
    with (
        mock.patch("ui.history_commands.move_item_for", side_effect=move_item),
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert (item.x, item.y) == (0.0, 0.0)
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )


def test_move_rollback_uses_raw_savepoint_when_canonical_apply_mutates_then_raises() -> None:
    canvas = _Canvas()
    items = [_RawStateSceneItem("first"), _RawStateSceneItem("second")]
    for index, item in enumerate(items):
        item.x = float(index)
        item.metadata_x = float(index)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    move_failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "test", "x": item.x, "metadata_x": item.metadata_x}

    def partially_failing_apply(_canvas, item, state) -> None:
        item.x = state["x"] + 100.0
        item.metadata_x = state["metadata_x"] + 100.0
        raise RuntimeError("canonical apply failed after mutation")

    def move_with_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal move_failed
        assert not update_selection
        item.x += dx
        item.metadata_x += dx
        if item is items[1] and not move_failed:
            move_failed = True
            raise RuntimeError("move failed after mutation")

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch("ui.history_commands.scene_item_state_for", side_effect=snapshot_state),
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=partially_failing_apply),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="move failed after mutation"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


def test_move_rollback_restores_raw_orbital_center_before_canonical_apply() -> None:
    canvas = _Canvas()
    items = [_RawStateSceneItem("first"), _RawStateSceneItem("second")]
    for index, item in enumerate(items, start=1):
        item.x = float(index)
        item.metadata_x = float(index * 10)
        canvas.scene().attach(item)
    before = [(item.x, item.metadata_x) for item in items]
    move_failed = False

    def snapshot_state(_canvas, item):
        return {"kind": "orbital", "center": item.metadata_x}

    def apply_orbital_state(_canvas, item, state) -> None:
        desired_center = state["center"]
        item.x += desired_center - item.metadata_x
        item.metadata_x = desired_center

    def move_before_center_failure(_canvas, item, dx, _dy, *, update_selection) -> None:
        nonlocal move_failed
        assert not update_selection
        item.x += dx
        if item is items[1] and not move_failed:
            move_failed = True
            raise RuntimeError("orbital move failed before center update")
        item.metadata_x += dx

    command = MoveItemsCommand(items, 4.0, 0.0)
    with (
        mock.patch("ui.history_commands.scene_item_state_for", side_effect=snapshot_state),
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=apply_orbital_state),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_before_center_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="before center update"),
    ):
        command.redo(canvas)

    assert [(item.x, item.metadata_x) for item in items] == before


@pytest.mark.parametrize("kind", ["arrow", "ts_bracket"])
def test_move_rollback_canonical_apply_normalizes_absolute_path_position(kind: str) -> None:
    canvas = _Canvas()
    item = _RawStateSceneItem(kind)
    item.x = 3.0
    item.metadata_x = 13.0
    item.geometry_x = 10.0
    canvas.scene().attach(item)

    def snapshot_state(_canvas, current_item):
        return {"kind": kind, "absolute_x": current_item.metadata_x}

    def apply_absolute_state(_canvas, current_item, state) -> None:
        current_item.x = 0.0
        current_item.geometry_x = state["absolute_x"]
        current_item.metadata_x = state["absolute_x"]

    def move_then_fail(_canvas, current_item, dx, _dy, *, update_selection) -> None:
        assert not update_selection
        current_item.x += dx
        current_item.metadata_x += dx
        raise RuntimeError("absolute item move failed")

    command = MoveItemsCommand([item], 4.0, 0.0)
    with (
        mock.patch("ui.history_commands.scene_item_state_for", side_effect=snapshot_state),
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=apply_absolute_state),
        mock.patch("ui.history_commands.move_item_for", side_effect=move_then_fail),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="absolute item move failed"),
    ):
        command.redo(canvas)

    assert item.x == 0.0
    assert item.geometry_x == 13.0
    assert item.metadata_x == 13.0


@pytest.mark.parametrize("method_name", ["redo", "undo"])
@pytest.mark.parametrize("failure_point", ["apply", "refresh"])
def test_update_scene_item_command_compensates_current_child_failure(
    method_name: str,
    failure_point: str,
) -> None:
    before_state = {"value": 1}
    after_state = {"value": 2}
    target_state = after_state if method_name == "redo" else before_state
    rollback_state = before_state if method_name == "redo" else after_state
    canvas = SimpleNamespace(value=rollback_state["value"])
    command = UpdateSceneItemCommand("item", before_state, after_state)
    apply_failed = False
    refresh_failed = False

    def apply_state(_canvas, _item, state) -> None:
        nonlocal apply_failed
        canvas.value = state["value"]
        if failure_point == "apply" and state is target_state and not apply_failed:
            apply_failed = True
            raise RuntimeError("scene apply failed after mutation")

    def refresh(_canvas) -> None:
        nonlocal refresh_failed
        if failure_point == "refresh" and not refresh_failed:
            refresh_failed = True
            raise RuntimeError("refresh failed after scene apply")

    with (
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=apply_state),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas", side_effect=refresh),
        pytest.raises(RuntimeError, match="failed"),
    ):
        getattr(command, method_name)(canvas)

    assert canvas.value == rollback_state["value"]


def test_update_scene_item_restores_old_outline_objects_when_refresh_rebuild_fails() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    canvas.value = 1
    old_outline = _SceneItem("old-outline")
    canvas.scene().attach(old_outline)
    outlines = [old_outline]
    canvas.selection_outline_state.outlines = outlines
    partial_outlines: list[_SceneItem] = []

    def apply_state(_canvas, _item, state) -> None:
        canvas.value = state["value"]

    def refresh_then_fail(_canvas) -> None:
        for outline in list(canvas.selection_outline_state.outlines):
            canvas.scene().detach(outline)
        partial = _SceneItem(f"partial-{len(partial_outlines)}")
        partial_outlines.append(partial)
        canvas.scene().attach(partial)
        canvas.selection_outline_state.outlines = [partial]
        raise RuntimeError("outline rebuild failed after clear")

    command = UpdateSceneItemCommand("item", {"value": 1}, {"value": 2})
    with (
        mock.patch("ui.history_commands._apply_scene_item_state", side_effect=apply_state),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas", side_effect=refresh_then_fail),
        pytest.raises(RuntimeError, match="outline rebuild failed after clear"),
    ):
        command.redo(canvas)

    assert canvas.value == 1
    assert canvas.selection_outline_state.outlines is outlines
    assert outlines == [old_outline]
    assert canvas.scene().items() == [old_outline]
    assert all(partial.scene() is None for partial in partial_outlines)


@pytest.mark.parametrize("method_name", ["redo", "undo"])
def test_change_atom_label_command_compensates_smiles_failure_after_label_mutation(
    method_name: str,
) -> None:
    before = ("C", False, "before")
    after = ("N", True, "after")
    target = after if method_name == "redo" else before
    rollback = before if method_name == "redo" else after
    canvas = SimpleNamespace(element=rollback[0], explicit_label=rollback[1], smiles=rollback[2])
    command = ChangeAtomLabelCommand(
        atom_id=7,
        before_element=before[0],
        after_element=after[0],
        before_explicit_label=before[1],
        after_explicit_label=after[1],
        before_smiles_input=before[2],
        after_smiles_input=after[2],
    )
    smiles_failed = False

    def apply_label(
        _canvas,
        _atom_id,
        element,
        *,
        clear_smiles,
        record,
        allow_merge,
        show_carbon,
    ) -> None:
        assert not clear_smiles
        assert not record
        assert not allow_merge
        canvas.element = element
        canvas.explicit_label = show_carbon

    def apply_smiles(_canvas, value) -> None:
        nonlocal smiles_failed
        canvas.smiles = value
        if value == target[2] and not smiles_failed:
            smiles_failed = True
            raise RuntimeError("smiles failed after label mutation")

    with (
        mock.patch("ui.history_commands.add_or_update_atom_label", side_effect=apply_label),
        mock.patch("ui.history_commands.set_last_smiles_input_for", side_effect=apply_smiles),
        pytest.raises(RuntimeError, match="smiles failed"),
    ):
        getattr(command, method_name)(canvas)

    assert (canvas.element, canvas.explicit_label, canvas.smiles) == rollback


def _group_snapshot(canvas) -> tuple[dict[int, CanvasSceneGroup], int, bool]:
    state = group_state_for(canvas)
    return dict(state.groups), state.next_group_id, state.expanding


def test_group_redo_rolls_back_when_second_absorbed_group_removal_mutates_then_raises() -> None:
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    absorbed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    state.groups.update(absorbed)
    state.next_group_id = 3
    before = _group_snapshot(canvas)
    command = GroupSceneItemsCommand({1, 2, 3}, [], absorbed=absorbed)

    def remove_with_failure(_canvas, group_id):
        removed = state.groups.pop(group_id, None)
        if group_id == 2:
            raise RuntimeError("remove group failed after mutation")
        return removed

    with (
        mock.patch("ui.history_commands.remove_group_for", side_effect=remove_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="remove group failed after mutation"),
    ):
        command.redo(canvas)

    assert _group_snapshot(canvas) == before
    assert command.group_id is None


def test_group_undo_rolls_back_when_second_absorbed_group_restore_mutates_then_raises() -> None:
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    absorbed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    merged = CanvasSceneGroup({1, 2, 3}, [])
    state.groups[3] = merged
    state.next_group_id = 4
    before = _group_snapshot(canvas)
    command = GroupSceneItemsCommand({1, 2, 3}, [], absorbed=absorbed, group_id=3)

    def restore_with_failure(_canvas, group_id, group):
        state.groups[group_id] = group
        if group_id == 2:
            raise RuntimeError("restore group failed after mutation")

    with (
        mock.patch("ui.history_commands.restore_group_for", side_effect=restore_with_failure),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match="restore group failed after mutation"),
    ):
        command.undo(canvas)

    assert _group_snapshot(canvas) == before
    assert command.group_id == 3


def test_group_command_restores_exact_outline_runtime_after_persistent_refresh_failure() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    state = group_state_for(canvas)
    absorbed_group = CanvasSceneGroup({1}, [])
    state.groups[1] = absorbed_group
    groups_object = state.groups
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )
    command = GroupSceneItemsCommand(
        {1, 2},
        [],
        absorbed=[(1, absorbed_group)],
    )

    with (
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert state.groups is groups_object
    assert state.groups == {1: absorbed_group}
    assert state.groups[1] is absorbed_group
    assert command.group_id is None
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )


@pytest.mark.parametrize("method_name", ["redo", "undo"])
def test_ungroup_command_rolls_back_when_second_group_mutates_then_raises(method_name: str) -> None:
    canvas = SimpleNamespace()
    state = group_state_for(canvas)
    removed = [
        (1, CanvasSceneGroup({1}, [])),
        (2, CanvasSceneGroup({2}, [])),
    ]
    if method_name == "redo":
        state.groups.update(removed)
    state.next_group_id = 3
    before = _group_snapshot(canvas)
    command = UngroupSceneItemsCommand(removed)

    def remove_with_failure(_canvas, group_id):
        group = state.groups.pop(group_id, None)
        if group_id == 2:
            raise RuntimeError("remove group failed after mutation")
        return group

    def restore_with_failure(_canvas, group_id, group):
        state.groups[group_id] = group
        if group_id == 2:
            raise RuntimeError("restore group failed after mutation")

    operation = remove_with_failure if method_name == "redo" else restore_with_failure
    operation_name = "remove_group_for" if method_name == "redo" else "restore_group_for"
    error_pattern = "remove group failed" if method_name == "redo" else "restore group failed"
    with (
        mock.patch(f"ui.history_commands.{operation_name}", side_effect=operation),
        mock.patch("ui.history_commands.refresh_selection_outline_for_canvas"),
        pytest.raises(RuntimeError, match=error_pattern),
    ):
        getattr(command, method_name)(canvas)

    assert _group_snapshot(canvas) == before


def test_ungroup_command_restores_exact_outline_runtime_after_persistent_refresh_failure() -> None:
    canvas = _Canvas()
    _install_scene_runtime_state(canvas)
    state = group_state_for(canvas)
    removed_group = CanvasSceneGroup({1}, [])
    state.groups[1] = removed_group
    groups_object = state.groups
    old_outline, outlines, partial_outlines, refresh_then_fail = (
        _persistent_outline_failure(canvas)
    )
    command = UngroupSceneItemsCommand([(1, removed_group)])

    with (
        mock.patch(
            "ui.history_commands.refresh_selection_outline_for_canvas",
            side_effect=refresh_then_fail,
        ),
        pytest.raises(RuntimeError, match="persistent outline rebuild failure"),
    ):
        command.redo(canvas)

    assert state.groups is groups_object
    assert state.groups == {1: removed_group}
    assert state.groups[1] is removed_group
    _assert_original_outline_restored(
        canvas,
        old_outline,
        outlines,
        partial_outlines,
    )
