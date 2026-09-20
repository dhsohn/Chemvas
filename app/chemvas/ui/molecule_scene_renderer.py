from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemvas.domain.document import MoleculeModel
    from chemvas.ui.scene_render_context import SceneRenderContext


def prepare_molecule_for_scene(model: MoleculeModel) -> None:
    """Preserve the label preparation historically performed by whole-model loads.

    Native state allows surrounding whitespace. The former editor-label path
    stripped it and cleared the literal-label flag when the stored text changed.
    Keep that ingress policy explicit; drawing an already prepared model below
    never changes the document.
    """
    for atom in model.atoms.values():
        text = atom.element.strip()
        if text != atom.element:
            if text:
                atom.element = text
            atom.explicit_label = False


def render_molecule(context: SceneRenderContext) -> None:
    """Draw the current molecular model without editing it or recording history.

    Preserve native insertion order: bonds first, then labels and their incident
    bond redraws. Equal-z overlapping bonds retain the editor's stacking order.
    """
    for bond_id, bond in enumerate(context.model.bonds):
        if bond is not None:
            context.bonds.add_bond_graphics(bond_id)
    for atom_id, atom in context.model.atoms.items():
        if atom.element.upper() == "C" and not atom.explicit_label:
            context.atom_labels.ensure_carbon_dot(atom_id)
        else:
            context.atom_labels.draw_atom(atom_id)
            context.bonds.redraw_connected_bonds(atom_id)


__all__ = ["prepare_molecule_for_scene", "render_molecule"]
