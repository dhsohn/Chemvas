from __future__ import annotations

import base64
import random
import re
import struct
import zlib
from io import BytesIO
from xml.etree import ElementTree as ET

import pytest
from PIL import Image
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QGraphicsRectItem, QGraphicsScene

from chemvas.bootstrap import document_render
from chemvas.bootstrap.document_cli_shared import (
    graphics_record_count,
    offscreen_canvas,
)
from chemvas.core import document_io, svg_roundtrip
from chemvas.core.document_io import read_document, read_exact_document, write_document
from chemvas.domain.document import CANVAS_FILE_VERSION, image_state_from_bytes
from chemvas.features.document_composition import compose_document_state
from chemvas.features.document_patch import apply_document_patch
from chemvas.features.export import (
    collect_export_items,
    content_bounds,
    export_scene,
    render_scene_to_pdf_bytes,
    render_scene_to_svg_bytes,
)
from chemvas.ui.image_item import ImageItem
from chemvas.ui.layout_qa_service import check_canvas_layout


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    yield app


def _source_bytes(*, image_format="PNG", transparent=False, size=(64, 48)) -> bytes:
    width, height = size
    image = Image.frombytes(
        "RGB", size, random.Random(710).randbytes(width * height * 3)
    )
    if transparent:
        image = image.convert("RGBA")
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.putpixel((1, 0), (255, 0, 0, 128))
    # Distinct content at every outer corner catches accidental crop/trim.
    image.putpixel((width - 1, 0), (255, 0, 0))
    image.putpixel((0, height - 1), (0, 255, 0))
    image.putpixel((width - 1, height - 1), (0, 0, 255))
    with BytesIO() as buffer:
        image.save(buffer, format=image_format)
        return buffer.getvalue()


def _scene(data: bytes, **geometry):
    scene = QGraphicsScene()
    item = ImageItem(image_state_from_bytes(data, **geometry))
    scene.addItem(item)
    return scene, item


def _state(data: bytes, **geometry):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )
    state["images"] = [image_state_from_bytes(data, **geometry)]
    return state


def _svg_image(svg: bytes) -> QImage:
    root = ET.fromstring(svg)
    images = list(root.iter("{http://www.w3.org/2000/svg}image"))
    assert len(images) == 1
    href = images[0].attrib["{http://www.w3.org/1999/xlink}href"]
    assert href.startswith("data:image/png;base64,")
    return QImage.fromData(base64.b64decode(href.split(",", 1)[1]))


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_svg_copy_retains_original_pixel_dimensions_when_display_is_scaled(
    image_format,
):
    data = _source_bytes(image_format=image_format)
    scene, item = _scene(data, x=-30, y=20, width=16, height=12)
    items = collect_export_items(scene)
    bounds = content_bounds(items)
    assert items == [item]
    assert bounds == QRectF(-30, 20, 16, 12)

    svg = render_scene_to_svg_bytes(scene, source=bounds, items=items)

    decoded = _svg_image(svg)
    original = QImage.fromData(data)
    assert decoded.size() == original.size()
    for y in range(original.height()):
        for x in range(original.width()):
            assert decoded.pixelColor(x, y) == original.pixelColor(x, y)


def test_png_export_preserves_full_area_alpha_and_boundary_pixels(tmp_path):
    data = _source_bytes(transparent=True)
    scene, _item = _scene(data)
    path = tmp_path / "full.png"

    export_scene(scene, str(path), fmt="png", margin=0, dpi=72)

    output = QImage(str(path))
    original = QImage.fromData(data)
    assert output.size() == original.size()
    for x, y in [(0, 0), (1, 0), (63, 0), (0, 47), (63, 47), (32, 24)]:
        assert output.pixelColor(x, y) == original.pixelColor(x, y)


