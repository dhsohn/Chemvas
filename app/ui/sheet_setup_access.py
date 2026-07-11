from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from types import MemberDescriptorType
from typing import Any, Protocol, cast

from PyQt6.QtCore import QRectF

from ui.input_view_access import (
    CanvasSceneRectStateSnapshot,
    set_scene_rect_for,
    update_viewport_for,
)
from ui.sheet_setup_logic import (
    SHEET_MARGIN_PX,
    sheet_dimensions_px,
)
from ui.sheet_setup_state import (
    set_sheet_setup_state_for,
    sheet_setup_state_for,
    sheet_setup_values_for,
)

_MISSING_ATTRIBUTE = object()


class _SheetSetupStateLike(Protocol):
    size_name: object
    orientation: object
    rect: object


def _class_attribute(target: object, name: str) -> object:
    for owner in type(target).__mro__:
        namespace = vars(owner)
        if name in namespace:
            return namespace[name]
    return _MISSING_ATTRIBUTE


@dataclass(frozen=True, slots=True)
class _OptionalAttributeSnapshot:
    target: object
    name: str
    present: bool
    value: object
    getter: Callable[[], object]
    setter: Callable[[object], object]
    deleter: Callable[[], object]
    identity: bool
    class_attribute_present: bool

    @classmethod
    def capture(
        cls,
        target: object,
        name: str,
        *,
        identity: bool = True,
    ) -> _OptionalAttributeSnapshot:
        static_value = inspect.getattr_static(
            target,
            name,
            _MISSING_ATTRIBUTE,
        )
        class_value = _class_attribute(target, name)
        descriptor_getter = (
            inspect.getattr_static(
                type(class_value),
                "__get__",
                _MISSING_ATTRIBUTE,
            )
            if class_value is not _MISSING_ATTRIBUTE
            else _MISSING_ATTRIBUTE
        )
        descriptor_setter = (
            inspect.getattr_static(
                type(class_value),
                "__set__",
                _MISSING_ATTRIBUTE,
            )
            if class_value is not _MISSING_ATTRIBUTE
            else _MISSING_ATTRIBUTE
        )
        get_value: Callable[[], object]
        set_value: Callable[[object], object]
        if (
            static_value is class_value
            and callable(descriptor_getter)
            and callable(descriptor_setter)
        ):

            def descriptor_get_value(
                _getter=descriptor_getter,
                _descriptor=class_value,
                _target=target,
            ) -> object:
                return _getter(_descriptor, _target, type(_target))

            def descriptor_set_value(
                value: object,
                _setter=descriptor_setter,
                _descriptor=class_value,
                _target=target,
            ) -> object:
                return _setter(_descriptor, _target, value)

            get_value = descriptor_get_value
            set_value = descriptor_set_value

        else:
            getattribute = inspect.getattr_static(
                type(target),
                "__getattribute__",
            )
            setattribute = inspect.getattr_static(
                type(target),
                "__setattr__",
            )

            def attribute_get_value(
                _getattribute=getattribute,
                _target=target,
                _name=name,
            ) -> object:
                return _getattribute(_target, _name)

            def attribute_set_value(
                value: object,
                _setattribute=setattribute,
                _target=target,
                _name=name,
            ) -> object:
                return _setattribute(_target, _name, value)

            get_value = attribute_get_value
            set_value = attribute_set_value

        delattribute = inspect.getattr_static(type(target), "__delattr__")

        def delete_value(
            _delattribute=delattribute,
            _target=target,
            _name=name,
        ) -> object:
            return _delattribute(_target, _name)

        present = static_value is not _MISSING_ATTRIBUTE
        value = get_value() if present else _MISSING_ATTRIBUTE
        return cls(
            target=target,
            name=name,
            present=present,
            value=value,
            getter=get_value,
            setter=set_value,
            deleter=delete_value,
            identity=identity,
            class_attribute_present=class_value is not _MISSING_ATTRIBUTE,
        )

    def _current(self) -> tuple[bool, object]:
        try:
            return True, self.getter()
        except AttributeError:
            # A captured class descriptor exists even when its live getter
            # raises AttributeError internally; that is a port failure, not an
            # absent optional attribute.
            if self.class_attribute_present:
                raise
            if (
                inspect.getattr_static(
                    self.target,
                    self.name,
                    _MISSING_ATTRIBUTE,
                )
                is not _MISSING_ATTRIBUTE
            ):
                raise
            return False, _MISSING_ATTRIBUTE

    def restore(self) -> None:
        if self.present:
            self.setter(self.value)
            return
        current_present, _current_value = self._current()
        if current_present:
            self.deleter()

    def matches(self) -> bool:
        current_present, current_value = self._current()
        if current_present is not self.present:
            return False
        if not self.present:
            return True
        if current_value is self.value:
            return True
        if self.identity:
            return False
        try:
            return bool(current_value == self.value)
        except BaseException:
            return False


