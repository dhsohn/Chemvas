from __future__ import annotations

import math
import os
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, build_document_payload
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import content_bounds, export_item_closure
from chemvas.features.scheme_layout import LayoutRow, validate_layout_request
from chemvas.ui import scheme_layout_service
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_bond_graphics_state import bond_items_for
from chemvas.ui.canvas_document_state import document_item_lists_for
from chemvas.ui.canvas_group_state import group_state_for
from chemvas.ui.canvas_mark_registry import mark_registry_for
from chemvas.ui.canvas_model_access import model_for
from chemvas.ui.canvas_scene_items_state import ring_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_service_ports import history_service_for_access
from chemvas.ui.layout_qa_service import note_paint_scene_path
from chemvas.ui.scene_group_operations import expand_selection_to_groups_for
from chemvas.ui.scheme_layout_service import arrange_canvas

if TYPE_CHECKING:
    from pathlib import Path

_HASH = "a" * 64


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _state() -> dict[str, Any]:
    atoms = [
        {
            "id": index,
            "element": "C",
            "x": 150 + 30 * math.cos(index * math.pi / 3),
            "y": 100 + 30 * math.sin(index * math.pi / 3),
        }
        for index in range(6)
    ]
    atoms.extend(
        [
            {"id": 6, "element": "O", "x": 280, "y": 160, "formal_charge": -1},
            {"id": 7, "element": "C", "x": 310, "y": 180},
            {"id": 8, "element": "P", "x": 60, "y": 350},
            {"id": 9, "element": "Ph", "x": 130, "y": 350},
            {"id": 10, "element": "N", "x": 290, "y": 450},
            {"id": 11, "element": "O", "x": 290, "y": 400},
        ]
    )
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": atoms,
            "bonds": [
                {"a": index, "b": (index + 1) % 6, "order": 1} for index in range(6)
            ]
            + [{"a": index, "b": index + 1, "order": 1} for index in (6, 8, 10)],
            "notes": [
                {
                    "text": text,
                    "x": 200 + index * 7,
                    "y": 50 + index * 19,
                    "style": {"font_size": size, "color": "#214a88"},
                }
                for index, (text, size) in enumerate(
                    [
                        ("Reactant\nsecond line", 12),
                        ("G = 0", 10),
                        ("Transition structure", 24),
                        ("G = 1.5", 14),
                        ("Another row", 18),
                        ("E = 0", 10),
                        ("Product", 12),
                        ("E = -8.2", 20),
                        ("Unlisted source annotation", 15),
                    ]
                )
            ],
            "ring_fills": [
                {"atom_ids": list(range(6)), "color": "#aaffcc", "alpha": 0.3}
            ],
            "arrows": [
                {
                    "kind": "arrow",
                    "start": [200, 200],
                    "end": [250, 200],
                    "labels": {"above": "THF"},
                },
                {"kind": "equilibrium", "start": [200, 400], "end": [270, 400]},
            ],
            "ts_brackets": [
                {
                    "bracket_kind": "square_pair",
                    "left": 265,
                    "top": 145,
                    "right": 330,
                    "bottom": 190,
                }
            ],
            "shapes": [
                {
                    "shape_kind": "rect",
                    "left": 510,
                    "top": 510,
                    "right": 560,
                    "bottom": 550,
                    "stroke_style": "dashed",
                    "fill": "#ddeeff",
                    "fill_alpha": 0.2,
                }
            ],
        }
    )


def _request(state: dict[str, Any]):
    return validate_layout_request(
        state,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": _HASH,
            "gap": 12,
            "row_gap": 18,
            "caption_gap": 8,
            "line_gap": 5,
            "rows": [
                {
                    "blocks": [
                        {"atoms": list(range(6)), "captions": [0, 1], "anchor_atom": 0},
                        {
                            "atoms": [6, 7],
                            "captions": [2, 3],
                            "items": [["ts_brackets", 0]],
                            "anchor_atom": 6,
                        },
                    ],
                    "arrows": [0],
                },
                {
                    "blocks": [
                        {"atoms": [8, 9], "captions": [4, 5], "anchor_atom": 8},
                        {"atoms": [10, 11], "captions": [6, 7], "anchor_atom": 10},
                    ],
                    "arrows": [1],
                },
            ],
        },
        source_sha256=_HASH,
    )


