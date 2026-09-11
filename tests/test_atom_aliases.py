from chemvas.domain.atom_aliases import (
    AliasAttachment,
    alias_attachment_inventory,
    alias_attachments_for_atom,
)
from chemvas.domain.document import Atom, Bond, MoleculeModel


def test_alias_attachments_preserve_model_bond_order_and_raw_bond_contract() -> None:
    model = MoleculeModel(
        atoms={
            3: Atom("C", 0.0, 0.0),
            7: Atom("PPh3", 1.0, 0.0),
            9: Atom("N", 2.0, 0.0),
            11: Atom("O", 3.0, 0.0),
            12: Atom("H", 4.0, 0.0),
        },
        bonds=[
            Bond(11, 12, order=1, style="single"),
            None,
            Bond(7, 999, order=3, style="triple"),
            Bond(3, 7, order=2, style="bold_in"),
            Bond(7, 9, order=1, style="hash"),
        ],
    )

    assert alias_attachments_for_atom(model, 7) == (
        AliasAttachment("C", 2, "bold_in"),
        AliasAttachment("N", 1, "hash"),
    )

    inventory = alias_attachment_inventory(model)
    assert inventory.bonds == tuple(bond for bond in model.bonds if bond is not None)
    assert inventory.attachments_by_atom[7] == alias_attachments_for_atom(model, 7)
    assert inventory.attachments_by_atom[11] == alias_attachments_for_atom(model, 11)


def test_terminal_hydrides_require_one_single_attachment_and_no_electronic_marks():
    from chemvas.domain.atom_aliases import alias_attachment_error

    for label in ("OH", "NH2", "SH"):
        single = AliasAttachment("C", 1, "single")
        for attachments in (
            (),
            (single, single),
            (AliasAttachment("C", 2, "double"),),
            (AliasAttachment("C", 3, "triple"),),
        ):
            error = alias_attachment_error(label, atom_id=7, attachments=attachments)
            assert error and label in error and "7" in error
        for annotation in (
            {"formal_charge": 1},
            {"formal_charge": -1},
            {"radical_electrons": 1},
        ):
            error = alias_attachment_error(
                label, atom_id=7, attachments=(single,), annotation=annotation
            )
            assert error and "charge" in error and "radical" in error
        for style in ("single", "wedge", "hash"):
            assert (
                alias_attachment_error(
                    label, atom_id=7, attachments=(AliasAttachment("C", 1, style),)
                )
                is None
            )


def test_abbreviations_reject_multiple_attachment_bond_orders():
    from chemvas.domain.atom_aliases import (
        ATOM_ALIAS_DEFINITIONS,
        alias_attachment_error,
    )

    for label in ATOM_ALIAS_DEFINITIONS:
        for order in (2, 3):
            error = alias_attachment_error(
                label,
                atom_id=7,
                attachments=(AliasAttachment("C", order, "single"),),
            )
            assert error and label in error and "7" in error and "single" in error