@dataclass(frozen=True, slots=True)
class _RawSheetFieldsBaseline:
    state: object
    namespace: dict[str, object] | None
    namespace_items: tuple[tuple[str, object], ...]
    slot_values: tuple[tuple[MemberDescriptorType, object], ...]
    rect_values: tuple[tuple[QRectF, QRectF], ...]

    @classmethod
    def capture(cls, state: object | None) -> _RawSheetFieldsBaseline | None:
        if state is None:
            return None
        try:
            namespace_value = object.__getattribute__(state, "__dict__")
        except (AttributeError, TypeError):
            namespace = None
        else:
            namespace = namespace_value if isinstance(namespace_value, dict) else None
        namespace_items = (
            tuple(
                (key, dict.__getitem__(namespace, key))
                for key in tuple(dict.__iter__(namespace))
            )
            if namespace is not None
            else ()
        )
        slot_values: list[tuple[MemberDescriptorType, object]] = []
        for name in ("size_name", "orientation", "rect"):
            descriptor = _class_attribute(state, name)
            if isinstance(descriptor, MemberDescriptorType):
                slot_values.append((descriptor, descriptor.__get__(state, type(state))))
        rect_values: list[tuple[QRectF, QRectF]] = []
        seen_rects: set[int] = set()
        for value in (
            *(value for _name, value in namespace_items),
            *(value for _descriptor, value in slot_values),
        ):
            if isinstance(value, QRectF) and id(value) not in seen_rects:
                seen_rects.add(id(value))
                rect_values.append((value, QRectF(value)))
        return cls(
            state=state,
            namespace=namespace,
            namespace_items=namespace_items,
            slot_values=tuple(slot_values),
            rect_values=tuple(rect_values),
        )

    def restore(self) -> None:
        if self.namespace is not None:
            dict.clear(self.namespace)
            dict.update(self.namespace, self.namespace_items)
        for descriptor, value in self.slot_values:
            descriptor.__set__(self.state, value)
        for rect, value in self.rect_values:
            QRectF.setRect(
                rect,
                value.x(),
                value.y(),
                value.width(),
                value.height(),
            )


