"""Reorder document images and shapes without moving selection overlays."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.ui.window.main_window_like import MainWindowLike


def stacked_depths(
    depths: list[float], selected: set[int], *, front: bool
) -> list[tuple[int, float]]:
    """Original stable, bounded stacking bands for selected document objects."""
    # Stable sorting retains the document order when default depths are equal.
    objects = sorted(range(len(depths)), key=depths.__getitem__)
    chosen = [index for index in objects if index in selected]
    if not chosen:
        return []
    remaining = [
        index
        for index in objects
        if index not in selected
        and (depths[index] > 3.0 if front else depths[index] < -10.0)
    ]
    ordered = [*remaining, *chosen] if front else [*chosen, *remaining]
    # Bounded bands sit beyond native content (-10 .. 3), below UI overlays.
    # Reindex the band so repeated commands cannot exhaust depth precision.
    return [
        (item, (4.0 if front else -12.0) + index / len(ordered))
        for index, item in enumerate(ordered)
    ]


def stack_selection(canvas, *, front: bool) -> bool:
    from chemvas.ui.annotations.state import scene_item_state_for
    from chemvas.ui.canvas.canvas_document_state import document_item_lists_for
    from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
    from chemvas.ui.history.history_commands import (
        SetSceneGeometryCommand,
        UpdateSceneItemCommand,
    )
    from chemvas.ui.transactions.document import document_transaction

    lists = document_item_lists_for(canvas)
    objects = [*lists["images"], *lists["shapes"]]
    depths = stacked_depths(
        [item.zValue() for item in objects],
        {index for index, item in enumerate(objects) if item.isSelected()},
        front=front,
    )
    commands = []
    for index, z in depths:
        item = objects[index]
        before = scene_item_state_for(canvas, item)
        after = {**before, "z": z}
        if before != after:
            commands.append(
                UpdateSceneItemCommand(require_scene_record_id(item), before, after)
            )
    if not commands:
        return False
    history = canvas.services.history_service
    with document_transaction(canvas, history_service=history):
        command = SetSceneGeometryCommand(atom_commands=[], item_commands=commands)
        command.redo(history.operations)
        history.push(command)
    return True


def stack_selection_for_window(window: MainWindowLike, *, front: bool) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from chemvas.ui.window.main_window_ports import active_canvas_for_window

    canvas = active_canvas_for_window(window)
    try:
        stack_selection(canvas, front=front)
    except ValueError as error:
        QMessageBox.warning(window, "Stacking Order", str(error))
