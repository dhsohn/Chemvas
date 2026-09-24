from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from chemvas.core.rdkit_alias_fragments import _RDKitAliasFragments
from chemvas.core.rdkit_correspondence import _RDKitCorrespondence
from chemvas.core.rdkit_diagnostics import RDKIT_UNAVAILABLE_MESSAGE
from chemvas.core.rdkit_embedding import _RDKitEmbedding
from chemvas.core.rdkit_stereo import _RDKitStereo
from chemvas.domain.document import (
    AtomMapEntry,
    Bond,
    CalculationArtifacts,
    MoleculeModel,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chemvas.core.rdkit_adapter import RDKitAdapter
    from chemvas.domain.chemistry_types import (
        Molecule3DScene,
    )

logger = logging.getLogger(__name__)


class RDKitConversionHelper(
    _RDKitAliasFragments, _RDKitCorrespondence, _RDKitEmbedding, _RDKitStereo
):
    def __init__(self, adapter: RDKitAdapter) -> None:
        self.adapter = adapter

    def _valid_conversion_bonds(self, model: MoleculeModel) -> list[tuple[int, Bond]]:
        valid_bonds: list[tuple[int, Bond]] = []
        for bond_id, bond in enumerate(model.bonds):
            if bond is None or bond.a == bond.b:
                continue
            if bond.a not in model.atoms or bond.b not in model.atoms:
                continue
            valid_bonds.append((bond_id, bond))
        return valid_bonds

    def _add_conversion_atoms(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
        adjacency: Mapping[int, list[int]],
        rw,
        Chem,
        AllChem,
    ) -> (
        tuple[
            dict[int, int],
            dict[int, tuple[float, float]],
            dict[int, tuple[int, str]],
        ]
        | None
    ):
        """Add model atoms (expanding aliases) to ``rw``; None with last_error on failure."""
        atom_map: dict[int, int] = {}
        coord_map: dict[int, tuple[float, float]] = {}
        origins: dict[int, tuple[int, str]] = {}
        invalid_labels: list[str] = []
        for atom_id in sorted(model.atoms):
            atom = model.atoms[atom_id]
            formal_charge, radical_electrons = self._annotation_for_atom(
                atom_annotations, atom_id
            )
            annotation = (
                atom_annotations.get(atom_id) if atom_annotations is not None else None
            )
            if atom.element in self.adapter._alias_smiles:
                attachment_idx, alias_coords = self._build_alias_fragment(
                    atom.element,
                    atom_id=atom_id,
                    atom=atom,
                    neighbors=adjacency.get(atom_id, []),
                    model=model,
                    formal_charge=formal_charge,
                    radical_electrons=radical_electrons,
                    annotation=annotation,
                    rw=rw,
                    Chem=Chem,
                    AllChem=AllChem,
                )
                if attachment_idx is None or alias_coords is None:
                    return None
                atom_map[atom_id] = attachment_idx
                coord_map.update(alias_coords)
                origins.update(
                    {
                        rdkit_index: (
                            atom_id,
                            "alias_attachment"
                            if rdkit_index == attachment_idx
                            else "alias_expansion",
                        )
                        for rdkit_index in alias_coords
                    }
                )
                continue
            try:
                rd_atom = Chem.Atom(atom.element)
            except Exception:
                invalid_labels.append(f"{atom.element} (atom {atom_id})")
                continue
            # RDKit counts explicit H neighbours toward valence before filling
            # the remainder; a partially drawn NH2 must retain its other H.
            self._apply_atom_annotation(
                rd_atom,
                formal_charge=formal_charge,
                radical_electrons=radical_electrons,
            )
            new_idx = rw.AddAtom(rd_atom)
            atom_map[atom_id] = new_idx
            coord_map[new_idx] = (atom.x, atom.y)
            origins[new_idx] = (atom_id, "chemvas_atom")

        if invalid_labels:
            supported_aliases = ", ".join(sorted(self.adapter._alias_smiles))
            self.adapter.last_error = (
                "Unsupported atom labels for 3D conversion: "
                f"{self._format_atom_refs(invalid_labels)}. "
                f"Supported aliases: {supported_aliases}."
            )
            return None
        return atom_map, coord_map, origins

    def _add_conversion_bonds(
        self,
        valid_bonds: list[tuple[int, Bond]],
        *,
        atom_map: dict[int, int],
        rw,
        Chem,
    ) -> bool:
        """Add bonds with stereo directions to ``rw``; False with last_error on failure."""
        seen_bonds: set[tuple[int, int]] = set()
        for bond_id, bond in valid_bonds:
            if bond.style == "double_either" and bond.order != 2:
                self.adapter.last_error = (
                    f"Bond {bond_id} uses double_either without bond order 2. "
                    "Explicitly unspecified double bonds must have order 2."
                )
                return False
            if bond.style in {"dotted", "dotted_double", "dotted_double_outer"}:
                self.adapter.last_error = (
                    f"Bond {bond_id} is a dotted contact. Chemical conversion "
                    "cannot treat forming, breaking, or noncovalent contacts as "
                    "ordinary bonds. Use a drawing of the covalent structure "
                    "without contacts for identifiers and chemistry exports."
                )
                return False
            if bond.a not in atom_map or bond.b not in atom_map:
                continue
            rd_a = atom_map[bond.a]
            rd_b = atom_map[bond.b]
            key = (rd_a, rd_b) if rd_a <= rd_b else (rd_b, rd_a)
            if key in seen_bonds:
                continue
            seen_bonds.add(key)
            if bond.style in {"wedge", "hash"} and bond.order != 1:
                self.adapter.last_error = (
                    f"Bond {bond_id} uses style '{bond.style}' with order {bond.order}. "
                    "Stereo export currently supports wedge/hash on single bonds only."
                )
                return False
            rw.AddBond(rd_a, rd_b, self._bond_type(Chem, bond.order))
            rd_bond = (
                rw.GetBondBetweenAtoms(rd_a, rd_b)
                if hasattr(rw, "GetBondBetweenAtoms")
                else None
            )
            if rd_bond is None:
                continue
            if bond.style == "wedge":
                rd_bond.SetBondDir(Chem.BondDir.BEGINWEDGE)
            elif bond.style == "hash":
                rd_bond.SetBondDir(Chem.BondDir.BEGINDASH)
        return True

    def _attach_conversion_conformer(
        self, mol, coord_map: dict[int, tuple[float, float]], Chem
    ) -> None:
        if not hasattr(Chem, "Conformer"):
            return
        try:
            conf = Chem.Conformer(mol.GetNumAtoms())
            for atom_idx in range(mol.GetNumAtoms()):
                x, y = coord_map.get(atom_idx, (0.0, 0.0))
                # Canvas y grows downward; RDKit perceives wedge/hash chirality
                # from a y-up depiction (same negation the molfile writer
                # applies), so an unflipped y would tag every stereocenter as
                # its enantiomer.
                conf.SetAtomPosition(atom_idx, (x, -y, 0.0))
            mol.AddConformer(conf, assignId=True)
        except Exception:
            logger.debug(
                "Attaching 2D conformer for conversion failed; continuing.",
                exc_info=True,
            )

    def _build_conversion_rdkit_mol(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ):
        result = self._build_conversion_rdkit_mol_with_origins(
            model,
            atom_annotations=atom_annotations,
        )
        return None if result is None else result[0]

    def _build_conversion_rdkit_mol_with_origins(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ):
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = RDKIT_UNAVAILABLE_MESSAGE
            return None
        Chem, AllChem = rdkit
        rw = Chem.RWMol()
        adjacency = self._build_model_adjacency(model)
        valid_bonds = self._valid_conversion_bonds(model)
        active_annotations = (
            model.atom_annotations if atom_annotations is None else atom_annotations
        )

        atom_result = self._add_conversion_atoms(
            model,
            atom_annotations=active_annotations,
            adjacency=adjacency,
            rw=rw,
            Chem=Chem,
            AllChem=AllChem,
        )
        if atom_result is None:
            return None
        atom_map, coord_map, origins = atom_result

        if not self._add_conversion_bonds(
            valid_bonds, atom_map=atom_map, rw=rw, Chem=Chem
        ):
            return None

        mol = rw.GetMol()
        self._attach_conversion_conformer(mol, coord_map, Chem)
        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:

            def source_atom(match: re.Match[str]) -> str:
                index = int(match.group(1))
                origin = origins.get(index)
                if origin is None:
                    return f"RDKit atom index {index}"
                atom_id, origin_kind = origin
                label = model.atoms[atom_id].element
                suffix = " alias expansion" if origin_kind == "alias_expansion" else ""
                return f"Chemvas atom {atom_id} ({label}{suffix})"

            reason = re.sub(r"atom #\s*(\d+)", source_atom, str(exc))
            self.adapter.last_error = (
                f"3D conversion produced an invalid structure: {reason}"
            )
            return None
        # Stereo cleaning needs sanitized hybridization and ring membership;
        # otherwise supported bridgehead nitrogen centres are discarded.
        self._assign_conversion_stereo(mol, Chem)
        for bond_id, bond in valid_bonds:
            if bond.style == "double_either":
                # Stereo cleaning can discard an explicit either flag (including
                # on non-stereogenic doubles). Restore the native user's marker;
                # the drawing's coordinates must not choose an E/Z assignment.
                rd_bond = mol.GetBondBetweenAtoms(atom_map[bond.a], atom_map[bond.b])
                rd_bond.SetStereo(Chem.BondStereo.STEREOANY)
                rd_bond.SetBondDir(Chem.BondDir.EITHERDOUBLE)
                continue
            if bond.style not in {"wedge", "hash"}:
                continue
            start = mol.GetAtomWithIdx(atom_map[bond.a])
            if start.GetChiralTag() not in {
                Chem.ChiralType.CHI_TETRAHEDRAL_CW,
                Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
            }:
                self.adapter.last_error = (
                    f"Bond {bond_id} ({bond.a}-{bond.b}) has a {bond.style} whose "
                    f"narrow end at atom {bond.a} does not define supported "
                    "tetrahedral stereochemistry. Check its direction and "
                    "substituents; axial and other non-tetrahedral stereo are "
                    "not supported for chemical conversion."
                )
                return None
        if not self._consistent_conversion_wedges(mol, Chem, valid_bonds, atom_map):
            return None
        if not self._assign_drawn_double_stereo(
            mol, Chem, model, valid_bonds, atom_map, adjacency
        ):
            return None
        return mol, origins

    def model_to_calculation_artifacts(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> CalculationArtifacts | None:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = RDKIT_UNAVAILABLE_MESSAGE
            return None
        Chem, AllChem = rdkit
        built = self._build_conversion_rdkit_mol_with_origins(
            model,
            atom_annotations=atom_annotations,
        )
        if built is None:
            return None
        mol, origins = built

        mol_block = self._conversion_mol_block(mol, Chem, AllChem)

        mol_h = self.adapter._embed_3d_molecule(mol, Chem, AllChem)
        if mol_h is None:
            return None
        conformer = mol_h.GetConformer()
        xyz_lines = [str(mol_h.GetNumAtoms()), "Chemvas geometry v1"]
        atom_map: list[AtomMapEntry] = []
        base_atom_count = mol.GetNumAtoms()
        for atom_index, rd_atom in enumerate(mol_h.GetAtoms()):
            position = conformer.GetAtomPosition(atom_index)
            symbol = rd_atom.GetSymbol()
            xyz_lines.append(
                f"{symbol:<2} {position.x:.8f} {position.y:.8f} {position.z:.8f}"
            )
            if atom_index < base_atom_count:
                chemvas_atom_id, origin = origins[atom_index]
                atom_map.append(
                    AtomMapEntry(
                        xyz_index=atom_index + 1,
                        mol_index=atom_index + 1,
                        symbol=symbol,
                        origin=origin,
                        chemvas_atom_id=chemvas_atom_id,
                    )
                )
                continue

            neighbors = list(rd_atom.GetNeighbors())
            parent_index = neighbors[0].GetIdx() if len(neighbors) == 1 else None
            parent_origin = (
                origins.get(parent_index) if parent_index is not None else None
            )
            atom_map.append(
                AtomMapEntry(
                    xyz_index=atom_index + 1,
                    mol_index=None,
                    symbol=symbol,
                    origin="implicit_hydrogen",
                    chemvas_atom_id=None,
                    parent_xyz_index=(
                        parent_index + 1 if parent_index is not None else None
                    ),
                    parent_chemvas_atom_id=(
                        parent_origin[0] if parent_origin is not None else None
                    ),
                )
            )

        rd_base = getattr(Chem, "rdBase", None)
        rdkit_version = str(getattr(rd_base, "rdkitVersion", "unknown"))
        optimization_result = "not_recorded"
        if hasattr(mol_h, "HasProp") and mol_h.HasProp("_ChemvasOptimizationResult"):
            optimization_result = str(mol_h.GetProp("_ChemvasOptimizationResult"))
        return CalculationArtifacts(
            mol_block=mol_block,
            xyz_block="\n".join(xyz_lines) + "\n",
            atom_map=tuple(atom_map),
            rdkit_version=rdkit_version,
            rdkit_formal_charge=sum(
                int(atom.GetFormalCharge()) for atom in mol.GetAtoms()
            ),
            rdkit_radical_electrons=sum(
                int(atom.GetNumRadicalElectrons()) for atom in mol.GetAtoms()
            ),
            electron_count=(
                sum(int(atom.GetAtomicNum()) for atom in mol_h.GetAtoms())
                - sum(int(atom.GetFormalCharge()) for atom in mol.GetAtoms())
            ),
            geometry_embedding="ETKDGv3",
            geometry_random_seed=0xC0FFEE,
            geometry_optimization_policy="MMFF when parameterized, otherwise UFF",
            geometry_optimization_result=optimization_result,
            mol_atom_count=base_atom_count,
            xyz_atom_count=mol_h.GetNumAtoms(),
        )

    def model_to_3d_scene(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> Molecule3DScene | None:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = RDKIT_UNAVAILABLE_MESSAGE
            return None
        if not model.atoms:
            self.adapter.last_error = "There is no chemical structure to preview."
            return None
        Chem, AllChem = rdkit
        components = self._model_components(model)
        component_for_atom = {
            atom_id: index
            for index, atom_ids in enumerate(components)
            for atom_id in atom_ids
        }
        component_bonds: list[list[Bond]] = [[] for _ in components]
        # Partition once in source order; scanning the whole bond list for each
        # disconnected component makes preview preparation quadratic.
        for bond in model.bonds:
            if bond is None:
                continue
            index = component_for_atom.get(bond.a)
            if index is not None and component_for_atom.get(bond.b) == index:
                component_bonds[index].append(bond)
        component_scenes: list[Molecule3DScene] = []
        for component_atom_ids, bonds in zip(components, component_bonds, strict=True):
            component_model, component_annotations = self._build_component_model(
                model,
                component_atom_ids,
                atom_annotations=atom_annotations,
                bonds=bonds,
            )
            mol = self.adapter._build_conversion_rdkit_mol(
                component_model,
                atom_annotations=component_annotations,
            )
            if mol is None:
                if self.adapter.last_error is None:
                    self.adapter.last_error = "Failed to build a 3D preview structure."
                return None
            mol_h = self.adapter._embed_3d_molecule(mol, Chem, AllChem)
            if mol_h is None:
                return None
            component_scenes.append(self._scene_from_embedded_mol(mol_h))
        return self._layout_component_scenes(component_scenes)

    def model_to_xyz_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        scene = self.adapter.model_to_3d_scene(model, atom_annotations=atom_annotations)
        if scene is None:
            return None
        lines = [str(len(scene.atoms)), "Chemvas XYZ export"]
        for atom in scene.atoms:
            lines.append(f"{atom.symbol:<2} {atom.x:.6f} {atom.y:.6f} {atom.z:.6f}")
        return "\n".join(lines) + "\n"

    def model_to_mol_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = RDKIT_UNAVAILABLE_MESSAGE
            return None
        Chem, AllChem = rdkit
        # Reuse the 3D conversion builder so abbreviation labels (Ph, CF3, ...) are
        # expanded into explicit atoms and charge/stereo are applied. Then lay the
        # heavy-atom graph out in 2D for a conventional MDL depiction.
        mol = self.adapter._build_conversion_rdkit_mol(
            model, atom_annotations=atom_annotations
        )
        if mol is None:
            return None
        return self._conversion_mol_block(mol, Chem, AllChem)

    @staticmethod
    def _conversion_mol_block(mol, Chem, AllChem) -> str:
        """Regenerate the depiction and omit only chemically redundant valence."""
        depicted = Chem.Mol(mol)
        AllChem.Compute2DCoords(depicted)
        # Original wedge directions describe the old canvas coordinates. Derive
        # new wedges from the assigned stereo tags after regenerating the layout.
        for bond in depicted.GetBonds():
            if bond.GetBondDir() != Chem.BondDir.EITHERDOUBLE:
                bond.SetBondDir(Chem.BondDir.NONE)
        conformer = depicted.GetConformer()
        Chem.WedgeMolBonds(depicted, conformer)
        block = Chem.MolToMolBlock(depicted)
        lines = block.splitlines()
        if not lines[3].endswith("V2000"):
            return block
        # RDKit writes valence 3 for a carbon radical and 15 for zero-valent
        # ions even when M RAD/M CHG already convey everything. The native
        # reader deliberately rejects nonzero valence fields, so omit them
        # only if an RDKit roundtrip confirms that chemistry is unchanged.
        for index in range(4, 4 + depicted.GetNumAtoms()):
            lines[index] = lines[index][:48] + "  0" + lines[index][51:]
        candidate = "\n".join(lines) + "\n"
        original_mol = Chem.MolFromMolBlock(block, removeHs=False)
        candidate_mol = Chem.MolFromMolBlock(candidate, removeHs=False)
        if (
            original_mol is not None
            and candidate_mol is not None
            and Chem.MolToSmiles(original_mol) == Chem.MolToSmiles(candidate_mol)
        ):
            return candidate
        return block


__all__ = ["RDKitConversionHelper"]
