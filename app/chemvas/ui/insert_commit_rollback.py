from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from types import MemberDescriptorType
from typing import TYPE_CHECKING

from chemvas.domain.transactions import RestoreOutcome, restore_snapshot_with_retry
from chemvas.ui.canvas_smiles_input_state import (
    CanvasSmilesInputState,
    smiles_input_state_for,
)
from chemvas.ui.history_canvas_access import restore_history_transaction_for_history
from chemvas.ui.structure_insert_access import rollback_insert_mutation_for

if TYPE_CHECKING:
    from chemvas.ui.canvas_view import CanvasView


_MISSING_SMILES_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class SmilesInputRestoreAuthority:
    owner: object
    state: object
    state_getter: Callable[[], object]
    state_setter: Callable[[object], object]
    value_getter: Callable[[], object]
    value_setter: Callable[[object], object]

    @classmethod
    def capture(cls, canvas: object) -> SmilesInputRestoreAuthority:
        state = smiles_input_state_for(canvas)
        runtime_state = getattr(canvas, "runtime_state", None)
        if (
            runtime_state is not None
            and getattr(
                runtime_state,
                "smiles_input_state",
                _MISSING_SMILES_AUTHORITY,
            )
            is state
        ):
            owner = runtime_state
        else:
            owner = canvas

        owner_getattribute = inspect.getattr_static(type(owner), "__getattribute__")
        owner_setattr = inspect.getattr_static(type(owner), "__setattr__")
        state_getattribute = inspect.getattr_static(type(state), "__getattribute__")
        state_setattr = inspect.getattr_static(type(state), "__setattr__")
        if not all(
            callable(port)
            for port in (
                owner_getattribute,
                owner_setattr,
                state_getattribute,
                state_setattr,
            )
        ):
            raise RuntimeError("SMILES state has incomplete restore ports")

        # The production state is a slots dataclass.  Bind its raw slot through
        # ``object`` so a later class monkeypatch or Python ``__getattribute__``
        # hook cannot turn rollback verification into another mutation.  Plain
        # instance attributes on lightweight canvas owners have the same safe
        # object-level access.  Custom state descriptors retain their captured
        # ports, but the root/value/root composite below treats them as
        # untrusted and never omits the final root check.
        callback_free_value = type(state) is CanvasSmilesInputState
        static_owner_value = inspect.getattr_static(
            owner,
            "smiles_input_state",
            _MISSING_SMILES_AUTHORITY,
        )
        callback_free_root = static_owner_value is state or isinstance(
            static_owner_value, MemberDescriptorType
        )

        if callback_free_root:

            def get_state() -> object:
                return object.__getattribute__(owner, "smiles_input_state")

            def set_state(value: object) -> object:
                object.__setattr__(owner, "smiles_input_state", value)
                return value
        else:

            def get_state() -> object:
                return owner_getattribute(owner, "smiles_input_state")

            def set_state(value: object) -> object:
                return owner_setattr(owner, "smiles_input_state", value)

        if callback_free_value:

            def get_value() -> object:
                return object.__getattribute__(state, "last_smiles_input")

            def set_value(value: object) -> object:
                object.__setattr__(state, "last_smiles_input", value)
                return value
        else:

            def get_value() -> object:
                return state_getattribute(state, "last_smiles_input")

            def set_value(value: object) -> object:
                return state_setattr(state, "last_smiles_input", value)

        # Preflight every bound read before the caller begins mutation.
        if get_state() is not state:
            raise RuntimeError("SMILES state identity changed during capture")
        get_value()
        if get_state() is not state:
            raise RuntimeError(
                "SMILES state identity changed while capturing its value"
            )
        return cls(
            owner=owner,
            state=state,
            state_getter=get_state,
            state_setter=set_state,
            value_getter=get_value,
            value_setter=set_value,
        )

    def restore(self, target: str | None) -> RestoreOutcome:
        errors: list[BaseException] = []
        for attempt in range(2):
            try:
                if attempt == 0:
                    self.state_setter(self.state)
                    self.value_setter(target)
                else:
                    self.value_setter(target)
                    self.state_setter(self.state)
            except BaseException as error:
                errors.append(error)
            try:
                if self.state_getter() is not self.state:
                    raise RuntimeError("SMILES rollback did not restore state identity")
                if self.value_getter() != target:
                    raise RuntimeError(
                        "SMILES rollback setter did not restore the target value"
                    )
                # The value port is an untrusted descriptor for extension
                # states.  It may return the expected value while replacing the
                # captured root, so root identity must close the composite.
                if self.state_getter() is not self.state:
                    raise RuntimeError(
                        "SMILES rollback value verification changed state identity"
                    )
            except BaseException as error:
                errors.append(error)
                continue
            return RestoreOutcome(
                authoritative=True,
                fallback_to_inverse=False,
                errors=tuple(errors),
            )
        return RestoreOutcome(
            authoritative=False,
            fallback_to_inverse=False,
            errors=tuple(errors),
        )


def capture_smiles_input_restore_authority(
    canvas: object,
) -> SmilesInputRestoreAuthority:
    return SmilesInputRestoreAuthority.capture(canvas)


def _add_insert_rollback_note(
    original_error: BaseException,
    rollback_error: BaseException,
) -> None:
    try:
        add_note = getattr(original_error, "add_note", None)
        if not callable(add_note):
            return
        add_note(f"Insert rollback also failed: {rollback_error!r}")
    except BaseException:
        return


def rollback_insert_mutation(
    canvas: CanvasView,
    *,
    before_next_atom_id: int,
    before_bond_count: int,
    before_smiles_input: str | None,
    exact_transaction: object | None = None,
    smiles_authority: SmilesInputRestoreAuthority | None = None,
    original_error: BaseException | None = None,
) -> RestoreOutcome:
    if smiles_authority is None:
        smiles_authority = capture_smiles_input_restore_authority(canvas)
    rollback_errors: list[BaseException] = []
    authoritative = True
    try:
        rollback_insert_mutation_for(
            canvas,
            before_next_atom_id=before_next_atom_id,
            before_bond_count=before_bond_count,
        )
    except BaseException as caught_model_error:
        rollback_errors.append(caught_model_error)
        authoritative = False
    if exact_transaction is not None:
        restore_result = restore_snapshot_with_retry(
            lambda: restore_history_transaction_for_history(
                canvas,
                exact_transaction,
            ),
            description="insert transaction",
        )
        if original_error is not None or not restore_result.authoritative:
            rollback_errors.extend(restore_result.errors)
        authoritative = authoritative and restore_result.authoritative
    smiles_result = smiles_authority.restore(before_smiles_input)
    rollback_errors.extend(smiles_result.errors)
    authoritative = authoritative and smiles_result.authoritative

    if not rollback_errors:
        return RestoreOutcome(authoritative=authoritative)
    if original_error is not None:
        for rollback_error in rollback_errors:
            _add_insert_rollback_note(original_error, rollback_error)
        return RestoreOutcome(
            authoritative=authoritative,
            fallback_to_inverse=False,
            errors=tuple(rollback_errors),
        )
    if authoritative:
        return RestoreOutcome(
            authoritative=True,
            fallback_to_inverse=False,
            errors=tuple(rollback_errors),
        )
    if len(rollback_errors) == 1:
        raise rollback_errors[0]
    raise BaseExceptionGroup("Insert rollback failed", rollback_errors)


__all__ = [
    "SmilesInputRestoreAuthority",
    "capture_smiles_input_restore_authority",
    "rollback_insert_mutation",
]