def test_svg_and_png_apply_object_opacity_without_changing_source(tmp_path):
    data = _source_bytes(transparent=True)
    scene, item = _scene(data, opacity=0.5)
    svg = render_scene_to_svg_bytes(
        scene, source=item.sceneBoundingRect(), items=[item]
    )
    assert any(
        element.attrib.get("opacity") == "0.5" for element in ET.fromstring(svg).iter()
    )
    assert _svg_image(svg).pixelColor(1, 0).alpha() == 128
    path = tmp_path / "faded.png"
    export_scene(scene, str(path), fmt="png", margin=0, dpi=72)
    output = QImage(str(path))
    assert output.pixelColor(63, 47).alpha() in {127, 128}
    assert output.pixelColor(1, 0).alpha() in {63, 64}
    assert base64.b64decode(item.image_state()["data_base64"]) == data


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
@pytest.mark.parametrize("selection", [False, True])
@pytest.mark.parametrize("target_width", [None, 32])
def test_zero_opacity_image_does_not_expand_export_bounds(
    tmp_path, fmt, selection, target_width
):
    data = _source_bytes()
    scene, visible = _scene(data)
    hidden_state = image_state_from_bytes(
        data, x=200_000, y=200_000, width=60_000, height=45_000, opacity=0
    )
    hidden = ImageItem(hidden_state)
    scene.addItem(hidden)
    items = [visible, hidden] if selection else None
    assert hidden.isVisible() and hidden.effectiveOpacity() == 0
    assert content_bounds(items or collect_export_items(scene)) == QRectF(0, 0, 64, 48)

    path = tmp_path / f"visible-only.{fmt}"
    plan = export_scene(
        scene,
        str(path),
        fmt=fmt,
        items=items,
        margin=0,
        dpi=72,
        target_width_pt=target_width,
    )

    assert (plan.source_x, plan.source_y, plan.source_w, plan.source_h) == (
        0,
        0,
        64,
        48,
    )
    assert (plan.out_w_pt, plan.out_h_pt) == (
        target_width or 64,
        (target_width or 64) * 0.75,
    )
    assert path.stat().st_size > 0
    if fmt == "png":
        output = QImage(str(path))
        assert output.width() == plan.out_w_pt
        assert output.height() == plan.out_h_pt
        assert output.pixelColor(output.width() - 1, output.height() - 1).alpha() == 255
    assert hidden.image_state() == hidden_state
    assert hidden.isVisible()


@pytest.mark.parametrize("selection", [False, True])
def test_only_zero_opacity_image_has_nothing_to_export(tmp_path, selection):
    scene, item = _scene(_source_bytes(), opacity=0)
    path = tmp_path / "empty.png"

    with pytest.raises(ValueError, match="There is nothing to export"):
        export_scene(
            scene,
            str(path),
            fmt="png",
            items=[item] if selection else None,
            margin=0,
            dpi=72,
        )

    assert not path.exists()
    assert not item.sceneBoundingRect().isEmpty()


def test_image_export_bounds_use_effective_opacity_without_changing_geometry():
    scene, item = _scene(_source_bytes(), opacity=0.5)
    parent = QGraphicsRectItem()
    scene.addItem(parent)
    item.setParentItem(parent)
    bounds = item.sceneBoundingRect()
    assert content_bounds([item]) == bounds

    parent.setOpacity(0)

    assert item.opacity() == 0.5 and item.effectiveOpacity() == 0
    assert content_bounds([item]) is None
    assert item.sceneBoundingRect() == bounds
    parent.setOpacity(1)
    assert content_bounds([item]) == bounds


def test_fully_transparent_pixels_keep_frame_at_positive_object_opacity():
    with BytesIO() as buffer:
        Image.new("RGBA", (64, 48), (0, 0, 0, 0)).save(buffer, format="PNG")
        data = buffer.getvalue()
    scene, item = _scene(data, opacity=0.5)

    assert content_bounds(collect_export_items(scene)) == QRectF(0, 0, 64, 48)
    assert base64.b64decode(item.image_state()["data_base64"]) == data


def test_zero_opacity_image_survives_native_and_mixed_editable_svg(tmp_path):
    data = _source_bytes(image_format="JPEG")
    state = _state(data, x=200_000, y=200_000, opacity=0)
    state["images"].append(image_state_from_bytes(_source_bytes(), x=50, y=70))
    native = tmp_path / "hidden-image.chemvas"
    write_document(native, state, CANVAS_FILE_VERSION)
    assert read_document(native).state["images"] == state["images"]

    with offscreen_canvas(state, command="image-opacity-test") as (_canvas, service):
        path = tmp_path / "hidden-image.svg"
        service.export_figure(str(path), fmt="svg", scope="sheet", editable_svg=True)

    restored = svg_roundtrip.extract_chemvas_document_from_svg(path)
    assert restored.state["images"] == state["images"]
    assert base64.b64decode(restored.state["images"][0]["data_base64"]) == data


