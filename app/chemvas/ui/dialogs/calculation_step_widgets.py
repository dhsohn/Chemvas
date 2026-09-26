"""Small widgets and collaborator protocols used by the calculation step dialog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, override

from PyQt6.QtWidgets import (
    QComboBox,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from PyQt6.QtGui import QInputMethodEvent

    from chemvas.domain.chemistry_types import RDKitResult


@dataclass(frozen=True)
class _EndpointWidgets:
    state_id: QLineEdit
    charge: QSpinBox
    multiplicity: QSpinBox


@dataclass(frozen=True)
class CanvasMappingSnapshot:
    """Detached drawing data; selection and mapping mutations stay in the editor."""

    atoms: tuple[tuple[int, float, float], ...]
    pairs: tuple[tuple[int, int], ...]
    reactant_ids: frozenset[int]
    product_ids: frozenset[int]
    changed_bonds: tuple[tuple[int, int], ...]
    selected_reactant: int | None


class _MappingHighlighter(Protocol):
    def show_atom_labels(
        self,
        reactant_atom_ids: Iterable[int],
        product_atom_ids: Iterable[int],
        excluded_atom_ids: Iterable[int] = (),
    ) -> None: ...

    def clear_all(self) -> None: ...


class _CorrespondenceSuggester(Protocol):
    def __call__(
        self,
        reactant_atom_ids: frozenset[int],
        product_atom_ids: frozenset[int],
        existing_correspondence: Mapping[int, int],
    ) -> RDKitResult[list[tuple[int, int]]]: ...


class _NoInputMethodTableWidget(QTableWidget):
    """Table that ignores input-method composition outright.

    Neither dialog table takes text input: cells are read-only items or
    persistent combo widgets. QAbstractItemView still reacts to a
    QInputMethodEvent by starting or focusing an editor for the current
    cell, and for cells hosting a widget, edit() focuses that widget
    before consulting the edit triggers — so NoEditTriggers alone does
    not stop it. On Wayland (WSLg) each such focus change makes the
    text-input integration re-deliver the composition event, and the
    mutual recursion overflows the C stack; an active Korean IME crashed
    the app this way twice. Dropping the event here removes the app-side
    entry point of that recursion for every cell kind.
    """

    @override
    def inputMethodEvent(self, event: QInputMethodEvent | None) -> None:
        if event is not None:
            event.ignore()


class _MappingProductCombo(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # A structure with many same-element atoms gives this combo a long
        # candidate list. Qt otherwise ignores maxVisibleItems and shows every
        # item in one over-tall popup with no scrollbar, so the lower atoms run
        # off-screen and the wheel has nothing to scroll; disabling the native
        # combobox popup restores the capped, scrollable list.
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")
        self.setMaxVisibleItems(12)