@dataclass(frozen=True, slots=True)
class _RawSheetCaptureBaseline:
    roots: tuple[tuple[dict[str, object], str, bool, object], ...]
    slot_roots: tuple[tuple[object, MemberDescriptorType, object], ...]
    states: tuple[_RawSheetFieldsBaseline, ...]

    @staticmethod
    def _namespace(target: object) -> dict[str, object] | None:
        try:
            namespace = object.__getattribute__(target, "__dict__")
        except (AttributeError, TypeError):
            return None
        return namespace if isinstance(namespace, dict) else None

    @staticmethod
    def _looks_like_sheet_state(target: object) -> bool:
        return all(
            inspect.getattr_static(target, name, _MISSING_ATTRIBUTE)
            is not _MISSING_ATTRIBUTE
            for name in ("size_name", "orientation", "rect")
        )

    @classmethod
    def capture(cls, canvas: object) -> _RawSheetCaptureBaseline:
        owners: list[object] = [canvas]
        namespaces: list[dict[str, object]] = []
        canvas_namespace = cls._namespace(canvas)
        if canvas_namespace is not None:
            namespaces.append(canvas_namespace)
            runtime_state = dict.get(canvas_namespace, "runtime_state")
            if runtime_state is not None:
                owners.append(runtime_state)
            runtime_namespace = (
                cls._namespace(runtime_state) if runtime_state is not None else None
            )
            if runtime_namespace is not None:
                namespaces.append(runtime_namespace)

        roots: list[tuple[dict[str, object], str, bool, object]] = []
        candidates: list[object] = []
        seen_candidates: set[int] = set()
        slot_roots: list[tuple[object, MemberDescriptorType, object]] = []
        seen_slot_roots: set[tuple[int, int]] = set()
        fixed_names = {
            "runtime_state",
            "sheet_setup_state",
            "sheet_size",
            "sheet_orientation",
        }
        for namespace in namespaces:
            names = set(fixed_names)
            for name, value in tuple(dict.items(namespace)):
                if cls._looks_like_sheet_state(value):
                    names.add(name)
                    if id(value) not in seen_candidates:
                        seen_candidates.add(id(value))
                        candidates.append(value)
            for name in names:
                present = dict.__contains__(namespace, name)
                value = (
                    dict.__getitem__(namespace, name) if present else _MISSING_ATTRIBUTE
                )
                roots.append((namespace, name, present, value))
                if (
                    present
                    and cls._looks_like_sheet_state(value)
                    and id(value) not in seen_candidates
                ):
                    seen_candidates.add(id(value))
                    candidates.append(value)

        # Slots do not appear in ``__dict__``. Member descriptors are raw,
        # callback-free backing roots, so include fixed roots and any slot that
        # directly owns a sheet-state-like object (for example ``_state``).
        owner_index = 0
        while owner_index < len(owners):
            owner = owners[owner_index]
            owner_index += 1
            for owner_type in type(owner).__mro__:
                for name, descriptor in vars(owner_type).items():
                    if not isinstance(descriptor, MemberDescriptorType):
                        continue
                    key = (id(owner), id(descriptor))
                    if key in seen_slot_roots:
                        continue
                    try:
                        value = descriptor.__get__(owner, type(owner))
                    except AttributeError:
                        continue
                    if name not in fixed_names and not cls._looks_like_sheet_state(
                        value
                    ):
                        continue
                    seen_slot_roots.add(key)
                    slot_roots.append((owner, descriptor, value))
                    if name == "runtime_state" and value is not None:
                        owners.append(value)
                        runtime_namespace = cls._namespace(value)
                        if runtime_namespace is not None and all(
                            runtime_namespace is not existing for existing in namespaces
                        ):
                            namespaces.append(runtime_namespace)
                            runtime_names = set(fixed_names)
                            for runtime_name, runtime_value in tuple(
                                dict.items(runtime_namespace)
                            ):
                                if cls._looks_like_sheet_state(runtime_value):
                                    runtime_names.add(runtime_name)
                                    if id(runtime_value) not in seen_candidates:
                                        seen_candidates.add(id(runtime_value))
                                        candidates.append(runtime_value)
                            for runtime_name in runtime_names:
                                present = dict.__contains__(
                                    runtime_namespace,
                                    runtime_name,
                                )
                                roots.append(
                                    (
                                        runtime_namespace,
                                        runtime_name,
                                        present,
                                        dict.__getitem__(
                                            runtime_namespace,
                                            runtime_name,
                                        )
                                        if present
                                        else _MISSING_ATTRIBUTE,
                                    )
                                )
                    if (
                        cls._looks_like_sheet_state(value)
                        and id(value) not in seen_candidates
                    ):
                        seen_candidates.add(id(value))
                        candidates.append(value)

        states = tuple(
            baseline
            for candidate in candidates
            if (baseline := _RawSheetFieldsBaseline.capture(candidate)) is not None
        )
        return cls(
            roots=tuple(roots),
            slot_roots=tuple(slot_roots),
            states=states,
        )

    def restore(self) -> None:
        for baseline in self.states:
            baseline.restore()
        for namespace, name, present, value in self.roots:
            if present:
                dict.__setitem__(namespace, name, value)
            else:
                dict.pop(namespace, name, None)
        for owner, descriptor, value in self.slot_roots:
            descriptor.__set__(owner, value)
        # A replaced backing root may have poisoned the captured state before
        # being detached.  Close on the original state contents after roots.
        for baseline in self.states:
            baseline.restore()


