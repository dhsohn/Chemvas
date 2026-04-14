from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Optional

from core.model import Bond, MoleculeModel


@dataclass(frozen=True)
class Molecule3DAtom:
    symbol: str
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Molecule3DBond:
    a: int
    b: int
    order: int


@dataclass(frozen=True)
class Molecule3DScene:
    atoms: tuple[Molecule3DAtom, ...]
    bonds: tuple[Molecule3DBond, ...]


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
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, AllChem = rdkit
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            self.last_error = (
                "Invalid SMILES string. Example: CC(=O)O (acetic acid), "
                "c1ccccc1 (benzene), C1CCCCC1 (cyclohexane)."
            )
            return None
        AllChem.Compute2DCoords(mol)

        conf = mol.GetConformer()
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
                for i, (x1, y1) in enumerate(positions):
                    min_dist = None
                    for j, (x2, y2) in enumerate(positions):
                        if i == j:
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
        for atom in mol.GetAtoms():
            x, y = pos_by_idx[atom.GetIdx()]
            model.add_atom(atom.GetSymbol(), x * scale_factor, -y * scale_factor)

        for bond in mol.GetBonds():
            order = int(bond.GetBondTypeAsDouble())
            model.add_bond(bond.GetBeginAtomIdx(), bond.GetEndAtomIdx(), order)

        return model

    def _build_rdkit_mol_with_map(
        self,
        model: MoleculeModel,
        *,
        strict_labels: bool = False,
        unsupported_bond_styles: set[str] | None = None,
    ):
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None, None
        Chem, _ = rdkit
        rw = Chem.RWMol()
        adjacency = self._build_model_adjacency(model)
        atom_map = {}
        invalid_labels: list[str] = []
        for atom_id in sorted(model.atoms):
            atom = model.atoms[atom_id]
            try:
                rd_atom = Chem.Atom(atom.element)
            except Exception:
                if strict_labels:
                    invalid_labels.append(f"{atom.element} (atom {atom_id})")
                    continue
                rd_atom = Chem.Atom("C")
            if self._should_disable_implicit_hydrogens(model, atom_id, adjacency):
                rd_atom.SetNoImplicit(True)
            atom_map[atom_id] = rw.AddAtom(rd_atom)
        if invalid_labels:
            detail = ", ".join(invalid_labels[:5])
            if len(invalid_labels) > 5:
                detail = f"{detail}, ..."
            self.last_error = (
                "XYZ export supports element symbols only. "
                f"Unsupported atom labels: {detail}."
            )
            return None, None
        valid_atoms = set(atom_map.keys())
        seen_bonds: set[tuple[int, int]] = set()
        unsupported_styles: list[str] = []
        for bond_id, bond in enumerate(model.bonds):
            if bond is None:
                continue
            if bond.a == bond.b:
                continue
            if bond.a not in valid_atoms or bond.b not in valid_atoms:
                continue
            if unsupported_bond_styles and bond.style in unsupported_bond_styles:
                unsupported_styles.append(f"{bond.style} (bond {bond_id})")
                continue
            key = (bond.a, bond.b) if bond.a <= bond.b else (bond.b, bond.a)
            if key in seen_bonds:
                continue
            seen_bonds.add(key)
            btype = self._bond_type(Chem, bond.order)
            rw.AddBond(atom_map[bond.a], atom_map[bond.b], btype)
        if unsupported_styles:
            detail = ", ".join(unsupported_styles[:5])
            if len(unsupported_styles) > 5:
                detail = f"{detail}, ..."
            self.last_error = (
                "XYZ export does not yet support wedge/hash stereobonds. "
                f"Unsupported bond styles: {detail}."
            )
            return None, None
        mol = rw.GetMol()
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            pass
        return mol, atom_map

    def model_to_rdkit_with_map(self, model: MoleculeModel):
        return self._build_rdkit_mol_with_map(model)

    def model_to_rdkit(self, model: MoleculeModel):
        mol, _ = self.model_to_rdkit_with_map(model)
        return mol

    def compute_props(self, model: MoleculeModel) -> tuple[str | None, float | None, str | None]:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None, None, None
        Chem, _ = rdkit
        mol = self.model_to_rdkit(model)
        if mol is None:
            return None, None, None
        try:
            mol_h = Chem.AddHs(mol)
            from rdkit.Chem import Descriptors, rdMolDescriptors

            formula = rdMolDescriptors.CalcMolFormula(mol_h)
            mw = Descriptors.MolWt(mol_h)
            smiles = Chem.MolToSmiles(mol, canonical=True)
            return formula, mw, smiles
        except Exception:
            return None, None, None

    def _embed_3d_molecule(self, mol, Chem, AllChem):
        try:
            mol_h = Chem.AddHs(mol)
            params = AllChem.ETKDGv3()
            params.randomSeed = 0xC0FFEE
            status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                params.useRandomCoords = True
                status = AllChem.EmbedMolecule(mol_h, params)
            if status != 0:
                self.last_error = "3D embedding failed."
                return None
            try:
                if hasattr(AllChem, "MMFFHasAllMoleculeParams") and AllChem.MMFFHasAllMoleculeParams(mol_h):
                    AllChem.MMFFOptimizeMolecule(mol_h, maxIters=50)
                else:
                    AllChem.UFFOptimizeMolecule(mol_h, maxIters=50)
            except Exception:
                try:
                    AllChem.UFFOptimizeMolecule(mol_h, maxIters=50)
                except Exception:
                    pass
        except Exception as exc:
            self.last_error = f"3D coordinate generation failed: {exc}"
            return None
        if hasattr(mol_h, "GetNumConformers") and mol_h.GetNumConformers() == 0:
            self.last_error = "3D coordinate generation failed: no conformer."
            return None
        return mol_h

    def _bond_type(self, Chem, order: int):
        order_map = {
            1: Chem.BondType.SINGLE,
            2: Chem.BondType.DOUBLE,
            3: Chem.BondType.TRIPLE,
        }
        return order_map.get(order, Chem.BondType.SINGLE)

    def _annotation_for_atom(
        self,
        atom_annotations: Mapping[int, Mapping[str, int]] | None,
        atom_id: int,
    ) -> tuple[int, int]:
        if atom_annotations is None:
            return 0, 0
        annotation = atom_annotations.get(atom_id)
        if annotation is None:
            return 0, 0
        formal_charge = int(annotation.get("formal_charge", 0))
        radical_electrons = int(annotation.get("radical_electrons", 0))
        return formal_charge, radical_electrons

    @staticmethod
    def _format_atom_refs(refs: list[str]) -> str:
        detail = ", ".join(refs[:5])
        if len(refs) > 5:
            detail = f"{detail}, ..."
        return detail

    def _apply_atom_annotation(self, rd_atom, *, formal_charge: int, radical_electrons: int) -> None:
        if formal_charge:
            rd_atom.SetFormalCharge(formal_charge)
        if radical_electrons:
            rd_atom.SetNumRadicalElectrons(radical_electrons)

    @staticmethod
    def _build_model_adjacency(model: MoleculeModel) -> dict[int, list[int]]:
        adjacency: dict[int, list[int]] = {atom_id: [] for atom_id in model.atoms}
        for bond in model.bonds:
            if bond is None or bond.a == bond.b:
                continue
            if bond.a not in model.atoms or bond.b not in model.atoms:
                continue
            adjacency.setdefault(bond.a, []).append(bond.b)
            adjacency.setdefault(bond.b, []).append(bond.a)
        return adjacency

    @staticmethod
    def _should_disable_implicit_hydrogens(
        model: MoleculeModel,
        atom_id: int,
        adjacency: Mapping[int, list[int]],
    ) -> bool:
        atom = model.atoms.get(atom_id)
        if atom is None or atom.element.upper() == "C":
            return False
        for neighbor_id in adjacency.get(atom_id, []):
            neighbor = model.atoms.get(neighbor_id)
            if neighbor is not None and neighbor.element.upper() == "H":
                return True
        return False

    @staticmethod
    def _component_sort_key(model: MoleculeModel, atom_ids: set[int]) -> tuple[float, float, int]:
        xs = [model.atoms[atom_id].x for atom_id in atom_ids if atom_id in model.atoms]
        ys = [model.atoms[atom_id].y for atom_id in atom_ids if atom_id in model.atoms]
        center_x = (min(xs) + max(xs)) * 0.5 if xs else 0.0
        center_y = (min(ys) + max(ys)) * 0.5 if ys else 0.0
        return center_x, center_y, min(atom_ids) if atom_ids else -1

    def _model_components(self, model: MoleculeModel) -> list[set[int]]:
        adjacency = self._build_model_adjacency(model)
        seen: set[int] = set()
        components: list[set[int]] = []
        for start_atom_id in sorted(model.atoms):
            if start_atom_id in seen:
                continue
            component: set[int] = set()
            stack = [start_atom_id]
            seen.add(start_atom_id)
            while stack:
                current = stack.pop()
                component.add(current)
                for neighbor_id in adjacency.get(current, []):
                    if neighbor_id in seen:
                        continue
                    seen.add(neighbor_id)
                    stack.append(neighbor_id)
            components.append(component)
        components.sort(key=lambda atom_ids: self._component_sort_key(model, atom_ids))
        return components

    def _build_component_model(
        self,
        model: MoleculeModel,
        atom_ids: set[int],
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> tuple[MoleculeModel, dict[int, dict[str, int]]]:
        component_model = MoleculeModel()
        id_map: dict[int, int] = {}
        for old_id in sorted(atom_ids):
            atom = model.atoms.get(old_id)
            if atom is None:
                continue
            new_id = component_model.add_atom(atom.element, atom.x, atom.y)
            component_model.atoms[new_id].color = atom.color
            component_model.atoms[new_id].explicit_label = atom.explicit_label
            id_map[old_id] = new_id
        for bond in model.bonds:
            if bond is None:
                continue
            if bond.a not in id_map or bond.b not in id_map:
                continue
            component_model.bonds.append(
                Bond(
                    a=id_map[bond.a],
                    b=id_map[bond.b],
                    order=bond.order,
                    style=bond.style,
                    color=bond.color,
                )
            )
        component_annotations: dict[int, dict[str, int]] = {}
        if atom_annotations:
            for old_id, new_id in id_map.items():
                values = atom_annotations.get(old_id)
                if not values:
                    continue
                component_annotations[new_id] = {
                    key: int(value)
                    for key, value in values.items()
                }
        return component_model, component_annotations

    @staticmethod
    def _scene_from_embedded_mol(mol_h) -> Molecule3DScene:
        conf = mol_h.GetConformer()
        atoms = tuple(
            Molecule3DAtom(
                symbol=atom.GetSymbol(),
                x=conf.GetAtomPosition(atom.GetIdx()).x,
                y=conf.GetAtomPosition(atom.GetIdx()).y,
                z=conf.GetAtomPosition(atom.GetIdx()).z,
            )
            for atom in mol_h.GetAtoms()
        )
        bond_iterable = mol_h.GetBonds() if hasattr(mol_h, "GetBonds") else ()
        bonds = tuple(
            Molecule3DBond(
                a=bond.GetBeginAtomIdx(),
                b=bond.GetEndAtomIdx(),
                order=max(1, int(round(bond.GetBondTypeAsDouble()))),
            )
            for bond in bond_iterable
        )
        return Molecule3DScene(atoms=atoms, bonds=bonds)

    @staticmethod
    def _scene_bounds(scene: Molecule3DScene) -> tuple[float, float, float, float, float, float]:
        xs = [atom.x for atom in scene.atoms]
        ys = [atom.y for atom in scene.atoms]
        zs = [atom.z for atom in scene.atoms]
        return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)

    @staticmethod
    def _translate_scene(
        scene: Molecule3DScene,
        *,
        dx: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ) -> Molecule3DScene:
        return Molecule3DScene(
            atoms=tuple(
                Molecule3DAtom(
                    symbol=atom.symbol,
                    x=atom.x + dx,
                    y=atom.y + dy,
                    z=atom.z + dz,
                )
                for atom in scene.atoms
            ),
            bonds=scene.bonds,
        )

    def _layout_component_scenes(
        self,
        component_scenes: list[Molecule3DScene],
        *,
        gap: float = 2.5,
    ) -> Molecule3DScene:
        if not component_scenes:
            return Molecule3DScene(atoms=(), bonds=())
        if len(component_scenes) == 1:
            return component_scenes[0]

        combined_atoms: list[Molecule3DAtom] = []
        combined_bonds: list[Molecule3DBond] = []
        atom_offset = 0
        cursor_right: float | None = None
        for scene in component_scenes:
            min_x, max_x, min_y, max_y, min_z, max_z = self._scene_bounds(scene)
            centered_scene = self._translate_scene(
                scene,
                dx=-((min_x + max_x) * 0.5),
                dy=-((min_y + max_y) * 0.5),
                dz=-((min_z + max_z) * 0.5),
            )
            centered_min_x, centered_max_x, _, _, _, _ = self._scene_bounds(centered_scene)
            shift_x = 0.0 if cursor_right is None else cursor_right + gap - centered_min_x
            shifted_scene = self._translate_scene(centered_scene, dx=shift_x)
            combined_atoms.extend(shifted_scene.atoms)
            combined_bonds.extend(
                Molecule3DBond(
                    a=bond.a + atom_offset,
                    b=bond.b + atom_offset,
                    order=bond.order,
                )
                for bond in shifted_scene.bonds
            )
            _, shifted_max_x, _, _, _, _ = self._scene_bounds(shifted_scene)
            cursor_right = shifted_max_x
            atom_offset += len(shifted_scene.atoms)
        return Molecule3DScene(atoms=tuple(combined_atoms), bonds=tuple(combined_bonds))

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
        alias_smiles = self._alias_smiles.get(label)
        if alias_smiles is None:
            return None, None
        if len(neighbors) != 1:
            self.last_error = (
                f"Alias label '{label}' on atom {atom_id} requires exactly one attachment bond "
                f"for 3D conversion, but found {len(neighbors)}."
            )
            return None, None
        fragment = Chem.MolFromSmiles(alias_smiles)
        if fragment is None:
            self.last_error = f"Failed to expand alias label '{label}' for 3D conversion."
            return None, None
        if hasattr(AllChem, "Compute2DCoords"):
            try:
                AllChem.Compute2DCoords(fragment)
            except Exception:
                pass
        dummy_atoms = [frag_atom for frag_atom in fragment.GetAtoms() if frag_atom.GetAtomicNum() == 0]
        if len(dummy_atoms) != 1:
            self.last_error = f"Alias label '{label}' has an invalid attachment definition."
            return None, None
        dummy_atom = dummy_atoms[0]
        dummy_idx = dummy_atom.GetIdx()
        dummy_neighbors = list(dummy_atom.GetNeighbors())
        if len(dummy_neighbors) != 1:
            self.last_error = f"Alias label '{label}' has an invalid attachment topology."
            return None, None
        attachment_idx = dummy_neighbors[0].GetIdx()
        fragment_map: dict[int, int] = {}
        coord_map: dict[int, tuple[float, float]] = {}
        attachment_new_idx = None
        for frag_atom in fragment.GetAtoms():
            if frag_atom.GetIdx() == dummy_idx:
                continue
            new_atom = Chem.Atom(frag_atom)
            if frag_atom.GetIdx() == attachment_idx:
                self._apply_atom_annotation(
                    new_atom,
                    formal_charge=formal_charge,
                    radical_electrons=radical_electrons,
                )
            new_idx = rw.AddAtom(new_atom)
            fragment_map[frag_atom.GetIdx()] = new_idx
            if frag_atom.GetIdx() == attachment_idx:
                attachment_new_idx = new_idx
        for frag_bond in fragment.GetBonds():
            begin_idx = frag_bond.GetBeginAtomIdx()
            end_idx = frag_bond.GetEndAtomIdx()
            if dummy_idx in {begin_idx, end_idx}:
                continue
            rw.AddBond(
                fragment_map[begin_idx],
                fragment_map[end_idx],
                frag_bond.GetBondType(),
            )
        if attachment_new_idx is None:
            self.last_error = f"Alias label '{label}' could not be attached."
            return None, None

        conf = fragment.GetConformer() if fragment.GetNumConformers() else None
        if conf is None:
            coord_map[attachment_new_idx] = (atom.x, atom.y)
            return attachment_new_idx, coord_map

        dummy_pos = conf.GetAtomPosition(dummy_idx)
        attach_pos = conf.GetAtomPosition(attachment_idx)
        source_dx = dummy_pos.x - attach_pos.x
        source_dy = dummy_pos.y - attach_pos.y
        neighbor_atom = model.atoms.get(neighbors[0])
        if neighbor_atom is None:
            self.last_error = f"Alias label '{label}' is attached to a missing atom."
            return None, None
        target_dx = neighbor_atom.x - atom.x
        target_dy = neighbor_atom.y - atom.y
        source_angle = math.atan2(source_dy, source_dx) if abs(source_dx) > 1e-6 or abs(source_dy) > 1e-6 else 0.0
        target_angle = math.atan2(target_dy, target_dx) if abs(target_dx) > 1e-6 or abs(target_dy) > 1e-6 else 0.0
        rotation = target_angle - source_angle
        cos_theta = math.cos(rotation)
        sin_theta = math.sin(rotation)
        for frag_atom in fragment.GetAtoms():
            if frag_atom.GetIdx() == dummy_idx:
                continue
            frag_pos = conf.GetAtomPosition(frag_atom.GetIdx())
            rel_x = frag_pos.x - attach_pos.x
            rel_y = frag_pos.y - attach_pos.y
            rot_x = rel_x * cos_theta - rel_y * sin_theta
            rot_y = rel_x * sin_theta + rel_y * cos_theta
            coord_map[fragment_map[frag_atom.GetIdx()]] = (atom.x + rot_x, atom.y + rot_y)
        return attachment_new_idx, coord_map

    def _build_conversion_rdkit_mol(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ):
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            self.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        rw = Chem.RWMol()
        adjacency = self._build_model_adjacency(model)
        valid_bonds: list[tuple[int, object]] = []
        for bond_id, bond in enumerate(model.bonds):
            if bond is None or bond.a == bond.b:
                continue
            if bond.a not in model.atoms or bond.b not in model.atoms:
                continue
            valid_bonds.append((bond_id, bond))

        atom_map: dict[int, int] = {}
        coord_map: dict[int, tuple[float, float]] = {}
        invalid_labels: list[str] = []
        for atom_id in sorted(model.atoms):
            atom = model.atoms[atom_id]
            formal_charge, radical_electrons = self._annotation_for_atom(atom_annotations, atom_id)
            if atom.element in self._alias_smiles:
                attachment_idx, alias_coords = self._build_alias_fragment(
                    atom.element,
                    atom_id=atom_id,
                    atom=atom,
                    neighbors=adjacency.get(atom_id, []),
                    model=model,
                    formal_charge=formal_charge,
                    radical_electrons=radical_electrons,
                    rw=rw,
                    Chem=Chem,
                    AllChem=AllChem,
                )
                if attachment_idx is None or alias_coords is None:
                    return None
                atom_map[atom_id] = attachment_idx
                coord_map.update(alias_coords)
                continue
            try:
                rd_atom = Chem.Atom(atom.element)
            except Exception:
                invalid_labels.append(f"{atom.element} (atom {atom_id})")
                continue
            if self._should_disable_implicit_hydrogens(model, atom_id, adjacency):
                rd_atom.SetNoImplicit(True)
            self._apply_atom_annotation(
                rd_atom,
                formal_charge=formal_charge,
                radical_electrons=radical_electrons,
            )
            new_idx = rw.AddAtom(rd_atom)
            atom_map[atom_id] = new_idx
            coord_map[new_idx] = (atom.x, atom.y)

        if invalid_labels:
            supported_aliases = ", ".join(sorted(self._alias_smiles))
            self.last_error = (
                "Unsupported atom labels for 3D conversion: "
                f"{self._format_atom_refs(invalid_labels)}. "
                f"Supported aliases: {supported_aliases}."
            )
            return None

        seen_bonds: set[tuple[int, int]] = set()
        for bond_id, bond in valid_bonds:
            if bond.a not in atom_map or bond.b not in atom_map:
                continue
            rd_a = atom_map[bond.a]
            rd_b = atom_map[bond.b]
            key = (rd_a, rd_b) if rd_a <= rd_b else (rd_b, rd_a)
            if key in seen_bonds:
                continue
            seen_bonds.add(key)
            if bond.style in {"wedge", "hash"} and bond.order != 1:
                self.last_error = (
                    f"Bond {bond_id} uses style '{bond.style}' with order {bond.order}. "
                    "Stereo export currently supports wedge/hash on single bonds only."
                )
                return None
            rw.AddBond(rd_a, rd_b, self._bond_type(Chem, bond.order))
            rd_bond = rw.GetBondBetweenAtoms(rd_a, rd_b) if hasattr(rw, "GetBondBetweenAtoms") else None
            if rd_bond is None:
                continue
            if bond.style == "wedge":
                rd_bond.SetBondDir(Chem.BondDir.BEGINWEDGE)
            elif bond.style == "hash":
                rd_bond.SetBondDir(Chem.BondDir.BEGINDASH)

        mol = rw.GetMol()
        if hasattr(Chem, "Conformer"):
            try:
                conf = Chem.Conformer(mol.GetNumAtoms())
                for atom_idx in range(mol.GetNumAtoms()):
                    x, y = coord_map.get(atom_idx, (0.0, 0.0))
                    conf.SetAtomPosition(atom_idx, (x, y, 0.0))
                mol.AddConformer(conf, assignId=True)
            except Exception:
                pass
        try:
            if hasattr(Chem, "AssignChiralTypesFromBondDirs"):
                Chem.AssignChiralTypesFromBondDirs(mol)
            if hasattr(Chem, "SetBondStereoFromDirections"):
                Chem.SetBondStereoFromDirections(mol)
            if hasattr(Chem, "AssignStereochemistry"):
                Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
        except Exception:
            pass
        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:
            self.last_error = f"3D conversion produced an invalid structure: {exc}"
            return None
        return mol

    def model_to_3d_coords(self, model: MoleculeModel):
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            self.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        mol, atom_map = self.model_to_rdkit_with_map(model)
        if mol is None or atom_map is None:
            self.last_error = "Failed to build RDKit molecule."
            return None
        mol_h = self._embed_3d_molecule(mol, Chem, AllChem)
        if mol_h is None:
            return None
        conf = mol_h.GetConformer()
        coords = {}
        for atom_id, rd_idx in atom_map.items():
            pos = conf.GetAtomPosition(rd_idx)
            coords[atom_id] = (pos.x, pos.y, pos.z)
        return coords

    def model_to_3d_scene(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> Molecule3DScene | None:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            self.last_error = "RDKit is not available in this environment."
            return None
        if not model.atoms:
            self.last_error = "There is no chemical structure to preview."
            return None
        Chem, AllChem = rdkit
        component_scenes: list[Molecule3DScene] = []
        for component_atom_ids in self._model_components(model):
            component_model, component_annotations = self._build_component_model(
                model,
                component_atom_ids,
                atom_annotations=atom_annotations,
            )
            mol = self._build_conversion_rdkit_mol(
                component_model,
                atom_annotations=component_annotations,
            )
            if mol is None:
                if self.last_error is None:
                    self.last_error = "Failed to build a 3D preview structure."
                return None
            mol_h = self._embed_3d_molecule(mol, Chem, AllChem)
            if mol_h is None:
                return None
            component_scenes.append(self._scene_from_embedded_mol(mol_h))
        return self._layout_component_scenes(component_scenes)

    def model_to_xyz_block(
        self,
        model: MoleculeModel,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ) -> str | None:
        scene = self.model_to_3d_scene(model, atom_annotations=atom_annotations)
        if scene is None:
            return None
        lines = [str(len(scene.atoms)), "LiteDraw XYZ export"]
        for atom in scene.atoms:
            lines.append(f"{atom.symbol:<2} {atom.x:.6f} {atom.y:.6f} {atom.z:.6f}")
        return "\n".join(lines) + "\n"

    def get_name_from_smiles(self, smiles: str) -> str | None:
        rdkit = self._load_rdkit()
        if rdkit == (None, None):
            return None
        Chem, _ = rdkit
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                return None
            canonical = Chem.MolToSmiles(mol, canonical=True)
            return self._name_map.get(canonical)
        except Exception:
            return None

    def model_to_3d(self, model: MoleculeModel):
        return self.model_to_3d_coords(model)
