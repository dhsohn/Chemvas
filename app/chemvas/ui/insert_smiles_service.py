from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from chemvas.features.insertion import (
    plan_smiles_commit,
    smiles_preview_center,
    smiles_preview_offset,
)
from chemvas.ui.canvas_window_access import notify_error_for
from chemvas.ui.input_view_access import viewport_center_scene_pos_for
from chemvas.ui.insert_mode_logic import InsertSessionState
from chemvas.ui.insert_mode_logic import (
    begin_smiles_insert as begin_smiles_insert_state,
)
from chemvas.ui.insert_mode_logic import (
    cancel_smiles_insert as cancel_smiles_insert_state,
)
from chemvas.ui.preview_scene_access import add_smiles_preview_item_for
from chemvas.ui.preview_scene_access import (
    clear_smiles_preview_for as clear_smiles_preview_helper,
)
from chemvas.ui.rdkit_adapter_access import rdkit_last_error_for, smiles_to_2d_for
from chemvas.ui.renderer_style_access import bond_length_px_for, renderer_for
from chemvas.ui.smiles_preview_picture import render_smiles_preview_picture

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtCore import QPointF

    from chemvas.ui.canvas_insert_state import CanvasInsertState
    from chemvas.ui.insert_commit_service import InsertCommitService

MAX_SMILES_INPUT_LENGTH = 1024


class InsertSmilesService:
    def __init__(
        self,
        canvas,
        *,
        insert_state: CanvasInsertState,
        insert_commit_service: InsertCommitService,
        session_state: Callable[[], InsertSessionState],
        apply_session_state: Callable[[InsertSessionState], None],
        cancel_template_insert: Callable[[], None],
        cancel_smiles_insert=None,
        clear_smiles_preview=None,
        render_smiles_preview=None,
    ) -> None:
        self.canvas = canvas
        self.insert_state = insert_state
        self.insert_commit_service = insert_commit_service
        self._session_state = session_state
        self._apply_session_state = apply_session_state
        self._cancel_template_insert = cancel_template_insert
        self._cancel_smiles_insert_callback = cancel_smiles_insert
        self._clear_smiles_preview_callback = clear_smiles_preview
        self._render_smiles_preview_callback = render_smiles_preview

    def _warn_smiles_error(self, message: str) -> None:
        if not notify_error_for(self.canvas, f"SMILES: {message}"):
            QMessageBox.warning(self.canvas, "SMILES Error", message)

    def _reject_oversized_smiles(self, smiles: str) -> bool:
        if len(smiles) <= MAX_SMILES_INPUT_LENGTH:
            return False
        self._warn_smiles_error(
            f"SMILES input is too long (maximum {MAX_SMILES_INPUT_LENGTH} characters)."
        )
        return True

    def begin_smiles_insert(self, smiles: str) -> None:
        if self.insert_state.template_active:
            self._cancel_template_insert()
        smiles = smiles.strip()
        if not smiles:
            return
        if self._reject_oversized_smiles(smiles):
            return
        model = smiles_to_2d_for(
            self.canvas, smiles, scale=bond_length_px_for(self.canvas)
        )
        if model is None:
            self._warn_smiles_error(
                rdkit_last_error_for(self.canvas) or "Failed to render SMILES."
            )
            return
        center_xy = smiles_preview_center(model)
        if center_xy is None:
            return
        next_state = begin_smiles_insert_state(smiles, center_xy)
        if next_state is None:
            return
        # Rendered once per insertion; hovering only moves the replayed picture.
        self.insert_state.smiles_preview_picture = render_smiles_preview_picture(
            renderer_for(self.canvas), model
        )
        self.insert_state.smiles_preview_model = model
        self._apply_session_state(next_state)
        self._render_smiles_preview(viewport_center_scene_pos_for(self.canvas))

    def _render_smiles_preview(self, pos: QPointF) -> None:
        if self._render_smiles_preview_callback is not None:
            self._render_smiles_preview_callback(pos)
            return
        self.render_smiles_preview(pos)

    def cancel_smiles_insert(self) -> None:
        self.insert_state.smiles_preview_model = None
        self.insert_state.smiles_preview_picture = None
        next_state = cancel_smiles_insert_state(self._session_state())
        self._apply_session_state(next_state)

    def commit_smiles_insert(self, pos: QPointF) -> None:
        plan = plan_smiles_commit(
            self.insert_state.smiles_preview_model,
            None
            if self.insert_state.smiles_preview_center is None
            else (
                self.insert_state.smiles_preview_center.x(),
                self.insert_state.smiles_preview_center.y(),
            ),
            (pos.x(), pos.y()),
        )
        if plan is None:
            self._cancel_smiles_insert()
            return
        if not self.insert_commit_service.apply_smiles_commit(
            plan,
            after_smiles_input=self.insert_state.smiles_preview_smiles,
        ):
            self._cancel_smiles_insert()
            return
        self._cancel_smiles_insert()

    def _cancel_smiles_insert(self) -> None:
        if self._cancel_smiles_insert_callback is not None:
            self._cancel_smiles_insert_callback()
            return
        self.cancel_smiles_insert()

    def clear_smiles_preview(self) -> None:
        self.insert_state.smiles_preview_items = clear_smiles_preview_helper(
            self.canvas, self.insert_state.smiles_preview_items
        )

    def render_smiles_preview(self, pos: QPointF) -> None:
        model = self.insert_state.smiles_preview_model
        center = self.insert_state.smiles_preview_center
        picture = self.insert_state.smiles_preview_picture
        if model is None or center is None or picture is None or not model.atoms:
            self._clear_smiles_preview()
            return
        items = self.insert_state.smiles_preview_items
        item = items[0] if items else None
        if item is not None and item.picture() is not picture:
            # A new SMILES was inserted while the previous ghost was still up:
            # the item must show the picture the commit will place, not the
            # one it was built from.
            self._clear_smiles_preview()
            item = None
        if item is None:
            item = add_smiles_preview_item_for(self.canvas, picture)
            self.insert_state.smiles_preview_items = [item]
        item.setPos(
            *smiles_preview_offset((center.x(), center.y()), (pos.x(), pos.y()))
        )

    def _clear_smiles_preview(self) -> None:
        if self._clear_smiles_preview_callback is not None:
            self._clear_smiles_preview_callback()
            return
        self.clear_smiles_preview()


__all__ = ["MAX_SMILES_INPUT_LENGTH", "InsertSmilesService"]
