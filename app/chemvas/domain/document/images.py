"""Bounded PNG/JPEG payloads; original encoded bytes are never rewritten.

Pillow validates in-memory bytes only. File access belongs to bootstrap or UI.
Pixel dimensions describe the stored raster without applying EXIF orientation.
"""

from __future__ import annotations

import base64
import binascii
import math
import warnings
from collections.abc import Mapping
from decimal import Decimal
from io import BytesIO
from typing import cast

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_DOCUMENT_IMAGE_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_IMAGE_PIXELS = 100_000_000
MAX_DOCUMENT_IMAGES = 256
# Base64 expansion of the image budget plus bounded document metadata.
MAX_DOCUMENT_BYTES = 96 * 1024 * 1024
MAX_IMAGE_BASE64_CHARS = 4 * ((MAX_IMAGE_BYTES + 2) // 3)
_IMAGE_KEYS = frozenset(
    (
        "kind",
        "mime_type",
        "data_base64",
        "pixel_width",
        "pixel_height",
        "x",
        "y",
        "width",
        "height",
        "opacity",
        "lock_aspect",
    )
)
_FORMAT_MIME = {"PNG": "image/png", "JPEG": "image/jpeg"}


def image_state_from_bytes(
    data: bytes,
    *,
    x: float = 0.0,
    y: float = 0.0,
    width: float | None = None,
    height: float | None = None,
    opacity: float = 1.0,
    lock_aspect: bool = True,
) -> dict[str, object]:
    """Embed a complete raster; omitted dimensions follow its native ratio.

    When both dimensions are explicit they are retained, including intentional
    stretching. ``lock_aspect`` controls subsequent interactive resizing.
    """
    mime_type, pixel_width, pixel_height = _inspect_image_bytes(data)
    if width is None and height is None:
        width, height = float(pixel_width), float(pixel_height)
    elif width is None:
        height = _number(height, "height", positive=True)
        width = height * pixel_width / pixel_height
    elif height is None:
        width = _number(width, "width", positive=True)
        height = width * pixel_height / pixel_width
    state: dict[str, object] = {
        "kind": "image",
        "mime_type": mime_type,
        "data_base64": base64.b64encode(data).decode("ascii"),
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "opacity": opacity,
        "lock_aspect": lock_aspect,
    }
    _validate_fields(state)
    return state


def image_bytes_from_state(state: Mapping[str, object]) -> bytes:
    """Validate every field and decode the exact embedded source bytes."""
    _validate_fields(state)
    encoded = cast("str", state["data_base64"])
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Image data_base64 must be canonical base64.") from exc
    if base64.b64encode(data).decode("ascii") != encoded:
        raise ValueError("Image data_base64 must be canonical base64.")
    mime_type, pixel_width, pixel_height = _inspect_image_bytes(data)
    if (
        state["mime_type"] != mime_type
        or state["pixel_width"] != pixel_width
        or state["pixel_height"] != pixel_height
    ):
        raise ValueError("Image format or pixel dimensions do not match its bytes.")
    return data


def validate_image_state(state: Mapping[str, object]) -> None:
    image_bytes_from_state(state)


def validate_image_states(states: object) -> None:
    """Bound totals before allocating or decoding any complete raster."""
    if not isinstance(states, list) or len(states) > MAX_DOCUMENT_IMAGES:
        raise ValueError(
            f"Images must be an array of at most {MAX_DOCUMENT_IMAGES} items."
        )
    byte_count = 0
    pixel_count = 0
    for state in states:
        if not isinstance(state, Mapping):
            raise ValueError("An image must be an object.")
        _validate_fields(state)
        encoded = cast("str", state["data_base64"])
        byte_count += len(encoded) // 4 * 3 - (len(encoded) - len(encoded.rstrip("=")))
        pixel_count += cast("int", state["pixel_width"]) * cast(
            "int", state["pixel_height"]
        )
        if byte_count > MAX_DOCUMENT_IMAGE_BYTES:
            raise ValueError("Combined image bytes exceed the 64 MiB document limit.")
        if pixel_count > MAX_DOCUMENT_IMAGE_PIXELS:
            raise ValueError(
                "Combined image pixels exceed the 100 million document limit."
            )
    for state in states:
        validate_image_state(state)


def _validate_fields(state: Mapping[str, object]) -> None:
    if set(state) != _IMAGE_KEYS or state.get("kind") != "image":
        raise ValueError("Image state has missing or unknown fields.")
    mime_type = state.get("mime_type")
    if not isinstance(mime_type, str) or mime_type not in _FORMAT_MIME.values():
        raise ValueError("Only PNG and JPEG images are supported.")
    encoded = state.get("data_base64")
    if not isinstance(encoded, str) or not 0 < len(encoded) <= MAX_IMAGE_BASE64_CHARS:
        raise ValueError("Image data exceeds the 16 MiB byte limit or is empty.")
    if len(encoded) % 4 or len(encoded) - len(encoded.rstrip("=")) > 2:
        raise ValueError("Image data_base64 must be canonical base64.")
    _pixel_dimensions(state.get("pixel_width"), state.get("pixel_height"))
    for key in ("x", "y", "width", "height", "opacity"):
        value = _number(state.get(key), key, positive=key in {"width", "height"})
        if key == "opacity" and not 0.0 <= value <= 1.0:
            raise ValueError("Image opacity must be between 0 and 1.")
    if type(state.get("lock_aspect")) is not bool:
        raise ValueError("Image lock_aspect must be a boolean.")


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float, Decimal):
        raise ValueError(f"Image {name} must be a finite JSON-safe number.")
    try:
        number = float(cast("int | float | Decimal", value))
    except (ArithmeticError, ValueError) as exc:
        raise ValueError(f"Image {name} must be a finite JSON-safe number.") from exc
    if (
        not math.isfinite(number)
        or abs(number) > 2**53 - 1
        or (positive and number <= 0)
        or (type(value) is Decimal and Decimal(str(number)) != value)
    ):
        raise ValueError(
            f"Image {name} must be a finite JSON-safe {'positive ' if positive else ''}number."
        )
    return number


def _pixel_dimensions(width: object, height: object) -> tuple[int, int]:
    if type(width) is not int or type(height) is not int:
        raise ValueError("Image pixel dimensions must be positive integers.")
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Image exceeds the 25 million pixel limit or is empty.")
    return width, height


def _inspect_image_bytes(data: bytes) -> tuple[str, int, int]:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 16 MiB byte limit or is empty.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG", "JPEG")) as raster:
                mime_type = _FORMAT_MIME.get(raster.format or "")
                if mime_type is None:
                    raise ValueError("Only PNG and JPEG images are supported.")
                width, height = _pixel_dimensions(*raster.size)
                if mime_type == "image/png" and not data.endswith(
                    b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
                ):
                    # Pillow verify/load can accept a truncated IEND CRC because
                    # all pixel data precedes it. Require the complete end chunk.
                    raise ValueError("Invalid or truncated PNG/JPEG image.")
                if getattr(raster, "n_frames", 1) != 1:
                    raise ValueError(
                        "Animated or multi-frame images are not supported."
                    )
                raster.verify()
            # JPEG verify() does not read scan data; force a bounded full decode.
            with Image.open(BytesIO(data), formats=("PNG", "JPEG")) as raster:
                raster.load()
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Invalid or truncated PNG/JPEG image.") from exc
    return mime_type, width, height
