from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QBuffer, QIODevice, QMimeData
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
)

from chemvas.domain.document import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    image_state_from_bytes,
    validate_image_collection_budget,
    validate_image_state,
)
from chemvas.domain.document.images import image_to_state, inserted_image_box
from chemvas.ui.annotations.projections import resolve_projection
from chemvas.ui.canvas.canvas_document_state import document_item_lists_for
from chemvas.ui.canvas.canvas_scene_items_state import require_scene_record_id
from chemvas.ui.canvas.sheet_setup_access import sheet_rect_for
from chemvas.ui.history.history_commands import (
    AddSceneItemsCommand,
    UpdateSceneItemCommand,
)
from chemvas.ui.transactions.document import document_transaction
from chemvas.ui.window.main_window_config import IMAGE_PROPERTIES_SPEC
from chemvas.ui.window.main_window_ports import active_canvas_for_window

if TYPE_CHECKING:
    from chemvas.ui.annotations.items import ImageItem
    from chemvas.ui.window.main_window_like import MainWindowLike


def image_bytes_from_mime(mime: QMimeData) -> bytes | None:
    """Prefer encoded originals; native bitmap clipboards are embedded as PNG."""
    for mime_type in ("image/png", "image/jpeg"):
        if mime.hasFormat(mime_type):
            data = mime.data(mime_type)
            if data.size() > MAX_IMAGE_BYTES:
                raise ValueError("The clipboard image exceeds the 16 MiB limit.")
            return data.data()
    if not mime.hasImage():
        return None
    image = mime.imageData()
    if isinstance(image, QPixmap):
        if image.width() * image.height() > MAX_IMAGE_PIXELS:
            raise ValueError("The clipboard image exceeds the 25 million pixel limit.")
        image = image.toImage()
    if not isinstance(image, QImage) or image.isNull():
        raise ValueError("The clipboard does not contain a readable image.")
    if image.width() * image.height() > MAX_IMAGE_PIXELS:
        raise ValueError("The clipboard image exceeds the 25 million pixel limit.")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ValueError("Could not read the clipboard image.")
    try:
        if not image.save(buffer, "PNG"):
            raise ValueError("Could not encode the clipboard image as PNG.")
        if buffer.size() > MAX_IMAGE_BYTES:
            raise ValueError("The clipboard image exceeds the 16 MiB limit.")
        return buffer.data().data()
    finally:
        buffer.close()


def insert_image_bytes(canvas, data: bytes) -> ImageItem:
    state = image_state_from_bytes(data)
    viewport = canvas.viewport()
    visible = canvas.mapToScene(viewport.rect()).boundingRect()
    x, y, width, height = inserted_image_box(
        float(cast("float", state["width"])),
        float(cast("float", state["height"])),
        visible.getRect(),
        sheet_rect_for(canvas).getRect(),
    )
    state.update(width=width, height=height, x=x, y=y)
    existing = canvas.runtime_state.image_state.snapshot(image_to_state)
    # Incoming bytes were validated above; existing live sources were validated
    # when their ImageItems were constructed and cannot be replaced in-place.
    validate_image_collection_budget([*existing, state])
    history = canvas.services.history_service
    with document_transaction(canvas, history_service=history):
        command = AddSceneItemsCommand([state])
        command.redo(history.operations)
        item = resolve_projection(canvas, command.item_ids[0])
        canvas.services.selection.clear_note_selection()
        canvas.services.selection.clear_scene_selection()
        canvas.services.selection.set_items_selected([item], True, block_signals=False)
        canvas.services.selection.update_selection_outline()
        history.push(command)
    canvas.services.tool_mode_controller.set_tool("select")
    canvas.ensureVisible(item)
    return item


def insert_image_for_window(window: MainWindowLike) -> None:
    path, _filter = QFileDialog.getOpenFileName(
        window, "Insert Image", "", "PNG or JPEG images (*.png *.jpg *.jpeg)"
    )
    if not path:
        return
    try:
        with Path(path).open("rb") as source:
            data = source.read(MAX_IMAGE_BYTES + 1)
        insert_image_bytes(active_canvas_for_window(window), data)
    except (OSError, ValueError) as error:
        QMessageBox.warning(window, "Insert Image", str(error))


