from __future__ import annotations

from dataclasses import dataclass

import pytest
from chemvas.bootstrap import document_render


@dataclass(frozen=True)
class _Plan:
    out_w_pt: float
    out_h_pt: float


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("win32", "windows"), ("linux", "offscreen"), ("darwin", "offscreen")],
)
def test_qt_platform_for_render(platform: str, expected: str) -> None:
    assert document_render._qt_platform_for_render(platform) == expected


def test_svg_budget_reports_points_without_raster_dimensions() -> None:
    assert document_render._validate_render_budget(
        _Plan(144.0, 72.0),
        output_format="svg",
        dpi=1200,
    ) == (None, None)


def test_png_budget_uses_point_size_and_dpi() -> None:
    assert document_render._validate_render_budget(
        _Plan(144.0, 72.0),
        output_format="png",
        dpi=300,
    ) == (600, 300)


@pytest.mark.parametrize(
    "plan",
    [
        _Plan(0.0, 72.0),
        _Plan(-1.0, 72.0),
        _Plan(document_render.MAX_VECTOR_DIMENSION_POINTS + 0.1, 72.0),
    ],
)
def test_render_budget_rejects_invalid_or_extreme_point_dimensions(
    plan: _Plan,
) -> None:
    with pytest.raises(ValueError, match="points per side"):
        document_render._validate_render_budget(
            plan,
            output_format="svg",
            dpi=300,
        )


def test_png_budget_rejects_side_and_area_overflow() -> None:
    with pytest.raises(ValueError, match="PNG render exceeds"):
        document_render._validate_render_budget(
            _Plan(720.0, 720.0),
            output_format="png",
            dpi=1200,
        )
    with pytest.raises(ValueError, match="PNG render exceeds"):
        document_render._validate_render_budget(
            _Plan(3601.0, 3601.0),
            output_format="png",
            dpi=100,
        )


def test_graphics_record_count_includes_model_and_scene_records() -> None:
    state: dict[str, object] = {
        "model": {"atoms": {0: {}}, "bonds": [{"a": 0, "b": 1}]},
        "notes": [{"text": "n"}],
        "arrows": [{"kind": "arrow"}],
    }

    assert document_render._graphics_record_count(state) == 4
