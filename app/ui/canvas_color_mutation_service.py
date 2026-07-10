from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.history import (
    CompositeCommand,
    HistoryCommand,
    UpdateAtomColorCommand,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsEllipseItem,
    QGraphicsTextItem,
)

from ui.atom_label_access import implicit_carbon_dot_brush_for
from ui.bond_graphics_access import apply_color_to_bond_item_for
from ui.canvas_atom_graphics_state import (
    atom_dots_for,
    atom_items_for,
    visible_atom_item_for,
)
from ui.canvas_bond_graphics_state import bond_items_for_id
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.graphics_items import AtomDotItem
from ui.history_commands import UpdateSceneItemCommand
from ui.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from ui.scene_item_access import item_is_in_canvas_scene
from ui.scene_item_state import (
    note_state_dict_for,
    ring_state_dict_for,
    shape_state_dict_for,
)

if TYPE_CHECKING:
    from ui.canvas_view import CanvasView


class _CollectingHistory:
    """Drop-in for the history service that captures pushed commands instead of
    recording them, so a multi-element mutation can be bundled into one command."""

    def __init__(self, sink) -> None:
        self._sink = sink

    def push(self, command) -> None:
        self._sink(command)


def _set_graphics_brush_exact(item, brush: QBrush) -> None:
    if isinstance(item, QAbstractGraphicsShapeItem):
        QAbstractGraphicsShapeItem.setBrush(item, QBrush(brush))
        return
    item.setBrush(QBrush(brush))


def _set_graphics_pen_exact(item, pen: QPen) -> None:
    if isinstance(item, QAbstractGraphicsShapeItem):
        QAbstractGraphicsShapeItem.setPen(item, QPen(pen))
        return
    item.setPen(QPen(pen))


def _bond_graphics_style_restore(item) -> Callable[[], None]:
    brush_method = getattr(item, "brush", None)
    brush = None
    if callable(brush_method):
        with contextlib.suppress(TypeError, RuntimeError):
            brush = QBrush(brush_method())
    pen_method = getattr(item, "pen", None)
    pen = None
    if callable(pen_method):
        with contextlib.suppress(TypeError, RuntimeError):
            pen = QPen(pen_method())

    def restore() -> None:
        if pen is not None:
            _set_graphics_pen_exact(item, pen)
        if brush is not None:
            _set_graphics_brush_exact(item, brush)

    return restore


def _apply_bond_color_in_place(canvas, bond_id: int, color: QColor | str) -> None:
    bond = bond_for_id(canvas, bond_id)
    if bond is None:
        return
    color_value = QColor(color)
    if not color_value.isValid():
        return
    before_color = bond.color
    restores = [_bond_graphics_style_restore(item) for item in bond_items_for_id(canvas, bond_id)]
    try:
        bond.color = color_value.name()
        for bond_item in bond_items_for_id(canvas, bond_id):
            apply_color_to_bond_item_for(canvas, bond_item, color_value)
    except Exception:
        bond.color = before_color
        for restore in restores:
            with contextlib.suppress(Exception):
                restore()
        raise


@dataclass
class UpdateBondColorCommand(HistoryCommand):
    bond_id: int
    before_color: str
    after_color: str

    def undo(self, canvas) -> None:
        _apply_bond_color_in_place(canvas, self.bond_id, self.before_color)

    def redo(self, canvas) -> None:
        _apply_bond_color_in_place(canvas, self.bond_id, self.after_color)


@dataclass
class _NoteColorState:
    html: str
    cursor_anchor: int
    cursor_position: int
    interaction_flags: Qt.TextInteractionFlag
    default_text_color: QColor
    committed_text: str
    committed_html: str

    @classmethod
    def capture(cls, item: QGraphicsTextItem) -> _NoteColorState:
        cursor = item.textCursor()
        return cls(
            html=item.toHtml(),
            cursor_anchor=cursor.anchor(),
            cursor_position=cursor.position(),
            interaction_flags=item.textInteractionFlags(),
            default_text_color=QColor(item.defaultTextColor()),
            committed_text=committed_note_text_for(item),
            committed_html=committed_note_html_for(item),
        )

    def apply(self, item: QGraphicsTextItem) -> None:
        item.setHtml(self.html)
        QGraphicsTextItem.setDefaultTextColor(item, QColor(self.default_text_color))
        item.setTextInteractionFlags(self.interaction_flags)
        cursor = QTextCursor(item.document())
        cursor.setPosition(self.cursor_anchor)
        cursor.setPosition(self.cursor_position, QTextCursor.MoveMode.KeepAnchor)
        item.setTextCursor(cursor)
        set_committed_note_text_for(item, self.committed_text)
        set_committed_note_html_for(item, self.committed_html)


