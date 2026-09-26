"""Temporary atom-picking mode on the existing drawing canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING, override

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from chemvas.domain.document import included_atom_ids
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

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self.canvas.services.hover.clear_hover_highlight()
            self._old_cursor = self.viewport.cursor()
            self.viewport.setCursor(Qt.CursorShape.CrossCursor)
            self.canvas.setFocus()
            self.editor.suggestion_status.setText(
                "Click a reactant atom, then its product atom. Escape returns to drawing."
            )
        else:
            self.viewport.setCursor(self._old_cursor)
            self.editor._selected_reactant = None
        self.refresh()

    def refresh(self) -> None:
        if not self._active:
            self.highlighter.clear_all()
            return
        reactant, _ = self.editor._build_endpoint("reactant")
        product, _ = self.editor._build_endpoint("product")
        pairs = {
            entry.reactant_atom_id: entry.product_atom_id
            for entry in self.editor._active_correspondence(reactant, product)
        }
        self.highlighter.show_correspondence(
            pairs,
            included_atom_ids(reactant),
            included_atom_ids(product),
            self.editor._changed_bonds,
            self.editor._selected_reactant,
        )

    def focus_atom(self, atom_id: int) -> None:
        atom = self.editor._model.atoms[atom_id]
        self.canvas.centerOn(atom.x, atom.y)
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
        if not isinstance(event, QMouseEvent):
            return False
        if event.type() == QEvent.Type.MouseMove:
            return not bool(event.buttons() & Qt.MouseButton.MiddleButton)
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if event.type() in {
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        }:
            point = self.canvas.mapToScene(event.position().toPoint())
            radius = atom_pick_radius_for(self.canvas)
            candidates = [
                (atom_id, (atom.x - point.x()) ** 2 + (atom.y - point.y()) ** 2)
                for atom_id, atom in self.editor._model.atoms.items()
            ]
            if candidates:
                atom_id, distance = min(candidates, key=lambda item: item[1])
                if distance <= radius**2:
                    if self.editor._selected_reactant is None:
                        if atom_id in self.editor._mapping_combos:
                            self.editor._pick_reactant(atom_id)
                            self.editor.suggestion_status.setText(
                                f"Reactant #{atom_id} selected. Click its product atom."
                            )
                        else:
                            self.editor.suggestion_status.setText(
                                "Choose an included reactant atom first."
                            )
                    else:
                        self.editor._pick_product(atom_id)
            return True
        return event.type() in {
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
        }