def _baseline(note) -> float:
    layout = note.document().firstBlock().layout()
    line = layout.lineAt(0)
    return note.mapToScene(
        QPointF(0, layout.position().y() + line.y() + line.ascent())
    ).y()


def _arranged(state):
    request = _request(state)
    with offscreen_canvas(state, command="test-scheme-layout") as (canvas, _):
        return arrange_canvas(canvas, state, request)


def test_matching_rows_share_columns_and_caption_baselines_after_reopen() -> None:
    state = _state()
    candidate, report = _arranged(state)
    placements = report["placements"]
    assert placements[0]["center_x"] == pytest.approx(placements[2]["center_x"])
    assert placements[1]["center_x"] == pytest.approx(placements[3]["center_x"])
    with offscreen_canvas(candidate, command="test-scheme-layout-reopen") as (
        canvas,
        _,
    ):
        notes = document_item_lists_for(canvas)["notes"]
        text_block = notes[0].document().begin()
        line_count = 0
        while text_block.isValid():
            line_count += text_block.layout().lineCount()
            text_block = text_block.next()
        assert line_count >= 2
        for left, right in ((0, 2), (1, 3), (4, 6), (5, 7)):
            assert _baseline(notes[left]) == pytest.approx(
                _baseline(notes[right]), abs=1e-6
            )
        for block_index, pair in enumerate(((0, 1), (2, 3), (4, 5), (6, 7))):
            for note_index in pair:
                bounds = note_paint_scene_path(notes[note_index]).boundingRect()
                assert bounds.center().x() == pytest.approx(
                    placements[block_index]["center_x"], abs=1e-6
                )
            first = note_paint_scene_path(notes[pair[0]]).boundingRect()
            second = note_paint_scene_path(notes[pair[1]]).boundingRect()
            assert second.top() >= first.bottom() + 5 - 1e-6
        model = model_for(canvas)
        assert model.atoms[0].y == pytest.approx(model.atoms[6].y)
        assert model.atoms[8].y == pytest.approx(model.atoms[10].y)
        first_row_bottom = max(
            note_paint_scene_path(notes[i]).boundingRect().bottom() for i in range(4)
        )
        assert model.atoms[11].y >= first_row_bottom + 18 - 1e-6


def test_ring_fill_marks_bracket_and_arrow_move_without_semantic_changes() -> None:
    state = _state()
    original = deepcopy(state)
    candidate, report = _arranged(state)
    assert state == original
    build_document_payload(candidate, CANVAS_FILE_VERSION)
    placements = report["placements"]
    for placement in placements:
        dx, dy = placement["dx"], placement["dy"]
        for atom_id in placement["atoms"]:
            before = state["model"]["atoms"][atom_id]
            after = candidate["model"]["atoms"][atom_id]
            assert after["x"] == pytest.approx(before["x"] + dx)
            assert after["y"] == pytest.approx(before["y"] + dy)
            assert {k: v for k, v in after.items() if k not in {"x", "y"}} == {
                k: v for k, v in before.items() if k not in {"x", "y"}
            }
    assert candidate["model"]["bonds"] == state["model"]["bonds"]
    assert candidate["model"]["atom_annotations"] == state["model"]["atom_annotations"]
    for atom_id, point in zip(
        candidate["ring_fills"][0]["atom_ids"],
        candidate["ring_fills"][0]["points"],
        strict=True,
    ):
        atom = candidate["model"]["atoms"][atom_id]
        assert point == pytest.approx([atom["x"], atom["y"]])
    for before, after in zip(state["marks"], candidate["marks"], strict=True):
        placement = next(p for p in placements if before["atom_id"] in p["atoms"])
        assert after["x"] == pytest.approx(before["x"] + placement["dx"])
        assert after["y"] == pytest.approx(before["y"] + placement["dy"])
        assert {k: v for k, v in after.items() if k not in {"x", "y"}} == {
            k: v for k, v in before.items() if k not in {"x", "y"}
        }
    for before, after in zip(state["arrows"], candidate["arrows"], strict=True):
        assert after["end"][0] - after["start"][0] == pytest.approx(
            before["end"][0] - before["start"][0]
        )
        assert after.get("labels") == before.get("labels")
    for key in ("left", "right"):
        assert candidate["ts_brackets"][0][key] == pytest.approx(
            state["ts_brackets"][0][key] + placements[1]["dx"]
        )
    for key in ("top", "bottom"):
        assert candidate["ts_brackets"][0][key] == pytest.approx(
            state["ts_brackets"][0][key] + placements[1]["dy"]
        )


