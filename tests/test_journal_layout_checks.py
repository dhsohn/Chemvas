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
from chemvas.ui.canvas_arrow_build_service import ARROW_LABEL_ROLE
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


def _attached_label(canvas, arrow_index=0, side="above"):
    return next(
        child
        for child in arrow_items_for(canvas)[arrow_index].childItems()
        if child.data(0) == ARROW_LABEL_ROLE and child.data(1) == side
    )


def _labelled_arrow(*, y=150.0, labels=None):
    return {
        "kind": "arrow",
        "start": [-40.0, y],
        "end": [40.0, y],
        "labels": labels or {"above": "N", "below": "k_1^‡"},
    }


def _painted_label_point(item):
    bounds = item.boundingRect()
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
    item.paint(painter, QStyleOptionGraphicsItem())
    painter.end()
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 240:
                return item.mapToScene(
                    bounds.topLeft() + QPointF((x + 0.5) / scale, (y + 0.5) / scale)
                )
    pytest.fail("native label must paint a visible glyph")


@pytest.mark.parametrize("other_kind", ["atom", "note", "arrow-label"])
def test_attached_arrow_label_text_pairs_have_stable_side_refs(other_kind) -> None:
    state = _state(
        {7: Atom("N", 0.0, 0.0)} if other_kind == "atom" else {},
        notes=[{"text": "N", "x": 0.0, "y": 0.0}] if other_kind == "note" else [],
        arrows=[_labelled_arrow(), _labelled_arrow(y=250.0)],
    )
    with offscreen_canvas(state, command="test-arrow-label-text") as (canvas, service):
        label = _attached_label(canvas)
        other = (
            atom_items_for(canvas)[7]
            if other_kind == "atom"
            else note_items_for(canvas)[0]
            if other_kind == "note"
            else _attached_label(canvas, 1)
        )
        label.setFont(other.font())
        label.setHtml(other.toHtml())
        label.setPos(label.parentItem().mapFromScene(other.scenePos()))
        before = service.snapshot_state()
        report = check_canvas_layout(canvas)
        matches = [w for w in report["warnings"] if w["code"] == "text-text-overlap"]
        assert len(matches) == 1
        assert {"kind": "arrow-label", "index": 0, "side": "above"} in matches[0][
            "items"
        ]
        assert service.snapshot_state() == before
        label.moveBy(200.0, 0.0)
        assert check_canvas_layout(canvas)["counts"]["text-text-overlap"] == 0


@pytest.mark.parametrize("angle", [0, 37])
def test_scripted_arrow_label_crossing_bond_uses_native_ink(angle) -> None:
    from chemvas.ui.canvas_bond_graphics_state import bond_items_for

    state = _state(
        {7: Atom("C", -50.0, 0.0), 42: Atom("C", 50.0, 0.0)},
        bonds=[Bond(7, 42)],
        arrows=[_labelled_arrow()],
    )
    with offscreen_canvas(state, command="test-arrow-label-bond") as (canvas, _):
        label = _attached_label(canvas, side="below")
        label.setRotation(angle)
        point = _painted_label_point(label)
        bond = bond_items_for(canvas)[0][0]
        bond.setLine(point.x() - 5, point.y(), point.x() + 5, point.y())
        report = check_canvas_layout(canvas)
        matches = [w for w in report["warnings"] if w["code"] == "text-bond-overlap"]
        assert len(matches) == 1
        assert matches[0]["items"] == [
            {"kind": "arrow-label", "index": 0, "side": "below"},
            {"kind": "bond", "atom_ids": [7, 42]},
        ]
        label.moveBy(0, 80)
        assert check_canvas_layout(canvas)["counts"]["text-bond-overlap"] == 0


@pytest.mark.parametrize("owner_index", [0, 1])
def test_attached_label_crossing_own_or_other_arrow_stroke(owner_index) -> None:
    state = _state({}, arrows=[_labelled_arrow(y=0.0), _labelled_arrow(y=200.0)])
    with offscreen_canvas(state, command="test-arrow-label-stroke") as (canvas, _):
        label = _attached_label(canvas, owner_index)
        point = _painted_label_point(label)
        label.moveBy(-point.x(), -point.y())
        matches = [
            w
            for w in check_canvas_layout(canvas)["warnings"]
            if w["code"] == "text-arrow-overlap"
        ]
        assert len(matches) == 1
        assert matches[0]["items"] == [
            {"kind": "arrow-label", "index": owner_index, "side": "above"},
            {"kind": "arrow", "index": 0},
        ]


@pytest.mark.parametrize(
    "hidden_by", ["visibility", "parent", "opacity", "color", "whitespace"]
)
def test_attached_label_outside_sheet_ignores_invisible_ink(hidden_by) -> None:
    state = _state({}, arrows=[_labelled_arrow(labels={"above": "N"})])
    with offscreen_canvas(state, command="test-arrow-label-visibility") as (canvas, _):
        label = _attached_label(canvas)
        label.setPos(1000, 0)
        matches = check_canvas_layout(canvas)["warnings"]
        assert len(matches) == 1
        assert matches[0]["code"] == "outside-sheet"
        assert matches[0]["items"] == [
            {"kind": "arrow-label", "index": 0, "side": "above"}
        ]
        if hidden_by == "visibility":
            label.setVisible(False)
        elif hidden_by == "parent":
            label.parentItem().setVisible(False)
        elif hidden_by == "opacity":
            label.parentItem().setOpacity(0)
        elif hidden_by == "color":
            label.setHtml('<span style="color:transparent">N</span>')
        else:
            label.setPlainText("  ")
        assert check_canvas_layout(canvas)["ok"] is True


