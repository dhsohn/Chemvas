from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPen,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from chemvas.core.history import CompositeCommand, HistoryCommand
from chemvas.domain.transactions import HistoryAuthoritySnapshot
from chemvas.ui.canvas_scene_items_state import (
    remove_selected_note_for,
    selected_notes_for,
)
from chemvas.ui.canvas_text_style_state import text_style_state_for
from chemvas.ui.graphics_items import NoSelectRectItem
from chemvas.ui.history_commands import (
    AddSceneItemsCommand,
    DeleteSceneItemsCommand,
    UpdateSceneItemCommand,
    _restore_scene_runtime_snapshot,
    _run_rollback_step,
    _scene_runtime_snapshot,
    _SceneRuntimeSnapshot,
)
from chemvas.ui.input_view_access import (
    focus_canvas_for,
    focused_scene_item_for,
    set_focused_scene_item_for,
)
from chemvas.ui.note_item_access import (
    committed_note_html_for,
    committed_note_text_for,
    new_note_item_for,
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from chemvas.ui.note_selection_box import update_note_selection_box_for
from chemvas.ui.scene_item_access import attach_scene_item, remove_scene_item
from chemvas.ui.scene_item_state import note_state_dict_for
from chemvas.ui.selection_service_access import (
    refresh_selection_outline_for,
    selection_service_from_canvas,
)
from chemvas.ui.transactions.scene_item_attach import SceneItemAttachSnapshot
from chemvas.ui.transactions.scene_rect import SceneRectSnapshot

_MISSING_CAPTURE_ATTRIBUTE = object()


def _capture_optional_attribute(target: object, name: str) -> object:
    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_CAPTURE_ATTRIBUTE)
            is not _MISSING_CAPTURE_ATTRIBUTE
        ):
            raise
        return _MISSING_CAPTURE_ATTRIBUTE


def _call_required_rollback_method(target: object, name: str, *args) -> object:
    method = getattr(target, name)
    if not callable(method):
        raise TypeError(f"Rollback port {name!r} is not callable")
    return method(*args)


def _call_optional_rollback_method(target: object, name: str, *args) -> object | None:
    method = _capture_optional_attribute(target, name)
    if method is _MISSING_CAPTURE_ATTRIBUTE or not callable(method):
        return None
    return method(*args)


@dataclass(slots=True)
class _NoteMutationSnapshot:
    item: QGraphicsTextItem
    before_state: dict
    committed_text: str
    committed_html: str
    interaction_flags: Qt.TextInteractionFlag


@dataclass(slots=True)
class _NoteBoxSnapshot:
    role: int
    box: QGraphicsRectItem | None
    rect: QRectF | None
    pen: QPen | None
    brush: QBrush | None
    visible: bool | None

    @classmethod
    def capture(cls, item: QGraphicsTextItem, role: int) -> _NoteBoxSnapshot:
        box = item.data(role)
        if not isinstance(box, QGraphicsRectItem):
            return cls(role, None, None, None, None, None)
        return cls(
            role=role,
            box=box,
            rect=box.rect(),
            pen=box.pen(),
            brush=box.brush(),
            visible=box.isVisible(),
        )


@dataclass(slots=True)
class _EditingNoteSnapshot:
    item: QGraphicsTextItem
    html: str
    committed_text: str
    committed_html: str
    interaction_flags: Qt.TextInteractionFlag
    cursor_anchor: int
    cursor_position: int
    scene: object | None
    focus_item: object | None
    boxes: tuple[_NoteBoxSnapshot, ...]

    @classmethod
    def capture(cls, item: QGraphicsTextItem) -> _EditingNoteSnapshot:
        cursor = item.textCursor()
        scene = item.scene()
        focus_item_getter = _capture_optional_attribute(scene, "focusItem")
        return cls(
            item=item,
            html=item.toHtml(),
            committed_text=committed_note_text_for(item),
            committed_html=committed_note_html_for(item),
            interaction_flags=item.textInteractionFlags(),
            cursor_anchor=cursor.anchor(),
            cursor_position=cursor.position(),
            scene=scene,
            focus_item=focus_item_getter() if callable(focus_item_getter) else None,
            boxes=(
                _NoteBoxSnapshot.capture(item, 20),
                _NoteBoxSnapshot.capture(item, 21),
            ),
        )


