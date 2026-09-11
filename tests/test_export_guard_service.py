"""The GUI and CLI share dimension checks before creating public output."""

import re
from types import SimpleNamespace

import pytest

from chemvas.features.export import ExportPlan, export_error_message, points_for_mm
from chemvas.ui.export_guard_service import validate_export_budget


def _plan(width=72.0, height=144.0):
    return SimpleNamespace(out_w_pt=width, out_h_pt=height)


@pytest.mark.parametrize("fmt", ["svg", "pdf", "png", "tiff"])
@pytest.mark.parametrize("dimension", ["out_w_pt", "out_h_pt"])
def test_output_that_rounds_to_zero_is_rejected_before_render(fmt, dimension):
    plan = _plan()
    setattr(plan, dimension, 0.01)
    with pytest.raises(ValueError, match="too small"):
        validate_export_budget(plan, output_format=fmt, dpi=300)


@pytest.mark.parametrize("fmt", ["png", "tiff"])
def test_single_pixel_raster_remains_supported(fmt):
    assert validate_export_budget(
        _plan(72 / 300, 72 / 300), output_format=fmt, dpi=300
    ) == (1, 1)


@pytest.mark.parametrize("fmt", ["svg", "pdf", "png", "tiff"])
def test_maximum_height_is_checked_for_all_gui_formats(fmt):
    plan = _plan(height=73.8567)
    final_points = {"svg": 74, "pdf": 74, "png": 73.92, "tiff": 73.92}[fmt]
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


@pytest.mark.parametrize(
    ("fmt", "height_points"),
    [("svg", 74.0), ("pdf", 74.0), ("png", 73.92), ("tiff", 73.92)],
)
def test_height_error_reports_actual_output_and_preserves_cli_diagnostic(
    fmt, height_points
):
    with pytest.raises(ValueError) as failure:
        validate_export_budget(
            _plan(height=73.8567), output_format=fmt, dpi=300, max_height_mm=20
        )
    assert str(failure.value) == (
        "rendered height exceeds --max-height-mm 20; output was not resized"
    )
    assert failure.value.height_mm == pytest.approx(height_points / points_for_mm(1))
    assert failure.value.maximum_mm == 20


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


@pytest.mark.parametrize(("width", "height"), [(72.0, 73.8567), (595.0, 840.2)])
def test_pdf_height_limit_matches_written_page_geometry(width, height):
    from PyQt6.QtWidgets import QApplication, QGraphicsScene

    from chemvas.features.export.vector import render_pdf_bytes

    _app = QApplication.instance() or QApplication([])
    scene = QGraphicsScene()
    scene.addLine(0, 0, width, height)
    plan = ExportPlan(
        source_x=0,
        source_y=0,
        source_w=width,
        source_h=height,
        out_w_pt=width,
        out_h_pt=height,
    )
    pdf = render_pdf_bytes(scene, scene.items(), plan, "white", None)
    box = re.search(rb"/MediaBox\s*\[([^\]]+)\]", pdf)
    assert box is not None
    page_height_mm = float(box.group(1).split()[3]) / points_for_mm(1)
    validate_export_budget(
        plan, output_format="pdf", dpi=300, max_height_mm=page_height_mm
    )
    with pytest.raises(ValueError) as failure:
        validate_export_budget(
            plan,
            output_format="pdf",
            dpi=300,
            max_height_mm=page_height_mm - 0.01,
        )
    assert failure.value.height_mm == pytest.approx(page_height_mm)
    assert f"{page_height_mm:.2f} mm high" in export_error_message(failure.value)
