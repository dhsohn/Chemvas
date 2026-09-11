from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any, cast

from chemvas.domain.atom_aliases import ATOM_ALIAS_DEFINITIONS
from chemvas.domain.document import MoleculeModel
from chemvas.features.insertion import MoleculeIdentifiers

if TYPE_CHECKING:
    from chemvas.core.rdkit_adapter import RDKitAdapter


class RDKitImportHelper:
    def __init__(self, adapter: RDKitAdapter) -> None:
        self.adapter = adapter

    def smiles_to_2d(self, smiles: str, scale: float = 40.0) -> MoleculeModel | None:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, AllChem = rdkit
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.adapter.last_error = (
                "Invalid SMILES string. Example: CC(=O)O (acetic acid), "
                "c1ccccc1 (benzene), C1CCCCC1 (cyclohexane)."
            )
            return None
        # The whole-molecule racemic flag does not create a StereoGroup. Read
        # the extension retained by RDKit: legal atom labels may themselves
        # contain pipes, so splitting the user's text at a pipe is ambiguous.
        cx_fields = (
            mol.GetProp("_CXSMILES_Data")[1:-1] if mol.HasProp("_CXSMILES_Data") else ""
        )
        cx_fields = re.sub(r"\$[^$]*\$", "", cx_fields)
        if re.search(r"(?:^|,)\s*r\s*(?:,|$)", cx_fields):
            self.adapter.last_error = (
                "Cannot insert this SMILES: relative or racemic stereochemistry "
                "cannot be preserved as absolute wedge/hash bonds."
            )
            return None
        # "Ts" (tosyl) and "Ac" (acetyl) are element symbols too, so RDKit
        # returns tennessine and actinium for them. A canvas label of either
        # kind means the abbreviation, so placing one would put a different
        # molecule on the canvas than the SMILES asked for.
        shadowed = sorted(
            {atom.GetSymbol() for atom in mol.GetAtoms()}
            & set(self.adapter._alias_smiles)
        )
        if shadowed:
            self.adapter.last_error = (
                "Cannot insert this SMILES: Chemvas draws these element symbols "
                "as abbreviation labels instead: " + ", ".join(shadowed) + "."
            )
            return None
        # The document model has no isotope representation, so accepting the
        # input would silently draw the unlabeled isotopologue — every formula,
        # identifier, and export would then describe a different compound than
        # the SMILES asked for.
        isotopes = sorted(
            {
                f"{atom.GetIsotope()}{atom.GetSymbol()}"
                for atom in mol.GetAtoms()
                if atom.GetIsotope()
            }
        )
        if isotopes:
            self.adapter.last_error = (
                "Cannot insert this SMILES: Chemvas cannot represent isotope "
                "labels, so this would silently draw the unlabeled compound "
                "instead: " + ", ".join(isotopes) + "."
            )
            return None
        supported_chirality = {
            Chem.ChiralType.CHI_UNSPECIFIED,
            Chem.ChiralType.CHI_TETRAHEDRAL_CW,
            Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
        }
        if (
            any(
                atom.GetChiralTag() not in supported_chirality
                for atom in mol.GetAtoms()
            )
            or any(
                bond.GetStereo() != Chem.BondStereo.STEREONONE
                for bond in mol.GetBonds()
            )
            or any(
                group.GetGroupType() != Chem.StereoGroupType.STEREO_ABSOLUTE
                for group in mol.GetStereoGroups()
            )
        ):
            self.adapter.last_error = (
                "Cannot insert this SMILES: only absolute tetrahedral stereochemistry "
                "can be preserved as wedge/hash bonds. Double-bond, non-tetrahedral, "
                "and relative or racemic stereochemistry are not supported."
            )
            return None
        mol = self._kekulized_import_mol(Chem, mol)
        bond_orders = {
            Chem.BondType.SINGLE: 1,
            Chem.BondType.DOUBLE: 2,
            Chem.BondType.TRIPLE: 3,
        }
        unsupported_bond_types = sorted(
            {
                str(bond.GetBondType())
                for bond in mol.GetBonds()
                if bond.GetBondType() not in bond_orders
            }
        )
        if unsupported_bond_types:
            self.adapter.last_error = (
                "Cannot insert this SMILES: Chemvas cannot represent these bond "
                "types: " + ", ".join(unsupported_bond_types) + "."
            )
            return None
        AllChem.Compute2DCoords(mol)

        conf = mol.GetConformer()
        # RDKit may reverse bond endpoints so the stereocenter becomes the
        # beginning of a wedge. Read those endpoints only after wedging.
        Chem.WedgeMolBonds(mol, conf)
        pos_by_idx = {}
        for atom in mol.GetAtoms():
            pos = conf.GetAtomPosition(atom.GetIdx())
            pos_by_idx[atom.GetIdx()] = (pos.x, pos.y)

        bond_lengths = []
        for bond in mol.GetBonds():
            ax, ay = pos_by_idx[bond.GetBeginAtomIdx()]
            bx, by = pos_by_idx[bond.GetEndAtomIdx()]
            dist = math.hypot(ax - bx, ay - by)
            if dist > 0.0:
                bond_lengths.append(dist)
        if bond_lengths:
            avg_len = sum(bond_lengths) / len(bond_lengths)
        else:
            nearest = []
            positions = list(pos_by_idx.values())
            if len(positions) > 1:
                for index, (x1, y1) in enumerate(positions):
                    min_dist = None
                    for other_index, (x2, y2) in enumerate(positions):
                        if index == other_index:
                            continue
                        dist = math.hypot(x1 - x2, y1 - y2)
                        if dist <= 0.0:
                            continue
                        if min_dist is None or dist < min_dist:
                            min_dist = dist
                    if min_dist is not None:
                        nearest.append(min_dist)
            avg_len = sum(nearest) / len(nearest) if nearest else 0.0
        scale_factor = (scale / avg_len) if avg_len > 0.0 else 1.0

        model = MoleculeModel()
        atom_id_by_rd_idx: dict[int, int] = {}
        for atom in mol.GetAtoms():
            x, y = pos_by_idx[atom.GetIdx()]
            atom_id = model.add_atom(
                atom.GetSymbol(), x * scale_factor, -y * scale_factor
            )
            atom_id_by_rd_idx[atom.GetIdx()] = atom_id
            annotation = self._atom_annotation(atom)
            if annotation:
                model.atom_annotations[atom_id] = annotation

        for bond in mol.GetBonds():
            bond_id = model.add_bond(
                atom_id_by_rd_idx[bond.GetBeginAtomIdx()],
                atom_id_by_rd_idx[bond.GetEndAtomIdx()],
                bond_orders[bond.GetBondType()],
            )
            direction = bond.GetBondDir()
            if direction in (Chem.BondDir.BEGINWEDGE, Chem.BondDir.BEGINDASH):
                imported_bond = model.bonds[bond_id]
                assert imported_bond is not None
                imported_bond.style = (
                    "wedge" if direction == Chem.BondDir.BEGINWEDGE else "hash"
                )

        return model

    @staticmethod
    def _kekulized_import_mol(Chem, mol):
        try:
            has_aromatic_bond = any(
                bool(getattr(bond, "GetIsAromatic", lambda: False)())
                or abs(float(bond.GetBondTypeAsDouble()) - 1.5) < 1e-6
                for bond in mol.GetBonds()
            )
        except Exception:
            return mol
        if not has_aromatic_bond or not hasattr(Chem, "Kekulize"):
            return mol
        try:
            import_mol = Chem.Mol(mol) if hasattr(Chem, "Mol") else mol
            Chem.Kekulize(import_mol, clearAromaticFlags=True)
            return import_mol
        except Exception:
            return mol

    @staticmethod
    def _atom_annotation(atom) -> dict[str, int]:
        annotation: dict[str, int] = {}
        formal_charge_getter = getattr(atom, "GetFormalCharge", None)
        if callable(formal_charge_getter):
            formal_charge = int(formal_charge_getter())
            if formal_charge:
                annotation["formal_charge"] = formal_charge
        radical_getter = getattr(atom, "GetNumRadicalElectrons", None)
        if callable(radical_getter):
            radical_electrons = int(radical_getter())
            if radical_electrons:
                annotation["radical_electrons"] = radical_electrons
        return annotation

    def compute_props(
        self, model: MoleculeModel
    ) -> tuple[str | None, float | None, str | None]:
        identifiers = self.compute_identifiers(model)
        return identifiers.formula, identifiers.mw, identifiers.smiles

    def compute_identifiers(self, model: MoleculeModel) -> MoleculeIdentifiers:
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            return MoleculeIdentifiers()
        Chem, _ = rdkit
        # Terminal hydrides have a fixed H count and a shared attachment
        # validator. Other aliases, including the Ts/Ac element collisions,
        # retain the existing unavailable-identifier policy.
        if any(
            definition.terminal_hydrogens is None
            for atom in model.atoms.values()
            if (definition := ATOM_ALIAS_DEFINITIONS.get(atom.element)) is not None
        ):
            return MoleculeIdentifiers()
        mol = self.adapter._build_conversion_rdkit_mol(model)
        if mol is None:
            return MoleculeIdentifiers()
        try:
            mol_h = Chem.AddHs(mol)
            from rdkit.Chem import Descriptors, rdMolDescriptors

            formula = rdMolDescriptors.CalcMolFormula(mol_h)
            mw = cast("Any", Descriptors).MolWt(mol_h)
            smiles = Chem.MolToSmiles(mol, canonical=True)
        except Exception:
            return MoleculeIdentifiers()
        # InChI is computed separately so that a failure in the InChI backend
        # cannot blank out the formula/MW/SMILES we already have.
        try:
            inchi = Chem.MolToInchi(mol) or None
            inchikey = Chem.MolToInchiKey(mol) or None
        except Exception:
            inchi = None
            inchikey = None
        return MoleculeIdentifiers(
            formula=formula,
            mw=mw,
            smiles=smiles,
            inchi=inchi,
            inchikey=inchikey,
        )


__all__ = ["RDKitImportHelper"]
