"""Component selections owned by the reaction editor, independently of widgets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chemvas.domain.document import CalculationEndpointRole, CalculationStateMember

if TYPE_CHECKING:
    from chemvas.domain.document.inspection import ComponentSummary


@dataclass
class EndpointComponentChoice:
    inclusion: str = "unused"
    role: str = ""


class EndpointSelectionDraft:
    def __init__(self, components: tuple[ComponentSummary, ...]) -> None:
        self.components = components
        self.choices = {
            (side, row): EndpointComponentChoice(role=side)
            for side in ("reactant", "product")
            for row in range(len(components))
        }

    def set_inclusion(self, side: str, row: int, inclusion: str) -> None:
        choice = self.choices[side, row]
        choice.inclusion = inclusion
        if inclusion == "context_only" and choice.role == side:
            choice.role = "spectator"

    def side_locked(self, side: str, row: int) -> bool:
        choice = self.choices[side, row]
        if choice.inclusion == "context_only":
            return False
        opposite = "product" if side == "reactant" else "reactant"
        other = self.choices[opposite, row]
        return (
            other.inclusion != "unused"
            and other.role == opposite
            and not (choice.inclusion != "unused" and choice.role == side)
        )

    def members_and_roles(
        self, side: str
    ) -> tuple[tuple[CalculationStateMember, ...], tuple[CalculationEndpointRole, ...]]:
        members = []
        roles = []
        for row, component in enumerate(self.components):
            choice = self.choices[side, row]
            if choice.inclusion == "unused" or self.side_locked(side, row):
                continue
            members.append(CalculationStateMember(component.atom_ids, choice.inclusion))
            roles.append(CalculationEndpointRole(component.atom_ids, choice.role))
        return tuple(members), tuple(roles)

    def modeled_charge(self, side: str) -> int:
        return sum(
            component.formal_charge
            for row, component in enumerate(self.components)
            if self.choices[side, row].inclusion == "included"
            and not self.side_locked(side, row)
        )
