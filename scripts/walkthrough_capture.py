"""Shared harness for the documentation walkthrough captures.

A walkthrough drives the real main window offscreen with synthetic pointer and
keyboard input, grabs the window after each step under a chapter caption, and
writes the frames as one GIF. ``capture_first_scheme.py`` and
``capture_walkthroughs.py`` build their scenes on top of this class.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QToolButton, QWidget

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)

if TYPE_CHECKING:
    from collections.abc import Callable

WIDTH, HEIGHT = 1120, 580
HEADER = 76
LEFT_BUTTON = Qt.MouseButton.LeftButton
NO_MODIFIER = Qt.KeyboardModifier.NoModifier


class Walkthrough:
    def __init__(
        self, app: QApplication, output: Path, *, zoom_percent: int = 270
    ) -> None:
        self.app = app
        self.output = output
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.window = build_main_window()
        self.window.resize(WIDTH, HEIGHT)
        self.window.show()
        self.canvas = active_canvas_for_window(self.window)
        self.app.processEvents()
        set_zoom_percent_for_window(self.window, zoom_percent)
        self.canvas.centerOn(0.0, 0.0)
        self.cursor: QPoint | None = None
        # Extra top-level windows (the Molecule Info window) drawn over the
        # main window at a fixed spot in every frame while they are visible.
        self.extra_windows: list[tuple[QWidget, QPoint]] = []
        QTest.qWait(150)

    # -- frames --------------------------------------------------------------

    def capture(self, title: str, detail: str, duration: int = 1600) -> None:
        self.app.processEvents()
        frame = QImage(WIDTH, HEIGHT + HEADER, QImage.Format.Format_RGB32)
        frame.fill(QColor("#f7faf9"))
        painter = QPainter(frame)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, 0, WIDTH, HEADER, QColor("#123e39"))
        font = QFont("DejaVu Sans")
        font.setPixelSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(26, 33, title)
        font.setPixelSize(14)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#c5e9df"))
        painter.drawText(26, 58, detail)
        painter.drawPixmap(0, HEADER, self.window.grab())
        for widget, corner in self.extra_windows:
            if widget.isVisible():
                painter.drawPixmap(corner + QPoint(0, HEADER), widget.grab())
        dialog = self.app.activeModalWidget()
        if dialog is not None:
            point = dialog.mapToGlobal(QPoint(0, 0))
            point = self.window.mapFromGlobal(point) + QPoint(0, HEADER)
            painter.drawPixmap(point, dialog.grab())
        elif self.cursor is not None:
            painter.setPen(QColor("#0d9488"))
            painter.setBrush(QColor(13, 148, 136, 45))
            painter.drawEllipse(self.cursor + QPoint(0, HEADER), 9, 9)
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not frame.save(buffer, "PNG"):
            raise RuntimeError("Could not encode a walkthrough frame")
        self.frames.append(Image.open(io.BytesIO(bytes(data))).convert("RGB"))
        self.durations.append(duration)

    def save_gif(self, name: str) -> Path:
        path = self.output / name
        self.frames[0].save(
            path,
            save_all=True,
            append_images=self.frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
        )
        print(f"{name}: {len(self.frames)} frames; {sum(self.durations) / 1000:g} s")
        return path

    # -- pointer and keyboard ------------------------------------------------

    def point(self, x: float, y: float) -> QPoint:
        return self.canvas.mapFromScene(QPointF(x, y))

    def move(self, x: float, y: float) -> QPoint:
        point = self.point(x, y)
        QTest.mouseMove(self.canvas.viewport(), point)
        self.cursor = self.canvas.viewport().mapTo(self.window, point)
        self.app.processEvents()
        return point

    def hover(self, x: float, y: float) -> QPoint:
        """Move the pointer and refresh what the view shows under it: an
        insertion preview while a template or SMILES is pending, otherwise the
        hover highlight."""
        point = self.move(x, y)
        services = canvas_services_for(self.canvas)
        state = insert_state_for(self.canvas)
        if state.template_active:
            services.structure.insert_controller.render_template_preview(QPointF(x, y))
        elif state.smiles_active:
            services.structure.insert_controller.render_smiles_preview(QPointF(x, y))
        else:
            services.hover.update_hover_highlight(QPointF(x, y))
        self.app.processEvents()
        return point

    def click(self, x: float, y: float) -> None:
        point = self.move(x, y)
        QTest.mouseClick(self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, point)
        self.app.processEvents()

    def double_click(self, x: float, y: float) -> None:
        point = self.move(x, y)
        QTest.mouseDClick(self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, point)
        QTest.mouseRelease(self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, point)
        self.app.processEvents()

    def drag(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        *,
        title: str,
        detail: str,
        steps: int = 4,
        modifiers=NO_MODIFIER,
        frame_duration: int = 200,
    ) -> None:
        """Press at ``start``, move to ``end`` in ``steps`` captured frames,
        release."""
        QTest.mousePress(
            self.canvas.viewport(), LEFT_BUTTON, modifiers, self.move(*start)
        )
        for index in range(1, steps + 1):
            t = index / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            self.move(x, y)
            self.capture(title, detail, frame_duration)
        QTest.mouseRelease(
            self.canvas.viewport(), LEFT_BUTTON, modifiers, self.point(*end)
        )
        self.app.processEvents()

    def key(self, key: Qt.Key, modifiers=NO_MODIFIER) -> None:
        self.canvas.setFocus()
        QTest.keyClick(self.canvas, key, modifiers)
        self.app.processEvents()

    def type_text(self, text: str) -> None:
        self.canvas.setFocus()
        QTest.keyClicks(self.canvas, text)
        self.app.processEvents()

    # -- window controls -----------------------------------------------------

    def set_tool(self, key: str) -> None:
        tool_action_for_window(self.window, key).trigger()
        self.app.processEvents()

    def action(self, text: str) -> QAction:
        matches = [
            action
            for action in self.window.findChildren(QAction)
            if action.text().replace("&", "") == text
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {text!r} action; got {len(matches)}")
        return matches[0]

    def context_button(self, tooltip: str) -> QToolButton:
        """A visible options-bar button, found by the tooltip the user reads."""
        matches = [
            button
            for button in self.window.findChildren(QToolButton)
            if button.toolTip() == tooltip and button.isVisible()
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"Expected one visible {tooltip!r} button; got {len(matches)}"
            )
        return matches[0]

    def click_context_button(self, tooltip: str) -> None:
        button = self.context_button(tooltip)
        QTest.mouseClick(button, LEFT_BUTTON)
        self.app.processEvents()

    def dialog(self, invoke: Callable[[], object], title: str, fill) -> object:
        errors: list[Exception] = []

        def drive() -> None:
            dialog = self.app.activeModalWidget()
            try:
                if not isinstance(dialog, QDialog) or dialog.windowTitle() != title:
                    raise RuntimeError(f"Expected the {title!r} dialog")
                fill(dialog)
            except Exception as exc:
                errors.append(exc)
                if isinstance(dialog, QDialog):
                    dialog.reject()

        QTimer.singleShot(150, drive)
        result = invoke()
        if errors:
            raise errors[0]
        return result

    def wait(self, milliseconds: int) -> None:
        QTest.qWait(milliseconds)

    def rotate_selection(self, degrees: float, *, title: str, detail: str) -> None:
        """Drag the selection frame's rotation knob through ``degrees`` in
        captured steps, exactly as a pointer would."""
        from chemvas.features.selection import (
            HANDLE_SCREEN_PX,
            ROTATION_HANDLE_STEM_PX,
            ROTATION_HANDLE_TYPE,
        )
        from chemvas.ui.selection_outline_state import selection_outlines_for

        knobs = [
            item
            for item in selection_outlines_for(self.canvas)
            if item.data(1) == ROTATION_HANDLE_TYPE
        ]
        if len(knobs) != 1:
            raise RuntimeError(f"Expected one rotation knob; got {len(knobs)}")
        knob = knobs[0]
        anchor = self.canvas.mapFromScene(knob.pos())
        start = anchor - QPoint(
            0, round(ROTATION_HANDLE_STEM_PX + HANDLE_SCREEN_PX / 2)
        )
        frame = self.canvas.scene().selectionArea().boundingRect()
        bounds = QPointF(0.0, 0.0)
        selected = self.canvas.scene().selectedItems()
        if selected:
            rect = selected[0].sceneBoundingRect()
            for item in selected[1:]:
                rect = rect.united(item.sceneBoundingRect())
            bounds = rect.center()
        del frame
        center = self.canvas.mapFromScene(bounds)
        dx, dy = start.x() - center.x(), start.y() - center.y()
        viewport = self.canvas.viewport()
        QTest.mousePress(viewport, LEFT_BUTTON, NO_MODIFIER, start)
        steps = 4
        for index in range(1, steps + 1):
            radians = math.radians(degrees * index / steps)
            point = QPoint(
                round(center.x() + dx * math.cos(radians) - dy * math.sin(radians)),
                round(center.y() + dx * math.sin(radians) + dy * math.cos(radians)),
            )
            QTest.mouseMove(viewport, point, 20)
            self.cursor = viewport.mapTo(self.window, point)
            self.capture(title, detail, 220)
        QTest.mouseRelease(viewport, LEFT_BUTTON, NO_MODIFIER, point)
        self.app.processEvents()

    def close(self) -> None:
        from chemvas.ui.main_window_ports import services_for_window

        services_for_window(self.window).canvas_document_service.mark_clean(self.canvas)
        self.window.close()
        self.app.processEvents()


def run_with_profile(
    output: Path, run: Callable[[QApplication], None], *, command: str
) -> int:
    """Run ``run`` under a throwaway app-data profile so no user document or
    session is touched."""
    import os
    import tempfile

    with tempfile.TemporaryDirectory(prefix=f"chemvas-{command}-profile-") as profile:
        for kind in ("DATA", "CONFIG", "CACHE", "STATE"):
            os.environ[f"XDG_{kind}_HOME"] = str(Path(profile) / kind.lower())
        app = QApplication([])
        app.setApplicationName("Chemvas")
        app.setQuitOnLastWindowClosed(False)
        run(app)
    return 0


__all__ = [
    "HEADER",
    "HEIGHT",
    "LEFT_BUTTON",
    "NO_MODIFIER",
    "WIDTH",
    "Walkthrough",
    "run_with_profile",
]
