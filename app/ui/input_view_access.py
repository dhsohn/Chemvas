from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTransform
from PyQt6.QtWidgets import QGraphicsView

from ui.canvas_callback_state import callback_state_for
from ui.canvas_hover_state import hover_state_for
from ui.input_view_state import input_view_state_for
from ui.scene_rect_snapshot import (
    SceneRectStateSnapshot,
    ViewSceneRectStateSnapshot,
    set_explicit_scene_rect,
    set_explicit_view_scene_rect,
)
from ui.selection_info_state import selection_info_state_for

# View magnification limits and the per-step multiplier shared by the toolbar
# buttons and the Ctrl+= / Ctrl+- shortcuts. Ctrl+wheel uses a finer factor.
ZOOM_MIN = 0.2
ZOOM_MAX = 5.0
ZOOM_STEP = 1.25
_MISSING_CAPTURE_ATTRIBUTE = object()


def _capture_optional_attribute(target: object, name: str) -> object:
    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(target, name, _MISSING_CAPTURE_ATTRIBUTE)
            is not _MISSING_CAPTURE_ATTRIBUTE
        ):
            raise
        return _MISSING_CAPTURE_ATTRIBUTE


def _add_scene_rect_recovery_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        original_error.add_note(
            "Scene/view rect rollback also failed: "
            f"{type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        return


@dataclass(slots=True)
class CanvasSceneRectStateSnapshot:
    canvas: object
    scene: object | None
    scene_state: SceneRectStateSnapshot | None
    view_state: ViewSceneRectStateSnapshot | None
    view_scene_rect_getter: object
    view_set_scene_rect_setter: object
    active: bool = True
    recovery_errors: list[BaseException] = field(default_factory=list)

    @classmethod
    def capture(cls, canvas) -> CanvasSceneRectStateSnapshot:
        scene_getter = _capture_optional_attribute(canvas, "scene")
        scene = scene_getter() if callable(scene_getter) else None
        scene_state = None
        scene_rect = _capture_optional_attribute(scene, "sceneRect")
        set_scene_rect = _capture_optional_attribute(scene, "setSceneRect")
        if scene is not None and callable(scene_rect) and callable(set_scene_rect):
            scene_state = SceneRectStateSnapshot.capture(
                scene,
                scene_rect_getter=scene_rect,
                set_scene_rect_setter=set_scene_rect,
            )
        view_state = None
        view_scene_rect = _capture_optional_attribute(canvas, "sceneRect")
        view_set_scene_rect = _capture_optional_attribute(canvas, "setSceneRect")
        if callable(view_scene_rect) and callable(view_set_scene_rect):
            view_state = ViewSceneRectStateSnapshot.capture(
                canvas,
                scene_rect_getter=view_scene_rect,
                set_scene_rect_setter=view_set_scene_rect,
            )
        return cls(
            canvas=canvas,
            scene=scene,
            scene_state=scene_state,
            view_state=view_state,
            view_scene_rect_getter=view_scene_rect,
            view_set_scene_rect_setter=view_set_scene_rect,
        )

    @staticmethod
    def _restore_with_retry(snapshot) -> tuple[BaseException, ...]:
        recovery_errors = getattr(snapshot, "recovery_errors", None)
        prior_count = (
            len(recovery_errors) if isinstance(recovery_errors, list) else 0
        )
        try:
            snapshot.restore()
        except BaseException as error:
            return (error,)
        if isinstance(recovery_errors, list):
            return tuple(recovery_errors[prior_count:])
        return ()

    def restore(self) -> None:
        if not self.active:
            return
        errors: list[BaseException] = []
        # An inherited view reports its scene's live rect, so restore the scene
        # first and then verify the view's inherited/explicit value.
        for snapshot in (self.scene_state, self.view_state):
            if snapshot is None:
                continue
            attempt_errors = self._restore_with_retry(snapshot)
            if snapshot.active:
                errors.extend(attempt_errors)
            else:
                self.recovery_errors.extend(attempt_errors)
        if errors:
            raise BaseExceptionGroup(
                "scene/view rect rollback failed",
                [*self.recovery_errors, *errors],
            )
        self.active = False

    def release(self) -> None:
        if self.view_state is not None:
            self.view_state.release()
        if self.scene_state is not None:
            self.scene_state.release()
        self.active = False


def shortcut_modifiers_for(event) -> Qt.KeyboardModifier:
    mask = (
        Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
    )
    return event.modifiers() & mask


def reset_view_transform_for(canvas) -> None:
    state = input_view_state_for(canvas)
    state.base_transform = QTransform()
    state.perspective_shear = 0.0
    state.perspective_scale_y = 1.0
    # Keep the current magnification: scrolling and gestures clear the
    # transient rotation/perspective but must not snap zoom back to 100%.
    update_view_transform_for(canvas)


def update_view_transform_for(canvas) -> None:
    state = input_view_state_for(canvas)
    transform = QTransform(state.base_transform)
    if state.zoom != 1.0:
        transform.scale(state.zoom, state.zoom)
    if state.perspective_shear or state.perspective_scale_y != 1.0:
        transform.shear(state.perspective_shear, 0.0)
        transform.scale(1.0, state.perspective_scale_y)
    canvas.setTransform(transform)


def rotate_view_for(canvas, angle_degrees: float) -> None:
    if not angle_degrees:
        return
    state = input_view_state_for(canvas)
    transform = QTransform(state.base_transform)
    transform.rotate(angle_degrees)
    state.base_transform = transform
    update_view_transform_for(canvas)


def touch_interaction_for(canvas) -> None:
    selection_info_state_for(canvas).last_interaction_time = time.monotonic()


def viewport_center_scene_pos_for(canvas):
    return canvas.mapToScene(canvas.viewport().rect().center())


def focused_scene_item_for(canvas):
    scene = getattr(canvas, "scene", None)
    if not callable(scene):
        return None
    return scene().focusItem()


def focus_canvas_for(canvas, reason) -> None:
    canvas.setFocus(reason)


def set_scene_rect_for(canvas, rect) -> None:
    snapshot = CanvasSceneRectStateSnapshot.capture(canvas)
    try:
        if snapshot.scene is not None and snapshot.scene_state is not None:
            set_explicit_scene_rect(
                snapshot.scene,
                rect,
                scene_rect_getter=snapshot.scene_state.scene_rect_getter,
                set_scene_rect_setter=snapshot.scene_state.set_scene_rect_setter,
            )
        if snapshot.view_state is not None:
            set_explicit_view_scene_rect(
                canvas,
                rect,
                scene_rect_getter=snapshot.view_state.scene_rect_getter,
                set_scene_rect_setter=snapshot.view_state.set_scene_rect_setter,
            )
        elif callable(snapshot.view_set_scene_rect_setter):
            # Preserve the narrow legacy fallback for test doubles that expose
            # only a raw setter. The bound port captured before mutation is
            # still authoritative; live views take the verified branch above.
            snapshot.view_set_scene_rect_setter(rect)
        snapshot.release()
    except BaseException as original_error:
        try:
            snapshot.restore()
        except BaseException as rollback_error:
            _add_scene_rect_recovery_note(original_error, rollback_error)
        else:
            for recovered_error in snapshot.recovery_errors:
                _add_scene_rect_recovery_note(original_error, recovered_error)
        raise


def update_viewport_for(canvas) -> None:
    canvas.viewport().update()


def set_focused_scene_item_for(canvas, item) -> None:
    scene = getattr(canvas, "scene", None)
    if callable(scene):
        scene().setFocusItem(item)


def scene_pos_from_global_pos_for(canvas, global_pos):
    viewport = canvas.viewport()
    viewport_pos = viewport.mapFromGlobal(global_pos)
    if not viewport.rect().contains(viewport_pos):
        return None
    return canvas.mapToScene(viewport_pos)


def global_pos_from_event_for(canvas, event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    if hasattr(event, "globalPos"):
        return event.globalPos()
    return canvas.viewport().mapToGlobal(event.position().toPoint())


def device_pixel_ratio_for(canvas) -> float:
    return float(canvas.devicePixelRatioF())


def scroll_view_by_for(canvas, dx: int, dy: int) -> bool:
    if not dx and not dy:
        return False
    horizontal = canvas.horizontalScrollBar()
    vertical = canvas.verticalScrollBar()
    horizontal.setValue(horizontal.value() + dx)
    vertical.setValue(vertical.value() + dy)
    return True


def zoom_factor_for(canvas) -> float:
    return float(input_view_state_for(canvas).zoom)


def zoom_percent_for(canvas) -> int:
    return max(1, round(zoom_factor_for(canvas) * 100))


def _notify_zoom_changed_for(canvas) -> None:
    callback = callback_state_for(canvas).zoom
    if callback is not None:
        callback(zoom_percent_for(canvas))


def set_zoom_for(canvas, factor: float, *, under_mouse: bool = False) -> float:
    state = input_view_state_for(canvas)
    factor = max(ZOOM_MIN, min(ZOOM_MAX, float(factor)))
    state.zoom = factor
    if under_mouse:
        previous_anchor = canvas.transformationAnchor()
        canvas.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        update_view_transform_for(canvas)
        canvas.setTransformationAnchor(previous_anchor)
    else:
        # The view keeps AnchorViewCenter, so setTransform holds the viewport
        # centre point steady across the magnification change.
        update_view_transform_for(canvas)
    _notify_zoom_changed_for(canvas)
    return factor


def zoom_in_for(canvas, *, step: float = ZOOM_STEP, under_mouse: bool = False) -> float:
    return set_zoom_for(canvas, zoom_factor_for(canvas) * step, under_mouse=under_mouse)


def zoom_out_for(canvas, *, step: float = ZOOM_STEP, under_mouse: bool = False) -> float:
    return set_zoom_for(canvas, zoom_factor_for(canvas) / step, under_mouse=under_mouse)


def reset_zoom_for(canvas) -> float:
    return set_zoom_for(canvas, 1.0)


def fit_canvas_to_view_for(canvas, *, margin: float = 0.92) -> float:
    from ui.sheet_setup_access import sheet_rect_for

    sheet = sheet_rect_for(canvas)
    viewport = canvas.viewport().rect()
    if sheet.width() <= 0 or sheet.height() <= 0 or viewport.width() <= 0 or viewport.height() <= 0:
        return zoom_factor_for(canvas)
    factor = min(viewport.width() / sheet.width(), viewport.height() / sheet.height()) * margin
    set_zoom_for(canvas, factor)
    canvas.centerOn(sheet.center())
    return zoom_factor_for(canvas)


def should_override_chemdraw_shortcut_for(canvas, event) -> bool:
    modifiers = shortcut_modifiers_for(event)
    if modifiers not in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
        return False
    text = event.text()
    if hover_state_for(canvas).atom_id is not None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return True
        return text in {
            "+",
            "-",
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "a",
            "b",
            "c",
            "d",
            "e",
            "f",
            "h",
            "i",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "q",
            "r",
            "s",
            "u",
            "v",
            "w",
            "x",
            "z",
            "A",
            "B",
            "C",
            "E",
            "F",
            "H",
            "K",
            "L",
            "M",
            "N",
            "O",
            "P",
            "Q",
            "S",
            "Y",
            "Z",
        }
    if hover_state_for(canvas).bond_id is not None:
        return text in {
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "0",
            "a",
            "b",
            "c",
            "d",
            "h",
            "l",
            "r",
            "w",
            "B",
            "D",
            "H",
        }
    return False


__all__ = [
    "ZOOM_MAX",
    "ZOOM_MIN",
    "ZOOM_STEP",
    "CanvasSceneRectStateSnapshot",
    "device_pixel_ratio_for",
    "fit_canvas_to_view_for",
    "focus_canvas_for",
    "focused_scene_item_for",
    "global_pos_from_event_for",
    "reset_view_transform_for",
    "reset_zoom_for",
    "rotate_view_for",
    "scene_pos_from_global_pos_for",
    "scroll_view_by_for",
    "set_focused_scene_item_for",
    "set_scene_rect_for",
    "set_zoom_for",
    "shortcut_modifiers_for",
    "should_override_chemdraw_shortcut_for",
    "touch_interaction_for",
    "update_view_transform_for",
    "update_viewport_for",
    "viewport_center_scene_pos_for",
    "zoom_factor_for",
    "zoom_in_for",
    "zoom_out_for",
    "zoom_percent_for",
]