def update_image_properties(canvas, item: ImageItem, state: dict) -> bool:
    validate_image_state(state)
    before = item.image_state()
    if before == state:
        return False
    history = canvas.services.history_service
    with document_transaction(canvas, history_service=history):
        command = UpdateSceneItemCommand(require_scene_record_id(item), before, state)
        command.redo(history.operations)
        history.push(command)
    return True


class ImagePropertiesDialog(QDialog):
    def __init__(self, state: dict, parent=None) -> None:
        super().__init__(parent)
        spec = IMAGE_PROPERTIES_SPEC
        self.setWindowTitle(spec["title"])
        self._state = dict(state)
        self._ratio = state["pixel_width"] / state["pixel_height"]
        layout = QFormLayout(self)
        layout.addRow(
            QLabel(
                spec["original"].format(
                    width=state["pixel_width"], height=state["pixel_height"]
                )
            )
        )
        self.fields: dict[str, QDoubleSpinBox] = {}
        self._initial_values: dict[str, float] = {}
        for key, label in spec["fields"]:
            spin = QDoubleSpinBox(self)
            spin.setDecimals(spec["decimals"])
            spin.setRange(
                spec["size_minimum"]
                if key in {"width", "height"}
                else spec["coordinate_minimum"],
                spec["maximum"],
            )
            spin.setValue(state[key])
            self.fields[key] = spin
            self._initial_values[key] = spin.value()
            layout.addRow(spec["field_label"].format(label=label), spin)
        self.lock_aspect = QCheckBox(spec["lock_aspect"], self)
        self.lock_aspect.setChecked(state["lock_aspect"])
        layout.addRow(self.lock_aspect)
        self.fields["width"].valueChanged.connect(
            lambda _value: self._sync_size("width")
        )
        self.fields["height"].valueChanged.connect(
            lambda _value: self._sync_size("height")
        )
        self.lock_aspect.toggled.connect(
            lambda checked: self._sync_size("width") if checked else None
        )
        self.opacity = QDoubleSpinBox(self)
        self.opacity.setRange(0, 100)
        self.opacity.setDecimals(spec["opacity_decimals"])
        self.opacity.setSuffix(spec["opacity_suffix"])
        self.opacity.setValue(state["opacity"] * 100)
        layout.addRow(spec["opacity"], self.opacity)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _sync_size(self, changed: str) -> None:
        if not self.lock_aspect.isChecked():
            return
        other = "height" if changed == "width" else "width"
        value = self.fields[changed].value()
        value = value / self._ratio if changed == "width" else value * self._ratio
        blocked = self.fields[other].blockSignals(True)
        self.fields[other].setValue(value)
        self.fields[other].blockSignals(blocked)

    def image_state(self) -> dict:
        state = dict(self._state)
        for key, spin in self.fields.items():
            # Opening and accepting the dialog is an exact no-op despite display rounding.
            if spin.value() != self._initial_values[key]:
                state[key] = spin.value()
        state["lock_aspect"] = self.lock_aspect.isChecked()
        if self.opacity.value() != round(
            self._state["opacity"] * 100, IMAGE_PROPERTIES_SPEC["opacity_decimals"]
        ):
            state["opacity"] = self.opacity.value() / 100
        return state


def image_properties_for_window(window: MainWindowLike) -> None:
    canvas = active_canvas_for_window(window)
    items = [
        item
        for item in document_item_lists_for(canvas)["images"]
        if item is not None and item.isSelected()
    ]
    if not items:
        QMessageBox.information(
            window,
            IMAGE_PROPERTIES_SPEC["title"],
            IMAGE_PROPERTIES_SPEC["none_selected"],
        )
        return
    item = items[0]
    if len(items) > 1:
        choices = []
        for index, candidate in enumerate(items, start=1):
            state = candidate.image_state()
            choices.append(
                IMAGE_PROPERTIES_SPEC["choice"].format(
                    index=index,
                    width=state["pixel_width"],
                    height=state["pixel_height"],
                    x=state["x"],
                    y=state["y"],
                )
            )
        choice, accepted = QInputDialog.getItem(
            window,
            IMAGE_PROPERTIES_SPEC["title"],
            IMAGE_PROPERTIES_SPEC["choose"],
            choices,
            0,
            False,
        )
        if not accepted:
            return
        item = items[choices.index(choice)]
    dialog = ImagePropertiesDialog(item.image_state(), window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    try:
        update_image_properties(canvas, item, dialog.image_state())
    except ValueError as error:
        QMessageBox.warning(window, IMAGE_PROPERTIES_SPEC["title"], str(error))
