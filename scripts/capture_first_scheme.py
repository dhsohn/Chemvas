#!/usr/bin/env python3
"""Capture a real Chemvas walkthrough and save its editable drawing and exports.

Run with the development environment (including RDKit) and an empty output
directory. Qt's offscreen plugin is the default; QT_QPA_PLATFORM=wayland also
exercises an exposed desktop window. Only synthetic drawing data is used.
"""

from __future__ import annotations

import argparse
import io
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, QPointF, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QImage, QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLineEdit,
    QPushButton,
    QToolButton,
)

from chemvas.bootstrap.main_window import build_main_window
from chemvas.ui.canvas_atom_graphics_state import visible_atom_item_for
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.canvas_window_access import save_canvas_to_file_for
from chemvas.ui.main_window_document_dialogs import prompt_export_options
from chemvas.ui.main_window_ports import (
    active_canvas_for_window,
    document_session_service_for_window,
    services_for_window,
    set_zoom_percent_for_window,
    tool_action_for_window,
)
from chemvas.ui.scene_item_state_serialization import arrow_state_dict

WIDTH, HEIGHT = 1120, 580
HEADER = 76
LEFT_BUTTON = Qt.MouseButton.LeftButton
NO_MODIFIER = Qt.KeyboardModifier.NoModifier


