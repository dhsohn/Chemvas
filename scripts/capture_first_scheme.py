#!/usr/bin/env python3
"""Capture a real Chemvas walkthrough and save its editable drawing and exports.

Run with the development environment and an empty output
directory. Qt's offscreen plugin is the default; QT_QPA_PLATFORM=wayland also
exercises an exposed desktop window. Only synthetic drawing data is used.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
)
from walkthrough_capture import LEFT_BUTTON, NO_MODIFIER, Walkthrough, run_with_profile

from chemvas.ui.annotations.state import arrow_state_dict_for
from chemvas.ui.window.main_window_document_dialogs import prompt_export_options
from chemvas.ui.window.main_window_ports import document_session_service_for_window


class FirstScheme(Walkthrough):
    def insert(self, *, carbonyl: bool, x: float, y: float, title: str) -> int:
        """Draw a ring and its two-bond side chain through the visible tools."""
        previous_ids = set(self.canvas.model.atoms)
        self.set_tool("benzene")
        self.click(x, y)
        ring_ids = set(self.canvas.model.atoms) - previous_ids
        assert len(ring_ids) == 6
        self.capture(title, "Ring: click to place a benzene ring.", 1200)
        current = max(
            ring_ids,
            key=lambda i: (
                self.canvas.model.atoms[i].x,
                -self.canvas.model.atoms[i].y,
            ),
        )
        self.set_tool("bond")
        for dx, dy in ((30.31, -17.5), (30.31, 17.5)):
            atom = self.canvas.model.atoms[current]
            before = set(self.canvas.model.atoms)
            self.drag(
                (atom.x, atom.y),
                (atom.x + dx, atom.y + dy),
                title=title,
                detail="Bond: extend from the upper-right ring atom with a 30° zigzag.",
                steps=3,
                frame_duration=160,
            )
            added = set(self.canvas.model.atoms) - before
            assert len(added) == 1
            current = added.pop()
        if carbonyl:
            bond = self.canvas.model.bonds[-1]
            a, b = self.canvas.model.atoms[bond.a], self.canvas.model.atoms[bond.b]
            self.hover((a.x + b.x) / 2, (a.y + b.y) / 2)
            self.key(Qt.Key.Key_2)
            assert bond.order == 2
        atom = self.canvas.model.atoms[current]
        self.hover(atom.x, atom.y)
        self.key(Qt.Key.Key_O)
        assert self.canvas.model.atoms[current].element == "O"
        self.capture(title, "Hover the terminal atom and type O for oxygen.", 1200)
        self.set_tool("select")
        self.canvas.scene().clearSelection()
        self.capture(
            title, "Keep both rings upright and use matching side-chain angles.", 1000
        )
        return current

    def label_arrow(self) -> None:
        def fill(dialog: QDialog) -> None:
            above = dialog.findChild(QTextEdit, "arrowLabelAboveInput")
            if above is None:
                raise RuntimeError("Missing arrowLabelAboveInput")
            subscript = dialog.findChild(QToolButton, "arrowLabelSubscript")
            if subscript is None:
                raise RuntimeError("Missing arrowLabelSubscript")
            above.setFocus()
            QTest.keyClicks(above, "MnO2")
            cursor = above.textCursor()
            cursor.setPosition(3)
            cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
            above.setTextCursor(cursor)
            self.capture(
                "02 / Add reaction labels",
                "Double-click the arrow. Select text, then Subscript or Superscript.",
                2400,
            )
            QTest.mouseClick(subscript, Qt.MouseButton.LeftButton)
            self.capture(
                "02 / Add reaction labels",
                "Formatting applies to the selection.",
                2400,
            )
            below = dialog.findChild(QTextEdit, "arrowLabelBelowInput")
            if below is None:
                raise RuntimeError("Missing arrowLabelBelowInput")
            below.setFocus()
            QTest.keyClicks(below, "oxidation")
            self.capture(
                "02 / Add reaction labels",
                "Above: MnO₂. Below: oxidation. Click OK to apply both labels.",
                1800,
            )
            ok = next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK")
            if not ok.isEnabled():
                raise RuntimeError("OK must be enabled with valid labels")
            ok.click()

        def open_dialog() -> None:
            QTest.mouseDClick(
                self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(0, 0)
            )
            QTest.mouseRelease(
                self.canvas.viewport(), LEFT_BUTTON, NO_MODIFIER, self.point(0, 0)
            )

        self.dialog(open_dialog, "Arrow Labels", fill)
        (arrow,) = self.canvas.runtime_state.arrow_items()
        assert arrow_state_dict_for(self.canvas, arrow)["labels"] == {
            "above": "MnO_{2}",
            "below": "oxidation",
        }

    def label_hydroxyl(self, atom_id: int) -> None:
        atom = self.canvas.model.atoms[atom_id]
        self.move(atom.x, atom.y)
        self.canvas.services.hover.update_hover_highlight(QPointF(atom.x, atom.y))

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
            lambda: self.canvas.services.atom_label_service.prompt_atom_label(atom_id),
            "Atom Label",
            fill,
        )
        assert self.canvas.model.atoms[atom_id].element == "OH"

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
        alcohol = self.insert(
            carbonyl=False, x=-145, y=-20, title="01 / Draw a structure"
        )
        self.label_hydroxyl(alcohol)
        self.insert(carbonyl=True, x=105, y=20, title="01 / Add the product")
        assert len(self.canvas.model.atoms) == 16
        assert len(self.canvas.model.bonds) == 16
        graphics = self.canvas.runtime_state.bond_graphics_state.bond_items
        assert set(graphics) == set(range(16))
        assert all(
            any(item.isVisible() for item in items) for items in graphics.values()
        )

        self.window.ui_references.tool_action_for_key("arrow").trigger()
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
        self.window.ui_references.tool_action_for_key("select").trigger()
        self.label_arrow()
        self.capture("02 / Add reaction labels", "Labels stay attached to the arrow.")

        self.canvas.setFocus()
        QTest.keyClick(self.canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.capture(
            "03 / Align the scheme",
            "Select everything, then Edit → Align → Middle.",
            1400,
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

        warnings = self.canvas.services.canvas_document_session_service.save_to_file(
            str(self.output / "first-scheme.cdxml")
        )
        assert not warnings, warnings
        self.window.services.canvas_document_service.mark_clean(self.canvas)
        self.window.statusBar().clearMessage()
        self.cursor = None
        if not self.window.grab().save(str(self.output / "demo.png")):
            raise RuntimeError("Could not save the canvas screenshot")
        self.export()
        self.window.statusBar().showMessage("Exported first-scheme.svg · 174 mm")
        self.capture(
            "Saved as CDXML / Exported SVG",
            "Open first-scheme.cdxml to keep editing. Use the exported SVG in your manuscript.",
            2500,
        )
        self.save_gif("demo.gif")


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

    def run(app: QApplication) -> None:
        walkthrough = FirstScheme(app, output)
        try:
            walkthrough.run()
        finally:
            walkthrough.close()

    return run_with_profile(output, run, command="capture")


if __name__ == "__main__":
    raise SystemExit(main())
