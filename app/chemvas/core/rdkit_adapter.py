from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

from chemvas.core.rdkit_conversion import RDKitConversionHelper
from chemvas.core.rdkit_import import RDKitImportHelper
from chemvas.domain.atom_aliases import alias_fragment_smiles
from chemvas.domain.document import MoleculeModel
from chemvas.features.calculation_bundle import CalculationArtifacts
from chemvas.features.insertion import (
    Molecule3DAtom,
    Molecule3DBond,
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
)


class RDKitAdapter:
    def __init__(self) -> None:
        self._rdkit: tuple[Any, Any] | None = None
        self.last_error: str | None = None
        self._name_map = {
            "c1ccccc1": "Benzene",
            "C1CCCCC1": "Cyclohexane",
            "C1CCCC1": "Cyclopentane",
            "C1CCC1": "Cyclobutane",
            "C1CC1": "Cyclopropane",
            "c1ccc2ccccc2c1": "Naphthalene",
            "c1ccc2cc3ccccc3cc2c1": "Anthracene",
            "c1ccc2c(c1)ccc1ccccc12": "Phenanthrene",
            "c1ccncc1": "Pyridine",
            "c1cncnc1": "Pyrimidine",
            "c1c[nH]cn1": "Imidazole",
            "c1cc[nH]c1": "Pyrrole",
            "c1ccoc1": "Furan",
            "c1ccsc1": "Thiophene",
            "c1ccc2[nH]ccc2c1": "Indole",
            "c1ccc2ncccc2c1": "Quinoline",
            "c1ccc2cnccc2c1": "Isoquinoline",
            "c1ccc2[nH]cnc2c1": "Benzimidazole",
        }
        self._alias_smiles = alias_fragment_smiles()
        self._import_helper = RDKitImportHelper(self)
        self._conversion_helper = RDKitConversionHelper(self)

    def _load_rdkit(self) -> tuple[Any, Any]:
        if self._rdkit is None:
            try:
                from rdkit import Chem, RDLogger
                from rdkit.Chem import AllChem
            except Exception:
                self._rdkit = (None, None)
                self.last_error = "RDKit is not available in this environment."
                return self._rdkit
            # rdkit-stubs omits DisableLog even though rdkit provides it at runtime.
            RDLogger.DisableLog("rdApp.*")  # type: ignore[attr-defined]
            self._rdkit = (Chem, AllChem)
        return self._rdkit

    def is_loaded(self) -> bool:
        return self._rdkit not in (None, (None, None))

    def is_unavailable(self) -> bool:
        return self._rdkit == (None, None)

    def preload(self) -> bool:
        rdkit = self._load_rdkit()
        return rdkit != (None, None)

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> MoleculeModel | None:
        return self._import_helper.smiles_to_2d(smiles, scale=scale)

    def model_to_rdkit_with_map(self, model: MoleculeModel):
        return self.model_to_rdkit_with_map_strict_labels(model)

    def model_to_rdkit_with_map_tolerant(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit_with_map_tolerant(model)

    def model_to_rdkit_with_map_strict_labels(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit_with_map_strict_labels(model)

    def model_to_rdkit_strict_labels(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit_strict_labels(model)

    def model_to_rdkit(self, model: MoleculeModel):
        return self.model_to_rdkit_strict_labels(model)

    def model_to_rdkit_tolerant(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit_tolerant(model)

    def suggest_atom_correspondence(
        self,
        model: MoleculeModel,
        reactant_atom_ids: frozenset[int] | set[int],
        product_atom_ids: frozenset[int] | set[int],
    ) -> list[tuple[int, int]] | None:
        result = self._call_with_result(
            lambda: self._conversion_helper.suggest_atom_correspondence(
                model, reactant_atom_ids, product_atom_ids
            ),
            fallback_error="Failed to suggest an atom correspondence.",
        )
        self.last_error = result.error
        return result.value

    def compute_props(
        self, model: MoleculeModel
    ) -> tuple[str | None, float | None, str | None]:
        return self._import_helper.compute_props(model)

    def compute_identifiers(self, model: MoleculeModel) -> MoleculeIdentifiers:
        return self._import_helper.compute_identifiers(model)

    def _embed_3d_molecule(self, mol, Chem, AllChem):
        return self._conversion_helper._embed_3d_molecule(mol, Chem, AllChem)

    def _build_conversion_rdkit_mol(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ):
        return self._conversion_helper._build_conversion_rdkit_mol(
            model,
            atom_annotations=atom_annotations,
        )

    def model_to_3d_coords(self, model: MoleculeModel):
        return self._conversion_helper.model_to_3d_coords(model)

    def model_to_3d_scene(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> Molecule3DScene | None:
        result = self.model_to_3d_scene_result(model, atom_annotations=atom_annotations)
        self.last_error = result.error
        return result.value

    def model_to_3d_scene_result(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> RDKitResult[Molecule3DScene]:
        return self._call_with_result(
            lambda: self._conversion_helper.model_to_3d_scene(
                model, atom_annotations=atom_annotations
            ),
            fallback_error="Failed to build 3D preview.",
        )

    def model_to_xyz_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        result = self.model_to_xyz_block_result(
            model, atom_annotations=atom_annotations
        )
        self.last_error = result.error
        return result.value

    def model_to_xyz_block_result(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> RDKitResult[str]:
        return self._call_with_result(
            lambda: self._conversion_helper.model_to_xyz_block(
                model, atom_annotations=atom_annotations
            ),
            fallback_error="Failed to export 3D XYZ.",
        )

    def model_to_mol_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        result = self.model_to_mol_block_result(
            model, atom_annotations=atom_annotations
        )
        self.last_error = result.error
        return result.value

    def model_to_mol_block_result(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> RDKitResult[str]:
        return self._call_with_result(
            lambda: self._conversion_helper.model_to_mol_block(
                model, atom_annotations=atom_annotations
            ),
            fallback_error="Failed to export MOL.",
        )

    def model_to_calculation_artifacts(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> CalculationArtifacts | None:
        result = self.model_to_calculation_artifacts_result(
            model, atom_annotations=atom_annotations
        )
        self.last_error = result.error
        return result.value

    def model_to_calculation_artifacts_result(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> RDKitResult[CalculationArtifacts]:
        return self._call_with_result(
            lambda: self._conversion_helper.model_to_calculation_artifacts(
                model, atom_annotations=atom_annotations
            ),
            fallback_error="Failed to build calculation artifacts.",
        )

    def get_name_from_smiles(self, smiles: str) -> str | None:
        return self._import_helper.get_name_from_smiles(smiles)

    def model_to_3d(self, model: MoleculeModel):
        return self.model_to_3d_coords(model)

    def _call_with_result(self, callback, *, fallback_error: str):
        self.last_error = None
        try:
            value = callback()
        except Exception as exc:
            return RDKitResult(None, str(exc) or fallback_error)
        error = None if value is not None else self.last_error or fallback_error
        return RDKitResult(value, error)


def warm_rdkit_in_background() -> threading.Thread:
    """Import RDKit on a daemon thread so first use never stalls the GUI.

    The rdkit module import costs hundreds of milliseconds and, before this
    warmup, ran on the GUI thread the first time a selection or the 3D
    preview needed it — typically in the middle of a drag. Importing is
    process-wide, so warming a throwaway adapter makes every later
    ``RDKitAdapter._load_rdkit`` resolve instantly. When RDKit is not
    installed the thread just records the unavailability and exits.
    """

    thread = threading.Thread(
        target=RDKitAdapter().preload,
        name="rdkit-warmup",
        daemon=True,
    )
    thread.start()
    return thread


__all__ = [
    "Molecule3DAtom",
    "Molecule3DBond",
    "Molecule3DScene",
    "MoleculeIdentifiers",
    "RDKitAdapter",
    "RDKitResult",
    "warm_rdkit_in_background",
]
