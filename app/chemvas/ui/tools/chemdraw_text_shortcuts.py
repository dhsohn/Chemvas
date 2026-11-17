"""ChemDraw hover-key decisions on normalized key text (Qt-free).

The canvas runs these decisions after its input adapter turns a key press into
text. Each collaborator is a narrow protocol naming only the operations a key
can trigger, so the decisions are testable without Qt events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Protocol

from chemvas.ui.tools.bond_tool_logic import BOND_SHORTCUT_KEYS, bond_shortcut_style

if TYPE_CHECKING:
    from collections.abc import Callable

    from chemvas.domain.document import MoleculeModel


class AtomLabelShortcutTarget(Protocol):
    def add_or_update_atom_label(
        self, atom_id: int, text: str, *, show_carbon: bool = False
    ) -> object: ...


class StructureShortcutTarget(Protocol):
    def sprout_bond_from_atom(
        self, atom_id: int, *, style: str, order: int, cyclic: bool = False
    ) -> object: ...

    def sprout_acetyl_from_atom(self, atom_id: int) -> object: ...

    def sprout_benzene_from_atom(self, atom_id: int) -> object: ...

    def sprout_dimethyl_from_atom(self, atom_id: int) -> object: ...

    def sprout_regular_ring_from_atom(self, atom_id: int, n: int) -> object: ...

    def fuse_benzene_to_bond(self, bond_id: int) -> object: ...

    def fuse_regular_ring_to_bond(self, bond_id: int, n: int) -> object: ...

    def fuse_chair_to_bond(self, bond_id: int, mirrored: bool = False) -> object: ...


class BondStyleShortcutTarget(Protocol):
    def apply_bond_style(self, bond_id: int, style: str, order: int) -> object: ...


class ChargeShortcutTarget(Protocol):
    def change_charge_for_atom(self, atom_id: int, delta: int) -> object: ...


class ChemdrawTextShortcuts:
    """What one normalized key does to a hovered atom or bond."""

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
        atom_labels: AtomLabelShortcutTarget,
        structure_build: StructureShortcutTarget,
        bond_styles: BondStyleShortcutTarget,
        notify_error: Callable[[str], object],
        charges: ChargeShortcutTarget | None = None,
    ) -> None:
        self._model = model_provider
        self.atom_labels = atom_labels
        self.structure_build = structure_build
        self.bond_styles = bond_styles
        self.notify_error = notify_error
        self.charges = charges

    def handle_atom_text(self, text: str, atom_id: int) -> bool:
        """Run the native atom-key decisions after an input adapter normalizes text."""
        if self._model().atom_for_id(atom_id) is None:
            return False
        if not text:
            return False
        if text in {"+", "-"}:
            if self.charges is not None:
                self.charges.change_charge_for_atom(atom_id, 1 if text == "+" else -1)
            return True
        if text in self.LABEL_HOTKEYS:
            self.atom_labels.add_or_update_atom_label(
                atom_id,
                self.LABEL_HOTKEYS[text],
                show_carbon=True,
            )
            return True
        build = self.structure_build
        if text in {"0", "1"}:
            build.sprout_bond_from_atom(
                atom_id, style="single", order=1, cyclic=text == "0"
            )
            return True
        if text == "2":
            build.sprout_acetyl_from_atom(atom_id)
            return True
        if text in {"3", "a"}:
            build.sprout_benzene_from_atom(atom_id)
            return True
        if text == "9":
            build.sprout_dimethyl_from_atom(atom_id)
            return True
        bonds = {
            "4": ("wedge", 1),
            "5": ("hash", 1),
            "8": ("double", 2),
            "z": ("triple", 3),
        }
        if text in bonds:
            style, order = bonds[text]
            build.sprout_bond_from_atom(atom_id, style=style, order=order)
            return True
        rings = {"6": 6, "7": 5, "v": 3, "u": 4}
        if text in rings:
            build.sprout_regular_ring_from_atom(atom_id, rings[text])
            return True
        return False

    def handle_bond_text(self, text: str, bond_id: int) -> bool:
        """Run the native bond-key decisions with either presentation adapter."""
        bond = self._model().bond_for_id(bond_id)
        if bond is None:
            return False
        try:
            style = bond_shortcut_style(bond, text)
        except ValueError as error:
            self.notify_error(str(error))
            return True
        if style is not None:
            self.bond_styles.apply_bond_style(bond_id, *style)
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


__all__ = [
    "AtomLabelShortcutTarget",
    "BondStyleShortcutTarget",
    "ChargeShortcutTarget",
    "ChemdrawTextShortcuts",
    "StructureShortcutTarget",
]
