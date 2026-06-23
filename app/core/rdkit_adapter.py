from __future__ import annotations

from typing import Mapping, Optional

from core.model import MoleculeModel
from core.rdkit_conversion import RDKitConversionHelper
from core.rdkit_import import RDKitImportHelper
from core.rdkit_types import (
    Molecule3DAtom,
    Molecule3DBond,
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
)


class RDKitAdapter:
    def __init__(self) -> None:
        self._rdkit = None
        self.last_error: str | None = None
        self._name_map = {
            "c1ccccc1": "Benzene",
            "C1CCCCC1": "Cyclohexane",
            "C1CCCC1": "Cyclopentane",
            "C1CCC1": "Cyclobutane",
            "C1CC1": "Cyclopropane",
            "c1cccc2ccccc12": "Naphthalene",
            "c1ccc2cc3ccccc3cc2c1": "Anthracene",
            "c1ccc2c(c1)ccc3ccccc23": "Phenanthrene",
            "n1ccccc1": "Pyridine",
            "n1ccnc(n1)": "Pyrimidine",
            "c1ncc[nH]1": "Imidazole",
            "c1cc[nH]c1": "Pyrrole",
            "o1cccc1": "Furan",
            "s1cccc1": "Thiophene",
            "c1ccc2[nH]cc2c1": "Indole",
            "c1ccc2ncccc2c1": "Quinoline",
            "c1ccc2cccnc2c1": "Isoquinoline",
            "c1ccc2[nH]nc2c1": "Benzimidazole",
        }
        self._alias_smiles = {
            "Me": "[*:1]C",
            "Et": "[*:1]CC",
            "OH": "[*:1]O",
            "Ph": "[*:1]c1ccccc1",
            "OMe": "[*:1]OC",
            "Boc": "[*:1]C(=O)OC(C)(C)C",
            "CO2Me": "[*:1]C(=O)OC",
            "t-Bu": "[*:1]C(C)(C)C",
            "i-Pr": "[*:1]C(C)C",
        }
        self._import_helper = RDKitImportHelper(self)
        self._conversion_helper = RDKitConversionHelper(self)

    def _load_rdkit(self):
        if self._rdkit is None:
            try:
                from rdkit import Chem, RDLogger
                from rdkit.Chem import AllChem
            except Exception:
                self._rdkit = (None, None)
                self.last_error = "RDKit is not available in this environment."
                return self._rdkit
            RDLogger.DisableLog("rdApp.*")
            self._rdkit = (Chem, AllChem)
        return self._rdkit

    def is_loaded(self) -> bool:
        return self._rdkit not in (None, (None, None))

    def is_unavailable(self) -> bool:
        return self._rdkit == (None, None)

    def preload(self) -> bool:
        rdkit = self._load_rdkit()
        return rdkit != (None, None)

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> Optional[MoleculeModel]:
        return self._import_helper.smiles_to_2d(smiles, scale=scale)

    def model_to_rdkit_with_map(self, model: MoleculeModel, *, strict_labels: bool = False):
        return self._conversion_helper.model_to_rdkit_with_map(model, strict_labels=strict_labels)

    def model_to_rdkit(self, model: MoleculeModel, *, strict_labels: bool = False):
        return self._conversion_helper.model_to_rdkit(model, strict_labels=strict_labels)

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
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
            lambda: self._conversion_helper.model_to_3d_scene(model, atom_annotations=atom_annotations),
            fallback_error="Failed to build 3D preview.",
        )

    def model_to_xyz_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        result = self.model_to_xyz_block_result(model, atom_annotations=atom_annotations)
        self.last_error = result.error
        return result.value

    def model_to_xyz_block_result(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> RDKitResult[str]:
        return self._call_with_result(
            lambda: self._conversion_helper.model_to_xyz_block(model, atom_annotations=atom_annotations),
            fallback_error="Failed to export 3D XYZ.",
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


__all__ = [
    "Molecule3DAtom",
    "Molecule3DBond",
    "Molecule3DScene",
    "MoleculeIdentifiers",
    "RDKitResult",
    "RDKitAdapter",
]
