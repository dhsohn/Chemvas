from __future__ import annotations

from chemvas.ui.structure_growth_build_service import StructureGrowthBuildActions


def structure_growth_build_actions_for(service) -> StructureGrowthBuildActions:
    return StructureGrowthBuildActions(
        atom_point=service.atom_point,
        sprout_bond_endpoint=service.sprout_bond_endpoint,
        add_bond_between_points=service.add_bond_between_points,
        add_benzene_ring=service.add_benzene_ring,
        has_atom=service.has_atom,
        default_bond_endpoint=service.default_bond_endpoint,
        add_atom_label=service.committer.add_atom_label,
        regular_ring_points_for_atom=service.regular_ring_points_for_atom,
        regular_ring_points_for_bond=service.regular_ring_points_for_bond,
        cyclohexane_chair_points=service.cyclohexane_chair_points,
        template_points_for_bond=service.template_points_for_bond,
        add_ring_from_points=service.add_ring_from_points,
        bond_placement_context=service.bond_placement_context,
        run_recorded_additions_action=service._run_recorded_additions_action,
        add_atom=service.committer.add_atom,
        add_bond=service.committer.add_bond,
        add_bond_graphics=service.committer.add_bond_graphics,
    )


__all__ = ["structure_growth_build_actions_for"]
