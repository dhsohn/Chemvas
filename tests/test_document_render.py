from __future__ import annotations

from dataclasses import dataclass

import pytest

from chemvas.bootstrap import document_render
from chemvas.ui.export_guard_service import validate_export_budget


@dataclass(frozen=True)
class _Plan:
    out_w_pt: float
    out_h_pt: float


def test_svg_budget_reports_points_without_raster_dimensions() -> None:
    assert validate_export_budget(
        _Plan(144.0, 72.0),
        output_format="svg",
        dpi=1200,
    ) == (None, None)


def test_png_budget_uses_point_size_and_dpi() -> None:
    assert validate_export_budget(
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
        _Plan(float("nan"), 72.0),
        _Plan(72.0, float("inf")),
        _Plan(72.0, float("nan")),
    ],
)
def test_render_budget_rejects_invalid_or_extreme_point_dimensions(
    plan: _Plan,
) -> None:
    with pytest.raises(ValueError, match="points per side"):
        validate_export_budget(
            plan,
            output_format="svg",
            dpi=300,
        )


def test_png_budget_rejects_side_and_area_overflow() -> None:
    with pytest.raises(ValueError, match="PNG render exceeds"):
        validate_export_budget(
            _Plan(720.0, 720.0),
            output_format="png",
            dpi=1200,
        )
    with pytest.raises(ValueError, match="PNG render exceeds"):
        validate_export_budget(
            _Plan(3601.0, 3601.0),
            output_format="png",
            dpi=100,
        )


@pytest.mark.parametrize("output_format", ["svg", "png"])
def test_max_height_is_an_inclusive_gate_not_a_resize(output_format: str) -> None:
    plan = _Plan(144.0, 72.0)
    expected = (600, 300) if output_format == "png" else (None, None)
    assert (
        validate_export_budget(
            plan, output_format=output_format, dpi=300, max_height_mm=25.4
        )
        == expected
    )
    assert plan == _Plan(144.0, 72.0)
    with pytest.raises(ValueError, match="height exceeds --max-height-mm"):
        validate_export_budget(
            plan, output_format=output_format, dpi=300, max_height_mm=25.39
        )


@pytest.mark.parametrize("height", [0.0, -1.0, float("nan"), float("inf")])
def test_direct_budget_rejects_invalid_maximum_height(height: float) -> None:
    with pytest.raises(ValueError, match="maximum height must be a positive finite"):
        validate_export_budget(
            _Plan(144.0, 72.0), output_format="svg", dpi=300, max_height_mm=height
        )