class Walkthrough:
    def __init__(self, app: QApplication, output: Path) -> None:
        self.app = app
        self.output = output
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []
        self.window = build_main_window()
        self.window.resize(WIDTH, HEIGHT)
        self.window.show()
        self.canvas = active_canvas_for_window(self.window)
        self.app.processEvents()
        set_zoom_percent_for_window(self.window, 270)
        self.canvas.centerOn(0.0, 0.0)
        self.cursor: QPoint | None = None
        QTest.qWait(150)

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

    def point(self, x: float, y: float) -> QPoint:
        return self.canvas.mapFromScene(QPointF(x, y))

    def move(self, x: float, y: float) -> QPoint:
        point = self.point(x, y)
        QTest.mouseMove(self.canvas.viewport(), point)
        self.cursor = self.canvas.viewport().mapTo(self.window, point)
        self.app.processEvents()
        return point

    def insert(self, smiles: str, x: float, y: float, title: str) -> None:
        previous_ids = set(self.canvas.model.atoms)
        # The SMILES controls live on the Ring tool's options bar, so the
        # walkthrough chooses that tool the way the tutorial describes.
        tool_action_for_window(self.window, "benzene").trigger()
        self.app.processEvents()
        field = self.window.findChild(QLineEdit, "contextSmilesInput")
        button = self.window.findChild(QToolButton, "smiles_render_button")
        if field is None or button is None or not field.isVisible():
            raise RuntimeError("SMILES controls are unavailable on the Ring bar")
        field.setFocus()
        field.selectAll()
        QTest.keyClicks(field, smiles)
        self.capture(
            title,
            f"Choose Ring, enter {smiles} on its options bar, click Insert.",
            1200,
        )
        QTest.mouseClick(button, LEFT_BUTTON)
        self.canvas.setFocus()
        point = self.move(x, y)
        self.capture(title, "Preview the structure, then click to place it.", 1000)
        QTest.mouseClick(self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, point)
        self.app.processEvents()
        self.capture(title, "The structure remains editable on the canvas.", 1200)
        self.canvas.scene().clearSelection()
        for atom_id in set(self.canvas.model.atoms) - previous_ids:
            item = visible_atom_item_for(self.canvas, atom_id)
            if item is not None:
                item.setSelected(True)
        self.canvas.setFocus()
        for _ in range(3):
            QTest.keyClick(self.canvas, Qt.Key.Key_Up, Qt.KeyboardModifier.AltModifier)
        self.canvas.scene().clearSelection()
        self.capture(
            title, "Select the molecule; Alt + Up rotates it in 15° steps.", 1000
        )

    def action(self, text: str) -> QAction:
        matches = [
            action
            for action in self.window.findChildren(QAction)
            if action.text().replace("&", "") == text
        ]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {text!r} action; got {len(matches)}")
        return matches[0]

    def dialog(self, invoke, title: str, fill):
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

    def label_arrow(self) -> None:
        def fill(dialog: QDialog) -> None:
            for name, text in (
                ("arrowLabelAboveInput", "MnO_2"),
                ("arrowLabelBelowInput", "oxidation"),
            ):
                field = dialog.findChild(QLineEdit, name)
                if field is None:
                    raise RuntimeError(f"Missing {name}")
                field.setFocus()
                QTest.keyClicks(field, text)
            self.capture(
                "02 / Add reaction labels",
                "Double-click the arrow. An underscore formats a subscript.",
                2400,
            )
            next(
                b for b in dialog.findChildren(QPushButton) if b.text() == "OK"
            ).click()

        def open_dialog() -> None:
            QTest.mouseDClick(
                self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(0, 0)
            )
            QTest.mouseRelease(
                self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(0, 0)
            )

        self.dialog(open_dialog, "Arrow Labels", fill)
        (arrow,) = arrow_items_for(self.canvas)
        assert arrow_state_dict(arrow)["labels"] == {
            "above": "MnO_2",
            "below": "oxidation",
        }

    def label_hydroxyl(self) -> None:
        atom = self.canvas.model.atoms[0]
        self.move(atom.x, atom.y)
        canvas_services_for(self.canvas).hover.update_hover_highlight(
            QPointF(atom.x, atom.y)
        )

        def fill(dialog: QDialog) -> None:
            field = dialog.findChild(QLineEdit)
            if field is None:
                raise RuntimeError("Missing atom label field")
            field.selectAll()
            QTest.keyClicks(field, "OH")
            self.capture(
                "01 / Make the hydroxyl label explicit",
                "Hover over the alcohol oxygen, press Enter, and enter OH.",
                1800,
            )
            dialog.accept()

        self.dialog(
            lambda: canvas_services_for(
                self.canvas
            ).atom_label_service.prompt_atom_label(0),
            "Atom Label",
            fill,
        )
        assert self.canvas.model.atoms[0].element == "OH"

    def export(self) -> None:
        def fill(dialog: QDialog) -> None:
            for name, value in (
                ("exportFormatCombo", "svg"),
                ("exportSizeCombo", "col2"),
                ("exportScopeCombo", "sheet"),
                ("exportBackgroundCombo", "white"),
            ):
                combo = dialog.findChild(QComboBox, name)
                if combo is None or combo.findData(value) < 0:
                    raise RuntimeError(f"Missing export choice {name}={value}")
                combo.setCurrentIndex(combo.findData(value))
            self.capture(
                "04 / Export exactly",
                "Plain SVG · Fit 2-column (174 mm) · Whole canvas · White",
                2600,
            )
            next(
                b for b in dialog.findChildren(QPushButton) if b.text() == "Export"
            ).click()

        options = self.dialog(
            lambda: prompt_export_options(self.window), "Export Figure", fill
        )
        if options is None:
            raise RuntimeError("Export was cancelled")
        session = document_session_service_for_window(self.window)
        session.export_figure(
            str(self.output / "first-scheme.svg"),
            fmt=options.fmt,
            scope=options.scope,
            sizing=options.sizing,
            background=options.background,
            editable_svg=options.editable_svg,
        )
        session.export_figure(
            str(self.output / "first-scheme.png"),
            fmt="png",
            scope=options.scope,
            sizing=options.sizing,
            background=options.background,
            dpi=300,
        )
        # Qt emits trailing spaces in SVG attributes. Normalize only line ends
        # for the checked-in example; the exported drawing stays unchanged.
        svg_path = self.output / "first-scheme.svg"
        svg_path.write_text(
            "\n".join(
                line.rstrip()
                for line in svg_path.read_text(encoding="utf-8").splitlines()
            )
            + "\n",
            encoding="utf-8",
        )

    def run(self) -> None:
        self.capture(
            "Chemvas / Your first reaction scheme",
            "Draw interactively. Automate safely. Export exactly.",
            1200,
        )
        self.insert("OCc1ccccc1", -118, -22, "01 / Insert a structure")
        self.label_hydroxyl()
        self.insert("O=Cc1ccccc1", 118, 22, "01 / Add the product")
        assert len(self.canvas.model.atoms) == 16
        assert len(self.canvas.model.bonds) == 16

        tool_action_for_window(self.window, "arrow").trigger()
        QTest.mousePress(
            self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.move(-45, 0)
        )
        for x in (-25, 0, 25, 45):
            self.move(x, 0)
            self.capture(
                "02 / Draw the reaction arrow", "Drag between the structures.", 200
            )
        QTest.mouseRelease(
            self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(45, 0)
        )
        tool_action_for_window(self.window, "select").trigger()
        self.label_arrow()
        self.capture("02 / Add reaction labels", "Labels stay attached to the arrow.")

        self.canvas.setFocus()
        QTest.keyClick(self.canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.capture(
            "03 / Align the scheme", "Select all, then Edit → Align → Middle.", 1400
        )
        before = [(atom.x, atom.y) for atom in self.canvas.model.atoms.values()]
        self.action("Middle").trigger()
        after = [(atom.x, atom.y) for atom in self.canvas.model.atoms.values()]
        assert before != after, "The alignment demonstration must actually move atoms"
        QTest.mouseClick(
            self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(0, 70)
        )
        self.move(0, 85)
        self.capture("03 / Align the scheme", "Molecules move as whole structures.")

        warnings = save_canvas_to_file_for(
            self.canvas, str(self.output / "first-scheme.chemvas")
        )
        assert not warnings, warnings
        services_for_window(self.window).canvas_document_service.mark_clean(self.canvas)
        self.window.statusBar().clearMessage()
        self.cursor = None
        if not self.window.grab().save(str(self.output / "demo.png")):
            raise RuntimeError("Could not save the canvas screenshot")
        self.export()
        self.window.statusBar().showMessage("Exported first-scheme.svg · 174 mm")
        self.capture(
            "Saved as SVG / Keep the editable drawing",
            "Open first-scheme.chemvas to keep editing. Use the SVG in your manuscript.",
            2500,
        )
        self.frames[0].save(
            self.output / "demo.gif",
            save_all=True,
            append_images=self.frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
        )
        print(f"Captured {len(self.frames)} frames; {sum(self.durations) / 1000:g} s")

    def close(self) -> None:
        services_for_window(self.window).canvas_document_service.mark_clean(self.canvas)
        self.window.close()
        self.app.processEvents()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "--output-dir must be empty; existing artifacts are never replaced"
        )
    with tempfile.TemporaryDirectory(prefix="chemvas-capture-profile-") as profile:
        for kind in ("DATA", "CONFIG", "CACHE", "STATE"):
            os.environ[f"XDG_{kind}_HOME"] = str(Path(profile) / kind.lower())
        app = QApplication([])
        app.setApplicationName("Chemvas")
        app.setQuitOnLastWindowClosed(False)
        walkthrough = Walkthrough(app, output)
        try:
            walkthrough.run()
        finally:
            walkthrough.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
