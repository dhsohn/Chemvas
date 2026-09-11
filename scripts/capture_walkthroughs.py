#!/usr/bin/env python3
"""Capture the short reference-guide walkthroughs from the real application.

Each topic drives the main window offscreen with synthetic input and writes
one GIF: drawing, arrows, editing and chemistry. Run with the development
environment including RDKit and an empty output directory; only synthetic
drawing data is used and no user document is opened.
"""

from __future__ import annotations

import argparse
import os
import sys
from itertools import pairwise
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton
from walkthrough_capture import WIDTH, Walkthrough, run_with_profile

from chemvas.core.molfile import write_molfile
from chemvas.ui.canvas_insert_state import insert_state_for
from chemvas.ui.canvas_scene_items_state import arrow_items_for
from chemvas.ui.canvas_service_access import canvas_services_for
from chemvas.ui.main_window_ports import (
    document_session_service_for_window,
    preview_window_for_window,
    services_for_window,
)
from chemvas.ui.rdkit_adapter_access import smiles_to_2d_for
from chemvas.ui.renderer_style_access import bond_length_px_for
from chemvas.ui.scene_item_state_serialization import arrow_state_dict

TOPICS = ("drawing", "arrows", "editing", "chemistry")


def _bond_midpoint(canvas, index: int) -> tuple[float, float]:
    bond = canvas.model.bonds[index]
    a = canvas.model.atoms[bond.a]
    b = canvas.model.atoms[bond.b]
    return ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)


def _place_smiles(w: Walkthrough, smiles: str, x: float, y: float) -> list[int]:
    """Insert a structure the way the Ring bar's Insert button does, off camera."""
    previous = set(w.canvas.model.atoms)
    controller = canvas_services_for(w.canvas).structure.insert_controller
    controller.begin_smiles_insert(smiles)
    controller.render_smiles_preview(QPointF(x, y))
    controller.commit_smiles_insert(QPointF(x, y))
    w.app.processEvents()
    added = sorted(set(w.canvas.model.atoms) - previous)
    if not added:
        raise RuntimeError(f"{smiles!r} was not inserted")
    return added


# --- drawing ----------------------------------------------------------------


def drawing(w: Walkthrough) -> None:
    title = "Draw a structure"
    w.capture(title, "Bond tool: drag to draw, hover to edit, Ring to fuse.", 1200)
    w.set_tool("bond")
    w.drag((-70.0, 10.0), (-35.0, -10.0), title=title, detail="Drag to draw a bond.")
    # The tool snaps the drawn bond to 30° steps and the default length, so
    # each next drag starts from where the previous atom actually landed.
    for dx, dy in ((35.0, 20.0), (35.0, -20.0)):
        tip = max(w.canvas.model.atoms.values(), key=lambda atom: atom.x)
        w.drag(
            (tip.x, tip.y),
            (tip.x + dx, tip.y + dy),
            title=title,
            detail="Drag from an atom to extend the chain.",
        )
    if len(w.canvas.model.atoms) != 4:
        raise RuntimeError(f"expected 4 atoms, got {len(w.canvas.model.atoms)}")
    w.capture(title, "Three drags, three bonds.", 900)

    # The last chain bond: the ring fused onto the first bond below keeps its
    # full alternation only when no double bond meets the shared atom.
    w.hover(*_bond_midpoint(w.canvas, 2))
    w.key(Qt.Key.Key_2)
    if w.canvas.model.bonds[2].order != 2:
        raise RuntimeError("the hovered bond did not become double")
    w.capture(
        title, "Hover a bond and press 2 for a double bond (1 single, 3 triple).", 1500
    )

    last = max(w.canvas.model.atoms, key=lambda i: w.canvas.model.atoms[i].x)
    atom = w.canvas.model.atoms[last]
    w.hover(atom.x, atom.y)
    w.key(Qt.Key.Key_O)
    if w.canvas.model.atoms[last].element != "O":
        raise RuntimeError("the hovered atom did not become O")
    w.capture(
        title, "Hover an atom and type its element: o for oxygen, n for nitrogen.", 1500
    )
    w.key(Qt.Key.Key_Minus)
    w.capture(title, "Press - or + to add a charge to the hovered atom.", 1400)

    w.set_tool("benzene")
    state = insert_state_for(w.canvas)
    if not state.template_active:
        canvas_services_for(
            w.canvas
        ).structure.insert_controller.begin_ring_template_insert(6, "benzene")
    w.hover(*_bond_midpoint(w.canvas, 0))
    w.capture(title, "Ring: hover a bond to preview a fused benzene ring.", 1400)
    w.click(*_bond_midpoint(w.canvas, 0))
    if len(w.canvas.model.atoms) < 8:
        raise RuntimeError("the ring template was not fused")
    w.set_tool("select")
    w.move(0.0, 60.0)
    w.capture(title, "Click to fuse it. Esc leaves the Ring tool.", 2200)


