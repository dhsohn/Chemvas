from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast


@dataclass(slots=True)
class CanvasSmilesInputState:
    last_smiles_input: str | None = None


def smiles_input_state_for(canvas: Any) -> CanvasSmilesInputState:
    return cast(CanvasSmilesInputState, canvas.runtime_state.smiles_input_state)


def last_smiles_input_for(canvas: Any) -> str | None:
    return smiles_input_state_for(canvas).last_smiles_input


def set_last_smiles_input_for(canvas: Any, smiles: str | None) -> None:
    state = smiles_input_state_for(canvas)
    state.last_smiles_input = smiles


def clear_last_smiles_input_for(canvas: Any) -> None:
    set_last_smiles_input_for(canvas, None)


__all__ = [
    "CanvasSmilesInputState",
    "clear_last_smiles_input_for",
    "last_smiles_input_for",
    "set_last_smiles_input_for",
    "smiles_input_state_for",
]
