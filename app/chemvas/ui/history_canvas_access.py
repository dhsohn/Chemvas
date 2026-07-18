from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from chemvas.core.history import (
    capture_history_transaction_for_command as _capture_history_transaction_for_command,
)
from chemvas.core.history import (
    release_history_transaction_for_command as _release_history_transaction_for_command,
)
from chemvas.core.history import (
    restore_history_transaction_for_command as _restore_history_transaction_for_command,
)
from chemvas.domain.transactions import RestoreOutcome
from chemvas.ui.atom_coords_access import atom_coords_3d_for_id
from chemvas.ui.bond_length_graphics_refresh import refresh_bond_length_graphics_for
from chemvas.ui.canvas_model_access import atom_for_id
from chemvas.ui.canvas_rotation_state import rotation_state_for
from chemvas.ui.canvas_service_ports import (
    history_atom_mutation_service_for,
    history_bond_mutation_service_for,
    history_hit_testing_service_for,
)
from chemvas.ui.canvas_smiles_input_state import set_last_smiles_input_for
from chemvas.ui.history_atom_position_restore import set_atom_positions_for_history
from chemvas.ui.move_access import move_atoms_for
from chemvas.ui.renderer_style_access import set_bond_length_for
from chemvas.ui.scene_item_access import restore_mark_from_state

_MISSING_RENDERER_STYLE = object()
_MISSING_CAPTURE_ATTRIBUTE = object()


def _add_move_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if callable(add_note):
            add_note(
                "Move rollback also encountered "
                f"{type(rollback_error).__name__}: {rollback_error}"
            )
    except BaseException:
        return


def _capture_optional_attribute(
    target: object,
    name: str,
    *,
    default: object,
) -> object:
    """Read an optional transaction root once without hiding property errors."""

    try:
        return getattr(target, name)
    except AttributeError:
        if (
            inspect.getattr_static(
                target,
                name,
                _MISSING_CAPTURE_ATTRIBUTE,
            )
            is not _MISSING_CAPTURE_ATTRIBUTE
        ):
            raise
        return default


@dataclass(frozen=True, slots=True)
class _RendererStyleAccess:
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], None]


def _class_attribute(target: object, name: str) -> object:
    for owner in type(target).__mro__:
        namespace = vars(owner)
        if name in namespace:
            return namespace[name]
    return _MISSING_CAPTURE_ATTRIBUTE


