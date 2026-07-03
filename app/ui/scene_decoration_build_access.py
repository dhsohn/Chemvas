from __future__ import annotations

from ui.canvas_service_ports import scene_decoration_build_service_for_access


def _service_method(canvas, name: str):
    try:
        service = scene_decoration_build_service_for_access(canvas)
    except AttributeError:
        service = None
    method = getattr(service, name, None)
    return method if callable(method) else None


def build_arrow_item_for(canvas, start, end, kind: str):
    method = _service_method(canvas, "build_arrow_item")
    if method is not None:
        return method(start, end, kind)
    return None


def ts_bracket_path_for(canvas, rect, bracket_kind: str | None = None):
    method = _service_method(canvas, "ts_bracket_path")
    if method is not None:
        if bracket_kind is not None:
            try:
                return method(rect, bracket_kind)
            except TypeError:
                return method(rect)
        return method(rect)
    return None


def build_ts_bracket_item_for(canvas, rect, bracket_kind: str | None = None):
    method = _service_method(canvas, "build_ts_bracket_item")
    if method is not None:
        if bracket_kind is not None:
            try:
                return method(rect, bracket_kind)
            except TypeError:
                return method(rect)
        return method(rect)
    return None


def build_shape_item_for(canvas, rect, shape_kind=None, stroke_style=None, *, fill=None):
    method = _service_method(canvas, "build_shape_item")
    if method is None:
        return None
    return method(rect, shape_kind or "circle", stroke_style or "solid", fill=fill)


def build_orbital_items_for(canvas, center, kind: str):
    method = _service_method(canvas, "build_orbital_items")
    if method is not None:
        return method(center, kind)
    return []


def add_arrow_head_for(canvas, path, start, end, double: bool) -> None:
    method = _service_method(canvas, "add_arrow_head")
    if method is not None:
        method(path, start, end, double)
        return


__all__ = [
    "add_arrow_head_for",
    "build_arrow_item_for",
    "build_orbital_items_for",
    "build_shape_item_for",
    "build_ts_bracket_item_for",
    "ts_bracket_path_for",
]