def test_unlisted_records_and_all_note_metadata_remain_exact() -> None:
    state = _state()
    original = deepcopy(state)
    candidate, _ = _arranged(state)
    assert candidate["notes"][8] == original["notes"][8]
    assert candidate["shapes"] == original["shapes"]
    assert candidate["settings"] == original["settings"]
    for before, after in zip(state["notes"], candidate["notes"], strict=True):
        assert {k: v for k, v in after.items() if k not in {"x", "y"}} == {
            k: v for k, v in before.items() if k not in {"x", "y"}
        }
    assert state == original


def test_saved_group_reopens_moves_as_unit_and_undo_redo(
    tmp_path: Path, application
) -> None:
    source = _state()
    source_path, candidate_path = (
        tmp_path / "source.chemvas",
        tmp_path / "layout.chemvas",
    )
    write_document(source_path, source, CANVAS_FILE_VERSION)
    original_bytes = source_path.read_bytes()
    candidate, _ = _arranged(source)
    write_document(candidate_path, candidate, CANVAS_FILE_VERSION)
    _, restored = read_exact_document(candidate_path)
    with offscreen_canvas(restored.state, command="test-scheme-layout-history") as (
        canvas,
        session,
    ):
        assert len(group_state_for(canvas).groups) == 4
        original = session.snapshot_state()
        visible_atom_item_for(canvas, 6).setSelected(True)
        expand_selection_to_groups_for(canvas)
        application.processEvents()
        controller = canvas_services_for(
            canvas
        ).scene_operations.scene_transform_controller
        assert controller.translate_selected_items(13, -9)
        moved = session.snapshot_state()
        for atom_id in (6, 7):
            assert moved["model"]["atoms"][atom_id]["x"] == pytest.approx(
                original["model"]["atoms"][atom_id]["x"] + 13
            )
        for note_index in (2, 3):
            assert moved["notes"][note_index]["x"] == pytest.approx(
                original["notes"][note_index]["x"] + 13
            )
            assert moved["notes"][note_index]["y"] == pytest.approx(
                original["notes"][note_index]["y"] - 9
            )
        assert moved["ts_brackets"][0]["left"] == pytest.approx(
            original["ts_brackets"][0]["left"] + 13
        )
        history = history_service_for_access(canvas)
        history.undo()
        undone = session.snapshot_state()
        for atom_id in (6, 7):
            assert undone["model"]["atoms"][atom_id]["x"] == pytest.approx(
                original["model"]["atoms"][atom_id]["x"]
            )
        assert undone["notes"][2]["x"] == pytest.approx(original["notes"][2]["x"])
        history.redo()
        redone = session.snapshot_state()
        assert redone["notes"][2]["x"] == pytest.approx(moved["notes"][2]["x"])
        assert redone["groups"] == moved["groups"]
    assert source_path.read_bytes() == original_bytes