@dataclass(slots=True)
class _SheetSetupStateSnapshot:
    state: _SheetSetupStateLike | None
    state_fields: tuple[_OptionalAttributeSnapshot, ...]
    rect_object: object
    rect_value: QRectF | None
    state_attributes: tuple[_OptionalAttributeSnapshot, ...]
    compatibility_attributes: tuple[_OptionalAttributeSnapshot, ...]
    active: bool = True
    recovery_errors: list[BaseException] = field(default_factory=list)

    @staticmethod
    def _unwind_rect_after_capture_failure(
        original_error: BaseException,
        rect_snapshot: _OptionalAttributeSnapshot,
        rect_object: object,
        rect_value: QRectF | None,
    ) -> None:
        errors: list[BaseException] = []
        for _attempt in range(2):
            try:
                # Restore the public root first, then make the captured QRectF
                # contents the final writer. A preceding size/orientation or
                # compatibility getter may have mutated the same QRectF before
                # the next capture port terminated.
                rect_snapshot.restore()
                if isinstance(rect_object, QRectF) and rect_value is not None:
                    QRectF.setRect(
                        rect_object,
                        rect_value.x(),
                        rect_value.y(),
                        rect_value.width(),
                        rect_value.height(),
                    )
                if not rect_snapshot.matches():
                    raise RuntimeError(
                        "sheet rect root changed during failed snapshot capture"
                    )
                if (
                    isinstance(rect_object, QRectF)
                    and rect_value is not None
                    and rect_object != rect_value
                ):
                    raise RuntimeError(
                        "sheet rect contents changed during failed snapshot capture"
                    )
            except BaseException as recovery_error:
                errors.append(recovery_error)
                continue
            break
        for recorded_error in errors:
            _add_sheet_setup_recovery_note(
                original_error,
                recorded_error,
                phase="unwinding partial sheet-state snapshot capture",
            )

    @classmethod
    def capture(cls, canvas) -> _SheetSetupStateSnapshot:
        raw_capture_baseline = _RawSheetCaptureBaseline.capture(canvas)
        try:
            return cls._capture_live(canvas)
        except BaseException as original_error:
            for _attempt in range(2):
                try:
                    raw_capture_baseline.restore()
                except BaseException as recovery_error:
                    _add_sheet_setup_recovery_note(
                        original_error,
                        recovery_error,
                        phase="unwinding raw sheet capture roots",
                    )
                    continue
                break
            raise

    @classmethod
    def _capture_live(cls, canvas) -> _SheetSetupStateSnapshot:
        runtime_state_attribute = _OptionalAttributeSnapshot.capture(
            canvas,
            "runtime_state",
        )
        runtime_state = (
            runtime_state_attribute.value if runtime_state_attribute.present else None
        )
        runtime_sheet_state = (
            _OptionalAttributeSnapshot.capture(runtime_state, "sheet_setup_state")
            if runtime_state is not None
            else None
        )
        canvas_sheet_state = _OptionalAttributeSnapshot.capture(
            canvas,
            "sheet_setup_state",
        )
        state = None
        if (
            runtime_sheet_state is not None
            and runtime_sheet_state.present
            and runtime_sheet_state.value is not None
        ):
            state = cast(_SheetSetupStateLike, runtime_sheet_state.value)
        elif canvas_sheet_state.present and canvas_sheet_state.value is not None:
            state = cast(_SheetSetupStateLike, canvas_sheet_state.value)

        raw_fields_baseline = _RawSheetFieldsBaseline.capture(state)
        # Capture the mutable QRectF root and its raw value before invoking the
        # remaining live field/compatibility getters. Those getters are allowed
        # extension points and may mutate this object before a later getter
        # raises BaseException.
        rect_snapshot = (
            _OptionalAttributeSnapshot.capture(state, "rect")
            if state is not None
            else None
        )
        rect_object = (
            rect_snapshot.value if rect_snapshot is not None else _MISSING_ATTRIBUTE
        )
        try:
            rect_value = QRectF(cast(Any, rect_object)) if state is not None else None
        except (TypeError, ValueError):
            rect_value = None
        state_attributes = tuple(
            snapshot
            for snapshot in (runtime_sheet_state, canvas_sheet_state)
            if snapshot is not None
        )
        try:
            state_fields = (
                (
                    _OptionalAttributeSnapshot.capture(
                        state,
                        "size_name",
                        identity=False,
                    ),
                    _OptionalAttributeSnapshot.capture(
                        state,
                        "orientation",
                        identity=False,
                    ),
                    cast(_OptionalAttributeSnapshot, rect_snapshot),
                )
                if state is not None
                else ()
            )
            compatibility_attributes = (
                _OptionalAttributeSnapshot.capture(
                    canvas,
                    "sheet_size",
                    identity=False,
                ),
                _OptionalAttributeSnapshot.capture(
                    canvas,
                    "sheet_orientation",
                    identity=False,
                ),
            )
        except BaseException as original_error:
            if raw_fields_baseline is not None:
                try:
                    raw_fields_baseline.restore()
                except BaseException as recovery_error:
                    _add_sheet_setup_recovery_note(
                        original_error,
                        recovery_error,
                        phase="unwinding raw sheet fields",
                    )
            if rect_snapshot is not None:
                cls._unwind_rect_after_capture_failure(
                    original_error,
                    rect_snapshot,
                    rect_object,
                    rect_value,
                )
            if raw_fields_baseline is not None:
                try:
                    # Live rect-root verification above may itself mutate a
                    # sibling field. Close capture-abort recovery on the raw
                    # namespace/member descriptors again.
                    raw_fields_baseline.restore()
                except BaseException as recovery_error:
                    _add_sheet_setup_recovery_note(
                        original_error,
                        recovery_error,
                        phase="reasserting raw sheet fields",
                    )
            raise
        return cls(
            state=state,
            state_fields=state_fields,
            rect_object=rect_object,
            rect_value=rect_value,
            state_attributes=state_attributes,
            compatibility_attributes=compatibility_attributes,
        )

    def restore(self) -> None:
        if not self.active:
            return
        operations: list[tuple[str, Callable[[], None]]] = []

        def restore_rect_value() -> None:
            if isinstance(self.rect_object, QRectF) and self.rect_value is not None:
                self.rect_object.setRect(
                    self.rect_value.x(),
                    self.rect_value.y(),
                    self.rect_value.width(),
                    self.rect_value.height(),
                )

        if self.rect_value is not None:
            operations.append(("sheet rect contents", restore_rect_value))
        operations.extend(
            (f"sheet field {snapshot.name}", snapshot.restore)
            for snapshot in self.state_fields
        )
        operations.extend(
            (f"sheet state root {snapshot.name}", snapshot.restore)
            for snapshot in self.state_attributes
        )
        operations.extend(
            (f"sheet compatibility field {snapshot.name}", snapshot.restore)
            for snapshot in self.compatibility_attributes
        )

        all_attempt_errors: list[BaseException] = []
        for attempt_index in range(2):
            attempt_errors: list[BaseException] = []
            ordered = operations if attempt_index == 0 else list(reversed(operations))
            for phase, operation in ordered:
                try:
                    operation()
                except BaseException as error:
                    try:
                        error.add_note(f"while restoring {phase}")
                    except BaseException:
                        pass
                    attempt_errors.append(error)

            for snapshot in (
                *self.state_fields,
                *self.state_attributes,
                *self.compatibility_attributes,
            ):
                try:
                    if not snapshot.matches():
                        raise RuntimeError(
                            f"sheet attribute {snapshot.name!r} did not match "
                            "its captured value"
                        )
                except BaseException as error:
                    attempt_errors.append(error)
            if isinstance(self.rect_object, QRectF) and self.rect_value is not None:
                try:
                    if self.rect_object != self.rect_value:
                        raise RuntimeError(
                            "sheet rect contents did not match their captured value"
                        )
                except BaseException as error:
                    attempt_errors.append(error)

            if not attempt_errors:
                self.recovery_errors.extend(all_attempt_errors)
                self.active = False
                return
            all_attempt_errors.extend(attempt_errors)

        if len(all_attempt_errors) == 1:
            raise all_attempt_errors[0]
        raise BaseExceptionGroup(
            "sheet state rollback failed after two verified passes",
            all_attempt_errors,
        )

    def release(self) -> None:
        self.active = False


