"""Reorder document images and shapes without moving selection overlays."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from chemvas.ui.canvas_document_state import document_item_lists_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.history_commands import SetSceneGeometryCommand, UpdateSceneItemCommand
from chemvas.ui.main_window_ports import active_canvas_for_window
from chemvas.ui.scene_item_state import scene_item_state_for
from chemvas.ui.transactions.document import document_transaction


def stack_selection(canvas, *, front: bool) -> bool:
    lists = document_item_lists_for(canvas)
    # Stable sorting retains the document order when default depths are equal.
    objects = sorted(
        [*lists["images"], *lists["shapes"]], key=lambda item: item.zValue()
    )
    selected = [item for item in objects if item.isSelected()]
    if not selected:
        return False
    remaining = [
        item
        for item in objects
        if item not in selected
        and (item.zValue() > 3.0 if front else item.zValue() < -10.0)
    ]
    ordered = [*remaining, *selected] if front else [*selected, *remaining]
    commands = []
    for index, item in enumerate(ordered):
        before = scene_item_state_for(canvas, item)
        # Bounded bands sit beyond native content (-10 .. 3), below UI overlays.
        # Reindex the band so repeated commands cannot exhaust depth precision.
        z = (4.0 if front else -12.0) + index / len(ordered)
        after = {**before, "z": z}
        if before != after:
            commands.append(UpdateSceneItemCommand(item, before, after))
    if not commands:
        return False
    history = history_service_for_access(canvas)
    with document_transaction(canvas, history_service=history):
        command = SetSceneGeometryCommand(atom_commands=[], item_commands=commands)
        command.redo(history.operations)
        if not history.push(command):
            raise ValueError("History is disabled; the stacking order was not changed.")
    return True


def stack_selection_for_window(window, *, front: bool) -> None:
    canvas = active_canvas_for_window(window)
    try:
        stack_selection(canvas, front=front)
    except ValueError as error:
        QMessageBox.warning(window, "Stacking Order", str(error))
