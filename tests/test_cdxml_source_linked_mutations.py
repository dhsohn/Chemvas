"""Domain owners keep annotation arrays and native link arrays coupled."""

from __future__ import annotations

from copy import deepcopy

import pytest

from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.cdxml_source import (
    append_unbound_note,
    promote_linked_images_to_arrows,
)
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_editable_arrows import promote_snapshot_arrows
from chemvas.features.cdxml_graphics import graphic_image
from chemvas.features.cdxml_preservation import PreservingImporter
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch

SOURCE_HASH = "a" * 64


def _note(text: str = "caption", *, x: float = 1, y: float = 2) -> dict:
    return {"x": x, "y": y, "text": text}


def _source_state(
    *,
    notes: list[dict] | None = None,
    note_links: list[str | None] | object = ...,
    groups: list[dict] | None = None,
) -> dict:
    notes = notes or []
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [{"id": 0, "element": "C", "x": 0, "y": 0}],
            "bonds": [],
            "notes": notes,
        }
    )
    state["groups"] = deepcopy(groups or [])
    items: dict[str, list[str | None]] = {}
    native_objects = ['<n id="n0" p="0 0" Element="6"/>']
    if note_links is not ...:
        typed_links = list(note_links)  # type: ignore[arg-type]
        items["notes"] = typed_links
        for link in typed_links:
            if link is not None:
                native_objects.append(f'<t id="{link}" p="10 20"><s>x</s></t>')
    baseline = {key: deepcopy(value) for key, value in state.items()}
    state["cdxml_source"] = {
        "xml": '<CDXML><page id="1">' + "".join(native_objects) + "</page></CDXML>",
        "offset": [0.0, 0.0],
        "atoms": {"0": "n0"},
        "bonds": {},
        "items": items,
        "baseline_items": deepcopy(items),
        "baseline": baseline,
    }
    return state


def test_append_unbound_note_without_source_only_extends_notes() -> None:
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 2,
            "atoms": [{"id": 0, "element": "C", "x": 0, "y": 0}],
            "bonds": [],
            "notes": [_note("existing")],
        }
    )
    state["groups"] = [{"atoms": [0], "items": [["notes", 0]]}]
    before_groups = deepcopy(state["groups"])
    index = append_unbound_note(state, _note("added"))
    assert index == 1
    assert [note["text"] for note in state["notes"]] == ["existing", "added"]
    assert state["groups"] == before_groups
    assert "cdxml_source" not in state


def test_append_unbound_note_materializes_omitted_links_and_leaves_baseline() -> None:
    state = _source_state(notes=[_note("a"), _note("b")], note_links=...)
    baseline_before = deepcopy(state["cdxml_source"]["baseline"])
    baseline_items_before = deepcopy(state["cdxml_source"]["baseline_items"])
    groups_before = deepcopy(state["groups"])
    index = append_unbound_note(state, _note("c"))
    assert index == 2
    assert state["cdxml_source"]["items"]["notes"] == [None, None, None]
    assert state["cdxml_source"]["baseline"] == baseline_before
    assert state["cdxml_source"]["baseline_items"] == baseline_items_before
    assert state["groups"] == groups_before


def test_append_unbound_note_extends_existing_links() -> None:
    state = _source_state(
        notes=[_note("a")],
        note_links=["10"],
        groups=[{"atoms": [], "items": [["notes", 0]]}],
    )
    xml_before = state["cdxml_source"]["xml"]
    index = append_unbound_note(state, _note("b"))
    assert index == 1
    assert state["cdxml_source"]["items"]["notes"] == ["10", None]
    assert state["cdxml_source"]["xml"] is xml_before
    assert state["groups"] == [{"atoms": [], "items": [["notes", 0]]}]


def test_append_unbound_note_rejects_length_mismatch_without_partial_change() -> None:
    state = _source_state(notes=[_note("a"), _note("b")], note_links=["10"])
    before = deepcopy(state)
    with pytest.raises(ValueError, match="notes bindings"):
        append_unbound_note(state, _note("c"))
    assert state == before


def test_document_patch_add_note_uses_shared_owner_with_source() -> None:
    state = _source_state(notes=[_note("existing")], note_links=["10"])
    original = deepcopy(state)
    result = apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": SOURCE_HASH,
            "operations": [
                {
                    "op": "add_note",
                    "note_index": 1,
                    "note": {"x": 3, "y": 4, "text": "patched"},
                }
            ],
        },
        source_sha256=SOURCE_HASH,
        document_version=CANVAS_FILE_VERSION,
    )
    candidate = result.payload["state"]
    assert candidate["notes"][1]["text"] == "patched"
    assert candidate["cdxml_source"]["items"]["notes"] == ["10", None]
    assert candidate["cdxml_source"]["baseline"] == state["cdxml_source"]["baseline"]
    assert state == original


def _legacy_image_state(*, move: bool = False) -> dict:
    raw = (
        b'<CDXML LineWidth="0.75"><page id="1" BoundingBox="0 0 400 300">'
        b'<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" ArrowheadHead="Full"/>'
        b'<scheme id="20"><step id="21" ReactionStepArrows="10"/></scheme>'
        b"</page></CDXML>"
    )
    reader = PreservingImporter(raw.decode())
    state = reader.state()
    image = graphic_image(reader, reader.root.find(".//arrow"))
    retained = {
        "kind": "line",
        "start": [-50.0, -20.0],
        "end": [-10.0, -20.0],
        "color": "#000000",
    }
    state["arrows"] = [retained]
    state["images"] = [image]
    state["groups"] = [{"atoms": [], "items": [["arrows", 0], ["images", 0]]}]
    source = state["cdxml_source"]
    source["items"] = {"arrows": [None], "images": ["10"], "notes": []}
    source["baseline_items"] = {
        "arrows": [],
        "images": ["10"],
        "notes": [],
    }
    baseline = deepcopy(
        {key: value for key, value in state.items() if key != "cdxml_source"}
    )
    baseline["arrows"] = []
    baseline["images"] = [deepcopy(image)]
    baseline["groups"] = [{"atoms": [], "items": [["images", 0]]}]
    source["baseline"] = baseline
    if move:
        image["x"] += 20
        image["y"] += 10
        image["width"] *= 2
    return state


