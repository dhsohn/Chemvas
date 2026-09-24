from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtGui import QTransform


@dataclass(slots=True)
class InputViewState:
    base_transform: QTransform = field(default_factory=QTransform)
    perspective_shear: float = 0.0
    perspective_scale_y: float = 1.0
    # Persistent view magnification (1.0 == 100%). Survives the transform
    # resets that scrolling and native gestures trigger, unlike the transient
    # rotation/perspective tracked above.
    zoom: float = 1.0


__all__ = ["InputViewState"]
