from __future__ import annotations

import base64
import io
import re
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, PngImagePlugin
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.core.svg_roundtrip import extract_chemvas_document_from_svg
from chemvas.domain.document import image_state_from_bytes
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import (
    ExportPlan,
    export_scene,
    pdf_page_size,
    render_scene_to_pdf_bytes,
    render_scene_to_svg_bytes,
)
from chemvas.ui.image_item import ImageItem


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _state(atoms=()):
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": list(atoms),
            "bonds": [],
        }
    )


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
@pytest.mark.parametrize("sink", ["clipboard", "plain", "editable"])
def test_svg_render_strips_image_text_but_keeps_pixels_and_document_source(
    tmp_path, image_format, sink
):
    source = io.BytesIO()
    pixels = Image.new("RGBA", (16, 12), (17, 83, 219, 128))
    if image_format == "PNG":
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("Author", "synthetic-author")
        metadata.add_text("Comment", "/synthetic/private/figure", zip=True)
        metadata.add_itxt("Description", "synthetic-text", zip=True)
        pixels.save(source, format="PNG", pnginfo=metadata)
    else:
        pixels.convert("RGB").save(
            source, format="JPEG", comment=b"synthetic-private-comment"
        )
    data = source.getvalue()
    original = QImage.fromData(data)
    assert original.textKeys(), "The regression needs a metadata-bearing source"
    state = _state()
    state["images"] = [image_state_from_bytes(data)]
    with offscreen_canvas(state, command="export-metadata-test") as (canvas, service):
        if sink == "clipboard":
            items = [
                item for item in canvas.scene().items() if isinstance(item, ImageItem)
            ]
            svg = render_scene_to_svg_bytes(
                canvas.scene(), source=QRectF(0, 0, 16, 12), items=items
            )
        else:
            path = tmp_path / "figure.svg"
            service.export_figure(str(path), editable_svg=sink == "editable")
            svg = path.read_bytes()
            if sink == "editable":
                restored = extract_chemvas_document_from_svg(path)
                assert restored.state["images"] == state["images"]
        assert service.snapshot_state()["images"] == state["images"]
    embedded = ET.fromstring(svg).find(".//{http://www.w3.org/2000/svg}image")
    assert embedded is not None
    href = embedded.attrib["{http://www.w3.org/1999/xlink}href"]
    decoded = QImage.fromData(base64.b64decode(href.split(",", 1)[1]))
    assert decoded.textKeys() == []
    assert decoded.size() == original.size()
    for y in range(original.height()):
        for x in range(original.width()):
            assert decoded.pixelColor(x, y) == original.pixelColor(x, y)


@pytest.mark.parametrize("fmt", ["png", "tiff", "svg", "pdf"])
@pytest.mark.parametrize("existing", [False, True])
def test_default_gui_export_checks_budget_before_painting_or_replacing(
    tmp_path, monkeypatch, fmt, existing
):
    state = _state(
        [
            {"id": 0, "element": "O", "x": 0, "y": 0},
            {"id": 1, "element": "N", "x": 100000, "y": 0},
        ]
    )
    output = tmp_path / f"figure.{fmt}"
    if existing:
        output.write_bytes(b"existing figure")

    def unexpected_paint(*args, **kwargs):
        pytest.fail("over-budget export reached the painter")

    monkeypatch.setattr(
        "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
        unexpected_paint,
    )
    with offscreen_canvas(state, command="export-budget-test") as (_canvas, service):
        with pytest.raises(ValueError, match="14400 points"):
            service.export_figure(str(output), fmt=fmt)
    assert (
        output.read_bytes() == b"existing figure" if existing else not output.exists()
    )
    assert list(tmp_path.iterdir()) == ([output] if existing else [])


