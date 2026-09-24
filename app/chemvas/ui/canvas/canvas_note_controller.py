from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontInfo,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsTextItem

from chemvas.core.history import (
    CompositeCommand,
    HistoryCommand,
)
from chemvas.domain.transactions import run_rollback_step
from chemvas.ui.annotations.state import note_state_dict_for
from chemvas.ui.annotations.text import (
    apply_note_appearance,
    apply_note_style,
    update_note_box,
)
from chemvas.ui.canvas.canvas_note_snapshots import (
    _call_optional_rollback_method,
    _call_required_rollback_method,
    _EditingNoteSnapshot,
    _NoteMutationSnapshot,
    _NoteSceneRectTransaction,
)
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.canvas.canvas_window_access import notify_document_change_for
from chemvas.ui.canvas.input_view_access import (
    _capture_optional_attribute,
    focused_scene_item_for,
    set_focused_scene_item_for,
)
from chemvas.ui.history.history_commands import (
    AddSceneItemsCommand,
    DeleteSceneItemsCommand,
    SetAnnotationStyleCommand,
    UpdateSceneItemCommand,
)
from chemvas.ui.scene.note_item_access import (
    NoteTextState,
    committed_note_html_for,
    committed_note_text_for,
    new_note_item_for,
    set_committed_note_html_for,
    set_committed_note_text_for,
)
from chemvas.ui.scene.scene_item_access import remove_scene_item
from chemvas.ui.selection.selection_queries import selected_scene_items_for
from chemvas.ui.transactions.scene_item_attach import SceneItemAttachSnapshot
from chemvas.ui.transactions.scene_runtime import (
    SceneRuntimeSnapshot,
    capture_scene_runtime,
)
from chemvas.ui.transactions.scene_runtime_restore import restore_scene_runtime

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.ui.canvas.canvas_history_service import HistoryStackSnapshot


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
            return self.canvas.services.selection
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
            self.canvas.services.scene_item_controller.attach_scene_item(item)
            self.apply_note_style(item)
            set_committed_note_html_for(item, item.toHtml())
            item_snapshot.release()
        except Exception as original_error:
            run_rollback_step(
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
                run_rollback_step(original_error, phase, rollback)
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

    def finish_note_edit(self) -> None:
        item = self._editing_note()
        if item is not None:
            # NoteItem.focusOutEvent owns the existing commit/delete path.
            item.clearFocus()

    def _deselect_note(self, item: QGraphicsTextItem) -> None:
        if item in self.canvas.runtime_state.selection_state.selected_notes:
            # Route through the selection owner so notes-only groups deselect as a
            # unit and the group box outline refreshes; a direct state removal
            # would strand the grouped companions in the selection.
            toggle_note_selection = getattr(
                self._selection_controller(), "toggle_note_selection", None
            )
            if callable(toggle_note_selection):
                toggle_note_selection(item)
                return
            self.canvas.runtime_state.selection_state.remove_selected_note(item)
        self.canvas.services.selection.update_note_selection_box(item)

    def _push_history_or_rollback(
        self,
        command: HistoryCommand,
        *,
        after_push: Callable[[], None] | None = None,
        runtime_rollback: SceneRuntimeSnapshot | None = None,
        rollback_steps: tuple[tuple[str, Callable[[], object]], ...] = (),
    ) -> None:
        history_snapshot: HistoryStackSnapshot | None = None
        try:
            history_snapshot = self.history.capture_stack_snapshot()
            if self.history.push(command) is False and history_snapshot.enabled:
                raise RuntimeError("note history publication was declined")
            if after_push is not None:
                after_push()
        except Exception as original_error:
            run_rollback_step(
                original_error,
                "undoing a note command after its history push failed",
                partial(
                    _call_required_rollback_method,
                    command,
                    "undo",
                    self.history.operations,
                ),
            )
            if runtime_rollback is not None:
                self._restore_scene_runtime_step(runtime_rollback, original_error)
            for phase, rollback in rollback_steps:
                run_rollback_step(original_error, phase, rollback)
            if history_snapshot is not None:
                self.history.restore_stack_snapshot(
                    history_snapshot,
                    original_error,
                    phase="note mutation",
                )
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
                    require_scene_record_id(snapshot_to_restore.item),
                    snapshot_to_restore.before_state,
                    snapshot_to_restore.before_state,
                )
                _call_required_rollback_method(
                    command,
                    "undo",
                    self.history.operations,
                )

            run_rollback_step(
                original_error,
                "restoring a note after a batch formatting failure",
                restore_note_state,
            )
            for phase, rollback in self._restore_note_commit_metadata(
                snapshot.item,
                committed_text=snapshot.committed_text,
                committed_html=snapshot.committed_html,
            ):
                run_rollback_step(original_error, phase, rollback)
            run_rollback_step(
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

            # The Qt methods are looked up inside these bodies rather than bound
            # through a ``partial`` argument, so a document or item that no
            # longer offers them becomes a note instead of an AttributeError
            # that escapes the rollback step and masks the primary failure.
            def restore_blocked_signals() -> None:
                document.blockSignals(signals_blocked)

            def restore_snapshot_html() -> None:
                item.setHtml(snapshot.html)

            try:
                document.blockSignals(True)
            except Exception as block_error:
                run_rollback_step(
                    block_error,
                    "restoring an editing note's document signal state",
                    restore_blocked_signals,
                )
                run_rollback_step(
                    block_error,
                    "restoring editing-note HTML without signal blocking",
                    restore_snapshot_html,
                )
                raise
            try:
                item.setHtml(snapshot.html)
            except Exception as html_error:
                run_rollback_step(
                    html_error,
                    "restoring an editing note's document signal state",
                    restore_blocked_signals,
                )
                raise
            else:
                try:
                    document.blockSignals(signals_blocked)
                except Exception as signal_restore_error:
                    run_rollback_step(
                        signal_restore_error,
                        "restoring an editing note's document signal state",
                        restore_blocked_signals,
                    )
                    raise

        run_rollback_step(
            original_error,
            "restoring editing-note HTML after a formatting failure",
            restore_html,
        )
        for phase, rollback in self._restore_note_commit_metadata(
            item,
            committed_text=snapshot.committed_text,
            committed_html=snapshot.committed_html,
        ):
            run_rollback_step(original_error, phase, rollback)
        run_rollback_step(
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
            current = run_rollback_step(
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
                    run_rollback_step(
                        original_error,
                        "removing a new note box after formatting failure",
                        partial(
                            _call_required_rollback_method,
                            current,
                            "setParentItem",
                            None,
                        ),
                    )
                    current_scene = run_rollback_step(
                        original_error,
                        "reading a new note box's scene during rollback",
                        partial(
                            _call_required_rollback_method,
                            current,
                            "scene",
                        ),
                    )
                    if current_scene is not None:
                        run_rollback_step(
                            original_error,
                            "detaching a new note box after formatting failure",
                            partial(
                                _call_required_rollback_method,
                                current_scene,
                                "removeItem",
                                current,
                            ),
                        )
                run_rollback_step(
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
                run_rollback_step(
                    original_error,
                    f"restoring note-box {phase}",
                    partial(
                        _call_required_rollback_method,
                        box,
                        method_name,
                        value,
                    ),
                )
            run_rollback_step(
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
        run_rollback_step(
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

        run_rollback_step(
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
        snapshot: SceneRuntimeSnapshot,
        original_error: BaseException,
    ) -> None:
        run_rollback_step(
            original_error,
            "restoring exact note scene/runtime state",
            partial(
                restore_scene_runtime,
                snapshot,
                original_error=original_error,
            ),
        )

    def _deselect_note_atomically(self, item: QGraphicsTextItem) -> None:
        runtime_snapshot = capture_scene_runtime(self.canvas)
        try:
            self._deselect_note(item)
        except Exception as original_error:
            self._restore_scene_runtime_step(runtime_snapshot, original_error)
            raise

    def _remove_note_atomically(
        self,
        item: QGraphicsTextItem,
    ) -> SceneRuntimeSnapshot:
        runtime_snapshot = capture_scene_runtime(self.canvas)
        try:
            self._deselect_note(item)
            self.canvas.services.scene_item_controller.remove_scene_item(item)
            self.canvas.services.selection.update_selection_outline()
        except Exception as original_error:
            self._restore_scene_runtime_step(runtime_snapshot, original_error)
            raise
        return runtime_snapshot

    def _pending_note_edit_command(
        self, item: QGraphicsTextItem
    ) -> HistoryCommand | None:
        """Represent pending typing once, for both blur and color actions."""
        text = item.toPlainText().strip()
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        html_changed = bool(committed_html) and item.toHtml() != committed_html
        if not text or (text == committed_text.strip() and not html_changed):
            return None
        after_state = note_state_dict_for(self.canvas, item)
        if not committed_text:
            return AddSceneItemsCommand.from_items(
                item_states=[after_state], items=[item]
            )
        runtime = NoteTextState.capture(item)
        before = replace(
            runtime,
            html=committed_html,
            cursor_anchor=0,
            cursor_position=0,
            interaction_flags=Qt.TextInteractionFlag.NoTextInteraction,
        )
        after = replace(runtime, committed_text=text, committed_html=runtime.html)
        return SetAnnotationStyleCommand(
            before, after, "note", require_scene_record_id(item)
        )

    def apply_note_color(
        self, item: QGraphicsTextItem, color: QColor
    ) -> list[HistoryCommand]:
        """Mutate within the caller's document transaction and return commands."""
        original = NoteTextState.capture(item)
        pending = self._pending_note_edit_command(item)
        commands = [pending] if pending is not None else []
        if pending is not None:
            set_committed_note_text_for(item, item.toPlainText().strip())
            set_committed_note_html_for(item, item.toHtml())
        before = NoteTextState.capture(item)
        before_state = note_state_dict_for(self.canvas, item)
        char_format = QTextCharFormat()
        char_format.setForeground(color)
        cursor = item.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(char_format)
            item.setTextCursor(cursor)
        else:
            whole = QTextCursor(item.document())
            whole.select(QTextCursor.SelectionType.Document)
            whole.mergeCharFormat(char_format)
            item.setDefaultTextColor(color)
        if pending is not None or original.committed_html == original.html:
            set_committed_note_html_for(item, item.toHtml())
        if before_state != note_state_dict_for(self.canvas, item):
            commands.append(
                SetAnnotationStyleCommand(
                    before,
                    NoteTextState.capture(item),
                    "note",
                    require_scene_record_id(item),
                )
            )
        return commands

    def handle_note_focus_out(self, item: QGraphicsTextItem) -> None:
        self._end_note_editing(item)
        text = item.toPlainText().strip()
        committed_text = committed_note_text_for(item)
        committed_html = committed_note_html_for(item)
        current_html = item.toHtml()
        if text:
            command = self._pending_note_edit_command(item)
            if command is not None:

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
            empty_state = note_state_dict_for(self.canvas, item)
            # Deletion reattaches the same live item on Undo, which is already
            # empty. Restore its committed content as part of the same action.
            command = CompositeCommand(
                [
                    UpdateSceneItemCommand(
                        require_scene_record_id(item), before_state, empty_state
                    ),
                    DeleteSceneItemsCommand.capture(
                        self.history.operations, [empty_state], [item]
                    ),
                ]
            )
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
                command,
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
        notify_document_change_for(self.canvas)

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
            self.canvas.services.selection.update_note_selection_box(item)
            if item.hasFocus():
                # Live editor changes are not document-history commands yet.
                notify_document_change_for(self.canvas, edited_note=item)

        document.contentsChanged.connect(_resize)
        item.setData(22, True)

    def begin_note_edit(self, item: QGraphicsTextItem) -> None:
        if not item.hasFocus():
            # Prior sessions already belong to document history. Qt otherwise
            # coalesces typing across blur/re-entry and Undo erases saved text.
            document = item.document()
            if document is not None:
                document.clearUndoRedoStacks()
        if item not in self.canvas.runtime_state.selection_state.selected_notes:
            selection_controller = self._selection_controller()
            if selection_controller is not None:
                selection_controller.select_note(item, additive=False)
        self._ensure_note_box_autoresize(item)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.canvas.setFocus(Qt.FocusReason.MouseFocusReason)
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

    def text_format_targets(self) -> list[QGraphicsTextItem]:
        editing = self._editing_note()
        if editing is not None:
            return [editing]
        # A marquee uses Qt selection, while note clicks use the note registry.
        # Read the same union as move/copy/delete without changing either owner.
        return [
            item
            for item in selected_scene_items_for(self.canvas, excluded_kinds=set())
            if isinstance(item, QGraphicsTextItem) and item.data(0) == "note"
        ]

    def _text_format_cursor(self, item: QGraphicsTextItem) -> QTextCursor:
        if item is self._editing_note():
            return item.textCursor()
        cursor = QTextCursor(item.document())
        cursor.select(QTextCursor.SelectionType.Document)
        return cursor

    def _merge_text_char_format(self, mutate) -> None:
        def apply(item: QGraphicsTextItem) -> None:
            cursor = self._text_format_cursor(item)
            fmt = QTextCharFormat()
            mutate(cursor.charFormat(), fmt)
            cursor.mergeCharFormat(fmt)
            if item is self._editing_note():
                item.setTextCursor(cursor)

        self._apply_to_target_notes(apply)

    def toggle_text_bold(self) -> None:
        def mutate(current: QTextCharFormat, fmt: QTextCharFormat) -> None:
            is_bold = current.fontWeight() > QFont.Weight.Normal
            fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)

        self._merge_text_char_format(mutate)

    def toggle_text_italic(self) -> None:
        self._merge_text_char_format(
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

        self._merge_text_char_format(mutate)

    def adjust_text_size(self, delta: int) -> None:
        def apply(item: QGraphicsTextItem) -> None:
            cursor = self._text_format_cursor(item)

            def stepped_format(current: QTextCharFormat) -> QTextCharFormat:
                size = current.fontPointSize()
                if size <= 0:
                    font = current.font().resolve(item.font())
                    size = font.pointSizeF()
                    if size <= 0:
                        size = QFontInfo(font).pointSizeF()
                fmt = QTextCharFormat()
                fmt.setFontPointSize(max(6.0, min(96.0, size + delta)))
                return fmt

            if cursor.hasSelection():
                start, end = cursor.selectionStart(), cursor.selectionEnd()
                runs: list[tuple[int, int, QTextCharFormat]] = []
                document = cursor.document()
                if document is None:
                    raise RuntimeError("cannot format text without its document")
                block = document.findBlock(start)
                while block.isValid() and block.position() < end:
                    fragments = block.begin()
                    while not fragments.atEnd():
                        fragment = fragments.fragment()
                        first = max(start, fragment.position())
                        last = min(end, fragment.position() + fragment.length())
                        if fragment.isValid() and first < last:
                            runs.append(
                                (first, last, stepped_format(fragment.charFormat()))
                            )
                        fragments.__iadd__(1)
                    block = block.next()
                # Capture every run before merging: format changes may coalesce
                # adjacent QTextFragments. One click is one native text Undo.
                work = QTextCursor(cursor)
                work.beginEditBlock()
                try:
                    for first, last, fmt in runs:
                        work.setPosition(first)
                        work.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
                        work.mergeCharFormat(fmt)
                finally:
                    work.endEditBlock()
            else:
                cursor.mergeCharFormat(stepped_format(cursor.charFormat()))
            if item is self._editing_note():
                item.setTextCursor(cursor)

        self._apply_to_target_notes(apply)

    def set_text_font_family(self, family: str) -> None:
        self._merge_text_char_format(
            lambda _current, fmt: fmt.setFontFamilies([family])
        )

    def set_text_alignment(self, alignment: str) -> None:
        qt_alignment = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "center": Qt.AlignmentFlag.AlignHCenter,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(alignment, Qt.AlignmentFlag.AlignLeft)

        def mutate(item: QGraphicsTextItem) -> None:
            cursor = self._text_format_cursor(item)
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
                self.canvas.services.selection.update_note_selection_box(editing)
                rect_transaction.release()
            except Exception as original_error:
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
            for item in self.text_format_targets()
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
                self.canvas.services.selection.update_note_selection_box(item)
                after_state = note_state_dict_for(self.canvas, item)
                if batch_snapshot.before_state != after_state:
                    commands.append(
                        UpdateSceneItemCommand(
                            require_scene_record_id(item),
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
        except Exception as original_error:
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
        for item in self.canvas.runtime_state.selection_state.selected_notes:
            self.apply_note_style(item)

    def apply_note_style(self, item: QGraphicsTextItem) -> None:
        apply_note_style(item, self.canvas.runtime_state.text_style_state)
        self.canvas.services.selection.update_note_selection_box(item)

    def apply_note_appearance(
        self, item: QGraphicsTextItem, *, line_spacing: bool
    ) -> None:
        """Restyle document-wide boxes/spacing without changing text runs."""
        apply_note_appearance(
            item, self.canvas.runtime_state.text_style_state, line_spacing=line_spacing
        )
        self.canvas.services.selection.update_note_selection_box(item)

    def update_note_box(self, item: QGraphicsTextItem) -> None:
        update_note_box(item, self.canvas.runtime_state.text_style_state)


__all__ = ["CanvasNoteController"]
