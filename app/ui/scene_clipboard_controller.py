from __future__ import annotations

from PyQt6.QtWidgets import QApplication, QGraphicsItem

from ui.atom_label_access import add_or_update_atom_label
from ui.canvas_format_access import (
    clipboard_selection_mime_for,
    clipboard_selection_version_for,
)
from ui.canvas_mark_registry import mark_registry_for
from ui.canvas_model_access import (
    bonds_for,
)
from ui.canvas_scene_items_state import ring_items_for
from ui.history_canvas_access import apply_atom_color_for_history
from ui.scene_clipboard_access import (
    build_selection_clipboard_payload_for_canvas,
)
from ui.scene_clipboard_copy_io import (
    CLIPBOARD_PDF_MIME,
    CLIPBOARD_SVG_MIME,
)
from ui.scene_clipboard_copy_service import copy_selection_to_clipboard_for_canvas
from ui.scene_clipboard_logic import (
    clipboard_payload_candidates,
    decode_clipboard_selection_payload,
)
from ui.scene_clipboard_paste_service import (
    SceneClipboardPasteCallbacks,
    paste_selection_from_clipboard_for_canvas,
)
from ui.scene_clipboard_selection import select_pasted_content_for_canvas
from ui.scene_item_access import (
    create_scene_item_from_state as create_scene_item_from_state_helper,
)
from ui.scene_item_state import (
    atom_state_dict_for,
    bond_state_dict,
    scene_item_state_for,
)
from ui.selection_collection_access import (
    selected_ids_for,
    selected_items_for_transform_for,
)
from ui.structure_mutation_access import add_atom_for, add_bond_for


class SceneClipboardController:
    def __init__(
        self,
        canvas,
        *,
        selection_controller=None,
        bond_mutation_service=None,
    ) -> None:
        self.canvas = canvas
        self.selection_controller = selection_controller
        self.bond_mutation_service = bond_mutation_service
        self.marks = mark_registry_for(canvas)

    @property
    def _bonds(self):
        return bonds_for(self.canvas)

    def _bond_mutation_service(self):
        if self.bond_mutation_service is None:
            msg = "SceneClipboardController requires bond_mutation_service"
            raise RuntimeError(msg)
        return self.bond_mutation_service

    def _add_atom(self, element: str, x: float, y: float) -> int:
        return add_atom_for(self.canvas, element, x, y)

    def _add_bond(self, a_id: int, b_id: int, order: int = 1) -> int:
        return add_bond_for(self.canvas, a_id, b_id, order)

    def _add_or_update_atom_label(self, atom_id: int, element: str, **kwargs) -> None:
        add_or_update_atom_label(self.canvas, atom_id, element, **kwargs)

    def _apply_atom_color(self, atom_id: int, color) -> None:
        apply_atom_color_for_history(self.canvas, atom_id, color)

    def _restore_bond(self, bond_id: int, bond_state: dict) -> None:
        self._bond_mutation_service().restore_bond_from_state(bond_id, bond_state)

    def _atom_state(self, atom_id: int) -> dict:
        return atom_state_dict_for(self.canvas, atom_id)

    def _bond_state(self, bond) -> dict:
        return bond_state_dict(bond)

    def _scene_item_state(self, item) -> dict:
        return scene_item_state_for(self.canvas, item)

    def _create_scene_item_from_state(self, state: dict):
        return create_scene_item_from_state_helper(self.canvas, state)

    def _paste_callbacks(self) -> SceneClipboardPasteCallbacks:
        return SceneClipboardPasteCallbacks(
            add_atom=self._add_atom,
            apply_atom_color=self._apply_atom_color,
            add_or_update_atom_label=self._add_or_update_atom_label,
            add_bond=self._add_bond,
            restore_bond_from_state=self._restore_bond,
            create_scene_item_from_state=self._create_scene_item_from_state,
            select_pasted_content=self.select_pasted_content,
        )

    def _clear_note_selection(self) -> None:
        if self.selection_controller is not None:
            self.selection_controller.clear_note_selection()

    def _select_note(self, item, *, additive: bool = False) -> None:
        if self.selection_controller is not None:
            self.selection_controller.select_note(item, additive=additive)

    def _select_pasted_note(self, item) -> None:
        self._select_note(item, additive=True)

    def _clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            msg = "QApplication clipboard is unavailable"
            raise RuntimeError(msg)
        return clipboard

    def selection_payload_for_clipboard(self) -> dict | None:
        selected_items = selected_items_for_transform_for(self.canvas)
        explicit_atom_ids, bond_ids = selected_ids_for(self.canvas)
        return build_selection_clipboard_payload_for_canvas(
            self.canvas,
            selected_items=selected_items,
            explicit_atom_ids=explicit_atom_ids,
            selected_bond_ids=bond_ids,
            bonds=self._bonds,
            ring_items=ring_items_for(self.canvas),
            marks_by_atom=self.marks.by_atom,
            atom_state_getter=self._atom_state,
            bond_state_getter=self._bond_state,
            scene_item_state_getter=self._scene_item_state,
            version=clipboard_selection_version_for(self.canvas),
        )

    def clipboard_selection_payload(self) -> tuple[dict | None, str | None]:
        mime_data = self._clipboard().mimeData()
        payload_candidates = clipboard_payload_candidates(
            mime_data,
            mime_type=clipboard_selection_mime_for(self.canvas),
        )
        return decode_clipboard_selection_payload(
            payload_candidates,
            version=clipboard_selection_version_for(self.canvas),
        )

    def select_pasted_content(self, atom_ids: set[int], scene_items: list[QGraphicsItem]) -> None:
        select_pasted_content_for_canvas(
            self.canvas,
            atom_ids=atom_ids,
            scene_items=scene_items,
            clear_note_selection=self._clear_note_selection,
            select_note=self._select_pasted_note,
        )

    def copy_selection_to_clipboard(self, *, payload_provider=None) -> bool:
        provider = payload_provider if callable(payload_provider) else self.selection_payload_for_clipboard
        return copy_selection_to_clipboard_for_canvas(
            self.canvas,
            clipboard=self._clipboard(),
            payload_provider=provider,
        )

    def paste_selection_from_clipboard(self, *, payload_provider=None) -> bool:
        provider = payload_provider if callable(payload_provider) else self.clipboard_selection_payload
        return paste_selection_from_clipboard_for_canvas(
            self.canvas,
            payload_provider=provider,
            callbacks=self._paste_callbacks(),
        )


__all__ = [
    "CLIPBOARD_PDF_MIME",
    "CLIPBOARD_SVG_MIME",
    "SceneClipboardController",
]