def _capture_renderer_style_access(
    renderer: object | None,
) -> _RendererStyleAccess | None:
    if renderer is None:
        return None

    # Read the live value exactly once.  Static inspection distinguishes a
    # genuinely optional attribute from AttributeError raised by a present
    # descriptor without causing a second descriptor access.
    style = _capture_optional_attribute(
        renderer,
        "style",
        default=_MISSING_RENDERER_STYLE,
    )
    if style is _MISSING_RENDERER_STYLE:
        return None

    static_style = inspect.getattr_static(
        renderer,
        "style",
        _MISSING_CAPTURE_ATTRIBUTE,
    )
    class_style = _class_attribute(renderer, "style")
    descriptor_getter = (
        inspect.getattr_static(
            type(class_style),
            "__get__",
            _MISSING_CAPTURE_ATTRIBUTE,
        )
        if class_style is not _MISSING_CAPTURE_ATTRIBUTE
        else _MISSING_CAPTURE_ATTRIBUTE
    )
    descriptor_setter = (
        inspect.getattr_static(
            type(class_style),
            "__set__",
            _MISSING_CAPTURE_ATTRIBUTE,
        )
        if class_style is not _MISSING_CAPTURE_ATTRIBUTE
        else _MISSING_CAPTURE_ATTRIBUTE
    )
    if (
        static_style is class_style
        and callable(descriptor_getter)
        and callable(descriptor_setter)
    ):
        # Preserve the exact descriptor ports that produced the savepoint.
        # A later class-level monkeypatch must not silently redirect rollback.
        def get_descriptor_style(
            _getter=descriptor_getter,
            _descriptor=class_style,
            _renderer=renderer,
        ) -> object:
            return _getter(_descriptor, _renderer, type(_renderer))

        def set_descriptor_style(
            value: object,
            _setter=descriptor_setter,
            _descriptor=class_style,
            _renderer=renderer,
        ) -> None:
            _setter(_descriptor, _renderer, value)

        return _RendererStyleAccess(
            value=style,
            getter=get_descriptor_style,
            setter=set_descriptor_style,
        )

    # Plain instance attributes (the production Renderer case) use the
    # captured attribute operators. Dynamic __getattr__ implementations still
    # retain normal getattr semantics for verification.
    getattribute = inspect.getattr_static(
        type(renderer),
        "__getattribute__",
        _MISSING_CAPTURE_ATTRIBUTE,
    )
    setattribute = inspect.getattr_static(
        type(renderer),
        "__setattr__",
        _MISSING_CAPTURE_ATTRIBUTE,
    )

    def get_plain_style(
        _renderer: Any = renderer,
        _getattribute=getattribute,
    ) -> object:
        if callable(_getattribute):
            try:
                return _getattribute(_renderer, "style")
            except AttributeError:
                # Preserve __getattr__ behavior for dynamically exposed ports.
                return _renderer.style
        return _renderer.style

    def set_plain_style(
        value: object,
        _renderer: Any = renderer,
        _setattribute=setattribute,
    ) -> None:
        if callable(_setattribute):
            _setattribute(_renderer, "style", value)
            return
        _renderer.style = value

    return _RendererStyleAccess(
        value=style,
        getter=get_plain_style,
        setter=set_plain_style,
    )


@dataclass(slots=True)
class _HistoryCanvasTransactionSnapshot:
    canvas_snapshot: Any
    renderer_style: _RendererStyleAccess | None

    def _restore_renderer_style_once(self) -> tuple[BaseException, ...]:
        if self.renderer_style is None:
            return ()
        try:
            self.renderer_style.setter(self.renderer_style.value)
        except BaseException as error:
            return (error,)
        return ()

    def _verify_renderer_style(self) -> tuple[BaseException, ...]:
        if self.renderer_style is None:
            return ()
        try:
            restored_style = self.renderer_style.getter()
            if restored_style is not self.renderer_style.value:
                raise RuntimeError(
                    "renderer style setter did not restore the captured object"
                )
        except BaseException as error:
            return (error,)
        return ()

    def _verify_canvas_snapshot(self) -> tuple[BaseException, ...]:
        verify = getattr(self.canvas_snapshot, "_verify_exact_authorities", None)
        if not callable(verify):
            return ()
        try:
            return tuple(verify())
        except BaseException as error:
            return (error,)

    def verify_exact(self) -> tuple[BaseException, ...]:
        """Verify canvas/style globally, with canvas final after style getter."""

        return (
            *self._verify_canvas_snapshot(),
            *self._verify_renderer_style(),
            *self._verify_canvas_snapshot(),
        )

    def restore_with_result(self) -> RestoreOutcome:
        accumulated_errors: list[BaseException] = []
        for attempt in range(2):
            attempt_errors: list[BaseException] = []
            canvas_authoritative = False

            def restore_canvas(
                _attempt_errors: list[BaseException] = attempt_errors,
            ) -> None:
                nonlocal canvas_authoritative
                try:
                    result = self.canvas_snapshot.restore_with_result()
                except BaseException as error:
                    _attempt_errors.append(error)
                    return
                _attempt_errors.extend(result.errors)
                canvas_authoritative = result.authoritative
                if not result.authoritative and not result.errors:
                    _attempt_errors.append(
                        RuntimeError("canvas snapshot restore was not authoritative")
                    )

            if attempt == 0:
                # The first canvas restore owns the one-shot history/rect
                # publication. Renderer style must be the final writer after it.
                restore_canvas()
                attempt_errors.extend(self._restore_renderer_style_once())
            else:
                # Reverse the independent authorities on retry. The canvas
                # snapshot suppresses its already-consumed publication.
                attempt_errors.extend(self._restore_renderer_style_once())
                restore_canvas()
            # The style getter is an untrusted descriptor too. It can return
            # the captured object while re-mutating canvas state, so canvas
            # must be the final independently verified authority.
            verification_errors = list(self.verify_exact())
            if canvas_authoritative and not verification_errors:
                return RestoreOutcome(
                    authoritative=True,
                    fallback_to_inverse=False,
                    errors=tuple((*accumulated_errors, *attempt_errors)),
                )
            attempt_errors.extend(verification_errors)
            accumulated_errors.extend(attempt_errors)

        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=tuple(accumulated_errors),
        )

    def restore(self) -> list[BaseException]:
        return list(self.restore_with_result().errors)

    def release(self) -> None:
        release = getattr(self.canvas_snapshot, "release", None)
        if callable(release):
            release()