def _restore_snapshot_with_retry(snapshot) -> tuple[BaseException, ...]:
    errors: list[BaseException] = []
    # Sheet-state restore owns its two-pass sequential/reverse protocol. Do not
    # multiply that bound through this generic outer retry helper.
    attempts = 1 if isinstance(snapshot, _SheetSetupStateSnapshot) else 2
    for _attempt in range(attempts):
        try:
            snapshot.restore()
        except BaseException as error:
            errors.append(error)
            continue
        return tuple(errors)
    return tuple(errors)


def _add_sheet_setup_recovery_note(
    original_error: BaseException,
    rollback_error: BaseException,
    *,
    phase: str,
) -> None:
    try:
        original_error.add_note(
            f"Sheet setup rollback also failed during {phase}: "
            f"{type(rollback_error).__name__}: {rollback_error}"
        )
    except BaseException:
        return


def _run_sheet_setup_transaction(canvas, operation: Callable[[], None]) -> None:
    rect_snapshot = CanvasSceneRectStateSnapshot.capture(canvas)
    try:
        state_snapshot = _SheetSetupStateSnapshot.capture(canvas)
    except BaseException as original_error:
        # Composite capture is part of the transaction.  The second snapshot
        # reads live compatibility descriptors, and one of those readers may
        # mutate the already-captured scene/view rect before terminating.  Do
        # not strand that first authority merely because the operation body has
        # not started yet.
        attempt_errors = _restore_snapshot_with_retry(rect_snapshot)
        recovered_errors = [
            *attempt_errors,
            *getattr(rect_snapshot, "recovery_errors", ()),
        ]
        for rollback_error in recovered_errors:
            _add_sheet_setup_recovery_note(
                original_error,
                rollback_error,
                phase="unwinding sheet-state snapshot capture",
            )
        raise
    try:
        operation()
    except BaseException as original_error:
        # Restore the sheet descriptors first and the scene/view rect last.
        # A custom sheet-state setter is an extension callback and may mutate
        # the Qt rect while accepting the captured value.  Closing on the
        # callback-free rect authority prevents that late setter side effect
        # from surviving an otherwise successful rollback.
        for phase, snapshot in (
            ("sheet state restore", state_snapshot),
            ("scene/view rect restore", rect_snapshot),
        ):
            attempt_errors = _restore_snapshot_with_retry(snapshot)
            if snapshot.active and attempt_errors:
                _add_sheet_setup_recovery_note(
                    original_error,
                    BaseExceptionGroup(
                        f"{phase} failed after retries",
                        list(attempt_errors),
                    ),
                    phase=phase,
                )
                continue
            recovered_errors = [
                *attempt_errors,
                *getattr(snapshot, "recovery_errors", ()),
            ]
            for rollback_error in recovered_errors:
                _add_sheet_setup_recovery_note(
                    original_error,
                    rollback_error,
                    phase=phase,
                )
        raise
    rect_snapshot.release()
    state_snapshot.release()


