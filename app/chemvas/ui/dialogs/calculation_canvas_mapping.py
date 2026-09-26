"""Temporary atom-picking mode on the existing drawing canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QObject, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from chemvas.ui.canvas.pick_radius_access import atom_pick_radius_for
from chemvas.ui.dialogs.calculation_mapping_highlight import (
    CalculationMappingHighlighter,
)

if TYPE_CHECKING:
    from chemvas.ui.canvas.canvas_view import CanvasView
    from chemvas.ui.dialogs.calculation_step_dialog import CalculationStepDialog


class CalculationCanvasMapping(QObject):
    def __init__(self, canvas: CanvasView, editor: CalculationStepDialog) -> None:
        super().__init__(editor)
        self.canvas = canvas
        self.editor = editor
        self.highlighter = CalculationMappingHighlighter(canvas)
        self._active = False
        self._hovered: int | None = None
        viewport = canvas.viewport()
        if viewport is None:
            raise RuntimeError("Calculation mapping requires a canvas viewport.")
        self.viewport = viewport
        self._old_cursor = viewport.cursor()
        canvas.installEventFilter(self)
        self.viewport.installEventFilter(self)
        editor.mapping_mode.toggled.connect(self.set_active)
        editor.mapping_updated.connect(self.refresh)
        editor.focus_atom_requested.connect(self.focus_atom)
        editor.tabs.currentChanged.connect(self._tab_changed)

    def _tab_changed(self, index: int) -> None:
        if index != 1:
            self.editor.mapping_mode.setChecked(False)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._hovered = None
        if active:
            scene = self.canvas.scene()
            if scene is not None:
                scene.clearSelection()
            self.canvas.services.hover.clear_hover_highlight()
            self._old_cursor = self.viewport.cursor()
            self.viewport.setCursor(Qt.CursorShape.CrossCursor)
            self.canvas.setFocus()
            self.editor.suggestion_status.setText(
                "Click a reactant atom, then its product atom. Escape returns to drawing."
            )
        else:
            self.viewport.setCursor(self._old_cursor)
            self.editor.clear_canvas_mapping_selection()
        self.refresh()

    def refresh(self) -> None:
        if not self._active:
            self.highlighter.clear_all()
            return
        snapshot = self.editor.canvas_mapping_snapshot()
        pairs = dict(snapshot.pairs)
        focus = snapshot.selected_reactant
        if focus is None:
            focus = self._hovered
        reverse = {product: reactant for reactant, product in pairs.items()}
        if focus is not None:
            reactant_id = (
                focus if focus in snapshot.reactant_ids else reverse.get(focus)
            )
            product_id = pairs.get(reactant_id) if reactant_id is not None else None
            if product_id is not None and reactant_id is not None:
                number = sorted(pairs).index(reactant_id) + 1
                self.editor.suggestion_status.setText(
                    f"Pair {number}: reactant #{reactant_id} ↔ product #{product_id}. "
                    "Only this pair is highlighted."
                )
            else:
                side = "Reactant" if focus in snapshot.reactant_ids else "Product"
                self.editor.suggestion_status.setText(f"{side} #{focus}: not mapped.")
        else:
            self.editor.suggestion_status.setText(
                "Point to an atom to inspect its pair. Click a reactant, then its product."
            )
        self.highlighter.show_correspondence(
            pairs,
            snapshot.reactant_ids,
            snapshot.product_ids,
            snapshot.changed_bonds,
            focus,
        )

    def focus_atom(self, atom_id: int) -> None:
        snapshot = self.editor.canvas_mapping_snapshot()
        position = next(
            ((x, y) for key, x, y in snapshot.atoms if key == atom_id), None
        )
        if position is None:
            return
        self.canvas.centerOn(*position)
        self.editor.mapping_mode.setChecked(True)
        self.refresh()

    def shutdown(self) -> None:
        self.editor.mapping_mode.setChecked(False)
        self.highlighter.clear_all()
        self.canvas.removeEventFilter(self)
        self.viewport.removeEventFilter(self)

    @override
    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if not self._active or event is None:
            return False
        if isinstance(event, QKeyEvent) and event.key() == Qt.Key.Key_Escape:
            if event.type() == QEvent.Type.ShortcutOverride:
                event.accept()
                return True
            self.editor.mapping_mode.setChecked(False)
            return True
        if event.type() == QEvent.Type.Leave:
            self._hovered = None
            self.refresh()
        if not isinstance(event, QMouseEvent):
            return False
        if event.type() == QEvent.Type.MouseMove:
            atom_id = self._atom_at(event)
            if atom_id != self._hovered:
                self._hovered = atom_id
                self.refresh()
            return not bool(event.buttons() & Qt.MouseButton.MiddleButton)
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        }:
            atom_id = self._atom_at(event)
            if atom_id is not None:
                self._hovered = atom_id
                if self.editor.pick_canvas_atom(atom_id):
                    self.refresh()
            return True
        return event.type() in {
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }

    def _atom_at(self, event: QMouseEvent) -> int | None:
        point = event.position()
        transform = self.canvas.viewportTransform()
        # Keep small skeletal vertices targetable when the drawing is zoomed
        # out. Use model atoms, including carbons that have no text item.
        origin = transform.map(QPointF(0, 0))
        edge = transform.map(QPointF(atom_pick_radius_for(self.canvas), 0))
        radius = max(10.0, ((edge - origin).x() ** 2 + (edge - origin).y() ** 2) ** 0.5)
        snapshot = self.editor.canvas_mapping_snapshot()
        included = snapshot.reactant_ids | snapshot.product_ids
        candidates = []
        for atom_id, x, y in snapshot.atoms:
            if atom_id not in included:
                continue
            position = transform.map(QPointF(x, y))
            distance = (position.x() - point.x()) ** 2 + (position.y() - point.y()) ** 2
            candidates.append((atom_id, distance))
        if not candidates:
            return None
        atom_id, distance = min(candidates, key=lambda item: item[1])
        return atom_id if distance <= radius**2 else None
