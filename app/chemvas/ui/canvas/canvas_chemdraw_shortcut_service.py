from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from chemvas.features.annotations import DEFAULT_BRACKET_KIND
from chemvas.ui.canvas.canvas_tool_settings_state import CanvasToolSettingsState
from chemvas.ui.tools.bond_tool_logic import BOND_SHORTCUT_KEYS, bond_shortcut_style
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

    LABEL_HOTKEYS: ClassVar[dict[str, str]] = {
        "f": "F",
        "F": "CF3",
        "p": "P",
        "P": "Ph",
        "A": "Ac",
        "h": "H",
        "b": "Br",
        "B": "B",
        "i": "I",
        "r": "R",
        "s": "S",
        "S": "Si",
        "m": "Me",
        "n": "N",
        "w": "N",
        "N": "NO2",
        "c": "C",
        "l": "Cl",
        "C": "Cl",
        "x": "X",
        "o": "O",
        "q": "O",
        "d": "D",
        "e": "Et",
        "E": "CO2Me",
        "Z": "N3",
        "M": "MgBr",
        "L": "Li",
        "O": "OMe",
        "Q": "Fmoc",
        "H": "Cbz",
        "Y": "Boc",
        "k": "SO2",
        "K": "t-Bu",
    }

    ATOM_HOTKEYS = frozenset(LABEL_HOTKEYS) | frozenset("0123456789azvu+-")
    BOND_HOTKEYS = BOND_SHORTCUT_KEYS | frozenset("4567890a")

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

    def _add_mark_for_atom(self, atom_id: int, *, kind: str) -> None:
        if self.mark_scene_service is None:
            return
        self.mark_scene_service.change_charge_for_atom(
            atom_id, 1 if kind == "plus" else -1
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
        if self._model().atom_for_id(atom_id) is None:
            return False
        if not text:
            return False
        if text == "+":
            self._add_mark_for_atom(atom_id, kind="plus")
            return True
        if text == "-":
            self._add_mark_for_atom(atom_id, kind="minus")
            return True
        if text in self.LABEL_HOTKEYS:
            self.atom_labels.add_or_update_atom_label(
                atom_id,
                self.LABEL_HOTKEYS[text],
                show_carbon=True,
            )
            return True
        if text in {"0", "1"}:
            self.structure_build.sprout_bond_from_atom(
                atom_id, style="single", order=1, cyclic=text == "0"
            )
            return True
        if text == "2":
            self.structure_build.sprout_acetyl_from_atom(atom_id)
            return True
        if text in {"3", "a"}:
            self.structure_build.sprout_benzene_from_atom(atom_id)
            return True
        if text == "9":
            self.structure_build.sprout_dimethyl_from_atom(atom_id)
            return True
        if text == "4":
            self.structure_build.sprout_bond_from_atom(atom_id, style="wedge", order=1)
            return True
        if text == "5":
            self.structure_build.sprout_bond_from_atom(atom_id, style="hash", order=1)
            return True
        if text == "6":
            self.structure_build.sprout_regular_ring_from_atom(atom_id, 6)
            return True
        if text == "7":
            self.structure_build.sprout_regular_ring_from_atom(atom_id, 5)
            return True
        if text == "8":
            self.structure_build.sprout_bond_from_atom(atom_id, style="double", order=2)
            return True
        if text == "z":
            self.structure_build.sprout_bond_from_atom(atom_id, style="triple", order=3)
            return True
        if text == "v":
            self.structure_build.sprout_regular_ring_from_atom(atom_id, 3)
            return True
        if text == "u":
            self.structure_build.sprout_regular_ring_from_atom(atom_id, 4)
            return True
        return False

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
        bond = self._model().bond_for_id(bond_id)
        if bond is None:
            return False
        try:
            style = bond_shortcut_style(bond, text)
        except ValueError as error:
            self._notify_error(str(error))
            return True
        if style is not None:
            self.scene_transform.apply_bond_style(bond_id, *style)
            return True
        if text == "a":
            self.structure_build.fuse_benzene_to_bond(bond_id)
            return True
        if text in {"4", "5", "6", "7", "8"}:
            self.structure_build.fuse_regular_ring_to_bond(bond_id, int(text))
            return True
        if text in {"9", "0"}:
            self.structure_build.fuse_chair_to_bond(bond_id, mirrored=text == "0")
            return True
        return False


__all__ = ["CanvasChemdrawShortcutService"]