def sheet_setup_for(canvas) -> tuple[str, str]:
    return sheet_setup_values_for(canvas)


def sheet_size_for(canvas) -> str:
    return sheet_setup_for(canvas)[0]


def sheet_orientation_for(canvas) -> str:
    return sheet_setup_for(canvas)[1]


def _apply_sheet_scene_rect_unchecked(canvas) -> None:
    width, height = sheet_dimensions_px(*sheet_setup_for(canvas))
    state = sheet_setup_state_for(canvas)
    state.rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    set_scene_rect_for(
        canvas,
        state.rect.adjusted(
            -SHEET_MARGIN_PX,
            -SHEET_MARGIN_PX,
            SHEET_MARGIN_PX,
            SHEET_MARGIN_PX,
        ),
    )


def _raw_sheet_attribute(target: object | None, name: str) -> tuple[bool, object]:
    """Read a plain instance or slots root without invoking Python callbacks."""

    if target is None:
        return False, _MISSING_ATTRIBUTE
    namespace = _RawSheetCaptureBaseline._namespace(target)
    if namespace is not None and dict.__contains__(namespace, name):
        return True, dict.__getitem__(namespace, name)
    descriptor = _class_attribute(target, name)
    if isinstance(descriptor, MemberDescriptorType):
        try:
            return True, descriptor.__get__(target, type(target))
        except AttributeError:
            return False, _MISSING_ATTRIBUTE
    return False, _MISSING_ATTRIBUTE


def _verify_raw_sheet_setup_success(
    canvas: object,
    state: object,
    expected_size: str,
    expected_orientation: str,
    expected_sheet_rect: QRectF,
    *,
    canonical_root_was_present: bool,
) -> None:
    runtime_present, runtime_state = _raw_sheet_attribute(canvas, "runtime_state")
    canonical_owner = (
        runtime_state if runtime_present and runtime_state is not None else canvas
    )
    root_present, raw_state = _raw_sheet_attribute(
        canonical_owner,
        "sheet_setup_state",
    )
    if canonical_root_was_present and not root_present:
        raise RuntimeError(
            "raw sheet setup state root disappeared during finalization"
        )
    if root_present and raw_state is not state:
        raise RuntimeError("raw sheet setup state root changed during finalization")

    for name, expected in (
        ("size_name", expected_size),
        ("orientation", expected_orientation),
        ("rect", expected_sheet_rect),
    ):
        present, value = _raw_sheet_attribute(state, name)
        if name == "rect":
            matches = isinstance(value, QRectF) and QRectF(value) == expected
        else:
            matches = type(value) is str and value == expected
        if present and not matches:
            raise RuntimeError(
                f"raw sheet setup field {name!r} changed during finalization"
            )

    for name, expected in (
        ("sheet_size", expected_size),
        ("sheet_orientation", expected_orientation),
    ):
        present, value = _raw_sheet_attribute(canvas, name)
        if present and (type(value) is not str or value != expected):
            raise RuntimeError(
                f"raw sheet compatibility field {name!r} changed during finalization"
            )