def test_mixed_promotion_keeps_existing_arrows_retained_images_and_group_refs() -> None:
    state = _legacy_image_state(move=True)
    decorative = {
        "data_base64": state["images"][0]["data_base64"],
        "x": 5.0,
        "y": 6.0,
        "width": 7.0,
        "height": 8.0,
        "opacity": 1.0,
    }
    state["images"].append(decorative)
    state["cdxml_source"]["items"]["images"].append(None)
    state["groups"][0]["items"].append(["images", 1])
    baseline = state["cdxml_source"]["baseline"]
    baseline["images"].append(deepcopy(decorative))
    state["cdxml_source"]["baseline_items"]["images"].append(None)
    baseline["groups"] = [{"atoms": [], "items": [["images", 0], ["images", 1]]}]

    promote_snapshot_arrows(state)

    assert len(state["images"]) == 1
    assert state["images"][0]["x"] == decorative["x"]
    assert state["cdxml_source"]["items"]["images"] == [None]
    assert state["cdxml_source"]["items"]["arrows"] == [None, "10"]
    assert state["arrows"][0]["start"] == [-50.0, -20.0]
    assert state["arrows"][1]["start"][1] == pytest.approx(-90)
    assert state["groups"] == [
        {"atoms": [], "items": [["arrows", 0], ["arrows", 1], ["images", 0]]}
    ]
    baseline = state["cdxml_source"]["baseline"]
    assert baseline["images"] == [decorative]
    assert state["cdxml_source"]["baseline_items"]["images"] == [None]
    assert state["cdxml_source"]["baseline_items"]["arrows"] == ["10"]
    assert baseline["groups"] == [
        {"atoms": [], "items": [["arrows", 0], ["images", 0]]}
    ]


def test_live_and_baseline_can_promote_in_different_image_orders() -> None:
    state = _legacy_image_state()
    other = {
        "data_base64": state["images"][0]["data_base64"],
        "x": 1.0,
        "y": 2.0,
        "width": 3.0,
        "height": 4.0,
        "opacity": 1.0,
    }
    state["images"] = [other, state["images"][0]]
    state["cdxml_source"]["items"]["images"] = [None, "10"]
    state["groups"] = [{"atoms": [], "items": [["images", 1]]}]
    baseline = state["cdxml_source"]["baseline"]
    baseline["images"] = [deepcopy(state["images"][1]), other]
    state["cdxml_source"]["baseline_items"]["images"] = ["10", None]
    baseline["groups"] = [{"atoms": [], "items": [["images", 0]]}]

    promote_snapshot_arrows(state)

    assert state["cdxml_source"]["items"]["images"] == [None]
    assert state["cdxml_source"]["items"]["arrows"][-1] == "10"
    assert state["cdxml_source"]["baseline_items"]["images"] == [None]
    assert state["cdxml_source"]["baseline_items"]["arrows"] == ["10"]
    assert state["groups"] == [{"atoms": [], "items": [["arrows", 1]]}]
    assert state["cdxml_source"]["baseline"]["groups"] == [
        {"atoms": [], "items": [["arrows", 0]]}
    ]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda image: image.__setitem__("data_base64", "changed"), id="raster"
        ),
        pytest.param(lambda image: image.__setitem__("opacity", 0.5), id="opacity"),
    ],
)
def test_changed_raster_or_opacity_is_not_promoted(mutate) -> None:
    state = _legacy_image_state()
    mutate(state["images"][0])
    before = deepcopy(state)
    promote_snapshot_arrows(state)
    assert state == before


def test_unsupported_stroke_remains_an_image() -> None:
    raw = (
        b'<CDXML><page id="1" BoundingBox="0 0 400 300">'
        b'<arrow id="10" Tail3D="20 50 0" Head3D="100 50 0" Center3D="60 50 0" AngularSize="180"/>'
        b"</page></CDXML>"
    )
    state = parse_cdxml_document(raw, preserve_source=True).state
    assert state["arrows"] == []
    assert len(state["images"]) == 1
    before = deepcopy(state)
    promote_snapshot_arrows(state)
    assert state == before


def test_repeated_promotion_is_a_noop() -> None:
    state = _legacy_image_state(move=True)
    promote_snapshot_arrows(state)
    after_first = deepcopy(state)
    promote_snapshot_arrows(state)
    assert state == after_first


def test_failed_second_projection_leaves_entire_state_unchanged() -> None:
    state = _legacy_image_state()
    state["cdxml_source"]["baseline_items"]["images"] = []
    before = deepcopy(state)
    with pytest.raises(ValueError):
        promote_linked_images_to_arrows(
            state,
            {
                "10": {
                    "live": {
                        "kind": "arrow",
                        "start": [0.0, 0.0],
                        "end": [1.0, 0.0],
                        "color": "#000000",
                    },
                    "baseline": {
                        "kind": "arrow",
                        "start": [0.0, 0.0],
                        "end": [1.0, 0.0],
                        "color": "#000000",
                    },
                }
            },
        )
    assert state == before
