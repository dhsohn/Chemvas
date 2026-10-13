from __future__ import annotations

import random

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath

from chemvas.ui.export import layout_spatial


def _rect(x, y, width=2, height=2):
    path = QPainterPath()
    path.addRect(QRectF(x, y, width, height))
    return path


def test_spatial_candidates_match_exhaustive_bounds_with_stable_order():
    rng = random.Random(183)
    paths = [
        _rect(
            rng.randrange(100),
            rng.randrange(100),
            rng.randrange(1, 20),
            rng.randrange(1, 20),
        )
        for _ in range(150)
    ]
    expected = {
        (i, j)
        for i in range(len(paths))
        for j in range(i + 1, len(paths))
        if paths[i].boundingRect().intersects(paths[j].boundingRect())
    }
    actual = list(layout_spatial.overlapping_bounds(paths))
    assert set(actual) == expected
    assert len(actual) == len(expected)
    assert list(layout_spatial.overlapping_bounds(paths)) == actual


@pytest.mark.parametrize("axis", ["horizontal", "vertical", "grid"])
def test_twenty_thousand_sparse_paths_fit_search_budget(axis):
    paths = [
        _rect(
            i * 5
            if axis == "horizontal"
            else 0
            if axis == "vertical"
            else (i % 200) * 5,
            i * 5
            if axis == "vertical"
            else 0
            if axis == "horizontal"
            else (i // 200) * 5,
        )
        for i in range(20_000)
    ]
    assert list(layout_spatial.overlapping_bounds(paths)) == []


def test_dense_search_budget_fails_closed_even_for_unsupported_pairs(monkeypatch):
    monkeypatch.setattr(layout_spatial, "MAX_SPATIAL_PROBES", 1000)
    with pytest.raises(ValueError, match="layout spatial-search limit"):
        list(layout_spatial.overlapping_bounds([_rect(0, 0) for _ in range(100)]))


def test_empty_paths_are_not_candidates():
    assert list(layout_spatial.overlapping_bounds([QPainterPath(), _rect(0, 0)])) == []


@pytest.mark.parametrize(
    "limit", ["MAX_PATH_ELEMENTS", "MAX_TOTAL_PATH_ELEMENTS", "MAX_COLLISION_PATHS"]
)
def test_path_memory_limits_fail_closed(monkeypatch, limit):
    monkeypatch.setattr(layout_spatial, limit, 1)
    with pytest.raises(ValueError, match="layout .*limit"):
        list(layout_spatial.overlapping_bounds([_rect(0, 0), _rect(5, 5)]))


def test_nonfinite_bounds_fail_closed():
    class NonFinite:
        def elementCount(self):
            return 5

        def boundingRect(self):
            return QRectF(float("nan"), 0, 1, 1)

    with pytest.raises(ValueError, match="non-finite"):
        layout_spatial.validate_path(NonFinite())
