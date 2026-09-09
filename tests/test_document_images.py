from __future__ import annotations

import base64
import copy
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image

from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    CLIPBOARD_SELECTION_VERSION,
    build_document_payload,
    extract_document_state,
    image_bytes_from_state,
    image_state_from_bytes,
    selection_payload_to_canvas_state,
    validate_clipboard_selection_payload,
    validate_image_state,
    validate_image_states,
)
from chemvas.domain.document import images as image_policy
from chemvas.features.document_composition import compose_document_state


def _raster(format_name: str = "PNG") -> bytes:
    raster = Image.new("RGBA", (8, 4), (240, 250, 230, 255))
    raster.putpixel((0, 0), (220, 20, 20, 0))
    raster.putpixel((7, 3), (10, 20, 230, 255))
    if format_name != "PNG":
        raster = raster.convert("RGB")
    stream = BytesIO()
    raster.save(stream, format=format_name)
    return stream.getvalue()


def _canvas() -> dict:
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [],
            "bonds": [],
        }
    )


@pytest.mark.parametrize("removed", [1, 2, 3, 4])
def test_png_incomplete_end_chunk_is_rejected(removed):
    with pytest.raises(ValueError, match="Invalid or truncated"):
        image_state_from_bytes(_raster()[:-removed])


def _selection(image: dict[str, object]) -> dict[str, object]:
    return {
        "format": "chemvas-selection",
        "version": CLIPBOARD_SELECTION_VERSION,
        "atoms": [],
        "bonds": [],
        "rings": [],
        "marks": [],
        "scene_items": [image],
    }


@pytest.mark.parametrize("format_name", ["PNG", "JPEG"])
def test_image_bytes_and_full_pixel_dimensions_survive_document_roundtrip(
    format_name: str,
) -> None:
    data = _raster(format_name)
    image = image_state_from_bytes(data, x=15, y=-20, width=200, opacity=0.5)
    canvas = _canvas()
    canvas["images"] = [image]
    canvas["groups"] = [{"atoms": [], "items": [["images", 0]]}]

    restored = extract_document_state(
        build_document_payload(canvas, CANVAS_FILE_VERSION)
    )

    assert image_bytes_from_state(restored["images"][0]) == data
    assert (image["pixel_width"], image["pixel_height"]) == (8, 4)
    assert (image["width"], image["height"]) == (200, 100)
    assert image["mime_type"] == ("image/png" if format_name == "PNG" else "image/jpeg")
    assert restored["groups"] == [{"atoms": [], "items": [["images", 0]]}]


def test_image_selection_validates_and_converts_to_canvas_without_losing_bytes() -> (
    None
):
    data = _raster()
    selection = _selection(image_state_from_bytes(data, height=60))
    selection["groups"] = [{"atoms": [], "items": [["scene_items", 0]]}]

    assert validate_clipboard_selection_payload(selection)
    canvas = selection_payload_to_canvas_state(selection, _canvas()["settings"])

    assert image_bytes_from_state(canvas["images"][0]) == data
    assert canvas["images"][0]["width"] == 120
    assert canvas["images"][0]["height"] == 60


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "photo"},
        {"mime_type": "image/svg+xml"},
        {"mime_type": "image/jpeg"},
        {"pixel_width": 9},
        {"pixel_width": True},
        {"pixel_height": 0},
        {"pixel_height": 25_000_001},
        {"data_base64": ""},
        {"data_base64": "!!!!"},
        {"data_base64": "abcd="},
        {"data_base64": "é"},
        {"data_base64": "Zg=="},
        {"x": float("nan")},
        {"y": float("inf")},
        {"x": True},
        {"width": 0},
        {"height": -1},
        {"opacity": -0.1},
        {"opacity": 1.01},
        {"lock_aspect": 1},
        {"url": "https://example.test/image.png"},
        {"x": Decimal("0.12345678901234567890123456789")},
    ],
)
def test_malformed_image_rejected_by_document_and_clipboard(
    changes: dict[str, object],
) -> None:
    image = image_state_from_bytes(_raster()) | changes
    with pytest.raises(ValueError):
        validate_image_state(image)
    canvas = _canvas()
    canvas["images"] = [image]
    with pytest.raises(ValueError):
        build_document_payload(canvas, CANVAS_FILE_VERSION)
    assert not validate_clipboard_selection_payload(_selection(image))


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not an image",
        _raster("GIF"),
        _raster("BMP"),
        _raster()[:-20],
        _raster("JPEG")[:-30],
    ],
)
def test_unsupported_or_truncated_encoded_files_are_rejected(data: bytes) -> None:
    with pytest.raises(ValueError):
        image_state_from_bytes(data)


def test_animation_is_rejected_instead_of_silently_discarding_frames() -> None:
    stream = BytesIO()
    Image.new("RGB", (8, 4), "red").save(
        stream,
        format="PNG",
        save_all=True,
        append_images=[Image.new("RGB", (8, 4), "blue")],
        duration=100,
    )
    with pytest.raises(ValueError, match="multi-frame"):
        image_state_from_bytes(stream.getvalue())


def test_source_byte_and_pixel_limits_are_checked_before_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _raster()
    monkeypatch.setattr(image_policy, "MAX_IMAGE_BYTES", len(data) - 1)
    with pytest.raises(ValueError, match="byte limit"):
        image_state_from_bytes(data)
    monkeypatch.setattr(image_policy, "MAX_IMAGE_BYTES", len(data))
    monkeypatch.setattr(image_policy, "MAX_IMAGE_PIXELS", 31)
    with pytest.raises(ValueError, match="pixel limit"):
        image_state_from_bytes(data)


@pytest.mark.parametrize(
    "budget", ["MAX_DOCUMENT_IMAGE_BYTES", "MAX_DOCUMENT_IMAGE_PIXELS"]
)
def test_combined_budget_is_checked_before_decoding_any_image(
    monkeypatch: pytest.MonkeyPatch, budget: str
) -> None:
    image = image_state_from_bytes(_raster())
    monkeypatch.setattr(image_policy, budget, 1)

    def unexpected_decode(_data: bytes) -> None:
        pytest.fail("payload decoded before aggregate resource validation")

    monkeypatch.setattr(image_policy, "_inspect_image_bytes", unexpected_decode)
    with pytest.raises(ValueError, match="Combined"):
        validate_image_states([image])


def test_unknown_group_image_reference_is_rejected() -> None:
    canvas = _canvas()
    canvas["images"] = [image_state_from_bytes(_raster())]
    canvas["groups"] = [{"atoms": [], "items": [["images", 1]]}]
    with pytest.raises(ValueError):
        build_document_payload(canvas, CANVAS_FILE_VERSION)


def test_strict_base64_rejects_noncanonical_padding_bits() -> None:
    image = image_state_from_bytes(_raster())
    image["data_base64"] = "Zh=="  # decodes to the same byte as canonical Zg==
    with pytest.raises(ValueError, match="canonical base64"):
        image_bytes_from_state(image)


def test_explicit_stretch_and_alpha_do_not_change_embedded_pixels() -> None:
    data = _raster()
    image = image_state_from_bytes(
        data, width=50, height=90, lock_aspect=False, opacity=0.25
    )
    before = copy.deepcopy(image)
    validate_image_state(image)
    assert image == before
    assert image["width"] == 50 and image["height"] == 90
    assert base64.b64decode(image["data_base64"]) == data
