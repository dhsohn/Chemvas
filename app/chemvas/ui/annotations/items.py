"""Shared annotation items owned by the Qt rendering boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast, override

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

from chemvas.domain.document import (
    AnnotationCollection,
    image_bytes_from_state,
)
from chemvas.domain.document.images import Image, image_from_state, image_to_state
from chemvas.domain.document.notes import Note, note_to_state
from chemvas.domain.document.orbitals import orbital_from_state, orbital_to_state
from chemvas.domain.document.ring_fills import RingFill, ring_fill_to_state
from chemvas.features.annotations import sanitize_note_html
from chemvas.ui.graphics_items import (
    RING_FILL_Z_VALUE,
    ExportTextItem,
    NoSelectPolygonItem,
)
from chemvas.ui.scene_record_ids import (
    bind_scene_record,
    new_scene_record_id,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from chemvas.domain.document import MoleculeModel
    from chemvas.domain.document.orbitals import Orbital


class RingFillItem(NoSelectPolygonItem):
    def __init__(
        self,
        document: AnnotationCollection[RingFill],
        model_provider: Callable[[], MoleculeModel],
        record_id: int,
    ) -> None:
        super().__init__()
        self.document = document
        self.model_provider = model_provider
        self.record_id = record_id
        bind_scene_record(self, document, record_id)
        self.setData(0, "ring")
        self.setData(3, record_id)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(RING_FILL_Z_VALUE)
        self.render_geometry()
        self._render_fill()

    @override
    def data(self, key: int) -> Any:
        # Selection's topology role is a projection of the record, never a
        # second mutable list stored in QVariant data.
        if key == 2:
            return list(self.document.records[self.record_id].atom_ids)
        return super().data(key)

    def ring_state(self) -> dict[str, object]:
        return ring_fill_to_state(
            self.document.records[self.record_id], self.model_provider().atoms
        )

    def apply_ring_state(self, state: Mapping[str, object]) -> None:
        current = self.document.records[self.record_id]
        color = state.get("color", current.color)
        alpha = state.get("alpha", current.alpha)
        self.document.records[self.record_id] = RingFill(
            current.atom_ids,
            QColor(str(color)).name() if color else None,
            float(cast("float", alpha)) if color else 0.0,
        )
        self.render_geometry()
        self._render_fill()

    def set_fill(self, fill: QColor) -> None:
        self.apply_ring_state({"color": fill.name(), "alpha": fill.alphaF()})

    def render_geometry(self) -> None:
        points = self.ring_state()["points"]
        self.setPolygon(QPolygonF([QPointF(*point) for point in cast("list", points)]))

    def _render_fill(self) -> None:
        record = self.document.records[self.record_id]
        if record.color is None:
            self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        else:
            color = QColor(record.color)
            color.setAlphaF(record.alpha)
            self.setBrush(QBrush(color))


class NoteItem(ExportTextItem):
    """Native editor projecting a document record.

    Text input, including Qt's native Undo, publishes its resulting value to the
    record. Reading or saving the document never interrogates this editor.
    """

    def __init__(
        self,
        notes: AnnotationCollection[Note],
        on_focus_out: Callable[[NoteItem], None] | None = None,
    ) -> None:
        super().__init__()
        self.notes = notes
        self.record_id = new_scene_record_id()
        notes.records[self.record_id] = Note()
        bind_scene_record(self, notes, self.record_id)
        self.setData(0, "note")
        self.setData(3, self.record_id)
        self._on_focus_out = on_focus_out
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self._last_text = ""
        self._last_html = ""
        self._fitting_text_width = False
        document = self.document()
        assert document is not None
        document.contentsChanged.connect(self._text_changed)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.publish_text()

    def note_state(self) -> dict[str, object]:
        return note_to_state(self.notes.records[self.record_id])

    def publish_text(self) -> None:
        # Document reset can dispose an editor after its record has gone.
        current = self.notes.records.get(self.record_id)
        if current is not None:
            updated = replace(
                current,
                text=self.toPlainText(),
                html=sanitize_note_html(self.toHtml()) or "",
            )
            if updated != current:
                self.notes.records[self.record_id] = updated

    def _text_changed(self) -> None:
        self._fit_text_width()
        self.publish_text()

    @override
    def setHtml(self, html: str | None) -> None:
        super().setHtml(html)
        # Rollback deliberately blocks QTextDocument signals. Explicit text
        # replacement still has to restore the document record in that case.
        self.publish_text()

    @override
    def setPlainText(self, text: str | None) -> None:
        super().setPlainText(text)
        self.publish_text()

    @override
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        current = self.notes.records.get(self.record_id)
        if current is not None:
            if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
                if (current.x, current.y) != (value.x(), value.y()):
                    self.notes.records[self.record_id] = replace(
                        current, x=value.x(), y=value.y()
                    )
            elif change == QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged:
                if current.rotation != float(value):
                    self.notes.records[self.record_id] = replace(
                        current, rotation=float(value)
                    )
        return super().itemChange(change, value)

    def _fit_text_width(self) -> None:
        """Give paragraphs the longest natural line's width, without wrapping."""
        if self._fitting_text_width:
            return
        self._fitting_text_width = True
        try:
            self.setTextWidth(-1)
            document = self.document()
            if document is not None:
                self.setTextWidth(document.idealWidth())
        finally:
            self._fitting_text_width = False

    @override
    def sceneEvent(self, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
            and event.modifiers() == Qt.KeyboardModifier.ShiftModifier
            and self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
        ):
            # Backtab has no note-editing command. Do not let Qt move focus
            # into the window's toolbar/status-bar tab chain instead.
            event.accept()
            return True
        return super().sceneEvent(event)

    @override
    def keyPressEvent(self, event) -> None:
        cursor = self.textCursor()
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            and self.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
            and not cursor.hasSelection()
            and not cursor.block().text()
            and cursor.currentList() is None
        ):
            # Qt resets a formatted empty block on Return. Notes deliberately
            # apply line spacing, so preserve it and insert the requested block.
            cursor.insertBlock(cursor.blockFormat(), cursor.charFormat())
            self.setTextCursor(cursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def committed_text(self) -> str:
        return self._last_text

    def set_committed_text(self, text: str) -> None:
        self._last_text = str(text)

    def committed_html(self) -> str:
        return self._last_html

    def set_committed_html(self, html: str) -> None:
        self._last_html = str(html)

    @override
    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if event.reason() == Qt.FocusReason.PopupFocusReason:
            # A font/menu popup temporarily borrows focus from the editor.
            # Keep its cursor and native text Undo until a real editor exit.
            return
        if self._on_focus_out is not None:
            self._on_focus_out(self)


_SOURCE_KEYS = ("mime_type", "data_base64", "pixel_width", "pixel_height")


class ImageItem(QGraphicsRectItem):
    """Retain encoded original bytes; painting always includes the whole raster.

    The inherited rect, position, opacity and data roles are captured by the
    existing exact transaction savepoint. The decoded pixels never mutate.
    """

    def __init__(
        self, state: Mapping[str, object], document: AnnotationCollection[Image]
    ) -> None:
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
        self.document = document
        self.record_id = new_scene_record_id()
        document.records[self.record_id] = image_from_state(state)
        bind_scene_record(self, document, self.record_id)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setData(0, "image")
        self.setData(3, self.record_id)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        # image_bytes_from_state already validated this exact constructor input.
        self._render_geometry()

    def image(self) -> QImage:
        return QImage(self._image)

    def export_scene_bounding_rect(self) -> QRectF:
        if self.effectiveOpacity() <= 0.0:
            return QRectF()
        return self.sceneBoundingRect()

    def image_state(self) -> dict[str, object]:
        return image_to_state(self.document.records[self.record_id])

    def apply_image_state(self, state: Mapping[str, object]) -> None:
        # The constructor authenticated these immutable bytes. Validate all
        # fields again, but do not decode the same raster on every pointer frame.
        record = image_from_state(state)
        source = self.image_state()
        if any(state[key] != source[key] for key in _SOURCE_KEYS):
            raise ValueError(
                "An image source cannot be replaced; insert a new image instead."
            )
        self.document.records[self.record_id] = record
        self._render_geometry()

    def _render_geometry(self) -> None:
        record = self.document.records[self.record_id]
        self.setRect(0.0, 0.0, record.width, record.height)
        self.setPos(record.x, record.y)
        self.setOpacity(record.opacity)
        self.setZValue(record.z)

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


class OrbitalItem(QGraphicsItemGroup):
    def __init__(
        self,
        state: Mapping[str, object],
        document: AnnotationCollection[Orbital],
        lobes: list[QGraphicsItem],
        base_handle_dist: float,
    ) -> None:
        super().__init__()
        for lobe in lobes:
            self.addToGroup(lobe)
        record = orbital_from_state(state)
        self.document = document
        self.record_id = new_scene_record_id()
        document.records[self.record_id] = record
        bind_scene_record(self, document, self.record_id)
        self.setData(0, "orbital")
        self.setData(3, self.record_id)
        self.base_handle_dist = base_handle_dist
        self._lobe_center = QPointF(*record.center)
        self._render_geometry()

    def orbital_state(self) -> dict[str, object]:
        return orbital_to_state(self.document.records[self.record_id])

    def apply_orbital_state(self, state: Mapping[str, object]) -> None:
        record = orbital_from_state({**self.orbital_state(), **state})
        if record.kind != self.document.records[self.record_id].kind:
            raise ValueError("An orbital kind cannot be replaced in place.")
        self.document.records[self.record_id] = record
        self._render_geometry()

    def _render_geometry(self) -> None:
        record = self.document.records[self.record_id]
        center = QPointF(*record.center)
        self.setPos(center - self._lobe_center)
        self.setTransformOriginPoint(self._lobe_center)
        self.setScale(record.scale)
        self.setRotation(record.rotation)
        # Handle drawing uses the same rendered center and scale metric.
        self.setData(1, {"center": center, "base_handle_dist": self.base_handle_dist})
        self.setData(2, {"kind": record.kind})


__all__ = ["ImageItem", "NoteItem", "OrbitalItem", "RingFillItem"]
