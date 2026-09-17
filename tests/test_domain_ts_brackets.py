"""A TS bracket state and the TSBracket record describe the same thing, both ways."""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from chemvas.domain.document import (
    TSBracket,
    normalized_ts_bracket,
    ts_bracket_from_state,
    ts_bracket_to_state,
)
from chemvas.domain.document.state import VALID_TS_BRACKET_KINDS
from chemvas.features.annotations import BRACKET_MENU_SPECS, DEFAULT_BRACKET_KIND

REPO_ROOT = Path(__file__).resolve().parents[1]

BASE = {
    "kind": "ts_bracket",
    "left": 10.0,
    "top": 20.5,
    "right": 110.0,
    "bottom": 80.25,
    "bracket_kind": "double_dagger",
}


def _document_ts_bracket_states() -> list[dict]:
    states: list[dict] = []
    for path in [
        *sorted((REPO_ROOT / "tests" / "fixtures").rglob("*.chemvas")),
        *sorted((REPO_ROOT / "examples").rglob("*.chemvas")),
    ]:
        document = json.loads(path.read_text(encoding="utf-8"))
        state = document.get("state", document)
        states.extend(state.get("ts_brackets", []))
    return states


def test_the_repository_documents_contain_ts_brackets_to_check() -> None:
    # Only one tracked document carries a bracket today; the hand-written
    # cases below are what cover the kinds and number types.
    assert _document_ts_bracket_states()


@pytest.mark.parametrize("state", _document_ts_bracket_states())
def test_every_saved_ts_bracket_survives_the_round_trip(state) -> None:
    assert ts_bracket_to_state(ts_bracket_from_state(state)) == state


@pytest.mark.parametrize("bracket_kind", sorted(VALID_TS_BRACKET_KINDS))
def test_every_bracket_kind_survives_the_round_trip(bracket_kind) -> None:
    state = {**BASE, "bracket_kind": bracket_kind}

    assert ts_bracket_to_state(ts_bracket_from_state(state)) == state


def test_the_bracket_menu_offers_exactly_the_kinds_a_document_may_hold() -> None:
    # The features layer used to keep its own copy of the kind set.
    assert {kind for _label, kind in BRACKET_MENU_SPECS} == VALID_TS_BRACKET_KINDS
    assert len(BRACKET_MENU_SPECS) == len(VALID_TS_BRACKET_KINDS)
    assert DEFAULT_BRACKET_KIND in VALID_TS_BRACKET_KINDS


def test_integer_and_decimal_numbers_become_floats_of_the_same_value() -> None:
    state = {**BASE, "left": 350, "top": Decimal("130.5"), "right": 390, "bottom": 155}

    ts_bracket = ts_bracket_from_state(state)

    edges = (ts_bracket.left, ts_bracket.top, ts_bracket.right, ts_bracket.bottom)
    assert edges == (350.0, 130.5, 390.0, 155.0)
    assert all(type(value) is float for value in edges)
    assert ts_bracket_to_state(ts_bracket) == state


def test_a_decimal_comes_back_as_the_float_the_reader_would_have_made() -> None:
    # Decimal("0.1") != 0.1 in Python, so the promise is about the value the
    # document reader normalises to, not about the Decimal object.
    state = {**BASE, "left": Decimal("0.1")}

    assert ts_bracket_to_state(ts_bracket_from_state(state)) == {**BASE, "left": 0.1}


def test_a_ts_bracket_that_could_not_be_saved_cannot_be_built() -> None:
    ts_bracket = ts_bracket_from_state(BASE)

    for change in (
        {"bracket_kind": "angle_pair"},
        {"left": float("nan")},
        {"bottom": float("inf")},
    ):
        with pytest.raises(ValueError, match="Invalid TS bracket"):
            replace(ts_bracket, **change)


def test_a_ts_bracket_is_a_value() -> None:
    ts_bracket = ts_bracket_from_state(BASE)

    assert ts_bracket == TSBracket(
        left=10.0, top=20.5, right=110.0, bottom=80.25, bracket_kind="double_dagger"
    )
    with pytest.raises(FrozenInstanceError):
        ts_bracket.left = 0.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "state",
    [
        {key: value for key, value in BASE.items() if key != "bottom"},
        {key: value for key, value in BASE.items() if key != "bracket_kind"},
        {**BASE, "stroke_style": "dashed"},
        {**BASE, "kind": "shape"},
        {**BASE, "bracket_kind": "angle_pair"},
        {**BASE, "bracket_kind": ["dagger"]},
        {**BASE, "bracket_kind": None},
        {**BASE, "left": "10"},
        {**BASE, "left": True},
        {**BASE, "top": float("nan")},
        {**BASE, "right": None},
        {**BASE, "bottom": "x"},
    ],
)
@pytest.mark.parametrize(
    "error", ["Invalid Chemvas file.", "Invalid clipboard payload."]
)
def test_what_is_not_a_ts_bracket_state_is_refused_with_the_callers_message(
    state, error
) -> None:
    with pytest.raises(ValueError, match=re.escape(error)):
        ts_bracket_from_state(state, error=error)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ({"left": 110.0, "right": 10.0}, {"left": 10.0, "right": 110.0}),
        ({"top": 80.25, "bottom": 20.5}, {"top": 20.5, "bottom": 80.25}),
        (
            {"left": 110.0, "right": 10.0, "top": 80.25, "bottom": 20.5},
            {"left": 10.0, "right": 110.0, "top": 20.5, "bottom": 80.25},
        ),
    ],
)
def test_the_canonical_form_is_an_ordered_rectangle(given, expected) -> None:
    ts_bracket = normalized_ts_bracket(ts_bracket_from_state({**BASE, **given}))

    assert ts_bracket_to_state(ts_bracket) == {**BASE, **expected}


def test_ordering_keeps_the_edges_it_was_given() -> None:
    # QRectF(347.43, .., 10.2, ..).normalized() hands the left edge back as
    # 10.199999999999989; ordering a record is a swap, not arithmetic.
    ts_bracket = normalized_ts_bracket(
        ts_bracket_from_state(
            {**BASE, "left": 347.43, "right": 10.2, "top": 80.25, "bottom": 0.1 + 0.2}
        )
    )

    assert (ts_bracket.left, ts_bracket.right) == (10.2, 347.43)
    # Every digit of an edge is kept, not just the ones a rounding would.
    assert (ts_bracket.top, ts_bracket.bottom) == (0.30000000000000004, 80.25)


def test_a_canonical_ts_bracket_is_left_alone() -> None:
    ts_bracket = ts_bracket_from_state({**BASE, "left": 10.2, "right": 347.43})

    assert normalized_ts_bracket(ts_bracket) == ts_bracket
    assert ts_bracket_to_state(normalized_ts_bracket(ts_bracket)) == {
        **BASE,
        "left": 10.2,
        "right": 347.43,
    }