@pytest.mark.parametrize("sizing", ["bond", "col1", "col2"])
def test_gui_export_checks_tall_column_and_raster_limits(tmp_path, monkeypatch, sizing):
    state = _state(
        [
            {"id": 0, "element": "O", "x": 0, "y": 0},
            {"id": 1, "element": "N", "x": 0, "y": 5000},
        ]
    )
    monkeypatch.setattr(
        "chemvas.ui.canvas_document_session_service.export_canvas_scene_for",
        lambda *args, **kwargs: pytest.fail("over-budget raster reached painting"),
    )
    with offscreen_canvas(state, command="export-budget-test") as (_canvas, service):
        with pytest.raises(ValueError, match="limit|14400 points"):
            service.export_figure(str(tmp_path / "tall.png"), fmt="png", sizing=sizing)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (422.9, 597.9, (423, 598)),
        (423.6, 598.6, (424, 599)),
        (596, 843, (596, 843)),
        (614.6, 794.6, (615, 795)),
    ],
)
def test_pdf_uses_custom_whole_point_page_without_standard_paper_snap(
    width, height, expected
):
    plan = ExportPlan(
        source_x=0,
        source_y=0,
        source_w=width,
        source_h=height,
        out_w_pt=width,
        out_h_pt=height,
    )
    page = pdf_page_size(plan).sizePoints()
    assert (page.width(), page.height()) == expected
    scene = QGraphicsScene()
    scene.addRect(QRectF(0, 0, width, height))
    data = render_scene_to_pdf_bytes(
        scene, source=QRectF(0, 0, width, height), items=scene.items()
    )
    match = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", data)
    assert match is not None
    assert tuple(float(value) for value in match.groups()) == expected


@pytest.mark.parametrize("sink", ["clipboard", "file"])
def test_pdf_paint_target_fits_actual_page_after_rounding(tmp_path, monkeypatch, sink):
    from chemvas.features.export import vector

    scene = QGraphicsScene()
    rect = QRectF(0, 0, 422.4, 597.4)
    scene.addRect(rect, QPen(Qt.PenStyle.NoPen))
    targets = []
    paint = vector.paint_scene_region

    def observed_paint(painter, source_scene, plan, width, height, background):
        targets.append((width, height))
        return paint(painter, source_scene, plan, width, height, background)

    monkeypatch.setattr(vector, "paint_scene_region", observed_paint)
    if sink == "clipboard":
        render_scene_to_pdf_bytes(scene, source=rect, items=scene.items())
    else:
        export_scene(
            scene,
            str(tmp_path / "figure.pdf"),
            fmt="pdf",
            margin=0,
            dpi=72,
            items=scene.items(),
        )
    assert targets == [(422, 597)]


@pytest.mark.parametrize("mode", ["P", "I;16"])
def test_metadata_scrub_preserves_palette_and_high_bit_depth(mode):
    source = io.BytesIO()
    image = Image.new(mode, (4, 2))
    if mode == "P":
        image.putpalette([17, 83, 219, 201, 31, 54] + [0] * (768 - 6))
        image.putpixel((1, 1), 1)
    else:
        image.putpixel((1, 1), 12345)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Author", "synthetic-private")
    image.save(source, format="PNG", pnginfo=metadata)
    data = source.getvalue()
    original = QImage.fromData(data)
    item = ImageItem(image_state_from_bytes(data))
    rendered = item.image()
    assert rendered.textKeys() == []
    assert rendered.format() == original.format()
    assert rendered.colorTable() == original.colorTable()
    assert rendered.colorSpace() == original.colorSpace()
    for y in range(original.height()):
        for x in range(original.width()):
            assert rendered.pixelColor(x, y) == original.pixelColor(x, y)
    assert base64.b64decode(item.image_state()["data_base64"]) == data


def test_failed_metadata_pixel_copy_rejects_instead_of_loading_a_blank_image(
    monkeypatch,
):
    source = io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Author", "synthetic-author")
    Image.new("RGB", (4, 4), "blue").save(source, format="PNG", pnginfo=metadata)
    data = source.getvalue()
    assert not QImage.fromData(data).isNull()
    constructor = Mock(return_value=QImage())
    constructor.fromData = QImage.fromData
    monkeypatch.setattr("chemvas.ui.image_item.QImage", constructor)
    with pytest.raises(ValueError, match="pixels could not be copied"):
        ImageItem(image_state_from_bytes(data))