@dataclass(slots=True)
class _NoteSceneRectTransaction:
    snapshot: SceneRectSnapshot | None
    items_bounding_rect: Callable[[], QRectF] | None

    @classmethod
    def capture(cls, scene: object | None) -> _NoteSceneRectTransaction:
        items_bounding_rect = _capture_optional_attribute(
            scene,
            "itemsBoundingRect",
        )
        bound_items_bounding_rect = (
            items_bounding_rect if callable(items_bounding_rect) else None
        )
        # SceneRectSnapshot temporarily fixes an automatic Qt scene. Open it
        # only after the bounds port and every note snapshot are safely owned.
        snapshot = SceneRectSnapshot.capture(scene)
        return cls(snapshot, bound_items_bounding_rect)

    def release(self) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        expanded_rect = None
        if snapshot.automatic:
            items_bounding_rect = self.items_bounding_rect
            if not callable(items_bounding_rect):
                raise AttributeError(
                    "Automatic note-formatting scene requires itemsBoundingRect"
                )
            expanded_rect = QRectF(items_bounding_rect())
        snapshot.release(expanded_rect)

    def restore(self, original_error: BaseException) -> None:
        snapshot = self.snapshot
        if snapshot is None:
            return
        prior_recovery_count = len(snapshot.recovery_errors)
        _run_rollback_step(
            original_error,
            "restoring the note-formatting scene rect",
            snapshot.restore,
        )
        if not snapshot.active:
            for recovery_error in snapshot.recovery_errors[prior_recovery_count:]:

                def report_recovered_error(
                    error: BaseException = recovery_error,
                ) -> None:
                    raise error

                _run_rollback_step(
                    original_error,
                    "restoring the note-formatting scene rect",
                    report_recovered_error,
                )
        if snapshot.active:
            prior_recovery_count = len(snapshot.recovery_errors)
            _run_rollback_step(
                original_error,
                "retrying the note-formatting scene-rect restore",
                snapshot.restore,
            )
            if not snapshot.active:
                for recovery_error in snapshot.recovery_errors[prior_recovery_count:]:

                    def report_retry_recovery(
                        error: BaseException = recovery_error,
                    ) -> None:
                        raise error

                    _run_rollback_step(
                        original_error,
                        "retrying the note-formatting scene-rect restore",
                        report_retry_recovery,
                    )


