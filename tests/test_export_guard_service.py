"""The GUI and CLI share dimension checks before creating public output."""

from types import SimpleNamespace

import pytest

from chemvas.features.export import points_for_mm
from chemvas.ui.export_guard_service import validate_export_budget


def _plan(width=72.0, height=144.0):
    return SimpleNamespace(out_w_pt=width, out_h_pt=height)


@pytest.mark.parametrize("fmt", ["svg", "pdf", "png", "tiff"])
def test_maximum_height_is_checked_for_all_gui_formats(fmt):
    plan = _plan(height=73.8567)
    final_points = {"svg": 74, "pdf": 73.8567, "png": 73.92, "tiff": 73.92}[fmt]
    actual_height = final_points / points_for_mm(1.0)
    validate_export_budget(
        plan, output_format=fmt, dpi=300, max_height_mm=actual_height
    )
    with pytest.raises(ValueError, match="output was not resized"):
        validate_export_budget(
            plan, output_format=fmt, dpi=300, max_height_mm=actual_height - 0.00001
        )


@pytest.mark.parametrize("fmt", ["svg", "png", "tiff"])
def test_rounded_native_height_not_nominal_plan_controls_ceiling(fmt):
    plan = _plan(height=73.8567)
    nominal_height = plan.out_h_pt / points_for_mm(1.0)
    with pytest.raises(ValueError, match="output was not resized"):
        validate_export_budget(
            plan, output_format=fmt, dpi=300, max_height_mm=nominal_height
        )


def test_rounded_down_svg_height_can_fit_smaller_than_nominal_plan():
    validate_export_budget(
        _plan(height=74.2),
        output_format="svg",
        dpi=300,
        max_height_mm=74 / points_for_mm(1.0),
    )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_height_rejected(value):
    with pytest.raises(ValueError, match="positive finite"):
        validate_export_budget(
            _plan(), output_format="svg", dpi=300, max_height_mm=value
        )


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), 14400.01])
@pytest.mark.parametrize("dimension", ["out_w_pt", "out_h_pt"])
def test_vector_dimension_cap(value, dimension):
    plan = _plan()
    setattr(plan, dimension, value)
    with pytest.raises(ValueError, match="rendered dimensions"):
        validate_export_budget(plan, output_format="svg", dpi=300)


@pytest.mark.parametrize("fmt", ["png", "tiff"])
def test_raster_uses_native_rounding_and_area_limits(fmt):
    assert validate_export_budget(_plan(), output_format=fmt, dpi=300) == (300, 600)
    assert validate_export_budget(_plan(1.1, 2.2), output_format=fmt, dpi=150) == (
        2,
        5,
    )
    assert validate_export_budget(_plan(1200, 1200), output_format=fmt, dpi=300) == (
        5000,
        5000,
    )
    with pytest.raises(ValueError, match="area limit"):
        validate_export_budget(_plan(1201, 1200), output_format=fmt, dpi=300)
    with pytest.raises(ValueError, match="area limit"):
        validate_export_budget(_plan(2401, 10), output_format=fmt, dpi=300)


def test_exact_one_inch_height_is_inclusive():
    validate_export_budget(
        _plan(height=72), output_format="svg", dpi=300, max_height_mm=25.4
    )


@pytest.mark.parametrize("dpi", [0, -1, float("inf"), float("nan"), True])
def test_raster_rejects_invalid_resolution(dpi):
    with pytest.raises(ValueError, match="resolution"):
        validate_export_budget(_plan(), output_format="png", dpi=dpi)


def test_non_png_does_not_invent_raster_dimensions():
    assert validate_export_budget(_plan(), output_format="svg", dpi=300) == (None, None)