@pytest.mark.parametrize("text", ["", "   \n  "])
def test_empty_caption_fails_before_canvas_or_source_mutation(text: str) -> None:
    state = _state()
    state["notes"][0] = {"text": text, "x": 20, "y": 20}
    original = deepcopy(state)
    request = _request(state)
    with offscreen_canvas(state, command="test-scheme-layout-empty-caption") as (
        canvas,
        session,
    ):
        before = session.snapshot_state()
        with pytest.raises(ValueError, match="no visible text"):
            arrange_canvas(canvas, state, request)
        assert session.snapshot_state() == before
    assert state == original


def _chain(state, *, width=400, arrows=True):
    request = _request(state)
    blocks = tuple(block for row in request.rows for block in row.blocks)
    state["arrows"].append(
        {
            "kind": "arrow",
            "start": [10, 500],
            "end": [55, 500],
            "labels": {"above": "unchanged condition"},
            "color": "#123456",
        }
    )
    return replace(
        request,
        rows=(LayoutRow(blocks, (0, 1, 2) if arrows else ()),),
        max_row_width=width,
    )


def _line_bounds(canvas, request, line):
    items = document_item_lists_for(canvas)
    blocks = [
        request.rows[line["source_row"]].blocks[index]
        for index in line["source_columns"]
    ]
    atoms = {atom for block in blocks for atom in block.atoms}
    graphics = [visible_atom_item_for(canvas, atom) for atom in atoms]
    graphics = [item for item in graphics if item is not None]
    model = model_for(canvas)
    for bond_id, pieces in bond_items_for(canvas).items():
        if model.bonds[bond_id].a in atoms:
            graphics.extend(pieces)
    registry = mark_registry_for(canvas)
    for atom in atoms:
        graphics.extend(registry.get_for_atom(atom) or [])
    graphics.extend(
        ring for ring in ring_items_for(canvas) if set(ring.data(2) or []) <= atoms
    )
    for block in blocks:
        graphics.extend(items[kind][index] for kind, index in block.items)
    arrow_ids = line["arrows"] + (
        [line["leading_arrow"]] if line["leading_arrow"] is not None else []
    )
    graphics.extend(items["arrows"][index] for index in arrow_ids)
    bounds = content_bounds(export_item_closure(graphics))
    for block in blocks:
        for index in block.captions:
            ink = note_paint_scene_path(items["notes"][index]).boundingRect()
            bounds = ink if bounds is None else bounds.united(ink)
    return bounds


def test_wrapped_chain_preserves_entities_styles_and_each_arrow_once() -> None:
    state = _state()
    request = _chain(state)
    original = deepcopy(state)
    with offscreen_canvas(state, command="test-wrapped-chain") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert state == original
    assert report["row_count"] >= 3
    assert report["logical_row_count"] == 1
    assert report["max_row_width"] == 400
    lines = report["lines"]
    assert lines[0]["leading_arrow"] is None
    assert all(line["leading_arrow"] is not None for line in lines[1:])
    assert [index for line in lines for index in line["source_columns"]] == [0, 1, 2, 3]
    placed_arrows = [
        index
        for line in lines
        for index in (
            [line["leading_arrow"]] if line["leading_arrow"] is not None else []
        )
        + line["arrows"]
    ]
    assert placed_arrows == [0, 1, 2]
    assert [p["source_column"] for p in report["placements"]] == [0, 1, 2, 3]
    for kind in ("notes", "arrows", "ts_brackets", "shapes", "ring_fills", "marks"):
        assert len(candidate[kind]) == len(state[kind])
    assert candidate["model"]["bonds"] == state["model"]["bonds"]
    assert candidate["settings"] == state["settings"]
    for before, after in zip(state["arrows"], candidate["arrows"], strict=True):
        assert after["end"][0] - after["start"][0] == pytest.approx(
            before["end"][0] - before["start"][0]
        )
        assert {
            key: value
            for key, value in after.items()
            if key not in {"start", "end", "control"}
        } == {
            key: value
            for key, value in before.items()
            if key not in {"start", "end", "control"}
        }
    with offscreen_canvas(candidate, command="test-wrapped-reopen") as (canvas, _):
        for line in lines:
            bounds = _line_bounds(canvas, request, line)
            assert bounds is not None
            assert bounds.left() >= -1e-6
            assert bounds.right() <= 400 + 1e-6
            assert line["width"] <= 400 + 1e-6
        assert len(group_state_for(canvas).groups) == 4


