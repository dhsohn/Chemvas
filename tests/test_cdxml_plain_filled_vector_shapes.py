"""Plain filled native rectangles and circles import as vector shapes, not raster images."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from chemvas.domain.document.images import MAX_DOCUMENT_IMAGES
from chemvas.features.cdxml_document import parse_cdxml_document
from chemvas.features.cdxml_native_writer import update_native_document

_PAGE = '<page id="1" BoundingBox="0 0 400 300">'


def _cdxml(body: str, *, root_line_width: str = "1.5") -> bytes:
    return (
        f'<CDXML LineWidth="{root_line_width}"><colortable>'
        f'<color r="1" g="0" b="0"/></colortable>{_PAGE}{body}</page></CDXML>'
    ).encode()


def _filled_rect(
    identity: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    line_width: str | None = "0",
    extra: str = "",
) -> str:
    attrs = (
        f'id="{identity}" GraphicType="Rectangle" RectangleType="Filled" '
        f'BoundingBox="{x1} {y1} {x2} {y2}" color="2"'
    )
    if line_width is not None:
        attrs += f' LineWidth="{line_width}"'
    return f"<graphic {attrs}{extra}/>"


def _filled_circle(
    identity: int,
    cx: float,
    cy: float,
    r: float,
    *,
    line_width: str | None = "0",
) -> str:
    attrs = (
        f'id="{identity}" GraphicType="Oval" OvalType="Circle Filled" '
        f'BoundingBox="{cx + r} {cy} {cx} {cy + r}" '
        f'Center3D="{cx} {cy} 0" MajorAxisEnd3D="{cx + r} {cy} 0" '
        f'MinorAxisEnd3D="{cx} {cy + r} 0" color="2"'
    )
    if line_width is not None:
        attrs += f' LineWidth="{line_width}"'
    return f"<graphic {attrs}/>"


def test_local_zero_line_width_imports_as_shape_not_image():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 50, 50, 80, 90))).state
    assert len(state["shapes"]) == 1
    assert state["images"] == []
    shape = state["shapes"][0]
    assert shape["shape_kind"] == "rect"
    assert shape["stroke_style"] == "none"
    assert shape["fill"] == "#ff0000"
    assert shape.get("fill_alpha") == 1.0
    assert state["cdxml_source"]["items"]["shapes"] == ["2"]


def test_inherited_zero_without_local_line_width():
    state = parse_cdxml_document(
        _cdxml(_filled_rect(2, 10, 10, 30, 40, line_width=None), root_line_width="0")
    ).state
    assert len(state["shapes"]) == 1
    assert state["shapes"][0]["stroke_style"] == "none"


def test_chemdraw_omitted_width_has_no_pen_even_with_inherited_outline():
    state = parse_cdxml_document(
        _cdxml(_filled_rect(2, 10, 10, 30, 40, line_width=None), root_line_width="10")
    ).state
    assert len(state["shapes"]) == 1
    assert state["shapes"][0]["stroke_style"] == "none"
    assert state["images"] == []


def test_positive_local_line_width_stays_raster_image():
    state = parse_cdxml_document(
        _cdxml(_filled_rect(2, 10, 10, 30, 40, line_width="2"))
    ).state
    assert state["shapes"] == []
    assert len(state["images"]) == 1


def test_many_filled_rectangles_avoid_image_limit():
    count = MAX_DOCUMENT_IMAGES + 5
    graphics = "".join(_filled_rect(i + 2, 0, 0, 5, 5) for i in range(count))
    state = parse_cdxml_document(_cdxml(graphics)).state
    assert len(state["shapes"]) == count
    assert state["images"] == []


def test_circle_geometry_from_center_and_axes():
    state = parse_cdxml_document(_cdxml(_filled_circle(2, 100, 100, 20))).state
    shape = state["shapes"][0]
    assert shape["shape_kind"] == "circle"
    assert shape["left"] == pytest.approx(-120)
    assert shape["top"] == pytest.approx(-70)
    assert shape["right"] == pytest.approx(-80)
    assert shape["bottom"] == pytest.approx(-30)


def test_reversed_bounding_box_normalizes_without_geometry_change():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 80, 90, 50, 50))).state
    shape = state["shapes"][0]
    assert shape["left"] == pytest.approx(-150)
    assert shape["top"] == pytest.approx(-100)
    assert shape["right"] - shape["left"] == pytest.approx(30)
    assert shape["bottom"] - shape["top"] == pytest.approx(40)


def test_recolor_preserves_reversed_bounding_box_bytes():
    raw = _cdxml(_filled_rect(2, 80, 90, 50, 50))
    state = parse_cdxml_document(raw).state
    state["shapes"][0]["fill"] = "#0000ff"
    saved = update_native_document(state)
    assert b'BoundingBox="80 90 50 50"' in saved


def test_native_save_preserves_shape_binding_and_linewidth():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 50, 50, 80, 90))).state
    saved = update_native_document(state)
    root = ET.fromstring(saved)
    graphic = root.find('.//graphic[@id="2"]')
    assert graphic is not None
    assert graphic.get("LineWidth") == "0"
    assert graphic.get("RectangleType") == "Filled"
    rebound = parse_cdxml_document(saved).state
    assert len(rebound["shapes"]) == 1
    assert rebound["cdxml_source"]["items"]["shapes"] == ["2"]
    assert rebound["images"] == []


def test_moved_shape_updates_native_graphic_without_duplicate_bindings():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 50, 50, 80, 90))).state
    shape = state["shapes"][0]
    shape["left"] += 5
    shape["right"] += 5
    saved = update_native_document(state)
    rebound = parse_cdxml_document(saved).state
    assert len(rebound["shapes"]) == 1
    assert rebound["cdxml_source"]["items"]["shapes"] == ["2"]
    assert rebound["shapes"][0]["left"] == pytest.approx(shape["left"])


def test_invalid_line_width_rejects_import():
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(_cdxml(_filled_rect(2, 10, 10, 30, 40, line_width="500")))


def test_zero_width_stroke_only_is_rejected():
    line = (
        '<graphic id="2" GraphicType="Line" BoundingBox="10 10 40 40" LineWidth="0"/>'
    )
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(_cdxml(line))


def test_perpendicular_axes_use_vector_and_slanted_axes_keep_raster():
    attrs = ' Center3D="20 25 0" MajorAxisEnd3D="30 25 0" MinorAxisEnd3D="20 40 0"'
    assert (
        len(
            parse_cdxml_document(
                _cdxml(_filled_rect(2, 10, 10, 30, 40, extra=attrs))
            ).state["shapes"]
        )
        == 1
    )
    slanted = attrs.replace("30 25", "27 30")
    raw = _cdxml(_filled_rect(2, 10, 10, 30, 40, line_width=None, extra=slanted))
    state = parse_cdxml_document(raw).state
    assert state["shapes"] == []
    assert len(state["images"]) == 1
    with pytest.raises(ValueError, match="line width"):
        parse_cdxml_document(_cdxml(_filled_rect(2, 10, 10, 30, 40, extra=slanted)))


def test_circle_resize_keeps_equal_perpendicular_axes():
    state = parse_cdxml_document(_cdxml(_filled_circle(2, 100, 100, 20))).state
    state["shapes"][0]["right"] += 10
    raw = update_native_document(state)
    reopened = parse_cdxml_document(raw).state["shapes"][0]
    assert reopened["left"] == pytest.approx(-115)
    assert reopened["right"] - reopened["left"] == pytest.approx(40)
    assert reopened["bottom"] - reopened["top"] == pytest.approx(40)


def test_stroke_change_on_save_is_refused():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 50, 50, 80, 90))).state
    state["shapes"][0]["stroke_style"] = "solid"
    with pytest.raises(ValueError, match="stroke"):
        update_native_document(state)


def test_linked_fallback_moves_with_retained_graphic():
    target = _filled_rect(2, 10, 10, 30, 40, line_width=None)
    fallback = _filled_rect(3, 10, 10, 30, 40, extra=' SupersededBy="2"')
    state = parse_cdxml_document(_cdxml(target + fallback)).state
    assert state["shapes"] == []
    assert state["cdxml_source"]["items"]["images"] == ["2"]
    state["images"][0]["x"] += 50
    root = ET.fromstring(update_native_document(state))
    assert [item.get("BoundingBox") for item in root.iter("graphic")] == [
        "60 10 80 40",
        "60 10 80 40",
    ]


def test_graphic_only_page_uses_arrow_paint_band():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 10, 10, 30, 40))).state
    assert state["shapes"][0]["z"] == 1.0


def test_recolored_zero_outline_shape_updates_native_color():
    state = parse_cdxml_document(_cdxml(_filled_rect(2, 50, 50, 80, 90))).state
    state["shapes"][0]["fill"] = "#0000ff"
    saved = update_native_document(state)
    root = ET.fromstring(saved)
    graphic = root.find('.//graphic[@id="2"]')
    assert graphic is not None
    assert "color" in graphic.attrib


def test_zero_outline_circle_imports_as_shape():
    state = parse_cdxml_document(_cdxml(_filled_circle(2, 40, 40, 15))).state
    assert len(state["shapes"]) == 1
    assert state["shapes"][0]["stroke_style"] == "none"
    assert state["images"] == []