class CanvasNoteController:
    def __init__(
        self, canvas, *, selection_controller=None, history_service=None
    ) -> None:
        self.canvas = canvas
        self.history = history_service
        self.selection_controller = selection_controller

    def _selection_controller(self):
        if self.selection_controller is not None:
            return self.selection_controller
        try:
            return selection_service_from_canvas(self.canvas)
        except AttributeError:
            return None

    def create_text_note(self, pos: QPointF, text: str) -> QGraphicsTextItem:
        item = new_note_item_for(self.canvas)
        item.setPlainText(text)
        set_committed_note_text_for(item, text)
        item.setData(0, "note")
        item.setPos(pos)
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        item_snapshot = SceneItemAttachSnapshot.capture(self.canvas, item)
        try:
            attach_scene_item(self.canvas, item)
            self.apply_note_style(item)
            set_committed_note_html_for(item, item.toHtml())
            item_snapshot.release()
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "removing a partially created note",
                partial(remove_scene_item, self.canvas, item),
            )
            item_snapshot.restore(original_error, phase="failed note creation")
            for phase, rollback in self._restore_note_commit_metadata(
                item,
                committed_text=committed_text,
                committed_html=committed_html,
            ):
                _run_rollback_step(original_error, phase, rollback)
            raise
        return item

    def _end_note_editing(self, item: QGraphicsTextItem) -> None:
        """Leave edit mode: drop the text cursor selection (so a double-click
        highlight does not linger) and stop accepting editor input."""
        cursor = item.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            item.setTextCursor(cursor)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def _deselect_note(self, item: QGraphicsTextItem) -> None:
        if item in selected_notes_for(self.canvas):
            # Route through the note service so notes-only groups deselect as a
            # unit and the group box outline refreshes; a direct state removal
            # would strand the grouped companions in the selection.
            toggle_note_selection = getattr(
                self._selection_controller(), "toggle_note_selection", None
            )
            if callable(toggle_note_selection):
                toggle_note_selection(item)
                return
            remove_selected_note_for(self.canvas, item)
        update_note_selection_box_for(self.canvas, item)

    def _push_history_or_rollback(
        self,
        command: HistoryCommand,
        *,
        after_push: Callable[[], None] | None = None,
        runtime_rollback: _SceneRuntimeSnapshot | None = None,
        rollback_steps: tuple[tuple[str, Callable[[], object]], ...] = (),
    ) -> None:
        history_snapshot: HistoryAuthoritySnapshot | None = None
        try:
            history_snapshot = HistoryAuthoritySnapshot.capture(self.history)
            self.history.push(command)
            if after_push is not None:
                after_push()
        except BaseException as original_error:
            _run_rollback_step(
                original_error,
                "undoing a note command after its history push failed",
                partial(
                    _call_required_rollback_method,
                    command,
                    "undo",
                    self.canvas,
                ),
            )
            if runtime_rollback is not None:
                self._restore_scene_runtime_step(runtime_rollback, original_error)
            for phase, rollback in rollback_steps:
                _run_rollback_step(original_error, phase, rollback)
            if history_snapshot is not None:
                history_snapshot.restore(original_error, phase="note mutation")
            raise

    def _restore_note_mutation_snapshots(
        self,
        snapshots: list[_NoteMutationSnapshot],
        original_error: BaseException,
    ) -> None:
        for snapshot in reversed(snapshots):

            def restore_note_state(
                snapshot_to_restore: _NoteMutationSnapshot = snapshot,
            ) -> None:
                command = UpdateSceneItemCommand(
                    snapshot_to_restore.item,
                    snapshot_to_restore.before_state,
                    snapshot_to_restore.before_state,
                )
                _call_required_rollback_method(
                    command,
                    "undo",
                    self.canvas,
                )

            _run_rollback_step(
                original_error,
                "restoring a note after a batch formatting failure",
                restore_note_state,
            )
            for phase, rollback in self._restore_note_commit_metadata(
                snapshot.item,
                committed_text=snapshot.committed_text,
                committed_html=snapshot.committed_html,
            ):
                _run_rollback_step(original_error, phase, rollback)
            _run_rollback_step(
                original_error,
                "restoring a batch-formatted note's interaction flags",
                partial(
                    _call_required_rollback_method,
                    snapshot.item,
                    "setTextInteractionFlags",
                    snapshot.interaction_flags,
                ),
            )

    def _restore_editing_note_snapshot(
        self,
        snapshot: _EditingNoteSnapshot,
        original_error: BaseException,
    ) -> None:
        item = snapshot.item

        def restore_html() -> None:
            document = item.document()
            assert document is not None
            signals_blocked = document.signalsBlocked()

            def restore_signal_state(primary_error: BaseException) -> None:
                try:
                    document.blockSignals(signals_blocked)
                except BaseException as secondary_error:
                    try:
                        add_note = getattr(primary_error, "add_note", None)
                        if callable(add_note):
                            add_note(
                                "Editing-note signal-state restore also encountered "
                                f"{type(secondary_error).__name__}: {secondary_error}"
                            )
                    except BaseException:
                        pass

            try:
                document.blockSignals(True)
            except BaseException as block_error:
                restore_signal_state(block_error)
                try:
                    QGraphicsTextItem.setHtml(item, snapshot.html)
                except BaseException as html_error:
                    try:
                        add_note = getattr(block_error, "add_note", None)
                        if callable(add_note):
                            add_note(
                                "Unblocked editing-note HTML restore also encountered "
                                f"{type(html_error).__name__}: {html_error}"
                            )
                    except BaseException:
                        pass
                raise
            try:
                QGraphicsTextItem.setHtml(item, snapshot.html)
            except BaseException as html_error:
                restore_signal_state(html_error)
                raise
            else:
                try:
                    document.blockSignals(signals_blocked)
                except BaseException as signal_restore_error:
                    restore_signal_state(signal_restore_error)
                    raise

        _run_rollback_step(
            original_error,
            "restoring editing-note HTML after a formatting failure",
            restore_html,
        )
        for phase, rollback in self._restore_note_commit_metadata(
            item,
            committed_text=snapshot.committed_text,
            committed_html=snapshot.committed_html,
        ):
            _run_rollback_step(original_error, phase, rollback)
        _run_rollback_step(
            original_error,
            "restoring editing-note interaction flags",
            partial(
                _call_required_rollback_method,
                item,
                "setTextInteractionFlags",
                snapshot.interaction_flags,
            ),
        )

        for box_snapshot in snapshot.boxes:
            current = _run_rollback_step(
                original_error,
                "reading a note-box reference during rollback",
                partial(
                    _call_required_rollback_method,
                    item,
                    "data",
                    box_snapshot.role,
                ),
            )
            if box_snapshot.box is None:
                if isinstance(current, QGraphicsRectItem):
                    _run_rollback_step(
                        original_error,
                        "removing a new note box after formatting failure",
                        partial(
                            _call_required_rollback_method,
                            current,
                            "setParentItem",
                            None,
                        ),
                    )
                    current_scene = _run_rollback_step(
                        original_error,
                        "reading a new note box's scene during rollback",
                        partial(
                            _call_required_rollback_method,
                            current,
                            "scene",
                        ),
                    )
                    if current_scene is not None:
                        _run_rollback_step(
                            original_error,
                            "detaching a new note box after formatting failure",
                            partial(
                                _call_required_rollback_method,
                                current_scene,
                                "removeItem",
                                current,
                            ),
                        )
                _run_rollback_step(
                    original_error,
                    "clearing a new note-box reference",
                    partial(
                        _call_required_rollback_method,
                        item,
                        "setData",
                        box_snapshot.role,
                        None,
                    ),
                )
                continue
            box = box_snapshot.box
            operations: list[tuple[str, str, object]] = []
            if box_snapshot.rect is not None:
                operations.append(("rect", "setRect", box_snapshot.rect))
            if box_snapshot.pen is not None:
                operations.append(("pen", "setPen", box_snapshot.pen))
            if box_snapshot.brush is not None:
                operations.append(("brush", "setBrush", box_snapshot.brush))
            if box_snapshot.visible is not None:
                operations.append(("visibility", "setVisible", box_snapshot.visible))
            for phase, method_name, value in operations:
                _run_rollback_step(
                    original_error,
                    f"restoring note-box {phase}",
                    partial(
                        _call_required_rollback_method,
                        box,
                        method_name,
                        value,
                    ),
                )
            _run_rollback_step(
                original_error,
                "restoring note-box identity",
                partial(
                    _call_required_rollback_method,
                    item,
                    "setData",
                    box_snapshot.role,
                    box,
                ),
            )
        _run_rollback_step(
            original_error,
            "restoring editing-note focus",
            partial(
                _call_optional_rollback_method,
                snapshot.scene,
                "setFocusItem",
                snapshot.focus_item,
            ),
        )

        # Focus restoration can rewrite the QTextCursor selection. Reapply the
        # exact anchor/position last so selection direction is authoritative.
        def restore_cursor() -> None:
            document = item.document()
            assert document is not None
            restored = QTextCursor(document)
            restored.setPosition(snapshot.cursor_anchor)
            restored.setPosition(
                snapshot.cursor_position,
                QTextCursor.MoveMode.KeepAnchor,
            )
            item.setTextCursor(restored)

        _run_rollback_step(
            original_error,
            "restoring editing-note cursor selection",
            restore_cursor,
        )

    def _restore_note_commit_metadata(
        self,
        item: QGraphicsTextItem,
        *,
        committed_text: str,
        committed_html: str,
    ) -> tuple[tuple[str, Callable[[], object]], ...]:
        return (
            (
                "restoring committed note text",
                partial(set_committed_note_text_for, item, committed_text),
            ),
            (
                "restoring committed note HTML",
                partial(set_committed_note_html_for, item, committed_html),
            ),
        )

    def _restore_scene_runtime_step(
        self,
        snapshot: _SceneRuntimeSnapshot,
        original_error: BaseException,
    ) -> None:
        _run_rollback_step(
            original_error,
            "restoring exact note scene/runtime state",
            partial(
                _restore_scene_runtime_snapshot,
                snapshot,
                original_error=original_error,
            ),
        )

    def _deselect_note_atomically(self, item: QGraphicsTextItem) -> None:
        runtime_snapshot = _scene_runtime_snapshot(self.canvas, strict=True)
        try:
            self._deselect_note(item)
        except BaseException as original_error:
            self._restore_scene_runtime_step(runtime_snapshot, original_error)
            raise

    def _remove_note_atomically(
        self,
        item: QGraphicsTextItem,
    ) -> _SceneRuntimeSnapshot:
        runtime_snapshot = _scene_runtime_snapshot(self.canvas, strict=True)
        try:
            self._deselect_note(item)
            remove_scene_item(self.canvas, item)
            refresh_selection_outline_for(self.canvas)
        except BaseException as original_error:
            self._restore_scene_runtime_step(runtime_snapshot, original_error)
            raise
        return runtime_snapshot

    def handle_note_focus_out(self, item: QGraphicsTextItem) -> None:
        self._end_note_editing(item)
        text = item.toPlainText().strip()
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        current_html = item.toHtml()
        html_changed = bool(committed_html) and current_html != committed_html
        if text:
            if text != committed_text or html_changed:
                after_state = note_state_dict_for(self.canvas, item)
                if not committed_text:
                    command: HistoryCommand = AddSceneItemsCommand(
                        item_states=[after_state],
                        items=[item],
                    )
                else:
                    before_state = note_state_dict_for(self.canvas, item)
                    before_state["text"] = committed_text
                    before_state["html"] = committed_html
                    command = UpdateSceneItemCommand(item, before_state, after_state)

                def commit_note_metadata() -> None:
                    set_committed_note_text_for(item, text)
                    set_committed_note_html_for(item, current_html)

                self._push_history_or_rollback(
                    command,
                    after_push=commit_note_metadata,
                    rollback_steps=self._restore_note_commit_metadata(
                        item,
                        committed_text=committed_text,
                        committed_html=committed_html,
                    ),
                )
            # Clicking away from the text ends the selection too, so the dashed box
            # disappears instead of lingering after focus moves elsewhere.
            self._deselect_note_atomically(item)
            return
        if committed_text:
            before_state = note_state_dict_for(self.canvas, item)
            before_state["text"] = committed_text
            before_state["html"] = committed_html
            # Deselect before removal so grouped companion notes drop with it,
            # then refresh again after removal: a mixed group's box is spanned
            # by attached members, so the pre-removal refresh still covered
            # this note and the lifecycle refresh skips already-deselected
            # notes.
            runtime_snapshot = self._remove_note_atomically(item)

            def clear_note_metadata() -> None:
                set_committed_note_text_for(item, "")
                set_committed_note_html_for(item, "")

            self._push_history_or_rollback(
                DeleteSceneItemsCommand(
                    item_states=[before_state],
                    items=[item],
                ),
                after_push=clear_note_metadata,
                runtime_rollback=runtime_snapshot,
                rollback_steps=(
                    *self._restore_note_commit_metadata(
                        item,
                        committed_text=committed_text,
                        committed_html=committed_html,
                    ),
                ),
            )
            return
        self._remove_note_atomically(item)

    def update_text_note(self, item: QGraphicsTextItem, text: str) -> None:
        item.setPlainText(text)
        self.apply_note_style(item)

    def _ensure_note_box_autoresize(self, item: QGraphicsTextItem) -> None:
        """Keep the background/selection boxes sized to the text while it is typed.

        The boxes are derived from ``item.boundingRect()`` but were only refreshed
        on formatting commands, so plain typing left them at their initial width.
        Connecting once to the document's ``contentsChanged`` resizes them live.
        """
        if item.data(22):
            return
        document = item.document()
        if document is None:
            return

        def _resize() -> None:
            self.update_note_box(item)
            update_note_selection_box_for(self.canvas, item)

        document.contentsChanged.connect(_resize)
        item.setData(22, True)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        if item not in selected_notes_for(self.canvas):
            selection_controller = self._selection_controller()
            if selection_controller is not None:
                selection_controller.select_note(item, additive=False)
        self._ensure_note_box_autoresize(item)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        focus_canvas_for(self.canvas, Qt.FocusReason.MouseFocusReason)
        item.setFocus(Qt.FocusReason.MouseFocusReason)
        set_focused_scene_item_for(self.canvas, item)
        cursor = item.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        item.setTextCursor(cursor)

    def _editing_note(self) -> QGraphicsTextItem | None:
        item = focused_scene_item_for(self.canvas)
        if isinstance(item, QGraphicsTextItem) and item.data(0) == "note":
            return item
        return None

    def _merge_editing_char_format(self, mutate) -> None:
        item = self._editing_note()
        if item is None:
            return
        cursor = item.textCursor()
        fmt = QTextCharFormat()
        mutate(cursor.charFormat(), fmt)
        cursor.mergeCharFormat(fmt)
        item.setTextCursor(cursor)
        self.update_note_box(item)
        update_note_selection_box_for(self.canvas, item)

    def toggle_text_bold(self) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            is_bold = current.fontWeight() > QFont.Weight.Normal
            fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)

        self._merge_editing_char_format(mutate)

    def toggle_text_italic(self) -> None:
        self._merge_editing_char_format(
            lambda current, fmt: fmt.setFontItalic(not current.fontItalic())
        )

    def toggle_text_superscript(self) -> None:
        self._toggle_vertical_alignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript
        )

    def toggle_text_subscript(self) -> None:
        self._toggle_vertical_alignment(
            QTextCharFormat.VerticalAlignment.AlignSubScript
        )

    def _toggle_vertical_alignment(
        self, alignment: QTextCharFormat.VerticalAlignment
    ) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            if current.verticalAlignment() == alignment:
                fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
            else:
                fmt.setVerticalAlignment(alignment)

        self._merge_editing_char_format(mutate)

    def adjust_text_size(self, delta: int) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            size = current.fontPointSize()
            if size <= 0:
                size = float(text_style_state_for(self.canvas).text_font_size)
            fmt.setFontPointSize(max(6.0, min(96.0, size + delta)))

        self._merge_editing_char_format(mutate)

    def set_text_font_family(self, family: str) -> None:
        def mutate(item: QGraphicsTextItem) -> None:
            cursor = QTextCursor(item.document())
            cursor.select(QTextCursor.SelectionType.Document)
            char_format = QTextCharFormat()
            char_format.setFontFamilies([family])
            cursor.mergeCharFormat(char_format)

        self._apply_to_target_notes(mutate)

    def set_text_alignment(self, alignment: str) -> None:
        qt_alignment = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(alignment, Qt.AlignmentFlag.AlignLeft)

        def mutate(item: QGraphicsTextItem) -> None:
            cursor = QTextCursor(item.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            block_format.setAlignment(qt_alignment)
            cursor.mergeBlockFormat(block_format)

        self._apply_to_target_notes(mutate)

    def _scene_for_note_formatting(
        self,
        snapshots: list[_NoteMutationSnapshot],
    ) -> object | None:
        scene_getter = _capture_optional_attribute(self.canvas, "scene")
        if callable(scene_getter):
            return scene_getter()
        if not snapshots:
            return None
        item_scene = _capture_optional_attribute(snapshots[0].item, "scene")
        return item_scene() if callable(item_scene) else None

    def _apply_to_target_notes(self, mutate) -> None:
        editing = self._editing_note()
        if editing is not None:
            editing_snapshot = _EditingNoteSnapshot.capture(editing)
            rect_transaction = _NoteSceneRectTransaction.capture(editing_snapshot.scene)
            try:
                mutate(editing)
                self.update_note_box(editing)
                update_note_selection_box_for(self.canvas, editing)
                rect_transaction.release()
            except BaseException as original_error:
                self._restore_editing_note_snapshot(editing_snapshot, original_error)
                rect_transaction.restore(original_error)
                raise
            return
        # Capture every input before the first mutation. In particular, a
        # serializer or committed-metadata accessor for item N must not be able
        # to strand already-formatted items 0..N-1 without history.
        snapshots = [
            _NoteMutationSnapshot(
                item=item,
                before_state=note_state_dict_for(self.canvas, item),
                committed_text=committed_note_text_for(item),
                committed_html=committed_note_html_for(item),
                interaction_flags=item.textInteractionFlags(),
            )
            for item in list(selected_notes_for(self.canvas))
        ]
        if not snapshots:
            return
        scene = self._scene_for_note_formatting(snapshots)
        rect_transaction = _NoteSceneRectTransaction.capture(scene)
        commands: list[UpdateSceneItemCommand] = []
        changed_snapshots: list[_NoteMutationSnapshot] = []
        attempted_snapshots: list[_NoteMutationSnapshot] = []
        try:
            for batch_snapshot in snapshots:
                item = batch_snapshot.item
                attempted_snapshots.append(batch_snapshot)
                mutate(item)
                self.update_note_box(item)
                update_note_selection_box_for(self.canvas, item)
                after_state = note_state_dict_for(self.canvas, item)
                if batch_snapshot.before_state != after_state:
                    commands.append(
                        UpdateSceneItemCommand(
                            item,
                            batch_snapshot.before_state,
                            after_state,
                        )
                    )
                    changed_snapshots.append(batch_snapshot)
            if not commands or self.history is None:
                rect_transaction.release()
                return
            command: HistoryCommand
            if len(commands) == 1:
                command = commands[0]
            else:
                command = CompositeCommand(list(commands))

            def commit_note_html_and_scene_rect() -> None:
                for snapshot in changed_snapshots:
                    set_committed_note_html_for(
                        snapshot.item,
                        snapshot.item.toHtml(),
                    )
                # Finalize while the history savepoint still owns the pushed
                # command. A failing finalizer then rolls back both the notes
                # and append-then-raise history mutation before rect recovery.
                rect_transaction.release()

            rollback_metadata = tuple(
                rollback
                for snapshot in changed_snapshots
                for rollback in self._restore_note_commit_metadata(
                    snapshot.item,
                    committed_text=snapshot.committed_text,
                    committed_html=snapshot.committed_html,
                )
            )
            rollback_interaction_flags = tuple(
                (
                    "restoring a batch-formatted note's interaction flags",
                    partial(
                        snapshot.item.setTextInteractionFlags,
                        snapshot.interaction_flags,
                    ),
                )
                for snapshot in changed_snapshots
            )
            self._push_history_or_rollback(
                command,
                after_push=commit_note_html_and_scene_rect,
                rollback_steps=(
                    *rollback_metadata,
                    *rollback_interaction_flags,
                ),
            )
        except BaseException as original_error:
            self._restore_note_mutation_snapshots(
                attempted_snapshots,
                original_error,
            )
            # Scene rect is deliberately last: note state, boxes, metadata,
            # interaction flags, and history may all expose temporary far
            # geometry while they are being restored.
            rect_transaction.restore(original_error)
            raise

    def apply_text_style_to_selected(self) -> None:
        for item in selected_notes_for(self.canvas):
            self.apply_note_style(item)

    def apply_note_style(self, item: QGraphicsTextItem) -> None:
        style = text_style_state_for(self.canvas)
        font = QFont(style.text_font_family, style.text_font_size)
        font.setWeight(style.text_font_weight)
        font.setItalic(style.text_italic)
        item.setFont(font)
        item.setDefaultTextColor(style.text_color)
        doc = item.document()
        if doc is None:
            return
        option = doc.defaultTextOption()
        option.setAlignment(style.text_alignment)
        doc.setDefaultTextOption(option)
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        line_height_type = getattr(QTextBlockFormat, "LineHeightType", None)
        if line_height_type is not None and hasattr(
            line_height_type, "ProportionalHeight"
        ):
            height_type = line_height_type.ProportionalHeight
        else:
            height_type = QTextBlockFormat.LineHeightTypes.ProportionalHeight
            if hasattr(height_type, "value"):
                height_type = height_type.value
        block_format.setLineHeight(int(style.text_line_spacing * 100), height_type)
        cursor.mergeBlockFormat(block_format)
        self.update_note_box(item)
        update_note_selection_box_for(self.canvas, item)

    def update_note_box(self, item: QGraphicsTextItem) -> None:
        style = text_style_state_for(self.canvas)
        box = item.data(20)
        rect = item.boundingRect().adjusted(
            -style.note_padding,
            -style.note_padding,
            style.note_padding,
            style.note_padding,
        )
        if not (style.note_box_enabled or style.note_border_enabled):
            if isinstance(box, QGraphicsRectItem):
                box.setVisible(False)
            return
        if not isinstance(box, QGraphicsRectItem):
            box = NoSelectRectItem(item)
            box.setData(0, "note_box")
            box.setZValue(-1)
            item.setData(20, box)
        box.setVisible(True)
        box.setRect(rect)
        if style.note_box_enabled:
            fill = QColor(style.note_box_color)
            fill.setAlphaF(style.note_box_alpha)
            box.setBrush(fill)
        else:
            box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if style.note_border_enabled:
            pen = QPen(style.note_border_color)
            pen.setWidthF(style.note_border_width)
            box.setPen(pen)
        else:
            box.setPen(QPen(Qt.PenStyle.NoPen))


__all__ = ["CanvasNoteController"]