def test_width_limited_rows_do_not_share_column_expansion_or_cross_paths() -> None:
    state = _state()
    request = replace(_request(state), max_row_width=400)
    with offscreen_canvas(state, command="test-wrapped-paths") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert report["logical_row_count"] == 2
    starts = [line for line in report["lines"] if line["source_columns"][0] == 0]
    assert len(starts) == 2
    assert all(line["leading_arrow"] is None for line in starts)
    for line in report["lines"]:
        arrows = line["arrows"] + (
            [line["leading_arrow"]] if line["leading_arrow"] is not None else []
        )
        assert set(arrows) <= set(request.rows[line["source_row"]].arrows)
    with offscreen_canvas(candidate, command="test-wrapped-paths-bounds") as (
        canvas,
        _,
    ):
        for line in report["lines"]:
            bounds = _line_bounds(canvas, request, line)
            assert bounds.right() <= 400 + 1e-6


def test_wrapping_gallery_without_arrows_leaves_unlisted_arrows_unchanged() -> None:
    state = _state()
    request = _chain(state, width=300, arrows=False)
    with offscreen_canvas(state, command="test-wrapped-gallery") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert report["row_count"] > 1
    assert all(
        line["leading_arrow"] is None and not line["arrows"] for line in report["lines"]
    )
    assert candidate["arrows"] == state["arrows"]
    assert candidate["notes"][8] == state["notes"][8]
    assert candidate["shapes"] == state["shapes"]


def test_impossible_continuation_rejects_before_any_canvas_mutation(
    monkeypatch,
) -> None:
    state = _state()
    request = _chain(state, width=300)
    original = deepcopy(state)

    def unexpected(*_args, **_kwargs):
        pytest.fail("impossible wrapping must fail before moving any scene object")

    monkeypatch.setattr(scheme_layout_service, "move_atoms_for", unexpected)
    monkeypatch.setattr(scheme_layout_service, "move_item_for", unexpected)
    with offscreen_canvas(state, command="test-impossible-wrap") as (canvas, session):
        before = session.snapshot_state()
        with pytest.raises(ValueError, match="incoming arrow 0 and block 1"):
            arrange_canvas(canvas, state, request)
        assert session.snapshot_state() == before
    assert state == original


def test_unbounded_layout_retains_existing_report_contract() -> None:
    _, report = _arranged(_state())
    assert set(report) == {
        "row_count",
        "block_count",
        "layout_width",
        "layout_height",
        "placements",
    }
    assert all(
        set(p) == {"row", "column", "atoms", "center_x", "anchor_y", "dx", "dy"}
        for p in report["placements"]
    )


def test_wrapped_mode_does_not_expand_opposite_wide_columns_past_budget() -> None:
    state = _state()
    wide, narrow = deepcopy(state["notes"][2]), deepcopy(state["notes"][6])
    state["notes"][0], state["notes"][2], state["notes"][6] = (
        wide,
        narrow,
        deepcopy(wide),
    )
    base = _request(state)
    request = replace(
        base,
        rows=tuple(LayoutRow(row.blocks) for row in base.rows),
        max_row_width=430,
    )
    with offscreen_canvas(state, command="test-opposite-wide-columns") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert report["row_count"] == 2
    assert report["placements"][0]["center_x"] != pytest.approx(
        report["placements"][2]["center_x"]
    )
    with offscreen_canvas(candidate, command="test-opposite-wide-bounds") as (
        canvas,
        _,
    ):
        assert all(
            _line_bounds(canvas, request, line).right() <= 430 + 1e-6
            for line in report["lines"]
        )


