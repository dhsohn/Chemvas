from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_GRAPHICS_RECORDS = 20_000


def json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def qt_platform(platform: str | None = None) -> str:
    return "windows" if (platform or sys.platform) == "win32" else "offscreen"


def graphics_record_count(state: Mapping[str, object]) -> int:
    model = state.get("model")
    if not isinstance(model, Mapping):
        raise ValueError("Invalid Chemvas file.")
    atoms = model.get("atoms")
    bonds = model.get("bonds")
    if not isinstance(atoms, Mapping) or not isinstance(bonds, list):
        raise ValueError("Invalid Chemvas file.")
    total = len(atoms) + len(bonds)
    for key in (
        "ring_fills",
        "notes",
        "marks",
        "arrows",
        "ts_brackets",
        "shapes",
        "orbitals",
    ):
        records = state.get(key, [])
        if isinstance(records, list):
            total += len(records)
    return total


@contextmanager
def offscreen_canvas(
    state: dict[str, Any],
    *,
    command: str,
    pin_locale: bool = False,
) -> Iterator[tuple[Any, Any]]:
    previous_qt_platform = os.environ.get("QT_QPA_PLATFORM")
    previous_locale = (
        {name: os.environ.get(name) for name in ("LC_ALL", "LANG")}
        if pin_locale
        else {}
    )
    os.environ["QT_QPA_PLATFORM"] = qt_platform()
    if pin_locale:
        os.environ["LC_ALL"] = "C.UTF-8"
        os.environ["LANG"] = "C.UTF-8"
    try:
        from PyQt6.QtCore import QEvent
        from PyQt6.QtWidgets import QApplication

        from chemvas.adapters.qt.renderer import Renderer
        from chemvas.ui.canvas_service_ports import (
            canvas_window_document_session_service,
        )
        from chemvas.ui.canvas_view import CanvasView

        existing = QApplication.instance()
        if existing is not None and not isinstance(existing, QApplication):
            raise RuntimeError(f"{command} requires a QApplication instance")
        application = existing or QApplication([f"chemvas-{command}"])
    finally:
        if previous_qt_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_qt_platform
        for name, value in previous_locale.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    restore_quit = application.quitOnLastWindowClosed()
    application.setQuitOnLastWindowClosed(False)
    canvas = None
    try:
        canvas = CanvasView(renderer=Renderer())
        service = canvas_window_document_session_service(canvas)
        service.apply_state(state)
        yield canvas, service
    finally:
        if canvas is not None:
            canvas.deleteLater()
            application.sendPostedEvents(canvas, QEvent.Type.DeferredDelete)
        application.setQuitOnLastWindowClosed(restore_quit)


__all__ = [
    "MAX_DOCUMENT_BYTES",
    "MAX_GRAPHICS_RECORDS",
    "graphics_record_count",
    "json_text",
    "offscreen_canvas",
    "qt_platform",
]
