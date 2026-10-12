"""Experimental, explicitly bound consumer measurements for caption placement."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import xml.etree.ElementTree as ET

from .cdxml_consumer_validation import parse_consumer_xml, validate_consumer_objects

MAX_CDXML_CONSUMER_BYTES = 64 * 1024 * 1024
MIN_CDXML_TEXT_MARGIN_PT = 72.0 / 25.4
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ROUNDING = 0.02
_PLACEMENT_MARGIN = MIN_CDXML_TEXT_MARGIN_PT + _ROUNDING
Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class CdxmlTextLayoutReference:
    consumer_xml: bytes
    note_indices: tuple[int, ...]
    source_sha256: str
    consumer_sha256: str
    reference_sha256: str
    producer_sha256: str
    export_options: dict[str, Any]
    label_bindings_sha256: str | None
    producer_frame: Rect
    consumer_frame: Rect
    font_mapping: dict[str, str]
    consumer_environment: dict[str, str]

    def report(self) -> dict[str, object]:
        return {
            "experimental": True,
            "note_indices": list(self.note_indices),
            "source_sha256": self.source_sha256,
            "consumer_sha256": self.consumer_sha256,
            "reference_sha256": self.reference_sha256,
            "producer_sha256": self.producer_sha256,
            "export_options": self.export_options,
            "label_bindings_sha256": self.label_bindings_sha256,
            "producer_frame": list(self.producer_frame),
            "consumer_frame": list(self.consumer_frame),
            "expected_font_mapping": self.font_mapping,
            "font_substitution_declared": any(
                a != b for a, b in self.font_mapping.items()
            ),
            "consumer_environment_declaration": self.consumer_environment,
            "environment_runtime_verified": False,
            "minimum_text_margin_pt": MIN_CDXML_TEXT_MARGIN_PT,
            "font_size_quantization_tolerance_pt": 0.025,
        }


@dataclass(frozen=True)
class CaptionGeometry:
    note_index: int
    texts: tuple[ET.Element, ...]
    source_bounds: Rect


def _digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def _frame(value: Any) -> Rect:
    if (
        not isinstance(value, list)
        or len(value) != 4
        or any(
            type(n) not in (int, float, Decimal) or not math.isfinite(n) for n in value
        )
    ):
        raise ValueError(
            "CDXML layout reference frame must contain four finite numbers"
        )
    frame = tuple(float(n) for n in value)
    if frame[0] != 0 or frame[1] != 0 or frame[2] <= 0 or frame[3] <= 0:
        raise ValueError(
            "CDXML layout reference frame must start at zero with positive size"
        )
    return frame[0], frame[1], frame[2], frame[3]


def _same_options(actual: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return False
    for key, want in expected.items():
        got = actual[key]
        if type(want) in (int, float):
            if (
                type(got) not in (int, float, Decimal)
                or not math.isfinite(got)
                or float(got) != float(want)
            ):
                return False
        elif type(got) is not type(want) or got != want:
            return False
    return True


def parse_cdxml_text_layout_reference(
    payload: Any,
    *,
    consumer_xml: bytes,
    source_sha256: str,
    reference_sha256: str,
    export_options: dict[str, Any],
    label_bindings_sha256: str | None,
) -> CdxmlTextLayoutReference:
    keys = {
        "version",
        "source_sha256",
        "consumer_sha256",
        "consumer_file",
        "notes",
        "producer_sha256",
        "export_options",
        "label_bindings_sha256",
        "producer_frame",
        "consumer_frame",
        "font_mapping",
        "consumer_environment",
    }
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ValueError(
            "CDXML layout reference has invalid fields; version 2 is required"
        )
    if type(payload["version"]) is not int or payload["version"] != 2:
        raise ValueError("CDXML layout reference version must be 2")
    for key in ("source_sha256", "consumer_sha256", "producer_sha256"):
        if not _digest(payload[key]):
            raise ValueError(f"CDXML layout reference {key} is not a SHA-256 digest")
    if payload["source_sha256"] != source_sha256:
        raise ValueError("CDXML layout reference does not match the source document")
    if not isinstance(payload["consumer_file"], str) or not payload["consumer_file"]:
        raise ValueError("CDXML layout reference consumer_file must be a path")
    if not _same_options(payload["export_options"], export_options):
        raise ValueError("CDXML layout reference does not match export options")
    if payload["label_bindings_sha256"] != label_bindings_sha256:
        raise ValueError("CDXML layout reference does not match label bindings")
    notes = payload["notes"]
    if (
        not isinstance(notes, list)
        or not notes
        or any(type(n) is not int or n < 0 for n in notes)
        or len(set(notes)) != len(notes)
    ):
        raise ValueError("CDXML layout reference notes must be distinct note indices")
    if len(consumer_xml) > MAX_CDXML_CONSUMER_BYTES:
        raise ValueError("CDXML consumer reference exceeds the byte limit")
    if hashlib.sha256(consumer_xml).hexdigest() != payload["consumer_sha256"]:
        raise ValueError("CDXML layout reference does not match the consumer file")
    fonts = payload["font_mapping"]
    if (
        not isinstance(fonts, dict)
        or not fonts
        or any(
            not isinstance(k, str) or not k or not isinstance(v, str) or not v
            for k, v in fonts.items()
        )
    ):
        raise ValueError("CDXML layout reference requires an explicit font mapping")
    environment = payload["consumer_environment"]
    if (
        not isinstance(environment, dict)
        or set(environment) != {"creation_program", "platform", "executable_sha256"}
        or any(not isinstance(v, str) or not v for v in environment.values())
        or not _digest(environment["executable_sha256"])
    ):
        raise ValueError("CDXML layout reference consumer environment is invalid")
    return CdxmlTextLayoutReference(
        consumer_xml,
        tuple(notes),
        source_sha256,
        payload["consumer_sha256"],
        reference_sha256,
        payload["producer_sha256"],
        dict(export_options),
        label_bindings_sha256,
        _frame(payload["producer_frame"]),
        _frame(payload["consumer_frame"]),
        dict(fonts),
        dict(environment),
    )


def _numbers(value: str, count: int) -> tuple[float, ...]:
    try:
        values = tuple(map(float, value.split()))
    except ValueError as exc:
        raise ValueError("CDXML consumer geometry must be numeric") from exc
    if len(values) != count or not all(math.isfinite(v) for v in values):
        raise ValueError("CDXML consumer geometry must be finite")
    return values


def _rect(value: str) -> Rect:
    left, top, right, bottom = _numbers(value, 4)
    if right <= left or bottom <= top:
        raise ValueError("CDXML consumer text has an empty bounding box")
    return left, top, right, bottom


def _union(rects: list[Rect]) -> Rect:
    return (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )


def _translated(rect: Rect, dx: float, dy: float) -> Rect:
    return rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy


def _overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _styles(text: ET.Element) -> list[tuple[float, str]]:
    styles: list[tuple[float, str]] = []
    for run in text.findall("s"):
        size = _numbers(run.get("size", ""), 1)[0]
        if size <= 0:
            raise ValueError("CDXML consumer font size must be positive")
        styles.extend([(size, run.get("face", "0"))] * len(run.text or ""))
    return styles


def _validate_text(source: ET.Element, measured: ET.Element) -> Rect:
    def shown(t: ET.Element) -> str:
        return "".join(s.text or "" for s in t.findall("s"))

    if shown(source) != shown(measured):
        raise ValueError("CDXML consumer reference changed caption text")
    if "LineStarts" in measured.attrib:
        raise ValueError("CDXML consumer reference rewrapped a caption line")
    a, b = _styles(source), _styles(measured)
    if len(a) != len(b) or any(
        abs(sa - sb) > 0.051 or fa != fb
        for (sa, fa), (sb, fb) in zip(a, b, strict=True)
    ):
        raise ValueError("CDXML consumer reference changed caption size or face")
    original = _numbers(source.get("p", ""), 2)
    baseline = _numbers(measured.get("p", ""), 2)
    if any(abs(a - b) > _ROUNDING for a, b in zip(original, baseline, strict=True)):
        raise ValueError("CDXML consumer reference changed caption position")
    rotation = 360 * 65536
    try:
        a_angle = int(source.get("RotationAngle", "0")) % rotation
        b_angle = int(measured.get("RotationAngle", "0")) % rotation
    except ValueError as exc:
        raise ValueError("CDXML consumer caption rotation is invalid") from exc
    if a_angle != b_angle:
        raise ValueError("CDXML consumer reference changed caption rotation")
    # Relate the measured box to the unrounded producer baseline.
    return _translated(
        _rect(measured.get("BoundingBox", "")),
        original[0] - baseline[0],
        original[1] - baseline[1],
    )


def reflow_cdxml_captions(
    captions: list[CaptionGeometry],
    reference: CdxmlTextLayoutReference,
    *,
    page_width: float,
    page_height: float,
    producer_xml: bytes,
) -> None:
    """Translate chosen note groups; retain page, molecular and font geometry.

    The caller supplies the source glyph bounds and the exact emitted text IDs.
    Validate measurements against producer objects before changing captions.
    """
    if hashlib.sha256(producer_xml).hexdigest() != reference.producer_sha256:
        raise ValueError(
            "CDXML layout reference does not match uncorrected producer output"
        )
    native = parse_consumer_xml(reference.consumer_xml)
    producer = parse_consumer_xml(producer_xml)
    frame = (0.0, 0.0, page_width, page_height)
    if any(
        abs(a - b) > 1e-8 for a, b in zip(frame, reference.producer_frame, strict=True)
    ):
        raise ValueError("CDXML layout reference changed producer frame")
    native_page = native.find("page")
    assert native_page is not None
    actual_frame = _numbers(native_page.get("BoundingBox", ""), 4)
    if any(
        abs(a - b) > 1e-8
        for a, b in zip(actual_frame, reference.consumer_frame, strict=True)
    ):
        raise ValueError("CDXML layout reference changed consumer frame")
    if (
        native.get("CreationProgram", "")
        != reference.consumer_environment["creation_program"]
    ):
        raise ValueError("CDXML layout reference changed consumer environment")
    validate_consumer_objects(producer, native, reference.font_mapping)
    by_id: dict[str, ET.Element] = {}
    for element in native.iter("t"):
        identity = element.get("id")
        if identity is not None:
            if identity in by_id:
                raise ValueError("CDXML consumer reference has duplicate IDs")
            by_id[identity] = element
    selected = set(reference.note_indices)
    if not selected <= {c.note_index for c in captions}:
        raise ValueError("CDXML layout reference selects a missing or hidden note")
    bounds: dict[int, Rect] = {}
    offsets = {c.note_index: [0.0, 0.0] for c in captions}
    for caption in captions:
        rects = []
        for source in caption.texts:
            measured = by_id.get(source.get("id", ""))
            if measured is None or measured.tag != "t":
                raise ValueError("CDXML consumer reference is missing a caption")
            rects.append(_validate_text(source, measured))
        bounds[caption.note_index] = _union(rects)
    layout_width = min(page_width, actual_frame[2])
    layout_height = min(page_height, actual_frame[3])
    # Only measured overflow consumes existing page margins. Never enlarge or
    # rescale the output, nor move the molecule to make room for a caption.
    for index in selected:
        box = bounds[index]
        if (
            box[2] - box[0] > layout_width - 2 * _PLACEMENT_MARGIN
            or box[3] - box[1] > layout_height - 2 * _PLACEMENT_MARGIN
        ):
            raise ValueError("CDXML consumer caption cannot fit the fixed page")
        dx = max(
            _PLACEMENT_MARGIN - box[0],
            min(0.0, layout_width - _PLACEMENT_MARGIN - box[2]),
        )
        dy = max(
            _PLACEMENT_MARGIN - box[1],
            min(0.0, layout_height - _PLACEMENT_MARGIN - box[3]),
        )
        offsets[index] = [dx, dy]
        bounds[index] = _translated(box, dx, dy)
    ordered = sorted(captions, key=lambda c: (c.source_bounds[0], c.note_index))
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            a, b = left.note_index, right.note_index
            if not ({a, b} & selected) or not _overlap(bounds[a], bounds[b]):
                continue
            if _overlap(left.source_bounds, right.source_bounds):
                continue  # An existing source overlap is not a substitution defect.
            gap = right.source_bounds[0] - left.source_bounds[2]
            if gap < 0 or b not in selected:
                raise ValueError(
                    "CDXML caption collision needs a different note selection"
                )
            dx = bounds[a][2] + max(gap, _ROUNDING) - bounds[b][0]
            offsets[b][0] += dx
            bounds[b] = _translated(bounds[b], dx, 0)
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            if (
                {left.note_index, right.note_index} & selected
                and not _overlap(left.source_bounds, right.source_bounds)
                and _overlap(bounds[left.note_index], bounds[right.note_index])
            ):
                raise ValueError("CDXML caption reflow leaves a new collision")
    for index in selected:
        box = bounds[index]
        if (
            box[0] < _PLACEMENT_MARGIN - 1e-9
            or box[1] < _PLACEMENT_MARGIN - 1e-9
            or box[2] > layout_width - _PLACEMENT_MARGIN + 1e-9
            or box[3] > layout_height - _PLACEMENT_MARGIN + 1e-9
        ):
            raise ValueError("CDXML caption reflow cannot fit the fixed page")
    for caption in captions:
        index = caption.note_index
        if index not in selected:
            continue
        dx, dy = offsets[index]
        for element in caption.texts:
            x, y = _numbers(element.get("p", ""), 2)
            element.set("p", f"{x + dx:.12g} {y + dy:.12g}")
