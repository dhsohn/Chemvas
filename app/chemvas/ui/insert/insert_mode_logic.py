from __future__ import annotations

from dataclasses import dataclass

from chemvas.features.insertion import (
    Point2D,
    TemplateInsertRequest,
    normalize_template_ring_style,
)

TEMPLATE_BOND_GATE_RATIO = 0.35


@dataclass(frozen=True, kw_only=True)
class InsertSessionState:
    template_active: bool = False
    template_ring_size: int | None = None
    template_ring_style: str | None = None


def clear_insert_session() -> InsertSessionState:
    return InsertSessionState()


def begin_template_insert(
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


def build_template_insert_request(
    state: InsertSessionState,
    cursor_pos: Point2D,
    bond_id: int | None,
    atom_id: int | None = None,
) -> TemplateInsertRequest | None:
    if not state.template_active or state.template_ring_size is None:
        return None
    return TemplateInsertRequest(
        ring_size=state.template_ring_size,
        cursor_pos=cursor_pos,
        bond_id=bond_id,
        ring_style=state.template_ring_style or "regular",
        atom_id=atom_id,
    )


__all__ = [
    "InsertSessionState",
    "begin_template_insert",
    "build_template_insert_request",
    "clear_insert_session",
]
