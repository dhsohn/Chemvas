"""Structure, template, and SMILES insertion planning."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .chemistry_types import (
    Molecule3DAtom,
    Molecule3DBond,
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
)
from .smiles import (
    SmilesAtomPlacement,
    SmilesBondPlacement,
    SmilesCommitPlan,
    SmilesMarkPlacement,
    SmilesPreviewGeometry,
    SmilesPreviewPlan,
    SmilesPreviewResolvers,
    SmilesPreviewSnapshot,
    annotation_mark_direction,
    annotation_mark_kinds,
    build_smiles_preview_geometry,
    build_smiles_preview_snapshot,
    normalized_atom_annotation,
    plan_smiles_commit,
    plan_smiles_preview_update,
    smiles_preview_center,
    snapshot_smiles_preview_geometry,
)
from .structure_payload import (
    build_3d_conversion_payload,
    build_atom_annotations,
    build_structure_payload,
    build_submodel,
    expand_atom_ids_for_structure,
    model_with_atom_annotations,
)
from .template import (
    Point2D,
    TemplateInsertPlan,
    TemplateInsertRequest,
    TemplateInsertResolution,
    TemplatePointResolvers,
    normalize_template_ring_style,
    plan_template_commit,
    plan_template_preview,
    resolve_template_insert,
)
from .template_preview import (
    TemplatePreviewGeometry,
    TemplatePreviewPlan,
    build_benzene_template_preview_geometry,
    build_template_preview_geometry,
    plan_template_preview_update,
)

if TYPE_CHECKING:
    from .ring_occupancy import (
        point_inside_any_ring,
        ring_polygon_points_for_atoms,
        ring_polygon_points_for_bond,
    )
    from .structure_growth import (
        BondPlacementContext,
        alternating_ring_bond_specs,
        crown_ether_elements,
        fused_benzene_centers,
        mirrored_local_points,
        other_atom_id_from_bond_result,
        resolve_bond_placement_context,
    )


_LAZY_EXPORTS: dict[str, str] = {
    "BondPlacementContext": ".structure_growth",
    "alternating_ring_bond_specs": ".structure_growth",
    "crown_ether_elements": ".structure_growth",
    "fused_benzene_centers": ".structure_growth",
    "mirrored_local_points": ".structure_growth",
    "other_atom_id_from_bond_result": ".structure_growth",
    "point_inside_any_ring": ".ring_occupancy",
    "resolve_bond_placement_context": ".structure_growth",
    "ring_polygon_points_for_atoms": ".ring_occupancy",
    "ring_polygon_points_for_bond": ".ring_occupancy",
}


def __getattr__(name: str) -> Any:
    """Load Qt-dependent insertion helpers only when callers request them."""
    try:
        module_name = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


__all__ = [
    "BondPlacementContext",
    "Molecule3DAtom",
    "Molecule3DBond",
    "Molecule3DScene",
    "MoleculeIdentifiers",
    "Point2D",
    "RDKitResult",
    "SmilesAtomPlacement",
    "SmilesBondPlacement",
    "SmilesCommitPlan",
    "SmilesMarkPlacement",
    "SmilesPreviewGeometry",
    "SmilesPreviewPlan",
    "SmilesPreviewResolvers",
    "SmilesPreviewSnapshot",
    "TemplateInsertPlan",
    "TemplateInsertRequest",
    "TemplateInsertResolution",
    "TemplatePointResolvers",
    "TemplatePreviewGeometry",
    "TemplatePreviewPlan",
    "alternating_ring_bond_specs",
    "annotation_mark_direction",
    "annotation_mark_kinds",
    "build_3d_conversion_payload",
    "build_atom_annotations",
    "build_benzene_template_preview_geometry",
    "build_smiles_preview_geometry",
    "build_smiles_preview_snapshot",
    "build_structure_payload",
    "build_submodel",
    "build_template_preview_geometry",
    "crown_ether_elements",
    "expand_atom_ids_for_structure",
    "fused_benzene_centers",
    "mirrored_local_points",
    "model_with_atom_annotations",
    "normalize_template_ring_style",
    "normalized_atom_annotation",
    "other_atom_id_from_bond_result",
    "plan_smiles_commit",
    "plan_smiles_preview_update",
    "plan_template_commit",
    "plan_template_preview",
    "plan_template_preview_update",
    "point_inside_any_ring",
    "resolve_bond_placement_context",
    "resolve_template_insert",
    "ring_polygon_points_for_atoms",
    "ring_polygon_points_for_bond",
    "smiles_preview_center",
    "snapshot_smiles_preview_geometry",
]
