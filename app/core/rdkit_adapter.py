from __future__ import annotations

from typing import Mapping, Optional

from core.model import MoleculeModel
from core.rdkit_conversion import RDKitConversionHelper
from core.rdkit_import import RDKitImportHelper
from core.rdkit_types import Molecule3DAtom, Molecule3DBond, Molecule3DScene


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
                from rdkit import Chem
                from rdkit import RDLogger
                from rdkit.Chem import AllChem
            except Exception:
                self.last_error = "RDKit is not available in this environment."
                return None, None
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

    def _build_rdkit_mol_with_map(
        self,
        model: MoleculeModel,
        *,
        strict_labels: bool = False,
        unsupported_bond_styles: set[str] | None = None,
    ):
        return self._conversion_helper._build_rdkit_mol_with_map(
            model,
            strict_labels=strict_labels,
            unsupported_bond_styles=unsupported_bond_styles,
        )

    def model_to_rdkit_with_map(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit_with_map(model)

    def model_to_rdkit(self, model: MoleculeModel):
        return self._conversion_helper.model_to_rdkit(model)

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
        return self._import_helper.compute_props(model)

    def _embed_3d_molecule(self, mol, Chem, AllChem):
        return self._conversion_helper._embed_3d_molecule(mol, Chem, AllChem)

    def _bond_type(self, Chem, order: int):
        return self._conversion_helper._bond_type(Chem, order)

    def _annotation_for_atom(
        self,
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
        atom_id: int,
    ) -> tuple[int, int]:
        return self._conversion_helper._annotation_for_atom(atom_annotations, atom_id)

    def _format_atom_refs(self, refs: list[str]) -> str:
        return self._conversion_helper._format_atom_refs(refs)

    def _apply_atom_annotation(self, rd_atom, *, formal_charge: int, radical_electrons: int) -> None:
        self._conversion_helper._apply_atom_annotation(
            rd_atom,
            formal_charge=formal_charge,
            radical_electrons=radical_electrons,
        )

    def _build_model_adjacency(self, model: MoleculeModel) -> dict[int, list[int]]:
        return self._conversion_helper._build_model_adjacency(model)

    def _should_disable_implicit_hydrogens(
        self,
        model: MoleculeModel,
        atom_id: int,
        adjacency: Mapping[int, list[int]],
    ) -> bool:
        return self._conversion_helper._should_disable_implicit_hydrogens(model, atom_id, adjacency)

    def _component_sort_key(self, model: MoleculeModel, atom_ids: set[int]) -> tuple[float, float, int]:
        return self._conversion_helper._component_sort_key(model, atom_ids)

    def _model_components(self, model: MoleculeModel) -> list[set[int]]:
        return self._conversion_helper._model_components(model)

    def _build_component_model(
        self,
        model: MoleculeModel,
        atom_ids: set[int],
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
        return self._conversion_helper._build_component_model(
            model,
            atom_ids,
            atom_annotations=atom_annotations,
        )

    def _scene_from_embedded_mol(self, mol_h) -> Molecule3DScene:
        return self._conversion_helper._scene_from_embedded_mol(mol_h)

    def _scene_bounds(self, scene: Molecule3DScene) -> tuple[float, float, float, float, float, float]:
        return self._conversion_helper._scene_bounds(scene)

    def _translate_scene(
        self,
        scene: Molecule3DScene,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ) -> Molecule3DScene:
        return self._conversion_helper._translate_scene(scene, dx=dx, dy=dy, dz=dz)

    def _layout_component_scenes(
        self,
        component_scenes: list[Molecule3DScene],
        *,
        gap: float = 2.5,
    ) -> Molecule3DScene:
        return self._conversion_helper._layout_component_scenes(component_scenes, gap=gap)

    def _build_alias_fragment(
        self,
        label: str,
        *,
        atom_id: int,
        atom,
        neighbors: list[int],
        model: MoleculeModel,
        formal_charge: int,
        radical_electrons: int,
        rw,
        Chem,
        AllChem,
    ) -> tuple[int | None, dict[int, tuple[float, float]] | None]:
        return self._conversion_helper._build_alias_fragment(
            label,
            atom_id=atom_id,
            atom=atom,
            neighbors=neighbors,
            model=model,
            formal_charge=formal_charge,
            radical_electrons=radical_electrons,
            rw=rw,
            Chem=Chem,
            AllChem=AllChem,
        )

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
        return self._conversion_helper.model_to_3d_scene(model, atom_annotations=atom_annotations)

    def model_to_xyz_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        return self._conversion_helper.model_to_xyz_block(model, atom_annotations=atom_annotations)

    def get_name_from_smiles(self, smiles: str) -> str | None:
        return self._import_helper.get_name_from_smiles(smiles)

    def model_to_3d(self, model: MoleculeModel):
        return self.model_to_3d_coords(model)


__all__ = [
    "Molecule3DAtom",
    "Molecule3DBond",
    "Molecule3DScene",
    "RDKitAdapter",
]
