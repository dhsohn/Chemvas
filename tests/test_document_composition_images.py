from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from chemvas.bootstrap.document_composition import _read_image_source
from chemvas.core.document_io import read_document
from chemvas.features.document_composition import compose_document_state

if TYPE_CHECKING:
    from pathlib import Path


def _composition() -> dict[str, object]:
    return {
        "format": "chemvas-document-composition",
        "version": 1,
        "atoms": [],
        "bonds": [],
    }


def _image_bytes(format_name: str) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (24, 12), "navy").save(stream, format_name)
    return stream.getvalue()


def _run(request: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            "compose-document",
            str(request),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_composition_cli_embeds_relative_png_and_absolute_jpeg_exactly(
    tmp_path: Path,
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    png = assets / "nmr.png"
    jpeg = assets / "sem.jpg"
    png.write_bytes(_image_bytes("PNG"))
    jpeg.write_bytes(_image_bytes("JPEG"))
    composition = _composition()
    composition["images"] = [
        {"source": "assets/nmr.png", "x": 20, "y": 40, "width": 300},
        {
            "source": str(jpeg),
            "x": 20,
            "y": 210,
            "width": 200,
            "height": 110,
            "opacity": 0.75,
            "lock_aspect": False,
        },
    ]
    request = tmp_path / "figures.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    output = tmp_path / "figures.chemvas"
    before = {path: path.read_bytes() for path in (png, jpeg, request)}

    result = _run(request, output)

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["image_count"] == 2
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    state = read_document(output).state
    for index, source in enumerate((png, jpeg)):
        assert base64.b64decode(state["images"][index]["data_base64"]) == before[source]
    assert state["images"][0]["height"] == 150
    assert state["images"][1]["height"] == 110
    assert all(path.read_bytes() == data for path, data in before.items())
    output_before = output.read_bytes()
    repeat = _run(request, output)
    assert repeat.returncode == 2
    assert "already exists" in repeat.stderr
    assert output.read_bytes() == output_before


@pytest.mark.parametrize("source", ["missing.png", "invalid.png", "unsupported.gif"])
def test_bad_source_produces_clean_error_and_no_output(
    tmp_path: Path, source: str
) -> None:
    (tmp_path / "invalid.png").write_bytes(b"invalid image")
    (tmp_path / "unsupported.gif").write_bytes(_image_bytes("PNG"))
    composition = _composition()
    composition["images"] = [{"source": source, "x": 0, "y": 0}]
    request = tmp_path / "composition.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    output = tmp_path / "result.chemvas"
    result = _run(request, output)
    assert result.returncode == 2
    assert "chemvas: error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize(
    "bad_data,reason",
    [
        (_image_bytes("PNG")[:-5], "Invalid or truncated"),
        (_image_bytes("BMP"), "Only PNG and JPEG"),
        (b"not an image", "Only PNG and JPEG"),
    ],
    ids=["truncated-png", "unsupported-bmp", "unrecognized-data"],
)
def test_third_image_decode_error_keeps_index_and_leaves_sources_unchanged(
    tmp_path: Path, bad_data: bytes, reason: str
) -> None:
    sources = [tmp_path / f"image-{index}.png" for index in range(3)]
    for index, source in enumerate(sources):
        source.write_bytes(bad_data if index == 2 else _image_bytes("PNG"))
    composition = _composition()
    composition["images"] = [
        {"source": source.name, "x": index * 40, "y": 0}
        for index, source in enumerate(sources)
    ]
    request = tmp_path / "composition.json"
    request.write_text(json.dumps(composition), encoding="utf-8")
    before = {path: path.read_bytes() for path in [request, *sources]}
    output = tmp_path / "result.chemvas"

    result = _run(request, output)

    assert result.returncode == 2
    assert f"image 2: {reason}" in result.stderr
    assert "Traceback" not in result.stderr
    assert not result.stdout
    assert not output.exists()
    assert all(path.read_bytes() == original for path, original in before.items())


def test_empty_images_do_not_add_a_new_native_key() -> None:
    composition = _composition()
    composition["images"] = []
    assert "images" not in compose_document_state(composition)


def test_feature_image_reader_is_explicit_and_framework_free() -> None:
    composition = _composition()
    composition["images"] = [{"source": "relative.png", "x": 1, "y": 2, "height": 30}]
    with pytest.raises(ValueError, match="image_source_reader"):
        compose_document_state(composition)
    seen: list[str] = []

    def reader(path: str) -> bytes:
        seen.append(path)
        return _image_bytes("PNG")

    state = compose_document_state(composition, image_source_reader=reader)
    assert seen == ["relative.png"]
    assert state["images"][0]["width"] == 60


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "https://example.test/image.png"},
        {"source": ""},
        {"width": None},
        {"height": 0},
        {"lock_aspect": "yes"},
        {"opacity": 1.1},
    ],
)
def test_composition_image_shape_is_strict(changes: dict[str, object]) -> None:
    composition = _composition()
    composition["images"] = [{"source": "test.png", "x": 0, "y": 0} | changes]
    with pytest.raises(ValueError):
        compose_document_state(
            composition, image_source_reader=lambda _source: _image_bytes("PNG")
        )


def test_source_reader_rejects_a_directory_before_open(tmp_path: Path) -> None:
    directory = tmp_path / "directory.png"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        _read_image_source(tmp_path, "directory.png")