@dataclass
class UpdateNoteColorCommand(HistoryCommand):
    item: QGraphicsTextItem
    before_state: _NoteColorState
    after_state: _NoteColorState

    def _apply(self, state: _NoteColorState, rollback_state: _NoteColorState) -> None:
        try:
            state.apply(self.item)
        except Exception:
            with contextlib.suppress(Exception):
                rollback_state.apply(self.item)
            raise

    def undo(self, canvas) -> None:
        del canvas
        self._apply(self.before_state, self.after_state)

    def redo(self, canvas) -> None:
        del canvas
        self._apply(self.after_state, self.before_state)


class CanvasColorMutationService:
    def __init__(self, canvas: CanvasView, *, graph_service, history_service=None) -> None:
        self.canvas = canvas
        self.history = history_service
        self.graph_service = graph_service

    def apply_color_to_item(self, item, color: QColor) -> None:
        if item is None or not color.isValid():
            return
        if not item_is_in_canvas_scene(self.canvas, item):
            return
        kind = item.data(0)
        if kind == "bond":
            self._apply_bond_color(item, color)
            return
        if kind == "atom":
            self._apply_atom_color(item, color)
            return
        if kind == "ring":
            self._apply_ring_structure_color(item, color)
            return
        if kind == "note" and isinstance(item, QGraphicsTextItem):
            self._apply_note_color(item, color)
            return
        if kind == "shape":
            self._apply_shape_fill(item, color)

    def apply_color_to_items(self, items: Iterable[object], color: QColor) -> None:
        items = tuple(items)
        rollback = self._batch_runtime_rollback(items, expand_ring_structures=True)

        def apply_all() -> None:
            for item in items:
                self.apply_color_to_item(item, color)

        self._run_history_transaction(apply_all, rollback=rollback)

    # Shape panels and ring fills stack behind the structure as ChemDraw-style
    # pastels: the picked colour is diluted toward the white sheet and applied
    # opaque, so it reads as tinted paper rather than translucent glass. A
    # translucent wash would blend with whatever sits underneath and look
    # layered instead.
    SHAPE_FILL_TINT = 0.12

    @staticmethod
    def _pastel_fill(color: QColor, tint: float) -> QColor:
        return QColor(
            round(255 - (255 - color.red()) * tint),
            round(255 - (255 - color.green()) * tint),
            round(255 - (255 - color.blue()) * tint),
        )

    def _record_scene_item_mutation(
        self,
        item,
        *,
        state_for: Callable[[object, object], dict],
        mutation: Callable[[], None],
        runtime_rollback: Callable[[], None] | None = None,
    ) -> None:
        before_state = state_for(self.canvas, item)
        rollback = UpdateSceneItemCommand(item, before_state, before_state)
        try:
            mutation()
            after_state = state_for(self.canvas, item)
            if before_state != after_state and self.history is not None:
                self._push_history_command(UpdateSceneItemCommand(item, before_state, after_state))
        except Exception:
            if runtime_rollback is not None:
                with contextlib.suppress(Exception):
                    runtime_rollback()
            else:
                self._rollback_commands([rollback])
            raise

    def _apply_shape_fill(self, item, color: QColor) -> None:
        self._record_scene_item_mutation(
            item,
            state_for=shape_state_dict_for,
            mutation=lambda: item.setBrush(self._pastel_fill(color, self.SHAPE_FILL_TINT)),
            runtime_rollback=self._graphics_runtime_rollback(item),
        )

    def apply_ring_fill_color(self, item, color: QColor, alpha: float = 0.25) -> None:
        if item is None or not color.isValid():
            return
        if item.data(0) != "ring":
            return
        # ``alpha`` is the pastel strength: 0 clears the fill, anything above
        # pre-dilutes the colour toward white and applies it opaque (the ring
        # sits behind the structure, so translucency is not needed).
        tint = max(0.0, min(1.0, float(alpha)))
        if tint <= 0.0:
            fill = QColor(color)
            fill.setAlphaF(0.0)
        else:
            fill = self._pastel_fill(color, tint)
        self._record_scene_item_mutation(
            item,
            state_for=ring_state_dict_for,
            mutation=lambda: item.setBrush(fill),
            runtime_rollback=self._graphics_runtime_rollback(item),
        )

    def apply_ring_fill_color_to_items(
        self,
        items: Iterable[object],
        color: QColor,
        alpha: float = 0.25,
    ) -> None:
        items = tuple(items)
        rollback = self._batch_runtime_rollback(items, expand_ring_structures=False)

        def apply_all() -> None:
            for item in items:
                self.apply_ring_fill_color(item, color, alpha)

        self._run_history_transaction(apply_all, rollback=rollback)

    def _run_history_transaction(
        self,
        mutation: Callable[[], None],
        *,
        rollback: Callable[[], None] | None = None,
    ) -> None:
        real_history = self.history
        collected: list[HistoryCommand] = []
        self.history = _CollectingHistory(collected.append)
        try:
            mutation()
        except BaseException as error:
            try:
                if rollback is not None:
                    rollback()
                else:
                    self._rollback_commands(collected)
            except BaseException as rollback_error:
                error.add_note(f"Color transaction rollback also failed: {rollback_error!r}")
            raise
        finally:
            self.history = real_history

        if not collected or real_history is None:
            return
        command = collected[0] if len(collected) == 1 else CompositeCommand(commands=collected)
        history_rollback = self._history_runtime_rollback(real_history)
        try:
            real_history.push(command)
        except BaseException as error:
            try:
                history_rollback()
            except BaseException as rollback_error:
                error.add_note(f"History stack rollback also failed: {rollback_error!r}")
            try:
                if rollback is not None:
                    rollback()
                else:
                    self._rollback_commands([command])
            except BaseException as rollback_error:
                error.add_note(f"Color transaction rollback also failed: {rollback_error!r}")
            raise

    def _rollback_commands(self, commands: Iterable[HistoryCommand]) -> None:
        for command in reversed(tuple(commands)):
            with contextlib.suppress(Exception):
                command.undo(self.canvas)

    def _push_history_command(self, command: HistoryCommand) -> None:
        if self.history is None:
            return
        restore_history = self._history_runtime_rollback(self.history)
        try:
            self.history.push(command)
        except BaseException as error:
            try:
                restore_history()
            except BaseException as rollback_error:
                error.add_note(f"History stack rollback also failed: {rollback_error!r}")
            raise

    @staticmethod
    def _history_runtime_rollback(history_service) -> Callable[[], None]:
        state = getattr(history_service, "state", None)
        history = getattr(state, "history", None)
        redo_stack = getattr(state, "redo_stack", None)
        if state is None or not isinstance(history, list) or not isinstance(redo_stack, list):
            return lambda: None
        history_items = list(history)
        redo_items = list(redo_stack)

        def restore() -> None:
            history[:] = history_items
            redo_stack[:] = redo_items
            state.history = history
            state.redo_stack = redo_stack
            notify_change = getattr(history_service, "notify_change", None)
            if callable(notify_change):
                with contextlib.suppress(Exception):
                    notify_change()

        return restore

    def _apply_note_color(self, item, color: QColor) -> None:
        before_runtime = _NoteColorState.capture(item)
        before_state = note_state_dict_for(self.canvas, item)
        committed_html_matches_runtime = before_runtime.committed_html == before_runtime.html

        def mutate() -> None:
            document = item.document()
            if document is None:
                return
            char_format = QTextCharFormat()
            char_format.setForeground(color)
            cursor = item.textCursor()
            if cursor.hasSelection():
                # Recolour only the text the user has selected, so a single note can
                # hold several colours. The selection is kept so it stays visible.
                cursor.mergeCharFormat(char_format)
                item.setTextCursor(cursor)
                return
            whole = QTextCursor(document)
            whole.select(QTextCursor.SelectionType.Document)
            whole.mergeCharFormat(char_format)
            item.setDefaultTextColor(color)

        try:
            mutate()
            # Formatting a fully committed note is itself the committed edit.
            # Keep the focus-out baseline in sync so the note controller does
            # not record the same colour change a second time later.  If the
            # note already contained uncommitted typing, leave its older
            # baseline alone so focus-out can still record that text edit.
            if committed_html_matches_runtime:
                set_committed_note_html_for(item, item.toHtml())
            after_state = note_state_dict_for(self.canvas, item)
            if before_state != after_state and self.history is not None:
                self._push_history_command(
                    UpdateNoteColorCommand(
                        item=item,
                        before_state=before_runtime,
                        after_state=_NoteColorState.capture(item),
                    )
                )
        except Exception:
            with contextlib.suppress(Exception):
                before_runtime.apply(item)
            raise

    def _apply_bond_color(self, item, color: QColor) -> None:
        bond_id = item.data(1)
        if not isinstance(bond_id, int):
            return
        bond = bond_for_id(self.canvas, bond_id)
        if bond is None:
            return
        before_color = bond.color
        rollback = self._bond_runtime_rollback(item)
        try:
            _apply_bond_color_in_place(self.canvas, bond_id, color)
            after_color = bond.color
            if before_color != after_color and self.history is not None:
                self._push_history_command(
                    UpdateBondColorCommand(
                        bond_id=bond_id,
                        before_color=before_color,
                        after_color=after_color,
                    )
                )
        except BaseException as error:
            try:
                rollback()
            except BaseException as rollback_error:
                error.add_note(f"Bond color rollback also failed: {rollback_error!r}")
            raise

    def _apply_atom_item_graphic(self, item, color: QColor) -> None:
        if isinstance(item, QGraphicsTextItem):
            item.setDefaultTextColor(color)
        elif isinstance(item, AtomDotItem):
            item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
        elif isinstance(item, QGraphicsEllipseItem):
            item.setBrush(color)

    def _apply_atom_color(self, item, color: QColor) -> None:
        atom_id = item.data(1)
        atom = atom_for_id(self.canvas, atom_id)
        if atom is None:
            self._apply_atom_item_graphic(item, color)
            return
        before_color = atom.color
        rollback = self._atom_runtime_rollback(item)
        try:
            self._apply_atom_item_graphic(item, color)
            atom.color = color.name()
            label_item = atom_items_for(self.canvas).get(atom_id)
            if label_item is not None and label_item is not item:
                label_item.setDefaultTextColor(color)
            dot_item = atom_dots_for(self.canvas).get(atom_id)
            if dot_item is not None and dot_item is not item:
                dot_item.setBrush(implicit_carbon_dot_brush_for(self.canvas))
            after_color = atom.color
            if before_color != after_color and self.history is not None:
                self._push_history_command(
                    UpdateAtomColorCommand(
                        atom_id=atom_id,
                        before_color=before_color,
                        after_color=after_color,
                    )
                )
        except BaseException as error:
            try:
                rollback()
            except BaseException as rollback_error:
                error.add_note(f"Atom color rollback also failed: {rollback_error!r}")
            raise

    def _apply_ring_structure_color(self, item, color: QColor) -> None:
        targets = self._ring_structure_targets(item)
        if not targets:
            return
        # A ring is itself one color transaction. This remains atomic when it is
        # nested inside a multi-selection transaction because the outer collector
        # captures this transaction's single command.
        self.apply_color_to_items(targets, color)

    def _ring_structure_targets(self, item) -> list[object]:
        ring_atom_ids = item.data(2)
        if not isinstance(ring_atom_ids, list):
            return []
        atom_ids = {
            atom_id
            for atom_id in ring_atom_ids
            if isinstance(atom_id, int) and atom_for_id(self.canvas, atom_id) is not None
        }
        if not atom_ids:
            return []
        bond_ids, _ = self.graph_service.bond_sets_for_atoms(atom_ids)
        targets: list[object] = []
        for atom_id in sorted(atom_ids):
            atom_item = visible_atom_item_for(self.canvas, atom_id)
            if atom_item is not None:
                targets.append(atom_item)
        for bond_id in sorted(bond_ids):
            bond_items = bond_items_for_id(self.canvas, bond_id)
            if bond_items:
                targets.append(bond_items[0])
        return targets

    def _graphics_runtime_rollback(self, item) -> Callable[[], None]:
        text_color = QColor(item.defaultTextColor()) if isinstance(item, QGraphicsTextItem) else None
        brush_method = getattr(item, "brush", None)
        brush = None
        if callable(brush_method):
            with contextlib.suppress(TypeError, RuntimeError):
                brush = QBrush(brush_method())
        pen_method = getattr(item, "pen", None)
        pen = None
        if callable(pen_method):
            with contextlib.suppress(TypeError, RuntimeError):
                pen = QPen(pen_method())

        def restore() -> None:
            if text_color is not None and isinstance(item, QGraphicsTextItem):
                QGraphicsTextItem.setDefaultTextColor(item, QColor(text_color))
            if pen is not None:
                _set_graphics_pen_exact(item, pen)
            if brush is not None:
                _set_graphics_brush_exact(item, brush)

        return restore

    def _note_runtime_rollback(self, item: QGraphicsTextItem) -> Callable[[], None]:
        state = _NoteColorState.capture(item)
        return lambda: state.apply(item)

    def _atom_runtime_rollback(self, item) -> Callable[[], None]:
        atom_id = item.data(1)
        atom = atom_for_id(self.canvas, atom_id)
        before_color = atom.color if atom is not None else None
        graphics_items = [item, atom_items_for(self.canvas).get(atom_id), atom_dots_for(self.canvas).get(atom_id)]
        restores = self._unique_graphics_restores(graphics_items)

        def restore() -> None:
            current_atom = atom_for_id(self.canvas, atom_id)
            if current_atom is not None and before_color is not None:
                current_atom.color = before_color
            for restore_graphics in restores:
                restore_graphics()

        return restore

    def _bond_runtime_rollback(self, item) -> Callable[[], None]:
        bond_id = item.data(1)
        bond = bond_for_id(self.canvas, bond_id)
        before_color = bond.color if bond is not None else None
        restores = self._unique_graphics_restores(bond_items_for_id(self.canvas, bond_id))

        def restore() -> None:
            current_bond = bond_for_id(self.canvas, bond_id)
            if current_bond is not None and before_color is not None:
                current_bond.color = before_color
            for restore_graphics in restores:
                restore_graphics()

        return restore

    def _unique_graphics_restores(self, items: Iterable[object | None]) -> list[Callable[[], None]]:
        restores: list[Callable[[], None]] = []
        seen_ids: set[int] = set()
        for item in items:
            if item is None or id(item) in seen_ids:
                continue
            seen_ids.add(id(item))
            restores.append(self._graphics_runtime_rollback(item))
        return restores

    def _batch_runtime_rollback(
        self,
        items: Iterable[object],
        *,
        expand_ring_structures: bool,
    ) -> Callable[[], None] | None:
        targets: list[object] = []
        for item in items:
            data_method = getattr(item, "data", None)
            kind = data_method(0) if callable(data_method) else None
            if expand_ring_structures and kind == "ring":
                targets.extend(self._ring_structure_targets(item))
            else:
                targets.append(item)

        restores: list[Callable[[], None]] = []
        seen_ids: set[int] = set()
        for item in targets:
            if item is None or id(item) in seen_ids:
                continue
            seen_ids.add(id(item))
            data_method = getattr(item, "data", None)
            kind = data_method(0) if callable(data_method) else None
            if kind not in {"atom", "bond", "note", "shape", "ring"}:
                # Keep the generic command-based transaction behavior for test
                # doubles and extension items whose runtime state this service
                # does not know how to snapshot exactly.
                return None
            if kind == "atom":
                restores.append(self._atom_runtime_rollback(item))
            elif kind == "bond":
                restores.append(self._bond_runtime_rollback(item))
            elif kind == "note" and isinstance(item, QGraphicsTextItem):
                restores.append(self._note_runtime_rollback(item))
            else:
                restores.append(self._graphics_runtime_rollback(item))

        def restore_all() -> None:
            for restore in reversed(restores):
                with contextlib.suppress(Exception):
                    restore()

        return restore_all


__all__ = [
    "CanvasColorMutationService",
    "UpdateBondColorCommand",
    "UpdateNoteColorCommand",
]
