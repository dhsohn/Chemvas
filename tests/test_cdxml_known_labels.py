"""Interpret only the labels covered by the native semantic witness."""

import xml.etree.ElementTree as ET

import pytest

from chemvas.domain.document import Atom, Bond
from chemvas.ui.export.export_cdxml import CdxmlLabelBinding
from tests.test_cdxml_export import _export_bound, _simple_state, _top_nodes

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.mark.parametrize("label", ["P", "O", "H", "Me", "tBu"])
def test_native_known_label_keeps_chemical_identity_and_original_text(label):
    raw, _ = _export_bound(
        _simple_state(
            atoms={0: Atom("C", 0, 0), 1: Atom(label, 30, 0)},
            bonds=[Bond(0, 1)],
        ),
        {},
    )
    root = ET.fromstring(raw)
    node = next(n for n in _top_nodes(root) if n.find("t") is not None)
    assert node.find("t").get("InterpretChemically") == "yes"
    assert "".join(node.find("t").itertext()) == label
    if label in {"Me", "tBu"}:
        assert node.get("NodeType") == "Nickname"
        assert node.find("fragment") is not None
    else:
        assert node.get("Element") == {"P": "15", "O": "8", "H": "1"}[label]
        assert node.find("fragment") is None
    assert "IgnoreWarnings" not in raw.decode()
    assert "AbnormalValence" not in raw.decode()


@pytest.mark.parametrize(
    "label,binding",
    [
        ("H\u1d43", CdxmlLabelBinding.element_identity("H")),
        ("Ar", CdxmlLabelBinding.aryl_fragment("Ph")),
        ("Ar", CdxmlLabelBinding.element_identity("Ar")),
        ("N", None),
        ("Ph", None),
    ],
)
def test_unproven_visible_spelling_does_not_gain_interpretation(label, binding):
    raw, _ = _export_bound(
        _simple_state(
            atoms={0: Atom("C", 0, 0), 1: Atom(label, 30, 0)},
            bonds=[Bond(0, 1)],
        ),
        {1: binding} if binding else {},
    )
    node = next(n for n in _top_nodes(ET.fromstring(raw)) if n.find("t") is not None)
    assert node.find("t").get("InterpretChemically") == "no"
    assert "".join(node.find("t").itertext()) == label
