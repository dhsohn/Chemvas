"""One meaning contract and one element table feed every CDXML label owner."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import fields

import pytest

from chemvas.domain.elements import ATOMIC_NUMBERS, ELEMENT_SYMBOLS, element_symbol
from chemvas.features.export.cdxml_label_bindings import (
    CDXML_LABEL_BINDING_MEANINGS,
    CdxmlLabelBindingEntry,
)
from chemvas.features.export.cdxml_label_meanings import (
    LABEL_BINDING_FIELD_NAMES,
    LABEL_BINDING_MEANING_FIELDS,
    SIDECAR_V1_LABEL_MEANINGS,
)
from chemvas.ui.export.export_cdxml import CdxmlLabelBinding


@pytest.mark.parametrize(
    "binding_type,identity_fields",
    [
        (CdxmlLabelBinding, {"meaning"}),
        (CdxmlLabelBindingEntry, {"atom_id", "expected_label", "meaning"}),
    ],
)
def test_binding_types_carry_exactly_the_contract_fields(binding_type, identity_fields):
    names = [field.name for field in fields(binding_type)]
    assert [name for name in names if name not in identity_fields] == list(
        LABEL_BINDING_FIELD_NAMES
    )


def test_every_meaning_uses_only_contract_fields():
    for meaning, required in LABEL_BINDING_MEANING_FIELDS.items():
        assert set(required) <= set(LABEL_BINDING_FIELD_NAMES), meaning


def test_sidecar_v1_is_the_contract_without_later_meanings():
    assert SIDECAR_V1_LABEL_MEANINGS <= set(LABEL_BINDING_MEANING_FIELDS)
    assert dict(CDXML_LABEL_BINDING_MEANINGS) == {
        meaning: LABEL_BINDING_MEANING_FIELDS[meaning]
        for meaning in SIDECAR_V1_LABEL_MEANINGS
    }


def test_element_table_numbers_symbols_from_hydrogen_to_oganesson():
    assert len(ELEMENT_SYMBOLS) == len(set(ELEMENT_SYMBOLS)) == 118
    assert ATOMIC_NUMBERS["H"] == 1
    assert ATOMIC_NUMBERS["C"] == 6
    assert ATOMIC_NUMBERS["Og"] == 118
    assert all(element_symbol(z) == symbol for symbol, z in ATOMIC_NUMBERS.items())
    assert element_symbol(0) is None
    assert element_symbol(119) is None