def _verify_sheet_setup_success(
    canvas,
    expected_size: str,
    expected_orientation: str,
) -> None:
    width, height = sheet_dimensions_px(expected_size, expected_orientation)
    expected_sheet_rect = QRectF(-width / 2.0, -height / 2.0, width, height)
    expected_scene_rect = expected_sheet_rect.adjusted(
        -SHEET_MARGIN_PX,
        -SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
        SHEET_MARGIN_PX,
    )
    state = sheet_setup_state_for(canvas)
    compatibility = (
        getattr(canvas, "sheet_size", _MISSING_ATTRIBUTE),
        getattr(canvas, "sheet_orientation", _MISSING_ATTRIBUTE),
    )
    if (
        state.size_name != expected_size
        or state.orientation != expected_orientation
        or state.rect != expected_sheet_rect
        or compatibility != (expected_size, expected_orientation)
        or sheet_setup_state_for(canvas) is not state
    ):
        raise RuntimeError("sheet setup changed during successful finalization")

    runtime_present, runtime_state = _raw_sheet_attribute(canvas, "runtime_state")
    canonical_owner = (
        runtime_state if runtime_present and runtime_state is not None else canvas
    )
    canonical_root_was_present, _canonical_state = _raw_sheet_attribute(
        canonical_owner,
        "sheet_setup_state",
    )
    rect_snapshot = CanvasSceneRectStateSnapshot.capture(canvas)
    try:
        if (
            rect_snapshot.scene_state is not None
            and rect_snapshot.scene_state.rect != expected_scene_rect
        ):
            raise RuntimeError(
                "sheet scene rect changed during successful finalization"
            )
        if (
            rect_snapshot.view_state is not None
            and rect_snapshot.view_state.rect != expected_scene_rect
        ):
            raise RuntimeError("sheet view rect changed during successful finalization")
        # Every live sheet/compatibility getter ran before rect capture. Rect
        # capture then consumes the remaining live scene/view getters. Close on
        # callback-free instance/slots roots so neither callback family can be
        # the successful transaction's unverified final writer.
        _verify_raw_sheet_setup_success(
            canvas,
            state,
            expected_size,
            expected_orientation,
            expected_sheet_rect,
            canonical_root_was_present=canonical_root_was_present,
        )
    finally:
        rect_snapshot.release()


def apply_sheet_scene_rect_for(canvas) -> None:
    def apply() -> None:
        expected_size, expected_orientation = sheet_setup_for(canvas)
        _apply_sheet_scene_rect_unchecked(canvas)
        _verify_sheet_setup_success(
            canvas,
            expected_size,
            expected_orientation,
        )

    _run_sheet_setup_transaction(canvas, apply)


def sheet_rect_for(canvas) -> QRectF:
    return QRectF(sheet_setup_state_for(canvas).rect)


def scene_pos_in_sheet_for(canvas, pos) -> bool:
    rect = sheet_rect_for(canvas)
    if rect.isNull() or rect.isEmpty():
        return True
    return rect.contains(pos)


def set_sheet_setup_for(canvas, size_name: str, orientation: str) -> None:
    def apply() -> None:
        expected_size, expected_orientation = set_sheet_setup_state_for(
            canvas,
            size_name,
            orientation,
        )
        _apply_sheet_scene_rect_unchecked(canvas)
        update_viewport_for(canvas)
        _verify_sheet_setup_success(
            canvas,
            expected_size,
            expected_orientation,
        )

    _run_sheet_setup_transaction(canvas, apply)


__all__ = [
    "apply_sheet_scene_rect_for",
    "scene_pos_in_sheet_for",
    "set_sheet_setup_for",
    "sheet_orientation_for",
    "sheet_rect_for",
    "sheet_setup_for",
    "sheet_size_for",
]
