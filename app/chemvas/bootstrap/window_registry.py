"""Open a new top-level document window through the composition root."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from chemvas.shell.window_registry import register_window

if TYPE_CHECKING:
    from collections.abc import Callable


def open_new_window(
    reference_window: Any | None = None,
    *,
    window_factory: Callable[[], Any] | None = None,
    inherit_settings: bool = False,
) -> Any:
    initialize_window: Callable[[Any], None] | None = None
    if window_factory is None:
        from chemvas.bootstrap.main_window import (
            build_main_window,
            initialize_main_window_document,
        )

        window_factory = build_main_window
        if inherit_settings:
            initialize_window = partial(
                initialize_main_window_document, template_window=reference_window
            )
        else:
            initialize_window = initialize_main_window_document
    window = window_factory()
    register_window(window)
    if initialize_window is not None:
        initialize_window(window)
    if reference_window is not None:
        _cascade(window, reference_window)
    window.show()
    return window


def _cascade(window: Any, reference_window: Any, *, offset: int = 32) -> None:
    reference_geometry = reference_window.geometry()
    window.move(reference_geometry.x() + offset, reference_geometry.y() + offset)


__all__ = ["open_new_window"]
