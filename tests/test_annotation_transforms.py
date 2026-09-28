from dataclasses import replace

import pytest

from chemvas.domain.document import (
    VALID_ARC_KINDS,
    VALID_EQUILIBRIUM_KINDS,
    Arrow,
    Shape,
    TSBracket,
)
from chemvas.features.annotations import flip_annotation, rotate_annotation


@pytest.mark.parametrize("horizontal", [False, True])
@pytest.mark.parametrize("kind", sorted(VALID_ARC_KINDS | VALID_EQUILIBRIUM_KINDS))
def test_arrow_reflection_is_involutive_and_preserves_label_side(kind, horizontal):
    equilibrium = kind in VALID_EQUILIBRIUM_KINDS
    record = Arrow(
        kind=kind,
        start=(2.0, 3.0),
        end=(22.0, 13.0),
        color="#123456",
        labels=(("above", "heat"), ("below", "solvent")) if equilibrium else (),
    )
    flipped = flip_annotation(record, center=(8.0, 9.0), horizontal=horizontal)
    assert flipped.start == ((14.0, 3.0) if horizontal else (2.0, 15.0))
    assert flipped.color == record.color
    if equilibrium:
        assert flipped.mirrored
        assert dict(flipped.labels) == (
            {"above": "heat", "below": "solvent"}
            if horizontal
            else {"below": "heat", "above": "solvent"}
        )
    else:
        assert flipped.kind != record.kind
    assert flip_annotation(flipped, center=(8.0, 9.0), horizontal=horizontal) == record


@pytest.mark.parametrize(
    "record",
    [
        Shape(
            left=10,
            top=20,
            right=30,
            bottom=60,
            shape_kind="rect",
            stroke_style="dashed",
            fill="#123456",
            fill_alpha=0.3,
            z=-5,
        ),
        TSBracket(left=10, top=20, right=30, bottom=60, bracket_kind="square_pair"),
    ],
)
def test_axis_aligned_records_orbit_without_rotating_their_bounds(record):
    rotated = rotate_annotation(record, center=(0, 0), angle_degrees=90)
    assert (rotated.left, rotated.top, rotated.right, rotated.bottom) == pytest.approx(
        (-50, 0, -30, 40)
    )
    assert (
        replace(
            rotated,
            left=record.left,
            top=record.top,
            right=record.right,
            bottom=record.bottom,
        )
        == record
    )
    restored = rotate_annotation(rotated, center=(0, 0), angle_degrees=-90)
    assert (
        restored.left,
        restored.top,
        restored.right,
        restored.bottom,
    ) == pytest.approx((10, 20, 30, 60))
    assert (
        flip_annotation(
            flip_annotation(record, center=(8, 9), horizontal=True),
            center=(8, 9),
            horizontal=True,
        )
        == record
    )


def test_curved_arrow_rotation_preserves_control_geometry_and_style():
    arrow = Arrow(
        kind="curved_single",
        start=(10, 0),
        end=(20, 0),
        control=(15, 5),
        color="#abcdef",
        double=True,
    )
    rotated = rotate_annotation(arrow, center=(0, 0), angle_degrees=90)
    assert rotated.start == pytest.approx((0, 10))
    assert rotated.end == pytest.approx((0, 20))
    assert rotated.control == pytest.approx((-5, 15))
    assert (
        replace(rotated, start=arrow.start, end=arrow.end, control=arrow.control)
        == arrow
    )