def test_wrapped_layout_is_deterministic_for_unchanged_source() -> None:
    state = _state()
    request = _chain(state)
    original = deepcopy(state)
    results = []
    for _ in range(2):
        with offscreen_canvas(state, command="test-repeat-wrapped-layout") as (
            canvas,
            _,
        ):
            results.append(arrange_canvas(canvas, state, request))
    assert results[0] == results[1]
    assert state == original


def test_output_line_limit_rejects_before_mutation(monkeypatch) -> None:
    state = _state()
    request = _chain(state)
    monkeypatch.setattr(scheme_layout_service, "MAX_LAYOUT_ROWS", 1)
    with offscreen_canvas(state, command="test-output-line-limit") as (canvas, session):
        before = session.snapshot_state()
        with pytest.raises(ValueError, match="1-row limit"):
            arrange_canvas(canvas, state, request)
        assert session.snapshot_state() == before


def _align_y_request(state):
    return validate_layout_request(
        state,
        {
            "format": "chemvas-scheme-layout",
            "version": 1,
            "source_sha256": _HASH,
            "mode": "align-y",
            "rows": [
                {
                    "reference_blocks": [0],
                    "blocks": [
                        {
                            "atoms": list(range(6)),
                            "captions": [0, 1],
                            "items": [["notes", 8]],
                        },
                        {
                            "atoms": [6, 7],
                            "captions": [2, 3],
                            "items": [["ts_brackets", 0]],
                        },
                        {
                            "atoms": [8, 9, 10, 11],
                            "parts": [[8, 9], [10, 11]],
                            "captions": [4, 5, 6, 7],
                        },
                    ],
                    "arrows": [0, 1],
                }
            ],
        },
        source_sha256=_HASH,
    )


def test_align_y_keeps_notes_x_groups_and_geometry_but_centers_separate_products(
    tmp_path,
) -> None:
    state = _state()
    state["groups"] = [
        {"atoms": list(range(6)), "items": [["notes", 0], ["notes", 1], ["notes", 8]]},
        {"atoms": [6, 7], "items": [["notes", 2], ["notes", 3], ["ts_brackets", 0]]},
        {"atoms": [8, 9, 10, 11], "items": [["notes", i] for i in range(4, 8)]},
    ]
    state["ts_brackets"][0].update(top=-1000, bottom=1900)
    original = deepcopy(state)
    request = _align_y_request(state)
    with offscreen_canvas(state, command="test-align-y-native") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert state == original
    assert report["mode"] == "align-y"
    assert report["block_count"] == 3
    assert report["part_count"] == 4
    target = report["rows"][0]["target_y"]
    assert target == pytest.approx(100, abs=1e-6)
    placements = report["placements"]
    assert placements[2]["dy"] != pytest.approx(placements[3]["dy"])
    for placement in placements:
        assert placement["dx"] == 0
        for atom_id in placement["atoms"]:
            before, after = (
                state["model"]["atoms"][atom_id],
                candidate["model"]["atoms"][atom_id],
            )
            assert {k: v for k, v in after.items() if k != "y"} == {
                k: v for k, v in before.items() if k != "y"
            }
            assert after["y"] - before["y"] == pytest.approx(placement["dy"])
    for key in ("notes", "groups", "settings", "shapes", "orbitals", "arrows"):
        assert candidate[key] == original[key]
    assert candidate["model"]["bonds"] == original["model"]["bonds"]
    for before, after in zip(original["marks"], candidate["marks"], strict=True):
        assert {k: v for k, v in after.items() if k != "y"} == {
            k: v for k, v in before.items() if k != "y"
        }
        placement = next(p for p in placements if before["atom_id"] in p["atoms"])
        assert after["y"] - before["y"] == pytest.approx(placement["dy"])
    for before, after in zip(
        original["ring_fills"][0]["points"],
        candidate["ring_fills"][0]["points"],
        strict=True,
    ):
        assert after == pytest.approx([before[0], before[1] + placements[0]["dy"]])
    for key in ("left", "right"):
        assert candidate["ts_brackets"][0][key] == original["ts_brackets"][0][key]
    for key in ("top", "bottom"):
        assert candidate["ts_brackets"][0][key] - original["ts_brackets"][0][
            key
        ] == pytest.approx(placements[1]["dy"])
    output = tmp_path / "aligned.chemvas"
    write_document(output, candidate, CANVAS_FILE_VERSION)
    _, reopened = read_exact_document(output)
    assert reopened.state["notes"] == candidate["notes"]
    assert reopened.state["groups"] == candidate["groups"]
    assert reopened.state["arrows"] == original["arrows"]
    with offscreen_canvas(reopened.state, command="test-align-y-reopen") as (canvas, _):
        items = document_item_lists_for(canvas)
        for placement in placements:
            measured = scheme_layout_service._block(
                canvas,
                scheme_layout_service.LayoutBlock(tuple(placement["atoms"])),
                items,
            )
            assert measured.bounds.center().y() == pytest.approx(target, abs=1e-6)


