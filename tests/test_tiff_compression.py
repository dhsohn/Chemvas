from __future__ import annotations

import io

import pytest
from PIL import Image
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication, QGraphicsScene

from chemvas.bootstrap.document_cli_shared import offscreen_canvas
from chemvas.features.document_composition import compose_document_state
from chemvas.features.export import export_scene
from chemvas.features.export.raster import save_tiff_with_pillow


@pytest.fixture(scope="module", autouse=True)
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.mark.parametrize("dpi", [300, 600, 1200])
@pytest.mark.parametrize("alpha", [0, 127, 255])
def test_tiff_is_lossless_lzw_with_unchanged_rgba_and_resolution(tmp_path, dpi, alpha):
    image = QImage(256, 192, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(255, 255, 255, alpha))
    for x in range(32):
        image.setPixelColor(x, 20, QColor(17 + x, 83, 219, 128))
    output = tmp_path / "figure.tiff"
    save_tiff_with_pillow(image, str(output), dpi)
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    with Image.open(output) as actual:
        assert actual.tag_v2[259] == 5  # TIFF's lossless LZW compression code.
        assert actual.mode == "RGBA"
        assert actual.size == (256, 192)
        assert actual.info["dpi"] == (dpi, dpi)
        assert actual.tag_v2[296] == 2  # Resolution is in inches.
        assert actual.tag_v2[338] == (2,)  # Unassociated alpha, as before.
        assert actual.tobytes() == rgba.constBits().asstring(rgba.sizeInBytes())
        uncompressed = io.BytesIO()
        actual.save(uncompressed, format="TIFF", dpi=(dpi, dpi), compression="raw")
    assert output.stat().st_size < len(uncompressed.getvalue()) / 10


@pytest.mark.parametrize("background", ["white", "transparent"])
def test_export_tiff_and_png_reopen_with_identical_pixels(tmp_path, background):
    scene = QGraphicsScene()
    rectangle = scene.addRect(QRectF(0, 0, 40, 20))
    rectangle.setData(0, "shape")
    plans = []
    for fmt in ("png", "tiff"):
        plans.append(
            export_scene(
                scene,
                str(tmp_path / f"figure.{fmt}"),
                fmt=fmt,
                margin=4,
                dpi=300,
                background=background,
            )
        )
    assert plans[0] == plans[1]
    with (
        Image.open(tmp_path / "figure.png") as png,
        Image.open(tmp_path / "figure.tiff") as tiff,
    ):
        assert tiff.size == png.size
        assert tiff.tobytes() == png.convert("RGBA").tobytes()
        assert tiff.tag_v2[259] == 5


@pytest.mark.parametrize("existing", [False, True])
def test_tiff_codec_failure_does_not_publish_partial_output(
    tmp_path, monkeypatch, existing
):
    state = compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [{"id": 0, "element": "O", "x": 0, "y": 0}],
            "bonds": [],
        }
    )
    output = tmp_path / "figure.tiff"
    if existing:
        output.write_bytes(b"previous figure")

    def fail_save(self, path, **kwargs):
        assert kwargs["compression"] == "tiff_lzw"
        with open(path, "wb") as partial:
            partial.write(b"incomplete TIFF")
        raise OSError("synthetic codec failure")

    monkeypatch.setattr(Image.Image, "save", fail_save)
    with offscreen_canvas(state, command="tiff-failure-test") as (canvas, service):
        before = service.snapshot_state()
        visible = [(item, item.isVisible()) for item in canvas.scene().items()]
        with pytest.raises(OSError, match="synthetic codec failure"):
            service.export_figure(str(output), fmt="tiff")
        assert service.snapshot_state() == before
        assert all(item.isVisible() == was_visible for item, was_visible in visible)
    assert (
        output.read_bytes() == b"previous figure" if existing else not output.exists()
    )
    assert list(tmp_path.iterdir()) == ([output] if existing else [])
