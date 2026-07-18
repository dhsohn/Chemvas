from __future__ import annotations

from chemvas.ui.structure_growth_build_service import StructureGrowthBuildActions


def structure_growth_build_actions_for(service) -> StructureGrowthBuildActions:
    return StructureGrowthBuildActions(
        atom_point=lambda atom_id: service.atom_point(atom_id),
        sprout_bond_endpoint=lambda atom_id, *, cyclic=False: (
            service.sprout_bond_endpoint(
                atom_id,
                cyclic=cyclic,
            )
        ),
        add_bond_between_points=lambda start, end, style, order: (
            service.add_bond_between_points(
                start,
                end,
                style,
                order,
            )
        ),
        add_benzene_ring=lambda center, **kwargs: service.add_benzene_ring(
            center, **kwargs
        ),
        has_atom=lambda atom_id: service.has_atom(atom_id),
        default_bond_endpoint=lambda start, start_atom_id: (
            service.default_bond_endpoint(start, start_atom_id)
        ),
        add_atom_label=lambda atom_id, element, **kwargs: (
            service.committer.add_atom_label(
                atom_id,
                element,
                **kwargs,
            )
        ),
        regular_ring_points_for_atom=lambda n, atom_id: (
            service.regular_ring_points_for_atom(n, atom_id)
        ),
        regular_ring_points_for_bond=lambda n, bond_id, midpoint: (
            service.regular_ring_points_for_bond(
                n,
                bond_id,
                midpoint,
            )
        ),
        cyclohexane_chair_points=lambda center: service.cyclohexane_chair_points(
            center
        ),
        template_points_for_bond=lambda points_local, bond_id, midpoint: (
            service.template_points_for_bond(
                points_local,
                bond_id,
                midpoint,
            )
        ),
        add_ring_from_points=lambda points, **kwargs: service.add_ring_from_points(
            points, **kwargs
        ),
        bond_placement_context=lambda bond_id: service.bond_placement_context(bond_id),
        run_recorded_additions_action=lambda action: (
            service._run_recorded_additions_action(action)
        ),
        add_atom=lambda element, x, y: service.committer.add_atom(element, x, y),
        add_bond=lambda a_id, b_id, order, **kwargs: service.committer.add_bond(
            a_id,
            b_id,
            order,
            **kwargs,
        ),
        add_bond_graphics=lambda bond_id: service.committer.add_bond_graphics(bond_id),
    )


__all__ = ["structure_growth_build_actions_for"]
