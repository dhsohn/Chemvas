"""ChemDraw chemical-property captions open as plain text."""

import xml.etree.ElementTree as ET

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document

CAPTION = "Chemical Formula: CH4\nMolecular Weight: 16.0430"


def drawing() -> bytes:
    return (
        '<CDXML><page id="1" BoundingBox="0 0 300 200">'
        '<fragment id="2"><n id="3" p="50 50"/><n id="4" p="80 50"/>'
        '<b id="5" B="3" E="4"/></fragment>'
        '<t id="6" p="40 80"><s font="3" size="10">'
        f"{CAPTION}</s></t>"
        '<chemicalproperty id="7" ChemicalPropertyDisplayID="6" '
        'ChemicalPropertyIsActive="yes" ChemicalPropertyType="2 4" '
        'BasisObjects="3 4 5"/>'
        "</page></CDXML>"
    ).encode()


def delete(state, collection: str, identity: str) -> None:
    bindings = state["cdxml_source"]["items"][collection]
    index = bindings.index(identity)
    bindings.pop(index)
    state[collection].pop(index)


def test_property_caption_opens_as_note_and_link_round_trips():
    state = parse_cdxml_document(drawing()).state
    assert [note["text"] for note in state["notes"]] == [CAPTION]
    assert ET.canonicalize(update_native_document(state).decode()) == ET.canonicalize(
        drawing().decode()
    )


def test_deleting_caption_drops_the_link():
    state = parse_cdxml_document(drawing()).state
    delete(state, "notes", "6")
    root = ET.fromstring(update_native_document(state))
    assert root.find(".//t") is None
    assert root.find(".//chemicalproperty") is None


def test_deleting_a_basis_atom_keeps_caption_as_plain_text():
    state = parse_cdxml_document(drawing()).state
    atoms = state["model"]["atoms"]
    removed = next(k for k in atoms if state["cdxml_source"]["atoms"][str(k)] == "4")
    del atoms[removed]
    state["model"]["bonds"] = []
    root = ET.fromstring(update_native_document(state))
    assert root.find(".//chemicalproperty") is None
    assert "".join(root.find(".//t").itertext()) == CAPTION
