from __future__ import annotations

from typing import ClassVar

from PyQt6.QtCore import Qt

from ui.atom_label_access import add_or_update_atom_label, prompt_atom_label_for
from ui.bracket_types import DEFAULT_BRACKET_KIND
from ui.canvas_hover_state import hover_state_for
from ui.canvas_model_access import atom_for_id, bond_for_id
from ui.input_view_access import shortcut_modifiers_for
from ui.structure_build_access import (
    fuse_benzene_to_bond_for,
    fuse_chair_to_bond_for,
    fuse_regular_ring_to_bond_for,
    sprout_acetyl_from_atom_for,
    sprout_benzene_from_atom_for,
    sprout_bond_from_atom_for,
    sprout_regular_ring_from_atom_for,
)
from ui.structure_geometry_access import atom_point_for


class CanvasChemdrawShortcutService:
    DEFAULT_ARROW_TYPE = "reaction"

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

    def __init__(self, canvas, *, scene_transform_controller, tool_mode_controller, mark_scene_service=None) -> None:
        self.canvas = canvas
        self.tool_mode = tool_mode_controller
        self.scene_transform = scene_transform_controller
        self.mark_scene_service = mark_scene_service

    def _add_mark_for_atom(self, atom_id: int, *, kind: str) -> None:
        if self.mark_scene_service is None:
            return
        self.mark_scene_service.add_mark_for_atom(atom_id, atom_point_for(self.canvas, atom_id), kind=kind)

    def handle_shortcut(self, event) -> bool:
        if self.handle_object_shortcut(event):
            return True
        hover_state = hover_state_for(self.canvas)
        hover_atom_id = hover_state.atom_id
        if hover_atom_id is not None:
            return self.handle_atom_hotkey(event, hover_atom_id)
        hover_bond_id = hover_state.bond_id
        if hover_bond_id is not None:
            return self.handle_bond_hotkey(event, hover_bond_id)
        return self.handle_generic_hotkey(event)

    def handle_object_shortcut(self, event) -> bool:
        modifiers = shortcut_modifiers_for(event)
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_H:
                self.scene_transform.flip_selected_items(horizontal=True)
                return True
            if event.key() == Qt.Key.Key_V:
                self.scene_transform.flip_selected_items(horizontal=False)
                return True
        return False

    def handle_generic_hotkey(self, event) -> bool:
        modifiers = shortcut_modifiers_for(event)
        if modifiers == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_Space:
                self.tool_mode.set_tool("select")
                return True
            if event.key() == Qt.Key.Key_X:
                self.tool_mode.set_bond_style("single", 1)
                return True
            if event.key() == Qt.Key.Key_A:
                self.tool_mode.set_tool("text")
                return True
            if event.key() == Qt.Key.Key_T:
                self.tool_mode.set_tool("note")
                return True
            if event.key() == Qt.Key.Key_E:
                self.tool_mode.set_arrow_type(self.DEFAULT_ARROW_TYPE)
                return True
            if event.key() == Qt.Key.Key_J:
                self.tool_mode.set_tool("benzene")
                return True
        if modifiers == Qt.KeyboardModifier.ShiftModifier and event.key() == Qt.Key.Key_G:
            self.tool_mode.set_bracket_type(DEFAULT_BRACKET_KIND)
            return True
        if modifiers == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_D:
            self.tool_mode.set_tool("perspective")
            return True
        return False

    def handle_atom_hotkey(self, event, atom_id: int) -> bool:
        if atom_for_id(self.canvas, atom_id) is None:
            return False
        modifiers = shortcut_modifiers_for(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            prompt_atom_label_for(self.canvas, atom_id)
            return True
        text = event.text()
        if not text:
            return False
        if text == "+":
            self._add_mark_for_atom(atom_id, kind="plus")
            return True
        if text == "-":
            self._add_mark_for_atom(atom_id, kind="minus")
            return True
        if text in self.LABEL_HOTKEYS:
            add_or_update_atom_label(
                self.canvas,
                atom_id,
                self.LABEL_HOTKEYS[text],
                show_carbon=True,
                include_default_kwargs=False,
            )
            return True
        if text in {"0", "1"}:
            sprout_bond_from_atom_for(self.canvas, atom_id, style="single", order=1, cyclic=text == "0")
            return True
        if text == "2":
            sprout_acetyl_from_atom_for(self.canvas, atom_id)
            return True
        if text in {"3", "a"}:
            sprout_benzene_from_atom_for(self.canvas, atom_id)
            return True
        if text == "4":
            sprout_bond_from_atom_for(self.canvas, atom_id, style="wedge", order=1)
            return True
        if text == "5":
            sprout_bond_from_atom_for(self.canvas, atom_id, style="hash", order=1)
            return True
        if text == "6":
            sprout_regular_ring_from_atom_for(self.canvas, atom_id, 6)
            return True
        if text == "7":
            sprout_regular_ring_from_atom_for(self.canvas, atom_id, 5)
            return True
        if text == "8":
            sprout_bond_from_atom_for(self.canvas, atom_id, style="double", order=2)
            return True
        if text == "z":
            sprout_bond_from_atom_for(self.canvas, atom_id, style="triple", order=3)
            return True
        if text == "v":
            sprout_regular_ring_from_atom_for(self.canvas, atom_id, 3)
            return True
        if text == "u":
            sprout_regular_ring_from_atom_for(self.canvas, atom_id, 4)
            return True
        return False

    def handle_bond_hotkey(self, event, bond_id: int) -> bool:
        if bond_for_id(self.canvas, bond_id) is None:
            return False
        modifiers = shortcut_modifiers_for(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if event.key() == Qt.Key.Key_B:
                self.scene_transform.apply_bond_style(bond_id, "bold_in", 2)
                return True
            if event.key() == Qt.Key.Key_H:
                self.scene_transform.apply_bond_style(bond_id, "hash", 1)
                return True
        text = event.text()
        if text == "1":
            self.scene_transform.apply_bond_style(bond_id, "single", 1)
            return True
        if text == "2":
            self.scene_transform.apply_bond_style(bond_id, "double", 2)
            return True
        if text == "3":
            self.scene_transform.apply_bond_style(bond_id, "triple", 3)
            return True
        if text == "b":
            self.scene_transform.apply_bond_style(bond_id, "bold_in", 1)
            return True
        if text == "w":
            self.scene_transform.apply_bond_style(bond_id, "wedge", 1)
            return True
        if text == "h":
            self.scene_transform.apply_bond_style(bond_id, "hash", 1)
            return True
        if text == "a":
            fuse_benzene_to_bond_for(self.canvas, bond_id)
            return True
        if text in {"4", "5", "6", "7", "8"}:
            fuse_regular_ring_to_bond_for(self.canvas, bond_id, int(text))
            return True
        if text in {"9", "0"}:
            fuse_chair_to_bond_for(self.canvas, bond_id, mirrored=text == "0")
            return True
        return False


__all__ = ["CanvasChemdrawShortcutService"]
