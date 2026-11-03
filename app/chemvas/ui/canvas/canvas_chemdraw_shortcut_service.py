from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.tools.chemdraw_text_shortcuts import ChemdrawTextShortcuts
from chemvas.ui.window.main_window_config import (
    ARROW_KEY_NUDGE,
    ARROW_KEY_ROTATION_DEGREES,
    SHIFT_TOOL_HOTKEYS,
    TOOL_HOTKEYS,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QKeyEvent

    from chemvas.domain.document import MoleculeModel
    from chemvas.features.hover import HoverState
    from chemvas.ui.canvas.canvas_mark_scene_service import CanvasMarkSceneService
    from chemvas.ui.canvas.canvas_tool_mode_controller import CanvasToolModeController
    from chemvas.ui.molecule.atom_label_service import AtomLabelService
    from chemvas.ui.molecule.structure_build_service import StructureBuildService
    from chemvas.ui.scene.scene_transform_controller import SceneTransformController


class CanvasChemdrawShortcutService:
    DEFAULT_ARROW_TYPE = "reaction"
    DEFAULT_ORBITAL_TYPE = "s"
    DEFAULT_MARK_KIND = "plus"

    # The key text decisions are shared with the browser editor.
    LABEL_HOTKEYS: ClassVar[dict[str, str]] = ChemdrawTextShortcuts.LABEL_HOTKEYS
    ATOM_HOTKEYS = ChemdrawTextShortcuts.ATOM_HOTKEYS
    BOND_HOTKEYS = ChemdrawTextShortcuts.BOND_HOTKEYS

    def __init__(
        self,
        model_provider: Callable[[], MoleculeModel],
        *,
        hover_state: HoverState,
        atom_label_service: AtomLabelService,
        structure_build_service: StructureBuildService,
        notify_error: Callable[[str], object],
        scene_transform_controller: SceneTransformController,
        tool_mode_controller: CanvasToolModeController,
        mark_scene_service: CanvasMarkSceneService | None = None,
    ) -> None:
        self._model = model_provider
        self.hover_state = hover_state
        self.atom_labels = atom_label_service
        self.structure_build = structure_build_service
        self._notify_error = notify_error
        self.tool_mode = tool_mode_controller
        self.scene_transform = scene_transform_controller
        self.mark_scene_service = mark_scene_service
        self.text_shortcuts = ChemdrawTextShortcuts(
            model_provider,
            atom_labels=atom_label_service,
            structure_build=structure_build_service,
            bond_styles=scene_transform_controller,
            # Resolved per call so a replaced error sink is still honored.
            notify_error=lambda message: self._notify_error(message),
            charges=mark_scene_service,
        )

    def handle_shortcut(self, event: QKeyEvent) -> bool:
        if self.handle_object_shortcut(event):
            return True
        # Hover handlers get priority but must not swallow keys they do not
        # handle: pressing a tool shortcut (Space, J, ...) while hovering an
        # atom still has to reach the generic hotkeys below.
        hover_state = self.hover_state
        hover_atom_id = hover_state.atom_id
        if hover_atom_id is not None and self.handle_atom_hotkey(event, hover_atom_id):
            return True
        hover_bond_id = hover_state.bond_id
        if hover_bond_id is not None and self.handle_bond_hotkey(event, hover_bond_id):
            return True
        return self.handle_generic_hotkey(event)

    def handle_object_shortcut(self, event: QKeyEvent) -> bool:
        from PyQt6.QtCore import Qt

        from chemvas.ui.canvas.input_view_access import shortcut_modifiers_for

        rotate_arrow_angles = {
            getattr(Qt.Key, f"Key_{name}"): angle
            for name, angle in ARROW_KEY_ROTATION_DEGREES.items()
        }
        nudge_arrow_offsets = {
            getattr(Qt.Key, f"Key_{name}"): offset
            for name, offset in ARROW_KEY_NUDGE.items()
        }

        modifiers = shortcut_modifiers_for(event)
        if modifiers == (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        ):
            if event.key() == Qt.Key.Key_H:
                self.scene_transform.flip_selected_items(horizontal=True)
                return True
            if event.key() == Qt.Key.Key_V:
                self.scene_transform.flip_selected_items(horizontal=False)
                return True
        if modifiers == Qt.KeyboardModifier.AltModifier:
            angle = rotate_arrow_angles.get(event.key())
            if angle is not None:
                self.scene_transform.rotate_selected_items(angle)
                return True
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            offset = nudge_arrow_offsets.get(event.key())
            if offset is not None:
                return bool(self.scene_transform.translate_selected_items(*offset))
        return False

    def handle_generic_hotkey(self, event: QKeyEvent) -> bool:
        from PyQt6.QtCore import Qt

        from chemvas.ui.canvas.input_view_access import shortcut_modifiers_for

        modifiers = shortcut_modifiers_for(event)
        if modifiers == Qt.KeyboardModifier.NoModifier:
            key = chr(event.key()).lower() if 0 <= event.key() < 128 else ""
            tool = TOOL_HOTKEYS.get(key)
            if tool == "bond":
                defaults = CanvasToolSettingsState()
                self.tool_mode.set_bond_style(
                    defaults.active_bond_style, defaults.active_bond_order
                )
            elif tool == "arrow":
                self.tool_mode.set_arrow_type(self.DEFAULT_ARROW_TYPE)
            elif tool is not None:
                self.tool_mode.set_tool(tool)
            if tool is not None:
                return True
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            key = chr(event.key()) if 0 <= event.key() < 128 else ""
            tool = SHIFT_TOOL_HOTKEYS.get(key)
            if tool == "ts_bracket":
                self.tool_mode.set_bracket_type(DEFAULT_BRACKET_KIND)
            elif tool == "orbital":
                self.tool_mode.set_orbital_type(self.DEFAULT_ORBITAL_TYPE)
            elif tool == "mark":
                self.tool_mode.set_mark_kind(self.DEFAULT_MARK_KIND)
            if tool is not None:
                return True
        if modifiers == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_D:
            self.tool_mode.set_tool("perspective")
            return True
        return False

    def handle_atom_hotkey(self, event: QKeyEvent, atom_id: int) -> bool:
        from PyQt6.QtCore import Qt

        from chemvas.ui.canvas.input_view_access import (
            chemdraw_shortcut_text_for,
            shortcut_modifiers_for,
        )

        if self._model().atom_for_id(atom_id) is None:
            return False
        modifiers = shortcut_modifiers_for(event)
        if modifiers not in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.ShiftModifier,
        ):
            return False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.atom_labels.prompt_atom_label(atom_id)
            return True
        text = chemdraw_shortcut_text_for(event)
        return self.handle_atom_text(text, atom_id)

    def handle_atom_text(self, text: str, atom_id: int) -> bool:
        """Run the native atom-key decisions after an input adapter normalizes text."""
        return self.text_shortcuts.handle_atom_text(text, atom_id)

    def handle_bond_hotkey(self, event: QKeyEvent, bond_id: int) -> bool:
        from PyQt6.QtCore import Qt

        from chemvas.ui.canvas.input_view_access import (
            chemdraw_shortcut_text_for,
            shortcut_modifiers_for,
        )

        bond = self._model().bond_for_id(bond_id)
        if bond is None:
            return False
        modifiers = shortcut_modifiers_for(event)
        if modifiers not in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.ShiftModifier,
        ):
            return False
        text = chemdraw_shortcut_text_for(event)
        if modifiers == Qt.KeyboardModifier.ShiftModifier and event.key() in {
            Qt.Key.Key_B,
            Qt.Key.Key_H,
            Qt.Key.Key_D,
        }:
            text = chr(event.key())
        return self.handle_bond_text(text, bond_id)

    def handle_bond_text(self, text: str, bond_id: int) -> bool:
        """Run the native bond-key decisions with either presentation adapter."""
        return self.text_shortcuts.handle_bond_text(text, bond_id)


__all__ = ["CanvasChemdrawShortcutService"]