def test_align_y_default_keeps_disconnected_encounter_whole_and_notes_unmeasured() -> (
    None
):
    state = _state()
    state["notes"][0]["text"] = " "
    state["notes"][0].pop("html", None)
    base = _align_y_request(state)
    blocks = tuple(replace(block, parts=()) for block in base.rows[0].blocks)
    request = replace(
        base, rows=(replace(base.rows[0], blocks=blocks, reference_blocks=()),)
    )
    with offscreen_canvas(state, command="test-align-y-whole-encounter") as (canvas, _):
        candidate, report = arrange_canvas(canvas, state, request)
    assert report["part_count"] == 3
    assert report["rows"][0]["reference_blocks"] == [0, 1, 2]
    deltas = [
        candidate["model"]["atoms"][a]["y"] - state["model"]["atoms"][a]["y"]
        for a in (8, 9, 10, 11)
    ]
    assert deltas == pytest.approx([deltas[0]] * 4)
    assert candidate["notes"] == state["notes"]
    assert "groups" not in candidate or candidate["groups"] == state.get("groups", [])


def test_align_y_deterministic_and_reference_rows_independent() -> None:
    state = _state()
    request = replace(
        _request(state),
        mode="align-y",
        rows=tuple(
            replace(
                row,
                blocks=tuple(replace(block, anchor_atom=None) for block in row.blocks),
            )
            for row in _request(state).rows
        ),
    )
    results = []
    for _ in range(2):
        with offscreen_canvas(state, command="test-align-y-repeat") as (canvas, _):
            results.append(arrange_canvas(canvas, state, request))
    assert results[0] == results[1]
    assert results[0][1]["rows"][0]["target_y"] != results[0][1]["rows"][1]["target_y"]


def test_align_y_measurement_failure_occurs_before_any_mutation(monkeypatch) -> None:
    state = _state()
    request = _align_y_request(state)
    original = scheme_layout_service._molecular_bounds

    def fail_on_final_part(canvas, ids, extra=None):
        if ids == {10, 11}:
            raise ValueError("injected unavailable part geometry")
        return original(canvas, ids, extra)

    monkeypatch.setattr(scheme_layout_service, "_molecular_bounds", fail_on_final_part)
    with offscreen_canvas(state, command="test-align-y-measure-failure") as (
        canvas,
        session,
    ):
        before = session.snapshot_state()
        with pytest.raises(ValueError, match="injected unavailable"):
            arrange_canvas(canvas, state, request)
        assert session.snapshot_state() == before
