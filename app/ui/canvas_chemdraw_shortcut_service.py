from __future__ import annotations

from PyQt6.QtCore import Qt


class CanvasChemdrawShortcutService:
    LABEL_HOTKEYS = {
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

    def __init__(self, canvas) -> None:
        self.canvas = canvas

    def handle_shortcut(self, event) -> bool:
        if self.handle_object_shortcut(event):
            return True
        if self.canvas.hover_atom_id is not None:
            return self.handle_atom_hotkey(event, self.canvas.hover_atom_id)
        if self.canvas.hover_bond_id is not None:
            return self.handle_bond_hotkey(event, self.canvas.hover_bond_id)
        return self.handle_generic_hotkey(event)

    def handle_object_shortcut(self, event) -> bool:
        modifiers = self.canvas._shortcut_modifiers(event)
        if modifiers == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if event.key() == Qt.Key.Key_H:
                self.canvas.flip_horizontal()
                return True
            if event.key() == Qt.Key.Key_V:
                self.canvas.flip_vertical()
                return True
        return False

    def handle_generic_hotkey(self, event) -> bool:
        modifiers = self.canvas._shortcut_modifiers(event)
        if modifiers == Qt.KeyboardModifier.NoModifier:
            if event.key() == Qt.Key.Key_Space:
                self.canvas.set_tool("select")
                return True
            if event.key() == Qt.Key.Key_X:
                self.canvas.set_bond_style("single", 1)
                return True
            if event.key() == Qt.Key.Key_T:
                self.canvas.set_tool("text")
                return True
            if event.key() == Qt.Key.Key_E:
                self.canvas.set_tool("arrow")
                return True
            if event.key() == Qt.Key.Key_J:
                self.canvas.set_tool("benzene")
                return True
        if modifiers == Qt.KeyboardModifier.ShiftModifier and event.key() == Qt.Key.Key_G:
            self.canvas.set_tool("ts_bracket")
            return True
        if modifiers == Qt.KeyboardModifier.AltModifier and event.key() == Qt.Key.Key_D:
            self.canvas.set_tool("perspective")
            return True
        return False

    def handle_atom_hotkey(self, event, atom_id: int) -> bool:
        if atom_id not in self.canvas.model.atoms:
            return False
        modifiers = self.canvas._shortcut_modifiers(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.canvas.prompt_atom_label(atom_id)
            return True
        text = event.text()
        if not text:
            return False
        if text == "+":
            self.canvas.add_mark_for_atom(atom_id, self.canvas._atom_point(atom_id), kind="plus")
            return True
        if text == "-":
            self.canvas.add_mark_for_atom(atom_id, self.canvas._atom_point(atom_id), kind="minus")
            return True
        if text in self.LABEL_HOTKEYS:
            self.canvas._atom_label_service.add_or_update_atom_label(
                atom_id,
                self.LABEL_HOTKEYS[text],
                show_carbon=True,
            )
            return True
        if text in {"0", "1"}:
            self.canvas._sprout_bond_from_atom(atom_id, style="single", order=1, cyclic=text == "0")
            return True
        if text == "2":
            self.canvas._sprout_acetyl_from_atom(atom_id)
            return True
        if text in {"3", "a"}:
            self.canvas._sprout_benzene_from_atom(atom_id)
            return True
        if text == "4":
            self.canvas._sprout_bond_from_atom(atom_id, style="wedge", order=1)
            return True
        if text == "5":
            self.canvas._sprout_bond_from_atom(atom_id, style="hash", order=1)
            return True
        if text == "6":
            self.canvas._sprout_regular_ring_from_atom(atom_id, 6)
            return True
        if text == "7":
            self.canvas._sprout_regular_ring_from_atom(atom_id, 5)
            return True
        if text == "8":
            self.canvas._sprout_bond_from_atom(atom_id, style="double", order=2)
            return True
        if text == "z":
            self.canvas._sprout_bond_from_atom(atom_id, style="triple", order=3)
            return True
        if text == "v":
            self.canvas._sprout_regular_ring_from_atom(atom_id, 3)
            return True
        if text == "u":
            self.canvas._sprout_regular_ring_from_atom(atom_id, 4)
            return True
        return False

    def handle_bond_hotkey(self, event, bond_id: int) -> bool:
        if not (0 <= bond_id < len(self.canvas.model.bonds)) or self.canvas.model.bonds[bond_id] is None:
            return False
        modifiers = self.canvas._shortcut_modifiers(event)
        if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
            return False
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            if event.key() == Qt.Key.Key_B:
                self.canvas.apply_bond_style(bond_id, "bold_in", 2)
                return True
            if event.key() == Qt.Key.Key_H:
                self.canvas.apply_bond_style(bond_id, "hash", 1)
                return True
        text = event.text()
        if text == "1":
            self.canvas.apply_bond_style(bond_id, "single", 1)
            return True
        if text == "2":
            self.canvas.apply_bond_style(bond_id, "double", 2)
            return True
        if text == "3":
            self.canvas.apply_bond_style(bond_id, "triple", 3)
            return True
        if text == "b":
            self.canvas.apply_bond_style(bond_id, "bold_in", 1)
            return True
        if text == "w":
            self.canvas.apply_bond_style(bond_id, "wedge", 1)
            return True
        if text == "h":
            self.canvas.apply_bond_style(bond_id, "hash", 1)
            return True
        if text == "a":
            self.canvas._fuse_benzene_to_bond(bond_id)
            return True
        if text in {"4", "5", "6", "7", "8"}:
            self.canvas._fuse_regular_ring_to_bond(bond_id, int(text))
            return True
        if text in {"9", "0"}:
            self.canvas._fuse_chair_to_bond(bond_id, mirrored=text == "0")
            return True
        return False


def canvas_chemdraw_shortcut_service_for(canvas) -> CanvasChemdrawShortcutService:
    return canvas._chemdraw_shortcut_service


__all__ = ["CanvasChemdrawShortcutService", "canvas_chemdraw_shortcut_service_for"]
