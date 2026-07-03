from __future__ import annotations

from ui.canvas_service_ports import scene_reset_service_for_access


def clear_scene_for(canvas) -> None:
    scene_reset_service_for_access(canvas).clear_scene()


__all__ = ["clear_scene_for"]
