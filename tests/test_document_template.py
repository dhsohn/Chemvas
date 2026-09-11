from __future__ import annotations

import math
from copy import deepcopy

import pytest

from chemvas.bootstrap.document_template import (
    insert_template,
    validate_template_request,
)
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.features.document_composition import compose_document_state

SOURCE_HASH = "a" * 64


@pytest.fixture(scope="module", autouse=True)
def application():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["template-test"])
    yield app


def _state():
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "C", "x": 0, "y": 0},
                {"id": 1, "element": "C", "x": 40, "y": 0},
            ],
            "bonds": [{"a": 0, "b": 1, "order": 1}],
            "notes": [{"text": "unchanged 12.30", "x": 250, "y": 200}],
        }
    )


def _request(style="benzene", anchor=None):
    return {
        "format": "chemvas-template-insertion",
        "version": 1,
        "source_sha256": SOURCE_HASH,
        "ring_size": 6,
        "style": style,
        "position": [200, 200],
        "anchor": anchor or {"kind": "free"},
    }


@pytest.mark.parametrize("size", [4, 5, 6])
@pytest.mark.parametrize("bond_style", ["double", "double_center", "double_outer"])
def test_regular_ring_fuses_to_plain_double_without_rewriting_anchor(size, bond_style):
    state = _state()
    state["model"]["bonds"][0].update(order=2, style=bond_style)
    before = deepcopy(state)
    raw = _request("regular", {"kind": "bond", "a": 0, "b": 1})
    raw["ring_size"] = size
    request = validate_template_request(state, raw, source_sha256=SOURCE_HASH)
    candidate, added = insert_template(state, request)
    assert state == before
    assert len(added) == size - 2
    assert candidate["model"]["bonds"][0] == before["model"]["bonds"][0]
    assert candidate["model"]["atoms"][0] == before["model"]["atoms"][0]
    assert candidate["model"]["atoms"][1] == before["model"]["atoms"][1]
    assert len(candidate["ring_fills"]) == 1
    build_document_payload(candidate, CANVAS_FILE_VERSION)


@pytest.mark.parametrize("style", ["regular", "benzene", "chair", "chair_flip", "boat"])
@pytest.mark.parametrize("anchor", [{"kind": "free"}, {"kind": "bond", "a": 0, "b": 1}])
def test_native_insertion_adds_exact_ring_and_preserves_source(style, anchor):
    state = _state()
    before = deepcopy(state)
    request = validate_template_request(
        state, _request(style, anchor), source_sha256=SOURCE_HASH
    )
    candidate, added = insert_template(state, request)
    assert state == before
    assert len(added) == (6 if anchor["kind"] == "free" else 4)
    assert candidate["model"]["bonds"][:1] == state["model"]["bonds"]
    assert candidate["model"]["atoms"][0] == state["model"]["atoms"][0]
    assert candidate["model"]["atoms"][1] == state["model"]["atoms"][1]
    assert candidate["notes"] == state["notes"]
    assert candidate["settings"] == state["settings"]
    assert len(candidate["ring_fills"]) == 1
    ring = candidate["ring_fills"][0]
    assert len(ring["atom_ids"]) == 6
    assert set(added).issubset(ring["atom_ids"])
    assert len(candidate["model"]["bonds"]) == (7 if anchor["kind"] == "free" else 6)
    assert sum(b["order"] == 2 for b in candidate["model"]["bonds"]) == (
        3 if style == "benzene" else 0
    )
    if style in {"regular", "benzene"}:
        lengths = [
            math.dist(ring["points"][i], ring["points"][(i + 1) % 6]) for i in range(6)
        ]
        assert lengths == pytest.approx([lengths[0]] * 6)
    build_document_payload(candidate, CANVAS_FILE_VERSION)


@pytest.mark.parametrize("style", ["regular", "benzene"])
def test_atom_anchor_and_repeat_are_deterministic(style):
    state = _state()
    request = validate_template_request(
        state,
        _request(style, {"kind": "atom", "atom_id": 1}),
        source_sha256=SOURCE_HASH,
    )
    first, added = insert_template(state, request)
    second, repeated = insert_template(state, request)
    assert first == second
    assert added == repeated == [2, 3, 4, 5, 6]
    assert first["ring_fills"][0]["atom_ids"].count(1) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"version": 2},
        {"source_sha256": "b" * 64},
        {"ring_size": True},
        {"ring_size": 2},
        {"ring_size": 13},
        {"ring_size": 5},
        {"style": "smiles"},
        {"style": "BENZENE"},
        {"position": [True, 0]},
        {"position": [float("nan"), 0]},
        {"position": [1e7, 0]},
        {"position": [1]},
        {"anchor": {"kind": "free", "atom_id": 1}},
        {"anchor": {"kind": "atom", "atom_id": True}},
        {"anchor": {"kind": "atom", "atom_id": 999}},
        {"anchor": {"kind": "bond", "a": 1, "b": 1}},
        {"style": "chair", "anchor": {"kind": "atom", "atom_id": 1}},
        {"unknown": True},
    ],
)
def test_request_refuses_unsupported_or_unpinned_values(change):
    with pytest.raises(ValueError):
        validate_template_request(
            _state(), {**_request(), **change}, source_sha256=SOURCE_HASH
        )


