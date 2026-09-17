"""A shape state and the Shape record describe the same thing, both ways."""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from chemvas.domain.document import Shape, shape_from_state, shape_to_state

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = {
    "kind": "shape",
    "left": 10.0,
    "top": 20.5,
    "right": 110.0,
    "bottom": 80.25,
    "shape_kind": "rounded_rect",
    "stroke_style": "dashed",
}


def _document_shape_states() -> list[dict]:
    states: list[dict] = []
    for path in [
        *sorted((REPO_ROOT / "tests" / "fixtures").rglob("*.chemvas")),
        *sorted((REPO_ROOT / "examples").rglob("*.chemvas")),
    ]:
        document = json.loads(path.read_text(encoding="utf-8"))
        state = document.get("state", document)
        states.extend(state.get("shapes", []))
    return states


def test_the_repository_documents_contain_shapes_to_check() -> None:
    # Only one tracked document carries a shape today; the hand-written cases
    # below are what cover the optional keys and number types.
    assert _document_shape_states()


@pytest.mark.parametrize("state", _document_shape_states())
def test_every_saved_shape_survives_the_round_trip(state) -> None:
    assert shape_to_state(shape_from_state(state)) == state


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"fill": "#fedcba", "fill_alpha": 0.25},
        {"fill": "#abc"},
        {"fill_alpha": 1.0},
        {"fill_alpha": 0},
    ],
)
def test_optional_keys_stay_exactly_as_present_as_they_were(extra) -> None:
    state = {**BASE, **extra}

    assert shape_to_state(shape_from_state(state)) == state
    assert set(shape_to_state(shape_from_state(state))) == set(state)


def test_integer_and_decimal_numbers_become_floats_of_the_same_value() -> None:
    state = {
        **BASE,
        "left": 350,
        "top": Decimal("130.5"),
        "right": 390,
        "bottom": 155,
        "fill_alpha": 1,
    }

    shape = shape_from_state(state)

    assert (shape.left, shape.top, shape.right, shape.bottom, shape.fill_alpha) == (
        350.0,
        130.5,
        390.0,
        155.0,
        1.0,
    )
    assert all(
        type(value) is float
        for value in (
            shape.left,
            shape.top,
            shape.right,
            shape.bottom,
            shape.fill_alpha,
        )
    )
    assert shape_to_state(shape) == state


def test_a_decimal_comes_back_as_the_float_the_reader_would_have_made() -> None:
    # Decimal("0.1") != 0.1 in Python, so the promise is about the value the
    # document reader normalises to, not about the Decimal object.
    state = {**BASE, "left": Decimal("0.1")}

    assert shape_to_state(shape_from_state(state)) == {**BASE, "left": 0.1}


def test_a_shape_that_could_not_be_saved_cannot_be_built() -> None:
    shape = shape_from_state(BASE)

    for change in (
        {"shape_kind": "hexagon"},
        {"left": float("nan")},
        {"fill": "red"},
        {"fill_alpha": 7.0},
    ):
        with pytest.raises(ValueError, match="Invalid shape"):
            replace(shape, **change)


def test_a_shape_is_a_value() -> None:
    shape = shape_from_state(BASE)

    assert shape == Shape(
        left=10.0,
        top=20.5,
        right=110.0,
        bottom=80.25,
        shape_kind="rounded_rect",
        stroke_style="dashed",
    )
    with pytest.raises(FrozenInstanceError):
        shape.left = 0.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "state",
    [
        {key: value for key, value in BASE.items() if key != "bottom"},
        {**BASE, "note": "extra key"},
        {**BASE, "kind": "ts_bracket"},
        {**BASE, "shape_kind": "hexagon"},
        {**BASE, "shape_kind": ["rect"]},
        {**BASE, "stroke_style": "wavy"},
        {**BASE, "left": "10"},
        {**BASE, "left": True},
        {**BASE, "top": float("nan")},
        {**BASE, "fill": "fedcba"},
        {**BASE, "fill": "#12"},
        {**BASE, "fill_alpha": 1.5},
        {**BASE, "fill_alpha": -0.1},
        {**BASE, "right": None},
        {**BASE, "bottom": "x"},
        {**BASE, "fill_alpha": "0.5"},
    ],
)
@pytest.mark.parametrize(
    "error", ["Invalid Chemvas file.", "Invalid clipboard payload."]
)
def test_what_is_not_a_shape_state_is_refused_with_the_callers_message(
    state, error
) -> None:
    with pytest.raises(ValueError, match=re.escape(error)):
        shape_from_state(state, error=error)