# --- arrows -----------------------------------------------------------------


def arrows(w: Walkthrough) -> None:
    title = "Arrows and labels"
    w.set_tool("arrow")
    w.move(-40.0, 0.0)
    w.capture(title, "Arrow tool: the options bar lists the arrow kinds.", 1400)
    w.drag(
        (-90.0, -20.0),
        (-10.0, -20.0),
        title=title,
        detail="Drag to draw a reaction arrow.",
    )

    def fill(dialog: QDialog) -> None:
        for name, text in (
            ("arrowLabelAboveInput", "k_1"),
            ("arrowLabelBelowInput", "25 °C"),
        ):
            field = dialog.findChild(QLineEdit, name)
            if field is None:
                raise RuntimeError(f"Missing {name}")
            field.setFocus()
            QTest.keyClicks(field, text)
        w.capture(
            title, "Double-click the arrow: _ makes a subscript, ^ a superscript.", 2400
        )
        next(b for b in dialog.findChildren(QPushButton) if b.text() == "OK").click()

    w.set_tool("select")
    w.dialog(lambda: w.double_click(-50.0, -20.0), "Arrow Labels", fill)
    w.move(-50.0, 10.0)
    w.capture(title, "Labels belong to the arrow and move with it.", 1600)

    w.set_tool("arrow")
    w.click_context_button("Equilibrium")
    w.drag(
        (-90.0, 30.0), (-10.0, 30.0), title=title, detail="Pick Equilibrium and drag."
    )
    w.click_context_button("Curved Single")
    w.drag(
        (20.0, 40.0),
        (80.0, -10.0),
        title=title,
        detail="Curved arrows follow the drag.",
    )
    # A reaction profile is where endpoint snapping earns its keep: energy
    # levels placed by clicking, connectors whose ends join the level ends.
    w.canvas.centerOn(0.0, 45.0)
    w.set_tool("line")
    w.move(-100.0, 100.0)
    w.capture(
        title, "Reaction profile: with Line, a click places a horizontal level.", 1600
    )
    levels: list[tuple[float, float, float, float]] = []
    for x, y in ((-120.0, 105.0), (-30.0, 55.0), (60.0, 95.0)):
        w.click(x, y)
        levels.append((x, y, x + 40.0, y))
    w.capture(title, "Reactant, transition state, product.", 1400)
    for (_, _, x2, y2), (nx1, ny1, _, _) in pairwise(levels):
        w.drag(
            (x2 - 2.0, y2 + 2.0),
            (nx1 + 2.0, ny1 - 2.0),
            title=title,
            detail="Drag from a level's end to the next: both ends snap to the level ends.",
        )
    items = arrow_items_for(w.canvas)
    if len(items) != 8:
        raise RuntimeError(f"expected 3 arrows and 5 lines, got {len(items)}")
    connectors = [arrow_state_dict(item) for item in items[-2:]]
    for connector, ((_, _, x2, y2), (nx1, ny1, _, _)) in zip(
        connectors, pairwise(levels), strict=True
    ):
        if tuple(connector["start"]) != (x2, y2) or tuple(connector["end"]) != (
            nx1,
            ny1,
        ):
            raise RuntimeError(f"connector did not snap to the level ends: {connector}")
    w.set_tool("select")
    w.move(0.0, 130.0)
    w.capture(
        title,
        "Arrows carry their labels; the profile's connectors stay joined to the levels.",
        2400,
    )


# --- editing ----------------------------------------------------------------


