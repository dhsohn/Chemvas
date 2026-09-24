"""Actual bond shortcuts and public Graph Patch agree on explicit bond edits."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from itertools import pairwise

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QCursor, QImage, QKeySequence, QMouseEvent, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsLineItem,
    QGraphicsPolygonItem,
    QStyleOptionGraphicsItem,
)

from chemvas.core.document_io import read_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION
from chemvas.domain.document.perspective import unproject_point_3d
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.selection.selection_queries import selected_ids_for
from tests.document_patch_workflow_support import run_patch
from tests.gui_workflow_support import app as app
from tests.gui_workflow_support import drawing as drawing
from tests.gui_workflow_support import qt_errors as qt_errors


def _normalized(value):
    return json.loads(json.dumps(value))


def _state(style, order, reverse=False):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "settings": {"bond_length_px": 18.0},
            "atoms": [
                {"id": index, "element": "C", "x": x, "y": y}
                for index, (x, y) in enumerate(
                    [(120, 140), (220, 140), (280, 230), (320, 230), (300, 270)]
                )
            ],
            "bonds": [
                {
                    "a": 1 if reverse else 0,
                    "b": 0 if reverse else 1,
                    "style": style,
                    "order": order,
                    "color": "#315579",
                },
                *[{"a": a, "b": b, "order": 1} for a, b in [(2, 3), (3, 4), (4, 2)]],
            ],
            "ring_fills": [{"atom_ids": [2, 3, 4], "color": "#a4b5c6", "alpha": 0.375}],
            "notes": [
                {
                    "x": 270,
                    "y": 300,
                    "runs": [
                        {"text": "Untouched ", "style": {"font_weight": 700}},
                        {"text": "한글", "style": {"italic": True, "color": "#135790"}},
                    ],
                }
            ],
        }
    )
    state["marks"] = [
        dict(kind=kind, text=None, atom_id=atom_id, dx=dx, dy=dy, x=x, y=y, color=color)
        for kind, atom_id, dx, dy, x, y, color in [
            ("plus", 0, 6.0, -15.0, 126.0, 125.0, "#123456"),
            ("minus", 0, None, None, 104.0, 148.0, "#654321"),
            ("radical", 2, 4.0, -14.0, 284.0, 216.0, "#008844"),
            ("minus", None, None, None, 310.0, 180.0, "#8751fe"),
        ]
    ]
    state["model"]["atom_annotations"] = {
        0: {"formal_charge": 0},
        2: {"radical_electrons": 1},
    }
    state["groups"] = [
        {"atoms": [2, 3, 4], "items": [["notes", 0], ["ring_fills", 0], ["marks", 3]]}
    ]
    center, anchor = (180.0, 190.0, 0.0), (180.0, 190.0)
    state["perspective"] = {
        "atom_coords_3d": {
            atom_id: unproject_point_3d(
                (atom["x"], atom["y"]),
                (36.0, 36.0, -24.0, 12.0, 0.0)[atom_id],
                bond_length_px=18.0,
                center_3d=center,
                anchor_2d=anchor,
            )
            for atom_id, atom in state["model"]["atoms"].items()
        },
        "projection_center_3d": center,
        "projection_anchor_2d": anchor,
    }
    return state


def _prepare(drawing, app, monkeypatch, style, order, reverse=False):
    window, canvas = drawing
    documents = canvas.services.canvas_document_session_service
    documents.apply_state(_state(style, order, reverse))
    canvas.services.tool_mode_controller.set_tool("select")
    canvas.centerOn(220, 210)
    canvas.scene().clearSelection()
    canvas.runtime_state.bond_graphics_state.bond_items.get(0, [])[0].setSelected(True)
    canvas.setFocus()
    app.processEvents()
    position = canvas.mapFromScene(QPointF(170, 140))
    assert canvas.viewport().rect().contains(position)
    global_position = canvas.viewport().mapToGlobal(position)
    # Wayland need not warp the hardware cursor. The real viewport event and
    # keyboard hover refresh share this scoped simulated pointer position.
    monkeypatch.setattr(QCursor, "pos", staticmethod(lambda: global_position))
    QApplication.sendEvent(
        canvas.viewport(),
        QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(position),
            QPointF(global_position),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )
    app.processEvents()
    assert canvas.runtime_state.hover_preview_state.bond_id == 0
    assert selected_ids_for(canvas) == (set(), {0})
    canvas.services.history_service.clear()
    return window, canvas, documents


def _sentinels(canvas):
    marks = {}
    for item in canvas.scene().items():
        if item.data(0) != "mark":
            continue
        data = deepcopy(item.data(1))
        for key in ("text", "dx", "dy"):
            data.setdefault(key, None)
        center = canvas.services.scene_decoration_build_service.mark_center(item)
        key = (data["atom_id"], data["kind"], data["color"])
        assert key not in marks
        marks[key] = ((center.x(), center.y()), data)
    assert len(marks) == 4
    rings = [
        (list(item.data(2)), [(p.x(), p.y()) for p in item.mapToScene(item.polygon())])
        for item in canvas.runtime_state.ring_items()
    ]
    assert len(rings) == 1
    return marks, rings, dict(canvas.runtime_state.atom_coords_3d_state.atom_coords_3d)


def _glyph(canvas, style, order, reverse=False):
    """Inspect actual Qt primitives, not the model or the renderer's planner."""
    items = canvas.runtime_state.bond_graphics_state.bond_items.get(0, [])
    assert items and all(
        item.isVisible() and item.scene() is canvas.scene() for item in items
    )
    lines, polygons = [], []
    for item in items:
        assert item.opacity() == 1.0
        assert item.pen().color().name() == "#315579"
        if isinstance(item, QGraphicsLineItem):
            line = item.line()
            a, b = item.mapToScene(line.p1()), item.mapToScene(line.p2())
            lines.append((a.x(), a.y(), b.x(), b.y()))
        else:
            assert isinstance(item, QGraphicsPolygonItem)
            assert item.brush().color().name() == "#315579"
            polygons.append([(p.x(), p.y()) for p in item.mapToScene(item.polygon())])
    if style == "wedge":
        assert not lines and len(polygons) == 1 and len(polygons[0]) == 3
        start, end = (220.0, 120.0) if reverse else (120.0, 220.0)
        points = sorted(
            polygons[0], key=lambda point: (point[0] - start) / (end - start)
        )
        tip, base_a, base_b = points
        assert (tip[0] - start) / (end - start) < 0.5
        assert (base_a[0] - start) / (end - start) > 0.9
        assert base_a[0] == base_b[0] and tip[1] == 140.0
        assert min(base_a[1], base_b[1]) < 140.0 < max(base_a[1], base_b[1])
    elif style == "hash":
        assert not polygons and len(lines) >= 3
        assert all(x1 == x2 and y1 != y2 for x1, y1, x2, y2 in lines)
        ordered = sorted(lines, key=lambda line: -line[0] if reverse else line[0])
        widths = [abs(y2 - y1) for _x1, y1, _x2, y2 in ordered]
        assert all(left < right for left, right in pairwise(widths))
    elif style == "double_either":
        assert not polygons and len(lines) == 2
        slopes = [(y2 - y1) / (x2 - x1) for x1, y1, x2, y2 in lines]
        assert slopes[0] * slopes[1] < 0
    else:
        assert not polygons and len(lines) == order
        assert all(
            abs(x2 - x1) > 70 and abs(y2 - y1) < 1e-10 for x1, y1, x2, y2 in lines
        )
        assert len({round((y1 + y2) / 2, 8) for _x1, y1, _x2, y2 in lines}) == order

    # Paint those live primitives in a fixed scene-space crop. No planner,
    # snapshot, or regenerated clone can conceal stale/empty bond graphics.
    image = QImage(280, 160, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    try:
        painter.scale(2, 2)
        painter.translate(-110, -100)
        for item in items:
            painter.save()
            painter.setWorldTransform(item.sceneTransform(), True)
            item.paint(painter, QStyleOptionGraphicsItem())
            painter.restore()
    finally:
        painter.end()
    assert any(image.pixelColor(x, y).alpha() for x in range(280) for y in range(160))
    return lines, polygons, bytes(image.constBits().asstring(image.sizeInBytes()))


def _expected(before, style, order):
    expected = deepcopy(before)
    expected["model"]["bonds"][0]["style"] = style
    expected["model"]["bonds"][0]["order"] = order
    return expected


@pytest.mark.parametrize(
    "initial_style,initial_order,key,target_style,target_order,reverse",
    [
        ("double", 2, Qt.Key.Key_1, "single", 1, False),
        ("single", 1, Qt.Key.Key_2, "double", 2, False),
        ("double", 2, Qt.Key.Key_3, "triple", 3, False),
        ("single", 1, Qt.Key.Key_W, "wedge", 1, False),
        ("single", 1, Qt.Key.Key_W, "wedge", 1, True),
        ("wedge", 1, Qt.Key.Key_H, "hash", 1, False),
        ("wedge", 1, Qt.Key.Key_H, "hash", 1, True),
        ("double_either", 2, Qt.Key.Key_2, "double", 2, False),
    ],
    ids=[
        "single",
        "double",
        "triple",
        "wedge",
        "reversed-wedge",
        "hash",
        "reversed-hash",
        "resolve-unknown",
    ],
)
def test_bond_shortcut_matches_cli_literal_edit_and_reopening(
    drawing,
    app,
    qt_errors,
    tmp_path,
    monkeypatch,
    initial_style,
    initial_order,
    key,
    target_style,
    target_order,
    reverse,
):
    _window, canvas, documents = _prepare(
        drawing, app, monkeypatch, initial_style, initial_order, reverse
    )
    before = documents.snapshot_state()
    expected = _expected(before, target_style, target_order)
    sentinels = _sentinels(canvas)
    groups = dict(canvas.runtime_state.group_state.groups)
    before_glyph = _glyph(canvas, initial_style, initial_order, reverse)
    source = tmp_path / "source.chemvas"
    write_document(source, before, CANVAS_FILE_VERSION)
    original = source.read_bytes()
    QTest.keyClick(canvas, key)
    app.processEvents()
    after_glyph = _glyph(canvas, target_style, target_order, reverse)
    assert after_glyph[2] != before_glyph[2]
    assert documents.snapshot_state() == expected
    assert _sentinels(canvas) == sentinels
    assert selected_ids_for(canvas) == (set(), {0})
    bond = before["model"]["bonds"][0]
    # Reverse lookup is legal but must not reverse the stored stereo endpoints.
    result, output = run_patch(
        tmp_path,
        source,
        [
            {
                "op": "update_bond",
                "a": bond["b"],
                "b": bond["a"],
                "changes": {"order": target_order, "style": target_style},
            }
        ],
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert (
        json.loads(result.stdout)["candidate_sha256"]
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert read_document(output).state == _normalized(expected)
    history = canvas.services.history_service
    assert len(history.state.history) == 1
    for _ in range(2):
        for key_sequence, state, style, order, glyph in [
            (
                QKeySequence.StandardKey.Undo,
                before,
                initial_style,
                initial_order,
                before_glyph,
            ),
            (
                QKeySequence.StandardKey.Redo,
                expected,
                target_style,
                target_order,
                after_glyph,
            ),
        ]:
            QTest.keySequence(canvas, QKeySequence(key_sequence))
            app.processEvents()
            assert documents.snapshot_state() == state
            assert _glyph(canvas, style, order, reverse) == glyph
            assert _sentinels(canvas) == sentinels
            assert selected_ids_for(canvas) == (set(), {0})
            assert canvas.runtime_state.group_state.groups.keys() == groups.keys()
            assert all(
                canvas.runtime_state.group_state.groups[key] is group
                for key, group in groups.items()
            )
    saved = tmp_path / "gui-saved.chemvas"
    assert documents.save_to_file(str(saved)) == []
    for path in (output, saved):
        stored = read_document(path).state
        assert stored == _normalized(expected)
        documents.apply_state(stored)
        app.processEvents()
        assert _normalized(documents.snapshot_state()) == stored
        assert _sentinels(canvas) == sentinels
        assert _glyph(canvas, target_style, target_order, reverse) == after_glyph
        assert not qt_errors
    assert source.read_bytes() == original
    assert not qt_errors


@pytest.mark.parametrize("policy", ["no-op", "unknown-cosmetic"])
def test_gui_bond_guards_and_explicit_cli_policy_remain_distinct(
    drawing,
    app,
    qt_errors,
    tmp_path,
    monkeypatch,
    policy,
):
    style = "double" if policy == "no-op" else "double_either"
    window, canvas, documents = _prepare(drawing, app, monkeypatch, style, 2)
    before = documents.snapshot_state()
    # An existing Redo must survive a no-op or refused cosmetic gesture.
    QTest.keyClick(canvas, Qt.Key.Key_1)
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    app.processEvents()
    assert documents.snapshot_state() == before
    history = canvas.services.history_service
    stacks = history.capture_stack_snapshot()
    sentinels = _sentinels(canvas)
    glyph = _glyph(canvas, style, 2)
    source = tmp_path / "source.chemvas"
    write_document(source, before, CANVAS_FILE_VERSION)
    key = Qt.Key.Key_2 if policy == "no-op" else Qt.Key.Key_C
    QTest.keyClick(canvas, key)
    app.processEvents()
    assert documents.snapshot_state() == before
    assert _sentinels(canvas) == sentinels
    assert _glyph(canvas, style, 2) == glyph
    assert selected_ids_for(canvas) == (set(), {0})
    history.verify_stack_snapshot(stacks)
    target_style = "double" if policy == "no-op" else "double_center"
    result, output = run_patch(
        tmp_path,
        source,
        [
            {
                "op": "update_bond",
                "a": 0,
                "b": 1,
                "changes": {"order": 2, "style": target_style},
            }
        ],
    )
    if policy == "no-op":
        assert result.returncode != 0
        assert "update_bond must change at least one value" in result.stderr
        assert result.stdout == "" and not output.exists()
    else:
        assert "Choose Double (2)" in window.statusBar().currentMessage()
        # CLI specifies the replacement style explicitly; it is not a request
        # to preserve unknown stereo while changing its cosmetic appearance.
        assert result.returncode == 0, result.stderr
        assert read_document(output).state == _normalized(
            _expected(before, target_style, 2)
        )
    # Refusal must preserve a usable Redo, not merely an unchanged stack size.
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Redo))
    app.processEvents()
    assert documents.snapshot_state() == _expected(before, "single", 1)
    QTest.keySequence(canvas, QKeySequence(QKeySequence.StandardKey.Undo))
    app.processEvents()
    assert documents.snapshot_state() == before
    assert _sentinels(canvas) == sentinels
    assert _glyph(canvas, style, 2) == glyph
    assert selected_ids_for(canvas) == (set(), {0})
    assert not qt_errors
