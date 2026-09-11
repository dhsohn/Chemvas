"""An embedded raster with immutable source pixels and editable scene geometry."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QWidget

from chemvas.domain.document import image_bytes_from_state, validate_image_state

if TYPE_CHECKING:
    from collections.abc import Mapping

_SOURCE_KEYS = ("mime_type", "data_base64", "pixel_width", "pixel_height")


class ImageItem(QGraphicsRectItem):
    """Retain encoded original bytes; painting always includes the whole raster.

    The inherited rect, position, opacity and data roles are captured by the
    existing exact transaction savepoint. The decoded pixels never mutate.
    """

    def __init__(self, state: Mapping[str, object]) -> None:
        super().__init__()
        data = image_bytes_from_state(state)
        image = QImage.fromData(
            data, "PNG" if state["mime_type"] == "image/png" else "JPEG"
        )
        if image.isNull() or (image.width(), image.height()) != (
            state["pixel_width"],
            state["pixel_height"],
        ):
            raise ValueError(
                "The embedded image could not be decoded at its original dimensions."
            )
        if image.textKeys():
            # The document keeps the encoded source, but a rendered figure must
            # not inherit its comments/authorship text through QSvgGenerator.
            # Construct from pixels: setText(key, "") retains the text keys.
            pixels = image.constBits()
            assert pixels is not None
            # SIP accepts a const pixel pointer; the stubs list only bytes.
            rendered = QImage(  # type: ignore[call-overload]
                pixels,
                image.width(),
                image.height(),
                image.bytesPerLine(),
                image.format(),
            ).copy()
            if rendered.isNull():
                raise ValueError(
                    "The embedded image pixels could not be copied for rendering."
                )
            if image.colorTable():
                rendered.setColorTable(image.colorTable())
            rendered.setColorSpace(image.colorSpace())
            image = rendered
        image.setDevicePixelRatio(1.0)
        self._image = image
        self.setPen(QPen(Qt.PenStyle.NoPen))
        # Keep annotation stacking independent of insertion/restore order:
        # shapes and ring fills are below images; native labels are above them.
        self.setZValue(-2.0)
        self.setData(0, "image")
        self.setData(1, {key: state[key] for key in _SOURCE_KEYS})
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.apply_image_state(state)

    def image(self) -> QImage:
        return QImage(self._image)

    def export_scene_bounding_rect(self) -> QRectF:
        if self.effectiveOpacity() <= 0.0:
            return QRectF()
        return self.sceneBoundingRect()

    def image_state(self) -> dict[str, object]:
        state = dict(self.data(1))
        state.update(
            kind="image",
            x=self.pos().x(),
            y=self.pos().y(),
            width=self.rect().width(),
            height=self.rect().height(),
            opacity=self.opacity(),
        )
        return state

    def apply_image_state(self, state: Mapping[str, object]) -> None:
        validate_image_state(state)
        source = self.data(1)
        if any(state[key] != source[key] for key in _SOURCE_KEYS):
            raise ValueError(
                "An image source cannot be replaced; insert a new image instead."
            )
        self.setRect(
            0.0,
            0.0,
            float(cast("float", state["width"])),
            float(cast("float", state["height"])),
        )
        self.setPos(float(cast("float", state["x"])), float(cast("float", state["y"])))
        self.setOpacity(float(cast("float", state["opacity"])))
        self.setData(1, {**source, "lock_aspect": state["lock_aspect"]})

    @override
    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        del option, widget
        if painter is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(self.rect(), self._image, QRectF(self._image.rect()))
        painter.restore()


__all__ = ["ImageItem"]
