"""Deterministic optional-backend artifacts for calculation CLI tests."""

from __future__ import annotations

from chemvas.features.calculation_bundle import AtomMapEntry, CalculationArtifacts


class _StateFakeAdapter:
    last_error: str | None = None

    def model_to_calculation_artifacts(self, model, atom_annotations=None):
        formal_charge = sum(
            values.get("formal_charge", 0)
            for values in (atom_annotations or {}).values()
        )
        atom_ids = sorted(model.atoms)
        entries = tuple(
            AtomMapEntry(
                xyz_index=index,
                mol_index=index,
                symbol=(
                    "C"
                    if model.atoms[atom_id].element == "Me"
                    else model.atoms[atom_id].element
                ),
                origin=(
                    "alias_attachment"
                    if model.atoms[atom_id].element == "Me"
                    else "chemvas_atom"
                ),
                chemvas_atom_id=atom_id,
            )
            for index, atom_id in enumerate(atom_ids, start=1)
        )
        xyz_lines = [str(len(entries)), "Chemvas geometry v1"]
        xyz_lines.extend(
            f"{entry.symbol} {entry.xyz_index}.0 0.0 0.0" for entry in entries
        )
        return CalculationArtifacts(
            mol_block=f"fake mol for {atom_ids}\n",
            xyz_block="\n".join(xyz_lines) + "\n",
            atom_map=entries,
            rdkit_version="test-rdkit",
            rdkit_formal_charge=formal_charge,
            rdkit_radical_electrons=0,
            electron_count=100 - formal_charge,
            geometry_embedding="ETKDGv3",
            geometry_random_seed=0xC0FFEE,
            geometry_optimization_policy="test",
            geometry_optimization_result="test_converged",
            mol_atom_count=len(entries),
            xyz_atom_count=len(entries),
        )
