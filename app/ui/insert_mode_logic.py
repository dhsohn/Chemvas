from __future__ import annotations

from dataclasses import dataclass

from ui.template_insert_logic import Point2D, TemplateInsertRequest, normalize_template_ring_style


@dataclass(frozen=True)
class InsertSessionState:
    template_active: bool = False
    template_ring_size: int | None = None
    template_ring_style: str | None = None
    smiles_active: bool = False
    smiles_text: str | None = None
    smiles_center: Point2D | None = None


def clear_insert_session() -> InsertSessionState:
    return InsertSessionState()


def begin_template_insert(
    state: InsertSessionState,
    ring_size: int,
    ring_style: str | None = "regular",
) -> InsertSessionState | None:
    normalized_style = normalize_template_ring_style(ring_style)
    if ring_size < 3 or normalized_style is None:
        return None
    return InsertSessionState(
        template_active=True,
        template_ring_size=ring_size,
        template_ring_style=normalized_style,
    )


def cancel_template_insert(state: InsertSessionState) -> InsertSessionState:
    return InsertSessionState(
        smiles_active=state.smiles_active,
        smiles_text=state.smiles_text,
        smiles_center=state.smiles_center,
    )


def begin_smiles_insert(
    state: InsertSessionState,
    smiles: str,
    center: Point2D | None,
) -> InsertSessionState | None:
    normalized_smiles = smiles.strip()
    if not normalized_smiles or center is None:
        return None
    return InsertSessionState(
        smiles_active=True,
        smiles_text=normalized_smiles,
        smiles_center=center,
    )


def cancel_smiles_insert(state: InsertSessionState) -> InsertSessionState:
    return InsertSessionState(
        template_active=state.template_active,
        template_ring_size=state.template_ring_size,
        template_ring_style=state.template_ring_style,
    )


def build_template_insert_request(
    state: InsertSessionState,
    cursor_pos: Point2D,
    bond_id: int | None,
) -> TemplateInsertRequest | None:
    if not state.template_active or state.template_ring_size is None:
        return None
    return TemplateInsertRequest(
        ring_size=state.template_ring_size,
        cursor_pos=cursor_pos,
        bond_id=bond_id,
        ring_style=state.template_ring_style or "regular",
    )


__all__ = [
    "InsertSessionState",
    "begin_smiles_insert",
    "begin_template_insert",
    "build_template_insert_request",
    "cancel_smiles_insert",
    "cancel_template_insert",
    "clear_insert_session",
]