@pytest.mark.parametrize("case", ["plan", "perspective", "stereo", "group", "triple"])
def test_insertion_rejects_unsupported_semantics_before_canvas(case, monkeypatch):
    from chemvas.bootstrap import document_template

    state = _state()
    if case == "plan":
        state["calculation_plan"] = {}
    elif case == "perspective":
        state["perspective"] = {"atom_coords_3d": {0: [0, 0, 0]}}
    elif case == "stereo":
        state["model"]["bonds"][0]["style"] = "hash"
    elif case == "group":
        state["groups"] = [{"atoms": [0, 1], "items": []}]
    else:
        state["model"]["bonds"][0].update(order=3, style="triple")
    monkeypatch.setattr(
        document_template,
        "offscreen_canvas",
        lambda *a, **k: pytest.fail("must reject before Qt"),
    )
    before = deepcopy(state)
    with pytest.raises(ValueError):
        validate_template_request(
            state,
            _request(anchor={"kind": "bond", "a": 0, "b": 1}),
            source_sha256=SOURCE_HASH,
        )
    assert state == before


def test_free_insertion_preserves_existing_group_and_ring_metadata():
    state = _state()
    state["groups"] = [{"atoms": [0, 1], "items": [["notes", 0]]}]
    first, _ = insert_template(
        state, validate_template_request(state, _request(), source_sha256=SOURCE_HASH)
    )
    raw = {**_request(), "position": [400, 400]}
    second, _ = insert_template(
        first, validate_template_request(first, raw, source_sha256=SOURCE_HASH)
    )
    assert second["groups"] == state["groups"]
    assert second["ring_fills"][:1] == first["ring_fills"]


def test_insertion_preserves_existing_charge_stereo_and_heteroatom_records():
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": 0, "element": "P", "formal_charge": 1, "x": 0, "y": 0},
                {"id": 1, "element": "O", "formal_charge": -1, "x": 40, "y": 0},
            ],
            "bonds": [
                {"a": 0, "b": 1, "order": 1, "style": "hash", "color": "#123456"}
            ],
        }
    )
    before = deepcopy(state)
    candidate, added = insert_template(
        state, validate_template_request(state, _request(), source_sha256=SOURCE_HASH)
    )
    assert len(added) == 6
    assert candidate["marks"] == before["marks"]
    assert candidate["model"]["atom_annotations"] == before["model"]["atom_annotations"]
    assert candidate["model"]["bonds"][:1] == before["model"]["bonds"]
    assert state == before


@pytest.mark.parametrize("size", [3, 12])
def test_regular_ring_size_boundaries(size):
    state = _state()
    request = {**_request("regular"), "ring_size": size}
    candidate, added = insert_template(
        state, validate_template_request(state, request, source_sha256=SOURCE_HASH)
    )
    assert len(added) == size
    points = candidate["ring_fills"][0]["points"]
    lengths = [math.dist(points[i], points[(i + 1) % size]) for i in range(size)]
    assert lengths == pytest.approx([lengths[0]] * size)


def test_source_coordinate_bounds_reject_before_canvas():
    state = _state()
    state["model"]["atoms"][0]["x"] = 1e30
    with pytest.raises(ValueError, match="coordinate bounds"):
        validate_template_request(state, _request(), source_sha256=SOURCE_HASH)


def test_resource_limit_precedes_canvas(monkeypatch):
    from chemvas.bootstrap import document_template

    monkeypatch.setattr(document_template, "MAX_GRAPHICS_RECORDS", 10)
    with pytest.raises(ValueError, match="graphics-record"):
        validate_template_request(_state(), _request(), source_sha256=SOURCE_HASH)


