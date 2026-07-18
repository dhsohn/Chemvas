from __future__ import annotations

from typing import Any

from PyQt6.QtGui import QColor

from chemvas.features.insertion import Molecule3DScene
from chemvas.ui.main_window_palette import PALETTE

PreviewStatusBadge = tuple[str, QColor, QColor, QColor]


def preview_payload_signature(model: Any, atom_annotations: Any) -> tuple:
    atom_sig = tuple(
        (
            atom_id,
            atom.element,
            round(atom.x, 3),
            round(atom.y, 3),
        )
        for atom_id, atom in sorted(model.atoms.items())
    )
    bond_sig = tuple(
        (
            bond.a,
            bond.b,
            bond.order,
            bond.style,
        )
        for bond in model.bonds
        if bond is not None
    )
    annotation_sig = tuple(
        (
            atom_id,
            int(values.get("formal_charge", 0)),
            int(values.get("radical_electrons", 0)),
        )
        for atom_id, values in sorted((atom_annotations or {}).items())
    )
    return atom_sig, bond_sig, annotation_sig


def preview_info_lines(formula: str, mw: str) -> list[str]:
    lines: list[str] = []
    if formula:
        lines.append(f"Formula: {formula}")
    if mw:
        lines.append(f"MW: {mw}")
    return lines


def preview_info_items(formula: str, mw: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if formula:
        items.append(("FORMULA", formula))
    if mw:
        items.append(("MW", mw))
    return items


def preview_metadata_summary(scene: Molecule3DScene | None, message: str) -> str:
    if scene is not None:
        atom_count = len(scene.atoms)
        bond_count = len(scene.bonds)
        atom_label = "atom" if atom_count == 1 else "atoms"
        bond_label = "bond" if bond_count == 1 else "bonds"
        return f"{atom_count} {atom_label} / {bond_count} {bond_label}"
    if message.startswith("Updating"):
        return "Preparing coordinates"
    if is_empty_preview_message(message):
        return ""
    return "Preview needs attention"


def preview_status_badge(
    scene: Molecule3DScene | None, message: str
) -> PreviewStatusBadge:
    if scene is not None:
        return (
            "Ready",
            QColor(PALETTE["checked_bg"]),
            QColor(PALETTE["checked_border"]),
            QColor(PALETTE["checked_text"]),
        )
    if message.startswith("Updating"):
        return (
            "Building",
            QColor(PALETTE["surface_context"]),
            QColor(PALETTE["border_strong"]),
            QColor(PALETTE["text_muted"]),
        )
    if is_empty_preview_message(message):
        return (
            "Empty",
            QColor(PALETTE["hover"]),
            QColor(PALETTE["border_strong"]),
            QColor(PALETTE["text_muted"]),
        )
    return (
        "Issue",
        QColor(PALETTE["danger_bg"]),
        QColor(PALETTE["danger_border"]),
        QColor(PALETTE["danger_text"]),
    )


def preview_empty_state_text(message: str) -> tuple[str, str]:
    normalized = " ".join((message or "3D preview unavailable").split())
    if normalized.startswith("Updating"):
        return "Building preview", "Preparing coordinates"
    if is_empty_preview_message(normalized):
        if "selected" in normalized.lower():
            return "No selected molecule", "Select a molecule to preview it in 3D."
        return "No molecule yet", "Draw or paste a structure to preview it in 3D."
    if len(normalized) > 96:
        normalized = f"{normalized[:93]}..."
    return "Preview unavailable", normalized


def is_empty_preview_message(message: str | None) -> bool:
    normalized = " ".join((message or "").split()).lower()
    return (
        normalized in {"", "3d preview unavailable"}
        or "no chemical structure" in normalized
    )


__all__ = [
    "PreviewStatusBadge",
    "is_empty_preview_message",
    "preview_empty_state_text",
    "preview_info_items",
    "preview_info_lines",
    "preview_metadata_summary",
    "preview_payload_signature",
    "preview_status_badge",
]
