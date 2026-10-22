"""Deleting visible artwork removes its hidden native fallback graphics."""

import xml.etree.ElementTree as ET
from copy import deepcopy

import pytest

from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document


def drawing(extra=""):
    return (
        '<CDXML><page id="1" BoundingBox="0 0 300 200">'
        '<graphic id="8" SupersededBy="9" GraphicType="Line"/>'
        '<group id="2"><graphic id="9" SupersededBy="10" GraphicType="Line"/>'
        '<arrow id="10" Head3D="100 50 0" Tail3D="20 50 0" ArrowheadHead="Full"/>'
        '<graphic id="11" SupersededBy="12" GraphicType="Line"/>'
        '<arrow id="12" Head3D="100 100 0" Tail3D="20 100 0" ArrowheadHead="Full"/>'
        f"</group>{extra}</page></CDXML>"
    ).encode()


def delete_arrow(state, identity="10"):
    bindings = state["cdxml_source"]["items"]["arrows"]
    index = bindings.index(identity)
    bindings.pop(index)
    state["arrows"].pop(index)


def test_delete_removes_only_target_and_transitive_fallbacks():
    state = parse_cdxml_document(drawing(), preserve_source=True).state
    original = deepcopy(state)
    delete_arrow(state)
    before_save = deepcopy(state)
    raw = update_native_document(state)
    root = ET.fromstring(raw)
    assert {e.get("id") for e in root.iter() if e.get("id")} == {"1", "2", "11", "12"}
    assert state == before_save
    old = ET.fromstring(drawing())
    for identity in ("11", "12"):
        assert ET.tostring(root.find(f'.//*[@id="{identity}"]')) == ET.tostring(
            old.find(f'.//*[@id="{identity}"]')
        )
    reopened = parse_cdxml_document(raw, preserve_source=True).state
    assert reopened["cdxml_source"]["items"]["arrows"] == ["12"]
    assert update_native_document(reopened) == raw
    # Undo restores both the visible target and its original fallback chain.
    assert ET.canonicalize(
        update_native_document(original).decode()
    ) == ET.canonicalize(drawing().decode())


@pytest.mark.parametrize("target", ["8", "9", "10"])
def test_reaction_reference_to_deleted_alias_or_target_is_pruned(target):
    raw = drawing(
        f'<scheme id="20"><step id="21" ReactionStepArrows="{target} 12" '
        f'ReactionStepObjectsAboveArrow="{target}" '
        'ReactionStepObjectsBelowArrow="12"/></scheme>'
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    delete_arrow(state)
    root = ET.fromstring(update_native_document(state))
    assert root.find(".//step").attrib == {
        "id": "21",
        "ReactionStepArrows": "12",
        "ReactionStepObjectsBelowArrow": "12",
    }


def test_no_deletion_preserves_aliases_exactly():
    raw = drawing()
    state = parse_cdxml_document(raw, preserve_source=True).state
    assert ET.canonicalize(update_native_document(state).decode()) == ET.canonicalize(
        raw.decode()
    )


def test_fallback_chemical_annotation_is_not_silently_discarded():
    raw = drawing().replace(
        b'<graphic id="9" SupersededBy="10" GraphicType="Line"/>',
        b'<graphic id="9" SupersededBy="10" GraphicType="Line">'
        b'<represent attribute="Charge" object="30"/></graphic>',
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    delete_arrow(state)
    with pytest.raises(ValueError, match="chemical annotation"):
        update_native_document(state)


def test_references_to_deleted_descendants_are_not_left_dangling():
    raw = drawing('<scheme id="20"><step id="21" BasisObjects="13"/></scheme>')
    raw = raw.replace(
        b'ArrowheadHead="Full"/>',
        b'ArrowheadHead="Full"><annotation id="13" Keyword="Name" Content="arrow"/></arrow>',
        1,
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    delete_arrow(state)
    with pytest.raises(ValueError, match="BasisObjects"):
        update_native_document(state)


def test_save_reopen_and_failed_save_preserve_destination(tmp_path):
    from chemvas.bootstrap.document_cli_shared import offscreen_canvas
    from chemvas.features.document_files import read_document

    state = parse_cdxml_document(drawing(), preserve_source=True).state
    delete_arrow(state)
    path = tmp_path / "drawing.cdxml"
    with offscreen_canvas(state, command="test-delete-save") as (_, service):
        service.save_to_file(str(path))
        loaded = read_document(path).state
        assert len(loaded["arrows"]) == 1
        service.apply_state(loaded)
        service.save_to_file(str(path))
        assert len(read_document(path).state["arrows"]) == 1
        saved = path.read_bytes()
        blocked = parse_cdxml_document(
            drawing('<scheme id="20"><step id="21" BasisObjects="9"/></scheme>'),
            preserve_source=True,
        ).state
        delete_arrow(blocked)
        service.apply_state(blocked)
        with pytest.raises(ValueError, match="BasisObjects"):
            service.save_to_file(str(path))
        assert path.read_bytes() == saved