@pytest.mark.parametrize("fault", ["raise", "old_atom", "extra_atom"])
def test_partial_native_mutation_is_discarded_and_never_changes_source(
    monkeypatch, fault
):
    from chemvas.ui import insert_template_commit_service
    from chemvas.ui.canvas_model_access import model_for

    real_commit = insert_template_commit_service.apply_template_commit_resolution

    def damaged_commit(canvas, *args, **kwargs):
        result = real_commit(canvas, *args, **kwargs)
        if fault == "raise":
            raise RuntimeError("injected after native mutation")
        model = model_for(canvas)
        if fault == "old_atom":
            model.atoms[0].x += 1
        else:
            model.add_atom("C", 500, 500)
        return result

    monkeypatch.setattr(
        insert_template_commit_service,
        "apply_template_commit_resolution",
        damaged_commit,
    )
    state = _state()
    before = deepcopy(state)
    request = validate_template_request(state, _request(), source_sha256=SOURCE_HASH)
    with pytest.raises((ValueError, RuntimeError)):
        insert_template(state, request)
    assert state == before


@pytest.mark.parametrize(
    "fault",
    [
        "remote_bond",
        "chord",
        "element",
        "coordinate",
        "bond_order",
        "bond_style",
        "bond_color",
    ],
)
def test_insertion_rejects_graph_that_differs_from_native_template_plan(
    monkeypatch, fault
):
    from chemvas.ui import insert_template_commit_service
    from chemvas.ui.canvas_model_access import model_for

    real_commit = insert_template_commit_service.apply_template_commit_resolution

    def damaged_commit(canvas, *args, **kwargs):
        result = real_commit(canvas, *args, **kwargs)
        model = model_for(canvas)
        added = sorted(set(model.atoms) - {0, 1})
        if fault == "remote_bond":
            model.add_bond(0, added[0], 1)
        elif fault == "chord":
            model.add_bond(added[0], added[3], 1)
        elif fault == "element":
            model.atoms[added[0]].element = "O"
        elif fault == "coordinate":
            model.atoms[added[0]].x += 1
        elif fault == "bond_order":
            model.bonds[1].order = 1
        elif fault == "bond_style":
            model.bonds[1].style = "double_outer"
        else:
            model.bonds[1].color = "#123456"
        return result

    monkeypatch.setattr(
        insert_template_commit_service,
        "apply_template_commit_resolution",
        damaged_commit,
    )
    state = _state()
    before = deepcopy(state)
    request = validate_template_request(state, _request(), source_sha256=SOURCE_HASH)
    with pytest.raises(ValueError, match="native template plan"):
        insert_template(state, request)
    assert state == before


@pytest.mark.parametrize("fault", ["membership", "color"])
def test_insertion_rejects_changed_ring_metadata(monkeypatch, fault):
    from PyQt6.QtGui import QBrush, QColor

    from chemvas.ui import insert_template_commit_service
    from chemvas.ui.canvas_scene_items_state import ring_items_for

    real_commit = insert_template_commit_service.apply_template_commit_resolution

    def damaged_commit(canvas, *args, **kwargs):
        result = real_commit(canvas, *args, **kwargs)
        ring = ring_items_for(canvas)[-1]
        if fault == "membership":
            ring.setData(2, list(reversed(ring.data(2))))
        else:
            ring.setBrush(QBrush(QColor("#123456")))
        return result

    monkeypatch.setattr(
        insert_template_commit_service,
        "apply_template_commit_resolution",
        damaged_commit,
    )
    state = _state()
    before = deepcopy(state)
    request = validate_template_request(state, _request(), source_sha256=SOURCE_HASH)
    with pytest.raises(
        ValueError, match="ring metadata differs from the native template plan"
    ):
        insert_template(state, request)
    assert state == before


@pytest.mark.parametrize("style", ["single", "double", "double_outer"])
@pytest.mark.parametrize("reversed_bond", [False, True])
@pytest.mark.parametrize("side", [-1, 1])
def test_benzene_bond_anchor_preserves_existing_direction_style_color(
    style, reversed_bond, side
):
    state = _state()
    bond = state["model"]["bonds"][0]
    bond.update(order=1 if style == "single" else 2, style=style, color="#123456")
    if reversed_bond:
        bond["a"], bond["b"] = bond["b"], bond["a"]
    raw = _request(anchor={"kind": "bond", "a": 0, "b": 1})
    raw["position"] = [20, side * 100]
    request = validate_template_request(state, raw, source_sha256=SOURCE_HASH)
    candidate, added = insert_template(state, request)
    assert len(added) == 4
    assert candidate["model"]["bonds"][0] == bond
    assert len(candidate["model"]["bonds"]) == 6
    assert sum(b["order"] == 2 for b in candidate["model"]["bonds"]) == 3