def _pdf_image_streams(data):
    result = []
    for body in re.findall(rb"\d+ 0 obj\n(.*?)\nendobj", data, re.DOTALL):
        header, separator, stream = body.partition(b"\nstream\n")
        if b"/Subtype /Image" in header:
            assert separator
            result.append((header, stream.removesuffix(b"\nendstream")))
    return result


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
@pytest.mark.parametrize("output", ["clipboard", "file"])
def test_pdf_embeds_full_resolution_lossless_pixels(tmp_path, image_format, output):
    data = _source_bytes(image_format=image_format)
    scene, item = _scene(data, width=16, height=12)

    if output == "clipboard":
        pdf = render_scene_to_pdf_bytes(
            scene, source=item.sceneBoundingRect(), items=[item]
        )
    else:
        path = tmp_path / "figure.pdf"
        export_scene(scene, str(path), fmt="pdf", margin=0, dpi=300)
        pdf = path.read_bytes()

    streams = _pdf_image_streams(pdf)
    assert len(streams) == 1
    header, stream = streams[0]
    assert b"/Width 64" in header
    assert b"/Height 48" in header
    assert b"/FlateDecode" in header
    assert b"/DCTDecode" not in header
    original = QImage.fromData(data).convertToFormat(QImage.Format.Format_RGB888)
    assert original.bytesPerLine() == 64 * 3
    assert zlib.decompress(stream) == original.constBits().asstring(
        original.sizeInBytes()
    )


def test_pdf_preserves_alpha_mask_and_object_opacity():
    scene, item = _scene(_source_bytes(transparent=True), opacity=0.5)
    pdf = render_scene_to_pdf_bytes(
        scene, source=item.sceneBoundingRect(), items=[item]
    )
    streams = _pdf_image_streams(pdf)
    assert len(streams) == 2
    assert any(b"/SMask" in header for header, _stream in streams)
    opacities = [float(value) for value in re.findall(rb"/ca ([\d.]+)", pdf)]
    assert any(abs(value - 0.5) <= 1 / 255 for value in opacities)
    masks = [
        zlib.decompress(stream)
        for header, stream in streams
        if b"/DeviceGray" in header
    ]
    assert len(masks) == 1
    assert masks[0][:2] == bytes([0, 128])
    assert masks[0][-1] == 255


def test_sixteen_bit_png_source_survives_native_and_svg_export(tmp_path):
    pixels = struct.pack("<3072H", *(index * 997 % 65536 for index in range(3072)))
    with BytesIO() as buffer:
        Image.frombytes("I;16", (64, 48), pixels).save(buffer, format="PNG")
        data = buffer.getvalue()
    scene, item = _scene(data, width=16, height=12)
    svg = render_scene_to_svg_bytes(
        scene, source=item.sceneBoundingRect(), items=[item]
    )
    image = _svg_image(svg)
    assert image.format() == QImage.Format.Format_Grayscale16
    original = QImage.fromData(data)
    assert image.constBits().asstring(
        image.sizeInBytes()
    ) == original.constBits().asstring(original.sizeInBytes())
    path = tmp_path / "sixteen-bit.chemvas"
    write_document(path, _state(data), CANVAS_FILE_VERSION)
    assert (
        base64.b64decode(read_document(path).state["images"][0]["data_base64"]) == data
    )
    # PDF is a display export: Qt retains pixel dimensions but uses 8-bit RGB.
    pdf = render_scene_to_pdf_bytes(
        scene, source=item.sceneBoundingRect(), items=[item]
    )
    header, _stream = _pdf_image_streams(pdf)[0]
    assert b"/BitsPerComponent 8" in header
    assert b"/Width 64" in header and b"/Height 48" in header


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_native_editable_svg_roundtrip_keeps_original_encoded_bytes(
    tmp_path, image_format
):
    data = _source_bytes(image_format=image_format)
    state = _state(data, x=50, y=70, width=128, height=80, lock_aspect=False)
    with offscreen_canvas(state, command="image-export-test") as (_canvas, service):
        path = tmp_path / "editable.svg"
        service.export_figure(str(path), fmt="svg", scope="sheet", editable_svg=True)

    restored = svg_roundtrip.extract_chemvas_document_from_svg(path)
    assert restored.state["images"] == state["images"]
    assert base64.b64decode(restored.state["images"][0]["data_base64"]) == data


