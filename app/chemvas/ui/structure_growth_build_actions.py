from __future__ import annotations

from chemvas.ui.structure_growth_build_service import StructureGrowthBuildActions


def structure_growth_build_actions_for(service) -> StructureGrowthBuildActions:
    # Mixed on purpose. The lambda fields are load-bearing late binding: tests
    # rebind those methods on the service (or on service.committer) after
    # construction — see tests/test_structure_build_service.py and
    # tests/test_insert_commit_service.py — so the record must resolve them at
    # call time. The plain bound-method fields wrap methods nothing rebinds.
    return StructureGrowthBuildActions(
        atom_point=service.atom_point,
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
        has_atom=service.has_atom,
        default_bond_endpoint=lambda start, start_atom_id: (
            service.default_bond_endpoint(start, start_atom_id)
        ),
        add_atom_label=service.committer.add_atom_label,
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
        bond_placement_context=service.bond_placement_context,
        run_recorded_additions_action=service._run_recorded_additions_action,
        add_atom=service.committer.add_atom,
        add_bond=service.committer.add_bond,
        add_bond_graphics=lambda bond_id: service.committer.add_bond_graphics(bond_id),
    )


__all__ = ["structure_growth_build_actions_for"]
