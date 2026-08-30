from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from chemvas.domain.document.model import Bond, MoleculeModel


@dataclass(frozen=True)
class AliasAttachment:
    neighbor_element: str
    bond_order: int
    bond_style: str


@dataclass(frozen=True)
class AliasAttachmentInventory:
    bonds: tuple[Bond, ...]
    attachments_by_atom: Mapping[int, tuple[AliasAttachment, ...]]


@dataclass(frozen=True)
class AliasAttachmentContract:
    allowed_neighbor_elements: frozenset[str]
    bond_order: int = 1
    bond_style: str = "single"
    allow_electronic_annotations: bool = True


@dataclass(frozen=True)
class AtomAliasDefinition:
    fragment_smiles: str
    intrinsic_formal_charge: int = 0
    attachment_contract: AliasAttachmentContract | None = None


ATOM_ALIAS_DEFINITIONS: Final[Mapping[str, AtomAliasDefinition]] = MappingProxyType(
    {
        "Me": AtomAliasDefinition("[*:1]C"),
        "Et": AtomAliasDefinition("[*:1]CC"),
        "OH": AtomAliasDefinition("[*:1]O"),
        "Ph": AtomAliasDefinition("[*:1]c1ccccc1"),
        "PPh3": AtomAliasDefinition(
            "[*:1][P+](c1ccccc1)(c1ccccc1)c1ccccc1",
            intrinsic_formal_charge=1,
            attachment_contract=AliasAttachmentContract(
                allowed_neighbor_elements=frozenset({"C"}),
                allow_electronic_annotations=False,
            ),
        ),
        "OMe": AtomAliasDefinition("[*:1]OC"),
        "Boc": AtomAliasDefinition("[*:1]C(=O)OC(C)(C)C"),
        "CO2Me": AtomAliasDefinition("[*:1]C(=O)OC"),
        "t-Bu": AtomAliasDefinition("[*:1]C(C)(C)C"),
        "tBu": AtomAliasDefinition("[*:1]C(C)(C)C"),
        "i-Pr": AtomAliasDefinition("[*:1]C(C)C"),
        "CF3": AtomAliasDefinition("[*:1]C(F)(F)F"),
        "OTs": AtomAliasDefinition("[*:1]OS(=O)(=O)c1ccc(C)cc1"),
        "Ts": AtomAliasDefinition("[*:1]S(=O)(=O)c1ccc(C)cc1"),
        "OMs": AtomAliasDefinition("[*:1]OS(=O)(=O)C"),
        "Ms": AtomAliasDefinition("[*:1]S(=O)(=O)C"),
        "OTf": AtomAliasDefinition("[*:1]OS(=O)(=O)C(F)(F)F"),
        "Tf": AtomAliasDefinition("[*:1]S(=O)(=O)C(F)(F)F"),
        "Ns": AtomAliasDefinition("[*:1]S(=O)(=O)c1ccc(cc1)[N+](=O)[O-]"),
        "OAc": AtomAliasDefinition("[*:1]OC(C)=O"),
        "Ac": AtomAliasDefinition("[*:1]C(C)=O"),
    }
)


def alias_fragment_smiles() -> dict[str, str]:
    return {
        label: definition.fragment_smiles
        for label, definition in ATOM_ALIAS_DEFINITIONS.items()
    }


def alias_attachments_for_atom(
    model: MoleculeModel,
    atom_id: int,
) -> tuple[AliasAttachment, ...]:
    attachments: list[AliasAttachment] = []
    for bond in model.bonds:
        attachment = _alias_attachment_for_bond(model, atom_id, bond)
        if attachment is not None:
            attachments.append(attachment)
    return tuple(attachments)


def alias_attachment_inventory(model: MoleculeModel) -> AliasAttachmentInventory:
    """Index present bonds and every atom's attachment context in one traversal."""
    present_bonds: list[Bond] = []
    attachments: dict[int, list[AliasAttachment]] = {}
    for bond in model.bonds:
        if bond is None:
            continue
        present_bonds.append(bond)
        first = _alias_attachment_for_bond(model, bond.a, bond)
        if first is not None:
            attachments.setdefault(bond.a, []).append(first)
        if bond.b != bond.a:
            second = _alias_attachment_for_bond(model, bond.b, bond)
            if second is not None:
                attachments.setdefault(bond.b, []).append(second)
    return AliasAttachmentInventory(
        bonds=tuple(present_bonds),
        attachments_by_atom={
            atom_id: tuple(atom_attachments)
            for atom_id, atom_attachments in attachments.items()
        },
    )


def _alias_attachment_for_bond(
    model: MoleculeModel,
    atom_id: int,
    bond: Bond | None,
) -> AliasAttachment | None:
    if bond is None or (atom_id != bond.a and atom_id != bond.b):
        return None
    neighbor_id = bond.b if bond.a == atom_id else bond.a
    neighbor = model.atoms.get(neighbor_id)
    if neighbor is None:
        return None
    return AliasAttachment(
        neighbor_element=neighbor.element,
        bond_order=bond.order,
        bond_style=bond.style,
    )


def modeled_atom_formal_charge(
    label: str,
    annotation: Mapping[str, int] | None = None,
    *,
    atom_id: int,
    attachments: Sequence[AliasAttachment],
) -> int:
    attachment_error = alias_attachment_error(
        label,
        atom_id=atom_id,
        attachments=attachments,
        annotation=annotation,
    )
    if attachment_error is not None:
        raise ValueError(attachment_error)
    explicit_charge = int(annotation.get("formal_charge", 0)) if annotation else 0
    if explicit_charge:
        return explicit_charge
    definition = ATOM_ALIAS_DEFINITIONS.get(label)
    return definition.intrinsic_formal_charge if definition is not None else 0


def alias_attachment_error(
    label: str,
    *,
    atom_id: int,
    attachments: Sequence[AliasAttachment],
    annotation: Mapping[str, int] | None = None,
) -> str | None:
    definition = ATOM_ALIAS_DEFINITIONS.get(label)
    contract = definition.attachment_contract if definition is not None else None
    if contract is None:
        return None
    if len(attachments) != 1:
        return (
            f"Alias label '{label}' on atom {atom_id} requires exactly one attachment bond, "
            f"but found {len(attachments)}."
        )
    attachment = attachments[0]
    if (
        attachment.neighbor_element not in contract.allowed_neighbor_elements
        or attachment.bond_order != contract.bond_order
        or attachment.bond_style != contract.bond_style
    ):
        return (
            f"Alias label '{label}' on atom {atom_id} requires one ordinary single bond "
            "to carbon; found "
            f"{attachment.neighbor_element} attachment with order {attachment.bond_order} "
            f"and style '{attachment.bond_style}'."
        )
    if (
        not contract.allow_electronic_annotations
        and annotation is not None
        and any(key in annotation for key in ("formal_charge", "radical_electrons"))
    ):
        return (
            f"Alias label '{label}' on atom {atom_id} does not support explicit charge "
            "or radical annotations."
        )
    return None


__all__ = [
    "ATOM_ALIAS_DEFINITIONS",
    "AliasAttachment",
    "AliasAttachmentContract",
    "AliasAttachmentInventory",
    "AtomAliasDefinition",
    "alias_attachment_error",
    "alias_attachment_inventory",
    "alias_attachments_for_atom",
    "alias_fragment_smiles",
    "modeled_atom_formal_charge",
]