def test_cli_render_and_editable_svg_support_image_larger_than_old_envelopes(tmp_path):
    data = _source_bytes(size=(1500, 1500))
    state = _state(data, x=50, y=70, width=200, height=200)
    path = tmp_path / "source.chemvas"
    write_document(path, state, CANVAS_FILE_VERSION)
    assert path.stat().st_size > 8 * 1024 * 1024
    assert read_document(path).state["images"] == state["images"]
    output = tmp_path / "large.svg"

    report = document_render._render_document(
        path, output=output, background="transparent", dpi=300
    )

    assert report["graphics_records"] == 1
    payload = svg_roundtrip.create_editable_svg_payload(
        state, document_version=CANVAS_FILE_VERSION, scope="sheet"
    )
    svg_roundtrip.embed_chemvas_document_in_svg(output, payload)
    root = ET.parse(output).getroot()
    source = root.find(".//{https://chemvas.app/ns/svg-source/1}source")
    assert source is not None and len(source.text) > 8 * 1024 * 1024
    restored = svg_roundtrip.extract_chemvas_document_from_svg(output)
    assert base64.b64decode(restored.state["images"][0]["data_base64"]) == data


def test_image_full_rectangle_is_counted_and_checked_against_sheet():
    state = _state(_source_bytes(transparent=True), x=-1000, y=70, width=120, height=90)
    assert graphics_record_count(state) == 1
    with offscreen_canvas(state, command="image-layout-test") as (canvas, _service):
        report = check_canvas_layout(canvas, sheet_only=True)
    assert not report["ok"]
    assert report["warnings"][0]["items"] == [{"kind": "image", "index": 0}]
    assert report["warnings"][0]["bounds"] == [-1000.0, 70.0, 120.0, 90.0]


def test_graph_patch_retains_embedded_image_bytes_and_geometry():
    state = _state(_source_bytes(), x=10, y=20, width=30, height=40)
    result = apply_document_patch(
        state,
        {
            "format": "chemvas-graph-patch",
            "version": 1,
            "source_sha256": "a" * 64,
            "operations": [
                {
                    "op": "add_atom",
                    "atom_id": 0,
                    "element": "C",
                    "x": 0,
                    "y": 0,
                    "color": "#000000",
                    "explicit_label": False,
                }
            ],
        },
        source_sha256="a" * 64,
        document_version=CANVAS_FILE_VERSION,
    )
    assert result.state["images"] == state["images"]


def test_document_and_svg_envelope_limits_fail_before_parsing(tmp_path, monkeypatch):
    path = tmp_path / "oversized.chemvas"
    path.write_bytes(b" " * 65)
    with pytest.raises(ValueError, match="64-byte limit"):
        read_exact_document(path, max_bytes=64)
    monkeypatch.setattr(svg_roundtrip, "_MAX_SVG_FILE_BYTES", 64)
    svg = tmp_path / "oversized.svg"
    svg.write_bytes(b" " * 65)
    with pytest.raises(ValueError, match="Invalid editable Chemvas metadata"):
        svg_roundtrip.extract_chemvas_document_from_svg(svg)


def test_editable_svg_writer_rejects_unreadable_metadata_without_overwrite(
    tmp_path, monkeypatch
):
    path = tmp_path / "figure.svg"
    original = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
    path.write_bytes(original)
    payload = svg_roundtrip.create_editable_svg_payload(
        _state(_source_bytes()), document_version=CANVAS_FILE_VERSION, scope="sheet"
    )
    monkeypatch.setattr(svg_roundtrip, "_MAX_SVG_PAYLOAD_BYTES", 64)
    with pytest.raises(ValueError, match="metadata exceeds"):
        svg_roundtrip.embed_chemvas_document_in_svg(path, payload)
    assert path.read_bytes() == original


def test_native_writer_rejects_unreadable_document_without_overwrite(
    tmp_path, monkeypatch
):
    path = tmp_path / "existing.chemvas"
    original = b"existing document"
    path.write_bytes(original)
    monkeypatch.setattr(document_io, "MAX_DOCUMENT_BYTES", 64)
    with pytest.raises(ValueError, match="output document exceeds"):
        write_document(path, _state(_source_bytes()), CANVAS_FILE_VERSION)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