@pytest.mark.parametrize("arrow_count", [49, 50])
def test_attached_label_work_limit_rejects_before_qt(
    tmp_path, monkeypatch, capsys, arrow_count
) -> None:
    source = tmp_path / "many-arrow-labels.chemvas"
    state = _state({}, arrows=[_labelled_arrow() for _ in range(arrow_count)])
    write_document(source, state, CANVAS_FILE_VERSION)

    def reject_qt(_state):
        assert arrow_count == 49, "attached label work limit must run before Qt"
        return {"ok": True}

    monkeypatch.setattr(document_layout_check, "_check_offscreen", reject_qt)
    if arrow_count == 49:
        assert document_layout_check.run(["check-layout", str(source)]) == 0
        assert capsys.readouterr().err == ""
    else:
        with pytest.raises(SystemExit) as error:
            document_layout_check.run(["check-layout", str(source)])
        assert error.value.code == 2
        assert "layout work limit" in capsys.readouterr().err


@pytest.mark.parametrize("target_kind", ["bond", "arrow"])
def test_attached_label_in_actual_dash_gap_is_clear(target_kind) -> None:
    from PyQt6.QtGui import QPainterPath, QPen

    from chemvas.ui.canvas_bond_graphics_state import bond_items_for

    state = _state(
        {7: Atom("C", -60.0, 0.0), 42: Atom("C", 60.0, 0.0)}
        if target_kind == "bond"
        else {},
        bonds=[Bond(7, 42)] if target_kind == "bond" else [],
        arrows=[_labelled_arrow(), _labelled_arrow(y=0.0, labels={"below": ""})],
    )
    with offscreen_canvas(state, command="test-arrow-label-dash-gap") as (canvas, _):
        label = _attached_label(canvas)
        label.setScale(0.05)
        point = _painted_label_point(label)
        label.moveBy(-48.0 - point.x(), -point.y())
        if target_kind == "bond":
            target = bond_items_for(canvas)[0][0]
        else:
            target = arrow_items_for(canvas)[1]
            path = QPainterPath(QPointF(-60, 0))
            path.lineTo(60, 0)
            target.setPath(path)
        pen = QPen(Qt.GlobalColor.black)
        pen.setWidthF(2)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setDashPattern([1, 10])
        target.setPen(pen)
        code = "text-bond-overlap" if target_kind == "bond" else "text-arrow-overlap"
        assert check_canvas_layout(canvas)["counts"][code] == 0
        pen.setStyle(Qt.PenStyle.SolidLine)
        target.setPen(pen)
        assert check_canvas_layout(canvas)["counts"][code] == 1


def test_attached_label_shape_border_and_glyph_gap() -> None:
    from PyQt6.QtGui import QPainterPath, QPen

    from chemvas.ui.canvas_scene_items_state import shape_items_for

    state = _state({}, arrows=[_labelled_arrow(labels={"above": "O"})])
    state["shapes"] = [
        {
            "shape_kind": "rect",
            "left": -10.0,
            "top": -10.0,
            "right": 10.0,
            "bottom": 10.0,
        }
    ]
    with offscreen_canvas(state, command="test-arrow-label-border") as (canvas, _):
        label = _attached_label(canvas)
        shape = shape_items_for(canvas)[0]
        # The centre of the O is a genuine unpainted hole, not a glyph hitbox.
        centre = label.mapToScene(label.boundingRect().center())
        shape.setPen(QPen(Qt.GlobalColor.black, 0.1))
        path = QPainterPath(centre - QPointF(0.1, 0))
        path.lineTo(centre + QPointF(0.1, 0))
        shape.setPath(path)
        assert check_canvas_layout(canvas)["counts"]["text-shape-border-overlap"] == 0
        point = _painted_label_point(label)
        path = QPainterPath(point - QPointF(1, 0))
        path.lineTo(point + QPointF(1, 0))
        shape.setPath(path)
        assert check_canvas_layout(canvas)["counts"]["text-shape-border-overlap"] == 1


def test_arrow_label_work_bound_counts_only_the_added_comparisons() -> None:
    state = _state(
        {7: Atom("N", 0, 0), 42: Atom("C", 40, 0)},
        bonds=[Bond(7, 42)],
        notes=[{"text": "note", "x": 0, "y": 60}],
        arrows=[_labelled_arrow(labels={"above": "", "below": ""})],
    )
    state["shapes"] = [{"shape_kind": "rect", "rect": [0, 0, 10, 10]}]
    before = document_layout_check._layout_work_units(state)
    state["arrows"][0]["labels"] = {"above": "k_1", "below": "k_-1"}
    # 5 new text pairs, 2 borders, 2 arrow strokes, 2 bonds and 2 labels.
    assert document_layout_check._layout_work_units(state) == before + 13