def capture_history_transaction_for_history(
    canvas,
    *,
    history_service=None,
    guard_scene_rect: bool = True,
):
    # Lazy import keeps the core history port free of an eager dependency on
    # the scene/history command graph (and therefore avoids an import cycle).
    from chemvas.ui.canvas_delete_transaction import CanvasDeleteTransactionSnapshot

    renderer = _capture_optional_attribute(
        canvas,
        "renderer",
        default=None,
    )
    renderer_style = _capture_renderer_style_access(renderer)
    canvas_snapshot = CanvasDeleteTransactionSnapshot.capture(
        canvas,
        history_service=history_service,
        guard_scene_rect=guard_scene_rect,
    )
    return _HistoryCanvasTransactionSnapshot(
        canvas_snapshot=canvas_snapshot,
        renderer_style=renderer_style,
    )


def restore_history_transaction_for_history(
    canvas,
    snapshot,
) -> RestoreOutcome:
    del canvas
    try:
        return snapshot.restore_with_result()
    except BaseException as rollback_error:
        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=(rollback_error,),
        )


def release_history_transaction_for_history(canvas, snapshot) -> None:
    del canvas
    release = getattr(snapshot, "release", None)
    if callable(release):
        release()


def verify_history_transaction_for_history(canvas, snapshot) -> None:
    """Require every authority in a frozen runtime snapshot to remain exact."""

    del canvas
    verify = getattr(snapshot, "verify_exact", None)
    if not callable(verify):
        raise RuntimeError("history transaction has no exact verification port")
    errors = tuple(verify())
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup(
            "history publication changed its frozen canvas after-state",
            list(errors),
        )


def move_atoms_for_history(
    canvas,
    atom_ids: set[int],
    dx: float,
    dy: float,
    *,
    bond_ids: set[int] | None = None,
    redraw_bond_ids: set[int] | None = None,
    update_selection: bool = True,
) -> None:
    transaction = _capture_history_transaction_for_command(canvas)
    before_positions: dict[int, tuple[float, float]] = {}
    before_coords_3d: dict[int, tuple[float, float, float]] = {}
    try:
        # Position and 3D-coordinate properties are live preflight ports. They
        # belong to the same exact transaction as the move so a fail-before
        # descriptor still publishes authoritative rollback to history stacks.
        for atom_id in atom_ids:
            atom = atom_for_id(canvas, atom_id)
            if atom is None:
                continue
            before_positions[atom_id] = (atom.x, atom.y)
            coords_3d = atom_coords_3d_for_id(canvas, atom_id)
            if coords_3d is not None:
                before_coords_3d[atom_id] = coords_3d
        move_atoms_for(
            canvas,
            atom_ids,
            dx,
            dy,
            bond_ids=bond_ids,
            redraw_bond_ids=redraw_bond_ids,
            update_selection=update_selection,
        )
        _release_history_transaction_for_command(canvas, transaction)
    except BaseException as original_error:
        # The move controller mutates atoms one at a time before redrawing
        # dependent graphics. Restore absolute positions instead of applying
        # the inverse delta to every requested atom: some atoms may not have
        # been reached when the original call failed.
        try:
            set_atom_positions_for_history(
                canvas,
                before_positions,
                update_selection=update_selection,
                coords_3d=before_coords_3d or None,
            )
        except BaseException as rollback_error:
            _add_move_rollback_note(original_error, rollback_error)
        # The canonical setter is itself a multi-atom operation and can stop
        # after restoring only an early atom. The exact transaction snapshot
        # restores all model/3D/graphics/selection state independently of that
        # partial compensation while retaining the primary exception.
        restore_result = _restore_history_transaction_for_command(
            canvas,
            transaction,
            original_error,
        )
        for exact_restore_error in restore_result.errors:
            _add_move_rollback_note(original_error, exact_restore_error)
        raise


