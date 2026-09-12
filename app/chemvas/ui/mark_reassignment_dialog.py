from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from chemvas.ui.canvas_model_access import atoms_for
from chemvas.ui.canvas_service_ports import mark_scene_service_for_access
from chemvas.ui.canvas_window_access import notify_error_for
from chemvas.ui.mark_ownership import mark_owner_text_for
from chemvas.ui.scene_item_access import (
    add_item_to_canvas_scene,
    remove_item_from_canvas_scene,
)
from chemvas.ui.selection_outline_items import selection_object_outline_item
from chemvas.ui.selection_outline_state import (
    append_selection_outline_for,
    selection_outlines_for,
)
from chemvas.ui.selection_style_access import selection_indicator_rect_for_atom_for

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem

    from chemvas.ui.canvas_view import CanvasView


class MarkReassignmentDialog(QDialog):
    """Explicit choice with a view-only candidate highlight, never a drag heuristic."""

    def __init__(self, canvas: CanvasView, item: QGraphicsItem) -> None:
        super().__init__(canvas)
        self.setWindowTitle("Reassign mark to atom")
        self.setObjectName("markReassignmentDialog")
        self.canvas = canvas
        self._preview = selection_object_outline_item(QPainterPath(), QColor("#a21caf"))
        self._preview.setData(2, {"kind": "mark_candidate"})
        self._preview.setZValue(22)
        self.atoms = QComboBox(self)
        self.atoms.setObjectName("markOwnerAtomCombo")
        owner = (item.data(1) or {}).get("atom_id")
        if owner is None:
            self.atoms.addItem("Free mark (unchanged)", None)
        for atom_id, atom in sorted(atoms_for(canvas).items()):
            suffix = " — current owner" if atom_id == owner else ""
            self.atoms.addItem(
                f"{atom.element} #{atom_id}  ({atom.x:.2f}, {atom.y:.2f}){suffix}",
                atom_id,
            )
        self.atoms.setCurrentIndex(self.atoms.findData(owner))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(mark_owner_text_for(canvas, item), self))
        explanation = QLabel(
            "Choose an atom; its outline is highlighted on the canvas.\nOnly Reassign changes the chemical owner.\nThe mark's position, kind and color stay unchanged.",
            self,
        )
        layout.addWidget(explanation)
        layout.addWidget(self.atoms)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        accept_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert accept_button is not None
        accept_button.setText("Reassign")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.atoms.currentIndexChanged.connect(self._preview_candidate)

    def _preview_candidate(self) -> None:
        atom_id = self.atoms.currentData()
        path = QPainterPath()
        if atom_id is not None:
            rect = selection_indicator_rect_for_atom_for(self.canvas, atom_id)
            if rect is not None:
                path.addEllipse(rect.adjusted(-2, -2, 2, 2))
                self.canvas.ensureVisible(rect, 80, 80)
        self._preview.setPath(path)
        self._preview.setData(2, {"kind": "mark_candidate", "atom_id": atom_id})

    def choose_atom(self) -> tuple[bool, int | None]:
        canvas = self.canvas
        horizontal = canvas.horizontalScrollBar()
        vertical = canvas.verticalScrollBar()
        viewport = canvas.viewport()
        assert horizontal is not None and vertical is not None and viewport is not None
        scroll = (horizontal.value(), vertical.value())
        try:
            add_item_to_canvas_scene(canvas, self._preview)
            append_selection_outline_for(canvas, self._preview)
            self._preview_candidate()
            self.adjustSize()
            # Keep the central drawing visible while choosing a highlighted atom.
            self.move(
                viewport.mapToGlobal(viewport.rect().topRight())
                - self.rect().topRight()
            )
            accepted = self.exec() == QDialog.DialogCode.Accepted
            if sip.isdeleted(canvas) or sip.isdeleted(self):
                return False, None
            return accepted, self.atoms.currentData()
        finally:
            if not sip.isdeleted(canvas):
                outlines = selection_outlines_for(canvas)
                if self._preview in outlines:
                    outlines.remove(self._preview)
                if not sip.isdeleted(self._preview):
                    remove_item_from_canvas_scene(canvas, self._preview)
                horizontal.setValue(scroll[0])
                vertical.setValue(scroll[1])


def reassign_mark_with_dialog(canvas: CanvasView, item: QGraphicsItem) -> bool:
    dialog = MarkReassignmentDialog(canvas, item)
    try:
        accepted, atom_id = dialog.choose_atom()
        if not accepted or atom_id is None or sip.isdeleted(canvas):
            return False
        try:
            return bool(
                mark_scene_service_for_access(canvas).rebind_mark(item, atom_id)
            )
        except ValueError as error:
            if notify_error_for(canvas, str(error)):
                return False
            raise
    finally:
        if not sip.isdeleted(dialog):
            dialog.deleteLater()
