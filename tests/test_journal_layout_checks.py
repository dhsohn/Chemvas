from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QStyleOptionGraphicsItem

from chemvas.bootstrap import document_layout_check
from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.ui.canvas_atom_graphics_state import atom_items_for
from chemvas.ui.canvas_scene_items_state import arrow_items_for, note_items_for
from chemvas.ui.layout_qa_service import check_canvas_layout

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _state(
    atoms: dict[int, Atom],
    *,
    bonds: list[Bond] | None = None,
    notes: list[dict[str, object]] | None = None,
    arrows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "model": serialize_model_state(MoleculeModel(atoms=atoms, bonds=bonds or [])),
        "notes": notes or [],
        "arrows": arrows or [],
        "ring_fills": [],
        "marks": [],
        "ts_brackets": [],
        "shapes": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=400,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def test_visible_atom_label_note_overlap_uses_document_atom_id() -> None:
    state = _state(
        {7: Atom("N", 0.0, 0.0)},
        notes=[{"text": "N", "x": 0.0, "y": 0.0}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        atom = atom_items_for(canvas)[7]
        note = note_items_for(canvas)[0]
        note.setFont(atom.font())
        note.setPos(atom.pos())

        report = check_canvas_layout(canvas)

        assert report["warning_count"] == 1
        warning = report["warnings"][0]
        assert warning["code"] == "text-text-overlap"
        assert warning["severity"] == "warning"
        assert warning["items"] == [
            {"kind": "atom", "id": 7},
            {"kind": "note", "index": 0},
        ]
        assert warning["bounds"][2] > 0
        assert warning["bounds"][3] > 0
        note.setPos(200, 200)
        assert check_canvas_layout(canvas)["ok"] is True


def test_stacked_hydride_note_collision_follows_painted_runs() -> None:
    state = _state(
        {7: Atom("NH2", 0.0, 0.0)},
        notes=[{"text": "M", "x": 200.0, "y": 200.0}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        atom = atom_items_for(canvas)[7]
        atom.set_stack_anchor("N", hydrogens_below=True)
        atom.setRotation(23)
        atom.setScale(1.5)
        bounds = atom.boundingRect()
        scale = 4
        image = QImage(
            int(bounds.width() * scale) + 1,
            int(bounds.height() * scale) + 1,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(scale, scale)
        painter.translate(-bounds.topLeft())
        atom.paint(painter, QStyleOptionGraphicsItem())
        painter.end()
        painted = [
            (x, y)
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 200
        ]
        assert painted
        x, y = painted[-1]
        point = atom.mapToScene(
            bounds.topLeft() + QPointF((x + 0.5) / scale, (y + 0.5) / scale)
        )
        note = note_items_for(canvas)[0]
        note.setFont(atom.font())
        note.setScale(0.1)
        note.setPos(point - note.boundingRect().center() * note.scale())

        report = check_canvas_layout(canvas)

        assert report["counts"]["text-text-overlap"] == 1


def test_overlapping_atom_labels_have_stable_sorted_ids() -> None:
    state = _state({42: Atom("CH3", 100.0, 0.0), 7: Atom("CH3", 0.0, 0.0)})
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        atom_items_for(canvas)[42].setPos(atom_items_for(canvas)[7].pos())
        report = check_canvas_layout(canvas)
        assert report["warning_count"] == 1
        assert report["warnings"][0]["items"] == [
            {"kind": "atom", "id": 7},
            {"kind": "atom", "id": 42},
        ]
        assert report["warnings"][0]["code"] == "text-text-overlap"
        atom = atom_items_for(canvas)[42]
        atom.setVisible(False)
        assert check_canvas_layout(canvas)["ok"] is True
        atom.setVisible(True)
        atom.setOpacity(0)
        assert check_canvas_layout(canvas)["ok"] is True
        atom.setOpacity(1)
        atom.setDefaultTextColor(Qt.GlobalColor.transparent)
        assert check_canvas_layout(canvas)["ok"] is True


def test_atom_pair_work_limit_rejects_before_qt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "many-labels.chemvas"
    state = _state({index: Atom("N", index * 25.0, 0.0) for index in range(142)})
    write_document(source, state, CANVAS_FILE_VERSION)

    def reject_qt(_state):
        pytest.fail("work limit must run before Qt scene construction")

    monkeypatch.setattr(document_layout_check, "_check_offscreen", reject_qt)
    with pytest.raises(SystemExit) as error:
        document_layout_check.run(["check-layout", str(source)])
    assert error.value.code == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "layout work limit of 10000" in result.err


def test_arrow_crossing_bond_reports_endpoints_not_runtime_bond_id() -> None:
    state = _state(
        {42: Atom("C", 30.0, 0.0), 7: Atom("C", -30.0, 0.0)},
        bonds=[Bond(42, 7)],
        arrows=[
            {"kind": "arrow", "start": [0.0, -30.0], "end": [0.0, 30.0]},
            {"kind": "arrow", "start": [0.0, -30.0], "end": [0.0, 30.0]},
        ],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        arrow_items_for(canvas)[0].setVisible(False)

        report = check_canvas_layout(canvas)

        assert report["warning_count"] == 1
        warning = report["warnings"][0]
        assert warning["code"] == "arrow-structure-overlap"
        assert warning["items"] == [
            {"kind": "arrow", "index": 1},
            {"kind": "bond", "atom_ids": [7, 42]},
        ]
        assert warning["bounds"][2] > 0
        assert warning["bounds"][3] > 0
        arrow_items_for(canvas)[1].setPos(100, 0)
        assert check_canvas_layout(canvas)["ok"] is True


def test_arrow_crossing_visible_atom_label_is_reported() -> None:
    state = _state(
        {7: Atom("N", 0.0, 0.0)},
        arrows=[{"kind": "arrow", "start": [-30.0, 0.0], "end": [30.0, 0.0]}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        report = check_canvas_layout(canvas)
        assert report["warning_count"] == 1
        assert report["warnings"][0]["items"] == [
            {"kind": "arrow", "index": 0},
            {"kind": "atom", "id": 7},
        ]
        assert report["warnings"][0]["code"] == "arrow-structure-overlap"
        atom_items_for(canvas)[7].setVisible(False)
        assert check_canvas_layout(canvas)["ok"] is True


def test_arrow_inside_rendered_wedge_fill_is_reported() -> None:
    from PyQt6.QtWidgets import QGraphicsPolygonItem

    from chemvas.ui.canvas_bond_graphics_state import bond_items_for

    state = _state(
        {7: Atom("C", -30.0, 0.0), 42: Atom("C", 30.0, 0.0)},
        bonds=[Bond(7, 42, style="wedge")],
        arrows=[{"kind": "arrow", "start": [-10.0, 0.0], "end": [10.0, 0.0]}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        wedge = next(iter(bond_items_for(canvas).values()))[0]
        assert isinstance(wedge, QGraphicsPolygonItem)
        assert wedge.brush().style() != Qt.BrushStyle.NoBrush
        arrow = arrow_items_for(canvas)[0]
        arrow.setScale(0.1)
        arrow.setPos(wedge.mapToScene(wedge.boundingRect().center()))

        report = check_canvas_layout(canvas)

        assert report["counts"]["arrow-structure-overlap"] == 1
        assert report["warnings"][0]["items"] == [
            {"kind": "arrow", "index": 0},
            {"kind": "bond", "atom_ids": [7, 42]},
        ]


def _rendered_alpha_near(item, point: QPointF) -> int:
    image = QImage(4, 4, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.translate(2, 2)
    painter.scale(8, 8)
    painter.translate(-point)
    item.paint(painter, QStyleOptionGraphicsItem(), None)
    painter.end()
    return max(image.pixelColor(x, y).alpha() for x in range(4) for y in range(4))


def test_rendered_dotted_fill_and_transparent_fill() -> None:
    from PyQt6.QtGui import QBrush, QPen

    from chemvas.ui.canvas_bond_graphics_state import bond_items_for

    state = _state(
        {7: Atom("C", -30.0, 0.0), 42: Atom("C", 30.0, 0.0)},
        bonds=[Bond(7, 42, style="dotted")],
        arrows=[{"kind": "arrow", "start": [-10.0, 0.0], "end": [10.0, 0.0]}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        dots = next(iter(bond_items_for(canvas).values()))[0]
        center = dots.path().toSubpathPolygons()[0].boundingRect().center()
        assert _rendered_alpha_near(dots, center) > 200
        arrow = arrow_items_for(canvas)[0]
        arrow.setScale(0.02)
        arrow.setPos(dots.mapToScene(center))
        assert check_canvas_layout(canvas)["counts"]["arrow-structure-overlap"] == 1
        dots.setPen(QPen(Qt.PenStyle.NoPen))
        dots.setBrush(QBrush(Qt.GlobalColor.transparent))
        assert _rendered_alpha_near(dots, center) == 0
        assert check_canvas_layout(canvas)["ok"] is True


def test_arrow_dash_hit_target_gap_uses_actual_paint() -> None:
    from PyQt6.QtGui import QPen

    state = _state(
        {7: Atom("C", 7.0, -10.0), 42: Atom("C", 7.0, 10.0)},
        bonds=[Bond(7, 42)],
        arrows=[{"kind": "arrow", "start": [0.0, 0.0], "end": [80.0, 0.0]}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        arrow = arrow_items_for(canvas)[0]
        pen = QPen(Qt.GlobalColor.black)
        pen.setWidthF(1)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setDashPattern([2, 10])
        arrow.setPen(pen)
        point = QPointF(7, 0)
        assert arrow.shape().contains(point)
        assert _rendered_alpha_near(arrow, point) == 0
        assert check_canvas_layout(canvas)["ok"] is True
        pen.setStyle(Qt.PenStyle.SolidLine)
        arrow.setPen(pen)
        assert _rendered_alpha_near(arrow, point) > 200
        assert check_canvas_layout(canvas)["counts"]["arrow-structure-overlap"] == 1


def test_atom_label_hit_rectangle_gap_uses_actual_paint() -> None:
    state = _state(
        {7: Atom("N", 0.0, 0.0)},
        arrows=[{"kind": "arrow", "start": [-10.0, 0.0], "end": [10.0, 0.0]}],
    )
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        atom = atom_items_for(canvas)[7]
        point = atom.boundingRect().topLeft() + QPointF(0.5, 0.5)
        assert atom.shape().contains(point)
        assert _rendered_alpha_near(atom, point) == 0
        arrow = arrow_items_for(canvas)[0]
        arrow.setScale(0.02)
        arrow.setPos(atom.mapToScene(point))
        assert check_canvas_layout(canvas)["ok"] is True


def test_highlight_panel_is_not_a_molecular_collision_target() -> None:
    from PyQt6.QtGui import QBrush, QColor, QPen

    from chemvas.ui.canvas_scene_items_state import shape_items_for

    state = _state(
        {7: Atom("N", 0.0, 0.0)},
        arrows=[{"kind": "arrow", "start": [-40.0, 20.0], "end": [40.0, 20.0]}],
    )
    state["shapes"] = [
        {
            "shape_kind": "rect",
            "left": -50.0,
            "top": -30.0,
            "right": 50.0,
            "bottom": 30.0,
        }
    ]
    with offscreen_canvas(state, command="test-layout") as (canvas, _):
        panel = shape_items_for(canvas)[0]
        panel.setPen(QPen(Qt.PenStyle.NoPen))
        panel.setBrush(QBrush(QColor(255, 255, 0, 100)))
        assert panel.path().contains(QPointF(0, 0))
        assert panel.path().contains(QPointF(0, 20))
        assert _rendered_alpha_near(panel, QPointF(0, 0)) == 100
        assert check_canvas_layout(canvas)["ok"] is True
        panel.setBrush(QBrush(Qt.GlobalColor.transparent))
        assert check_canvas_layout(canvas)["ok"] is True


def test_work_bound_excludes_only_implicit_carbons_and_includes_arrows() -> None:
    # Public synthetic counts, not a copy of any research drawing.
    state = _state(
        {
            index: Atom("C" if index < 42 else "N", index * 25.0, 0.0)
            for index in range(102)
        },
        bonds=[Bond(index, index + 1) for index in range(98)],
        notes=[{"text": "note", "x": 0.0, "y": 0.0} for _ in range(30)],
        arrows=[
            {"kind": "arrow", "start": [0.0, -30.0], "end": [0.0, 30.0]}
            for _ in range(20)
        ],
    )
    state["shapes"] = [
        {"shape_kind": "rect", "rect": [0.0, 0.0, 10.0, 10.0]} for _ in range(37)
    ]
    # The original 8520 units plus 60 visible labels × 98 candidate bonds.
    assert document_layout_check._layout_work_units(state) == 8520 + 60 * 98
    assert document_layout_check.MAX_LAYOUT_WORK_UNITS == 10000
    # Explicit C is visible; do not discard it with implicit skeletal vertices.
    state["model"]["atoms"][0]["explicit_label"] = True
    assert document_layout_check._layout_work_units(state) == 8631 + 61 * 98
