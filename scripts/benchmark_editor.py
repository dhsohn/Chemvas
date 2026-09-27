"""Measure real editor transactions; timings exclude setup and state validation."""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import statistics
import time
from collections import defaultdict
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QT_VERSION_STR
from PyQt6.QtWidgets import QApplication

from chemvas.adapters.qt.renderer import Renderer
from chemvas.features.document_composition import compose_document_state
from chemvas.ui.canvas.canvas_view import CanvasView
from chemvas.ui.transactions.document import DocumentSavepoint


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def document_state(count: int) -> dict:
    return compose_document_state(
        {
            "format": "chemvas-document-composition",
            "version": 1,
            "atoms": [
                {"id": i, "element": "C", "x": (i % 50) * 30, "y": (i // 50) * 60}
                for i in range(count)
            ],
            "bonds": [
                {"a": i - 1, "b": i, "order": 1} for i in range(1, count) if i % 50
            ],
        }
    )


def measure(action) -> tuple[float, int]:
    gc.collect()
    with mock.patch.object(
        DocumentSavepoint, "capture", wraps=DocumentSavepoint.capture
    ) as capture:
        start = time.perf_counter_ns()
        action()
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    return elapsed_ms, capture.call_count


def exercise(
    app: QApplication,
    state: dict,
    operation: str,
    *,
    edited_atoms: int | None = None,
    paste_atoms: int = 10,
) -> dict:
    canvas = CanvasView(renderer=Renderer())
    try:
        documents = canvas.services.canvas_document_session_service
        documents.apply_state(state)
        if edited_atoms is None:
            canvas.services.selection.select_all()
        else:
            if not 1 <= edited_atoms <= len(canvas.model.atoms):
                raise ValueError("edited_atoms must be within the document atom count")
            selected_ids = set(sorted(canvas.model.atoms)[:edited_atoms])
            canvas.services.selection.restore_ids(selected_ids, set())
            from chemvas.ui.selection.selection_queries import (
                selected_atom_ids_for_transform_for,
            )

            if selected_atom_ids_for_transform_for(canvas) != selected_ids:
                raise AssertionError("benchmark selection differs from edited_atoms")
        before = documents.snapshot_state()
        payload = {
            "format": "chemvas-selection",
            "version": 2,
            "atoms": [
                {"id": i, "element": "N", "x": i * 30, "y": -120}
                for i in range(paste_atoms)
            ],
            "bonds": [],
            "rings": [],
            "marks": [],
            "scene_items": [],
        }
        actions = {
            "move": lambda: (
                canvas.services.scene_transform_controller.translate_selected_items(
                    10, 5
                )
            ),
            "delete": canvas.services.scene_delete_controller.delete_selected_items,
            "paste": lambda: (
                canvas.services.scene_clipboard_controller.paste_selection_from_clipboard(
                    payload_provider=lambda: (payload, "benchmark-paste")
                )
            ),
        }
        result = {operation: measure(actions[operation])}
        after = documents.snapshot_state()
        if after == before:
            raise AssertionError(f"{operation} did not change the document")
        history = canvas.services.history_service
        result[f"{operation}_undo"] = measure(history.undo)
        if documents.snapshot_state() != before:
            raise AssertionError(f"{operation} Undo did not restore the document")
        result[f"{operation}_redo"] = measure(history.redo)
        if documents.snapshot_state() != after:
            raise AssertionError(f"{operation} Redo did not restore the edit")
        return result
    finally:
        canvas.services.canvas_scene_reset_service.clear_scene()
        canvas.close()
        canvas.deleteLater()
        app.processEvents()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atoms", type=positive_int, nargs="+", default=[100, 1000])
    parser.add_argument(
        "--edited-atoms",
        type=positive_int,
        help="Select this many atoms for move/delete; defaults to the whole document.",
    )
    parser.add_argument("--paste-atoms", type=positive_int, default=10)
    parser.add_argument(
        "--operations",
        nargs="+",
        choices=("move", "delete", "paste"),
        default=["move", "delete", "paste"],
    )
    parser.add_argument("--repeats", type=positive_int, default=3)
    args = parser.parse_args()
    if args.edited_atoms is not None and args.edited_atoms > min(args.atoms):
        parser.error("--edited-atoms must not exceed any --atoms document size")
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    report = {
        "environment": {
            "os": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "qt": QT_VERSION_STR,
            "qpa": os.environ["QT_QPA_PLATFORM"],
        },
        "repeats": args.repeats,
        "warmup_per_operation": 1,
        "paste_atoms": args.paste_atoms,
        "cases": [],
    }
    for count in args.atoms:
        state = document_state(count)
        samples = defaultdict(list)
        for operation in dict.fromkeys(args.operations):
            exercise(
                app,
                state,
                operation,
                edited_atoms=args.edited_atoms,
                paste_atoms=args.paste_atoms,
            )
            for _ in range(args.repeats):
                for name, sample in exercise(
                    app,
                    state,
                    operation,
                    edited_atoms=args.edited_atoms,
                    paste_atoms=args.paste_atoms,
                ).items():
                    samples[name].append(sample)
        report["cases"].append(
            {
                "initial_atoms": count,
                "selected_atoms": args.edited_atoms or count,
                "operations": {
                    name: {
                        "median_ms": round(statistics.median(t for t, _ in values), 3),
                        "min_ms": round(min(t for t, _ in values), 3),
                        "max_ms": round(max(t for t, _ in values), 3),
                        "savepoints_per_sample": [captures for _, captures in values],
                    }
                    for name, values in samples.items()
                },
            }
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