def editing(w: Walkthrough) -> None:
    title = "Select, move, rotate, align"
    _place_smiles(w, "c1ccccc1", -100.0, -5.0)
    ethanol = _place_smiles(w, "CCO", 10.0, 28.0)
    _place_smiles(w, "CC(=O)O", 105.0, -12.0)
    w.set_tool("select")
    w.canvas.scene().clearSelection()
    w.move(0.0, 60.0)
    w.capture(title, "Select tool: press on a structure and drag to move it.", 1400)
    handle = w.canvas.model.atoms[ethanol[1]]
    w.drag(
        (handle.x, handle.y),
        (handle.x + 10.0, handle.y - 30.0),
        title=title,
        detail="A molecule moves as a whole.",
    )
    w.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    from chemvas.ui.selection_service_access import refresh_selection_outline_for

    refresh_selection_outline_for(w.canvas)
    w.app.processEvents()
    w.capture(
        title, "Ctrl+A selects everything; the frame carries a rotation knob.", 1500
    )
    w.rotate_selection(
        25.0,
        title=title,
        detail="Drag the knob to rotate the selection (Shift snaps to 15°).",
    )
    w.capture(title, "One drag, one undo step.", 1200)
    w.click_context_button("Flip Horizontal (Ctrl+Shift+H)")
    w.capture(title, "Flip Horizontal / Flip Vertical act on the selection.", 1500)
    w.action("Middle").trigger()
    w.app.processEvents()
    w.capture(title, "Edit ▸ Align ▸ Middle lines the structures up.", 1800)
    w.action("Horizontally").trigger()
    w.app.processEvents()
    w.capture(
        title,
        "Edit ▸ Distribute ▸ Horizontally spaces them with equal gaps.",
        1800,
    )
    w.click(0.0, 100.0)
    w.move(0.0, 110.0)
    w.capture(
        title,
        "Whole molecules and groups move as units; one undo step reverses each edit.",
        2200,
    )


# --- chemistry --------------------------------------------------------------


def chemistry(w: Walkthrough) -> None:
    title = "Chemistry I/O (RDKit)"
    model = smiles_to_2d_for(
        w.canvas, "CC(=O)Oc1ccccc1C(=O)O", scale=bond_length_px_for(w.canvas)
    )
    if model is None:
        raise RuntimeError("RDKit could not convert the aspirin SMILES")
    mol_path = w.output / "aspirin.mol"
    mol_path.write_text(write_molfile(model), encoding="utf-8")
    w.capture(
        title,
        "SMILES insertion lives on the Ring bar; this covers files and identifiers.",
        1200,
    )
    services_for_window(w.window).document_action_service.load_canvas_from_path(
        w.window, str(mol_path)
    )
    w.app.processEvents()
    if len(w.canvas.model.atoms) != 13:
        raise RuntimeError(
            f"expected 13 atoms from the molfile, got {len(w.canvas.model.atoms)}"
        )
    # The status bar echoes the absolute path; the frame shows the file name.
    w.window.statusBar().showMessage(f"Imported MOL: {mol_path.name}")
    w.move(0.0, 70.0)
    w.capture(title, "File ▸ Open reads an MDL molfile (.mol) as a new drawing.", 1800)

    w.key(Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    w.canvas.centerOn(150.0, 0.0)
    preview_window = preview_window_for_window(w.window)
    preview_window.resize(520, 470)
    w.extra_windows.append((preview_window, QPoint(WIDTH - 536, 96)))
    w.action("Molecule Info").trigger()
    preview = preview_window._preview_widget
    for _ in range(100):
        w.app.processEvents()
        QTest.qWait(100)
        if getattr(preview, "_scene", None) is not None:
            break
    else:
        raise RuntimeError("the 3D preview did not finish")
    w.cursor = None
    w.capture(
        title,
        "View ▸ Molecule Info: 3D preview, formula, weight, SMILES, InChI and InChIKey.",
        2600,
    )

    session = document_session_service_for_window(w.window)
    session.export_mol(str(w.output / "aspirin-export.mol"), selected_only=True)
    w.window.statusBar().showMessage("Exported aspirin-export.mol")
    w.capture(
        title, "File ▸ Export MOL… writes the selection as a V2000 molfile.", 1800
    )
    session.export_xyz(str(w.output / "aspirin.xyz"), selected_only=True)
    preview_window.show_export_status("Exported aspirin.xyz")
    w.capture(
        title, "Export 3D XYZ in Molecule Info writes RDKit 3D coordinates.", 2200
    )
    preview_window.close()
    w.extra_windows.clear()


TOPIC_RUNNERS = {
    "drawing": drawing,
    "arrows": arrows,
    "editing": editing,
    "chemistry": chemistry,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--topic", choices=(*TOPICS, "all"), default="all")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(
            "--output-dir must be empty; existing artifacts are never replaced"
        )
    topics = TOPICS if args.topic == "all" else (args.topic,)

    def run(app: QApplication) -> None:
        for topic in topics:
            walkthrough = Walkthrough(app, output, zoom_percent=200)
            try:
                TOPIC_RUNNERS[topic](walkthrough)
                walkthrough.save_gif(f"walkthrough-{topic}.gif")
            finally:
                walkthrough.close()

    return run_with_profile(output, run, command="walkthroughs")


if __name__ == "__main__":
    raise SystemExit(main())