def restore_projection_state_for_history(
    canvas,
    projection_center_3d: tuple[float, float, float] | None,
    projection_anchor_2d: tuple[float, float] | None,
) -> None:
    rotation_state = rotation_state_for(canvas)
    rotation_state.projection_center_3d = projection_center_3d
    rotation_state.projection_anchor_2d = projection_anchor_2d


def set_ring_polygons_for_history(
    canvas,
    ring_items: list,
    polygons: list[list[tuple[float, float]]],
) -> None:
    for ring_item, points in zip(ring_items, polygons, strict=False):
        if ring_item is None:
            continue
        polygon = QPolygonF([QPointF(x, y) for x, y in points])
        ring_item.setPolygon(polygon)


def set_last_smiles_input_for_history(canvas, value: str | None) -> None:
    set_last_smiles_input_for(canvas, value)


def restore_bond_length_for_history(canvas, length_px: float) -> None:
    set_bond_length_for(canvas, length_px)
    refresh_bond_length_graphics_for(canvas)
    history_hit_testing_service_for(canvas).mark_spatial_index_dirty()


def remove_atom_for_history(canvas, atom_id: int, *, remove_marks: bool = True) -> None:
    history_atom_mutation_service_for(canvas).remove_atom_only(
        atom_id,
        remove_marks=remove_marks,
    )


def restore_atom_from_state_for_history(canvas, atom_id: int, state: dict) -> None:
    history_atom_mutation_service_for(canvas).restore_atom_from_state(atom_id, state)


def apply_atom_color_for_history(canvas, atom_id: int, color) -> None:
    history_atom_mutation_service_for(canvas).apply_atom_color(atom_id, color)


def restore_mark_from_state_for_history(canvas, mark_state: dict):
    return restore_mark_from_state(canvas, mark_state)


def restore_bond_from_state_for_history(canvas, bond_id: int, bond_state: dict) -> None:
    history_bond_mutation_service_for(canvas).restore_bond_from_state(
        bond_id, bond_state
    )


def remove_bond_for_history(canvas, bond_id: int) -> None:
    history_bond_mutation_service_for(canvas).remove_bond_by_id(bond_id)


def trim_bonds_for_history(canvas, length: int) -> None:
    history_bond_mutation_service_for(canvas).trim_bonds_to_length(length)


__all__ = [
    "apply_atom_color_for_history",
    "capture_history_transaction_for_history",
    "move_atoms_for_history",
    "release_history_transaction_for_history",
    "remove_atom_for_history",
    "remove_bond_for_history",
    "restore_atom_from_state_for_history",
    "restore_bond_from_state_for_history",
    "restore_bond_length_for_history",
    "restore_history_transaction_for_history",
    "restore_mark_from_state_for_history",
    "restore_projection_state_for_history",
    "set_atom_positions_for_history",
    "set_last_smiles_input_for_history",
    "set_ring_polygons_for_history",
    "trim_bonds_for_history",
    "verify_history_transaction_for_history",
]
