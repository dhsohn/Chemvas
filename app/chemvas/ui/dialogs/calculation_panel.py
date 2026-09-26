"""Window-owned reaction-pair panel with explicit source-snapshot invalidation."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from chemvas.shell.palette import PALETTE
from chemvas.ui.canvas.canvas_calculation_plan_state import calculation_plan_for
from chemvas.ui.dialogs.calculation_canvas_mapping import CalculationCanvasMapping
from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog
from chemvas.ui.window.main_window_ports import (
    active_canvas_for_window,
    document_session_service_for_window,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QHideEvent

    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.window.main_window_like import MainWindowLike


class CalculationPanel(QDockWidget):
    def __init__(self, window: MainWindowLike) -> None:
        super().__init__("Reaction Mapping", window)
        self.setObjectName("calculationDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.window_owner = window
        self.editor: CalculationStepDialog | None = None
        self.mapping: CalculationCanvasMapping | None = None
        self.canvas: CanvasView | None = None
        self._baseline: dict[str, object] | None = None
        self._saving = False
        self._stale = True
        content = QWidget(self)
        layout = QVBoxLayout(content)
        self.notice = QLabel("", self)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.reload_button = QPushButton("Load drawing / discard panel draft", self)
        self.reload_button.clicked.connect(self.reload_drawing)
        layout.addWidget(self.reload_button)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        self.setWidget(content)
        self.setMinimumWidth(360)
        window.installEventFilter(self)
        window.tab_references.canvas_tabs.currentChanged.connect(self.document_changed)

    def reload_drawing(self, *, step_id: str | None = None) -> None:
        from chemvas.ui.dialogs.calculation_plan_actions import (
            _correspondence_suggester_for,
        )

        self.shutdown()
        old = self.scroll_area.takeWidget()
        if old is not None:
            old.deleteLater()
        self.editor = None
        self.mapping = None
        self.canvas = active_canvas_for_window(self.window_owner)
        state = document_session_service_for_window(self.window_owner).snapshot_state()
        self._baseline = copy.deepcopy(state)
        self._stale = False
        if (
            calculation_plan_for(self.canvas) is not None
            and "calculation_plan" not in state
        ):
            self._show_load_error(
                "The drawing no longer matches its saved plan. Undo the structure change before reloading. Existing plan data has been kept."
            )
            return
        try:
            editor = CalculationStepDialog(
                state,
                parent=self,
                embedded=True,
                snapshot_is_current=self.snapshot_is_current,
                correspondence_suggester=_correspondence_suggester_for(
                    self.canvas, state
                ),
            )
        except ValueError as exc:
            self._show_load_error(str(exc))
            return
        self.editor = editor
        self.scroll_area.setWidget(editor)
        self.mapping = CalculationCanvasMapping(self.canvas, editor)
        editor.plan_saved.connect(self._save_plan)
        selected = editor.step_selector.findData(step_id) if step_id else -1
        if editor.step_selector.count() > 1:
            editor.step_selector.setCurrentIndex(selected if selected > 0 else 1)
        self.notice.setText(
            "Connect reactant and product atoms to describe 2D bond changes. "
            "Save the mapping in your .chemvas document to share with an AI assistant or collaborator."
        )
        if not editor._components:
            self.notice.setText(
                "Draw reactant and product structures, then load the drawing here."
            )
            editor.setEnabled(False)
        editor.show()

    def _show_load_error(self, message: str) -> None:
        self._stale = True
        self.notice.setText("The drawing needs attention before preparing a pair.")
        page = QWidget(self.scroll_area)
        page.setObjectName("calculationLoadError")
        page.setAutoFillBackground(True)
        page.setStyleSheet(
            f"QWidget#calculationLoadError {{ background: {PALETTE['surface_app']}; }}"
        )
        layout = QVBoxLayout(page)
        heading = QLabel("Could not load the drawing", page)
        heading.setWordWrap(True)
        heading.setStyleSheet("font-weight: 600;")
        layout.addWidget(heading)
        detail = QLabel(message, page)
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(detail)
        instructions = (
            "Your drawing is still editable. Correct the indicated structure on "
            "the canvas, then choose Load drawing above to try again. "
            "No calculation export is available until the drawing loads successfully."
        )
        if "Alias label 'OH'" in message:
            instructions += (
                "\n\nFor a separate hydroxide ion, draw O and H as separate atoms "
                "with a single bond and put the negative charge on O. The OH "
                "abbreviation is supported only when attached to another atom."
            )
        help_text = QLabel(instructions, page)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        edit = QPushButton("Return to drawing", page)
        edit.clicked.connect(self._focus_drawing)
        layout.addWidget(edit)
        layout.addStretch()
        self.scroll_area.setWidget(page)

    def _focus_drawing(self) -> None:
        active_canvas_for_window(self.window_owner).setFocus()

    def snapshot_is_current(self) -> bool:
        if self._stale or self.canvas is not active_canvas_for_window(
            self.window_owner
        ):
            return False
        current = document_session_service_for_window(
            self.window_owner
        ).snapshot_state()
        if current != self._baseline:
            self.document_changed()
            return False
        return True

    def document_changed(self, *_args: object) -> None:
        if self._saving or self.editor is None or self._stale:
            return
        self._stale = True
        self._detach_mapping()
        self.editor._invalidate_check()
        self.editor.setEnabled(False)
        self.notice.setText(
            "The drawing or active document changed. The previous check is invalid. Reload to prepare the current drawing; this discards the panel draft. Saved plans stay in the document."
        )

    def _save_plan(self, plan: object) -> None:
        from chemvas.ui.dialogs.calculation_plan_actions import (
            save_calculation_plan_for_window,
        )

        if not isinstance(plan, dict) or not self.snapshot_is_current():
            return
        step_id = (
            self.editor.step_id.text().strip() if self.editor is not None else None
        )
        self._saving = True
        try:
            save_calculation_plan_for_window(self.window_owner, plan)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Could not save pair", str(exc))
            return
        finally:
            self._saving = False
        self.reload_drawing(step_id=step_id)
        self.notice.setText(
            "Reaction mapping added to the document. Use File → Save to keep it "
            "in the .chemvas file you share. Undo restores the previous mapping."
        )

    def _detach_mapping(self) -> None:
        if self.mapping is not None:
            self.mapping.shutdown()
            self.mapping.deleteLater()
            self.mapping = None

    def shutdown(self) -> None:
        self._detach_mapping()
        if self.editor is not None:
            self.editor.shutdown()

    @override
    def hideEvent(self, event: QHideEvent | None) -> None:
        if self.editor is not None:
            self.editor.mapping_mode.setChecked(False)
            self.editor._checker.cancel()
        super().hideEvent(event)

    @override
    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.Close:
            if self.editor is not None:
                self.editor.shutdown()
        return False
