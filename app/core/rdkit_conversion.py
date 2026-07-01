from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING

from core.model import Bond, MoleculeModel
from core.rdkit_types import Molecule3DAtom, Molecule3DBond, Molecule3DScene

if TYPE_CHECKING:
    from core.rdkit_adapter import RDKitAdapter

logger = logging.getLogger(__name__)


class RDKitConversionHelper:
    def __init__(self, adapter: RDKitAdapter) -> None:
        self.adapter = adapter

    def _build_rdkit_mol_with_map(
        self,
        model: MoleculeModel,
        *,
        strict_labels: bool = False,
        unsupported_bond_styles: set[str] | None = None,
    ):
        rdkit = self.adapter._load_rdkit()
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
            self.adapter.last_error = (
                "XYZ export supports element symbols only. "
                f"Unsupported atom labels: {detail}."
            )
            return None, None
        valid_atoms = set(atom_map.keys())
        seen_bonds: set[tuple[int, int]] = set()
        unsupported_styles: list[str] = []
        for bond_id, bond in enumerate(model.bonds):
            if bond is None or bond.a == bond.b:
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
            self.adapter.last_error = (
                "XYZ export does not yet support wedge/hash stereobonds. "
                f"Unsupported bond styles: {detail}."
            )
            return None, None
        mol = rw.GetMol()
        # Sanitization is best-effort here: this export/round-trip path tolerates
        # structures RDKit cannot fully sanitize (e.g. unusual valences from a
        # work-in-progress drawing) and lets the caller's downstream embedding
        # surface any real failure. This deliberately differs from
        # ``_build_conversion_rdkit_mol``, which is strict and aborts on a
        # sanitize error. Keep the tolerant behavior (see
        # test_model_to_rdkit_with_map_ignores_invalid_bonds_and_sanitize_errors).
        try:
            Chem.SanitizeMol(mol)
        except Exception:
            logger.debug("SanitizeMol failed for tolerant round-trip build; continuing.", exc_info=True)
        return mol, atom_map

    def model_to_rdkit_with_map(self, model: MoleculeModel, *, strict_labels: bool = False):
        return self._build_rdkit_mol_with_map(model, strict_labels=strict_labels)

    def model_to_rdkit(self, model: MoleculeModel, *, strict_labels: bool = False):
        mol, _ = self.adapter.model_to_rdkit_with_map(model, strict_labels=strict_labels)
        return mol

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
                self.adapter.last_error = "3D embedding failed."
                return None
            try:
                if hasattr(AllChem, "MMFFHasAllMoleculeParams") and AllChem.MMFFHasAllMoleculeParams(mol_h):
                    AllChem.MMFFOptimizeMolecule(mol_h, maxIters=50)
                else:
                    AllChem.UFFOptimizeMolecule(mol_h, maxIters=50)
            except Exception:
                logger.debug("MMFF optimization failed; falling back to UFF.", exc_info=True)
                try:
                    AllChem.UFFOptimizeMolecule(mol_h, maxIters=50)
                except Exception:
                    logger.debug("UFF optimization fallback failed; using unoptimized geometry.", exc_info=True)
        except Exception as exc:
            self.adapter.last_error = f"3D coordinate generation failed: {exc}"
            return None
        if hasattr(mol_h, "GetNumConformers") and mol_h.GetNumConformers() == 0:
            self.adapter.last_error = "3D coordinate generation failed: no conformer."
            return None
        return mol_h

    @staticmethod
    def _bond_type(Chem, order: int):
        order_map = {
            1: Chem.BondType.SINGLE,
            2: Chem.BondType.DOUBLE,
            3: Chem.BondType.TRIPLE,
        }
        return order_map.get(order, Chem.BondType.SINGLE)

    @staticmethod
    def _annotation_for_atom(
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

    @staticmethod
    def _apply_atom_annotation(rd_atom, *, formal_charge: int, radical_electrons: int) -> None:
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
    def _should_disable_conversion_implicit_hydrogens(
        model: MoleculeModel,
        atom_id: int,
        adjacency: Mapping[int, list[int]],
        *,
        formal_charge: int = 0,
        radical_electrons: int = 0,
    ) -> bool:
        atom = model.atoms.get(atom_id)
        if atom is None or atom.element.upper() == "C":
            return False
        for neighbor_id in adjacency.get(atom_id, []):
            neighbor = model.atoms.get(neighbor_id)
            if neighbor is not None and neighbor.element.upper() == "H":
                return True
        if formal_charge or radical_electrons:
            return False
        return True

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

    @staticmethod
    def _build_component_model(
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
                component_annotations[new_id] = {key: int(value) for key, value in values.items()}
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
            centered_min_x, _, _, _, _, _ = self._scene_bounds(centered_scene)
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

    def _parse_alias_fragment(
        self,
        label: str,
        *,
        atom_id: int,
        neighbors: list[int],
        Chem,
        AllChem,
    ) -> tuple[object, int, int] | None:
        """Expand the alias SMILES; (fragment, dummy_idx, attachment_idx) or None."""
        alias_smiles = self.adapter._alias_smiles.get(label)
        if alias_smiles is None:
            return None
        if len(neighbors) != 1:
            self.adapter.last_error = (
                f"Alias label '{label}' on atom {atom_id} requires exactly one attachment bond "
                f"for 3D conversion, but found {len(neighbors)}."
            )
            return None
        fragment = Chem.MolFromSmiles(alias_smiles)
        if fragment is None:
            self.adapter.last_error = f"Failed to expand alias label '{label}' for 3D conversion."
            return None
        if hasattr(AllChem, "Compute2DCoords"):
            try:
                AllChem.Compute2DCoords(fragment)
            except Exception:
                logger.debug("Compute2DCoords for alias fragment '%s' failed; continuing.", label, exc_info=True)
        dummy_atoms = [frag_atom for frag_atom in fragment.GetAtoms() if frag_atom.GetAtomicNum() == 0]
        if len(dummy_atoms) != 1:
            self.adapter.last_error = f"Alias label '{label}' has an invalid attachment definition."
            return None
        dummy_atom = dummy_atoms[0]
        dummy_neighbors = list(dummy_atom.GetNeighbors())
        if len(dummy_neighbors) != 1:
            self.adapter.last_error = f"Alias label '{label}' has an invalid attachment topology."
            return None
        return fragment, dummy_atom.GetIdx(), dummy_neighbors[0].GetIdx()

    def _copy_alias_fragment_into(
        self,
        fragment,
        *,
        dummy_idx: int,
        attachment_idx: int,
        formal_charge: int,
        radical_electrons: int,
        rw,
        Chem,
    ) -> tuple[dict[int, int], int | None]:
        """Copy fragment atoms/bonds (minus the dummy) into ``rw``."""
        fragment_map: dict[int, int] = {}
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
            rw.AddBond(fragment_map[begin_idx], fragment_map[end_idx], frag_bond.GetBondType())
        return fragment_map, attachment_new_idx

    def _alias_fragment_coords(
        self,
        fragment,
        *,
        label: str,
        atom,
        neighbors: list[int],
        model: MoleculeModel,
        dummy_idx: int,
        attachment_idx: int,
        fragment_map: dict[int, int],
        attachment_new_idx: int,
    ) -> dict[int, tuple[float, float]] | None:
        """Place fragment atoms around ``atom``, aligned toward its neighbor."""
        conf = fragment.GetConformer() if fragment.GetNumConformers() else None
        if conf is None:
            return {attachment_new_idx: (atom.x, atom.y)}

        dummy_pos = conf.GetAtomPosition(dummy_idx)
        attach_pos = conf.GetAtomPosition(attachment_idx)
        source_dx = dummy_pos.x - attach_pos.x
        source_dy = dummy_pos.y - attach_pos.y
        neighbor_atom = model.atoms.get(neighbors[0])
        if neighbor_atom is None:
            self.adapter.last_error = f"Alias label '{label}' is attached to a missing atom."
            return None
        target_dx = neighbor_atom.x - atom.x
        target_dy = neighbor_atom.y - atom.y
        source_angle = math.atan2(source_dy, source_dx) if abs(source_dx) > 1e-6 or abs(source_dy) > 1e-6 else 0.0
        target_angle = math.atan2(target_dy, target_dx) if abs(target_dx) > 1e-6 or abs(target_dy) > 1e-6 else 0.0
        rotation = target_angle - source_angle
        cos_theta = math.cos(rotation)
        sin_theta = math.sin(rotation)
        coord_map: dict[int, tuple[float, float]] = {}
        for frag_atom in fragment.GetAtoms():
            if frag_atom.GetIdx() == dummy_idx:
                continue
            frag_pos = conf.GetAtomPosition(frag_atom.GetIdx())
            rel_x = frag_pos.x - attach_pos.x
            rel_y = frag_pos.y - attach_pos.y
            rot_x = rel_x * cos_theta - rel_y * sin_theta
            rot_y = rel_x * sin_theta + rel_y * cos_theta
            coord_map[fragment_map[frag_atom.GetIdx()]] = (atom.x + rot_x, atom.y + rot_y)
        return coord_map

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
        parsed = self._parse_alias_fragment(
            label,
            atom_id=atom_id,
            neighbors=neighbors,
            Chem=Chem,
            AllChem=AllChem,
        )
        if parsed is None:
            return None, None
        fragment, dummy_idx, attachment_idx = parsed
        fragment_map, attachment_new_idx = self._copy_alias_fragment_into(
            fragment,
            dummy_idx=dummy_idx,
            attachment_idx=attachment_idx,
            formal_charge=formal_charge,
            radical_electrons=radical_electrons,
            rw=rw,
            Chem=Chem,
        )
        if attachment_new_idx is None:
            self.adapter.last_error = f"Alias label '{label}' could not be attached."
            return None, None
        coord_map = self._alias_fragment_coords(
            fragment,
            label=label,
            atom=atom,
            neighbors=neighbors,
            model=model,
            dummy_idx=dummy_idx,
            attachment_idx=attachment_idx,
            fragment_map=fragment_map,
            attachment_new_idx=attachment_new_idx,
        )
        if coord_map is None:
            return None, None
        return attachment_new_idx, coord_map

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
    ) -> tuple[dict[int, int], dict[int, tuple[float, float]]] | None:
        """Add model atoms (expanding aliases) to ``rw``; None with last_error on failure."""
        atom_map: dict[int, int] = {}
        coord_map: dict[int, tuple[float, float]] = {}
        invalid_labels: list[str] = []
        for atom_id in sorted(model.atoms):
            atom = model.atoms[atom_id]
            formal_charge, radical_electrons = self._annotation_for_atom(atom_annotations, atom_id)
            if atom.element in self.adapter._alias_smiles:
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
            if self._should_disable_conversion_implicit_hydrogens(
                model,
                atom_id,
                adjacency,
                formal_charge=formal_charge,
                radical_electrons=radical_electrons,
            ):
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
            supported_aliases = ", ".join(sorted(self.adapter._alias_smiles))
            self.adapter.last_error = (
                "Unsupported atom labels for 3D conversion: "
                f"{self._format_atom_refs(invalid_labels)}. "
                f"Supported aliases: {supported_aliases}."
            )
            return None
        return atom_map, coord_map

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
            rd_bond = rw.GetBondBetweenAtoms(rd_a, rd_b) if hasattr(rw, "GetBondBetweenAtoms") else None
            if rd_bond is None:
                continue
            if bond.style == "wedge":
                rd_bond.SetBondDir(Chem.BondDir.BEGINWEDGE)
            elif bond.style == "hash":
                rd_bond.SetBondDir(Chem.BondDir.BEGINDASH)
        return True

    def _attach_conversion_conformer(self, mol, coord_map: dict[int, tuple[float, float]], Chem) -> None:
        if not hasattr(Chem, "Conformer"):
            return
        try:
            conf = Chem.Conformer(mol.GetNumAtoms())
            for atom_idx in range(mol.GetNumAtoms()):
                x, y = coord_map.get(atom_idx, (0.0, 0.0))
                conf.SetAtomPosition(atom_idx, (x, y, 0.0))
            mol.AddConformer(conf, assignId=True)
        except Exception:
            logger.debug("Attaching 2D conformer for conversion failed; continuing.", exc_info=True)

    def _assign_conversion_stereo(self, mol, Chem) -> None:
        try:
            if hasattr(Chem, "AssignChiralTypesFromBondDirs"):
                Chem.AssignChiralTypesFromBondDirs(mol)
            if hasattr(Chem, "SetBondStereoFromDirections"):
                Chem.SetBondStereoFromDirections(mol)
            if hasattr(Chem, "AssignStereochemistry"):
                Chem.AssignStereochemistry(mol, force=True, cleanIt=True)
        except Exception:
            logger.debug("Stereochemistry assignment for conversion failed; continuing.", exc_info=True)

    def _build_conversion_rdkit_mol(
        self,
        model: MoleculeModel,
        *,
        atom_annotations: Mapping[int, Mapping[str, int]] | None = None,
    ):
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        rw = Chem.RWMol()
        adjacency = self._build_model_adjacency(model)
        valid_bonds = self._valid_conversion_bonds(model)

        atom_result = self._add_conversion_atoms(
            model,
            atom_annotations=atom_annotations,
            adjacency=adjacency,
            rw=rw,
            Chem=Chem,
            AllChem=AllChem,
        )
        if atom_result is None:
            return None
        atom_map, coord_map = atom_result

        if not self._add_conversion_bonds(valid_bonds, atom_map=atom_map, rw=rw, Chem=Chem):
            return None

        mol = rw.GetMol()
        self._attach_conversion_conformer(mol, coord_map, Chem)
        self._assign_conversion_stereo(mol, Chem)
        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:
            self.adapter.last_error = f"3D conversion produced an invalid structure: {exc}"
            return None
        return mol

    def model_to_3d_coords(self, model: MoleculeModel):
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        mol, atom_map = self.adapter.model_to_rdkit_with_map(model)
        if mol is None or atom_map is None:
            self.adapter.last_error = "Failed to build RDKit molecule."
            return None
        mol_h = self.adapter._embed_3d_molecule(mol, Chem, AllChem)
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
        rdkit = self.adapter._load_rdkit()
        if rdkit == (None, None):
            self.adapter.last_error = "RDKit is not available in this environment."
            return None
        if not model.atoms:
            self.adapter.last_error = "There is no chemical structure to preview."
            return None
        Chem, AllChem = rdkit
        component_scenes: list[Molecule3DScene] = []
        for component_atom_ids in self._model_components(model):
            component_model, component_annotations = self._build_component_model(
                model,
                component_atom_ids,
                atom_annotations=atom_annotations,
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
            self.adapter.last_error = "RDKit is not available in this environment."
            return None
        Chem, AllChem = rdkit
        # Reuse the 3D conversion builder so abbreviation labels (Ph, CF3, ...) are
        # expanded into explicit atoms and charge/stereo are applied. Then lay the
        # heavy-atom graph out in 2D for a conventional MDL depiction.
        mol = self.adapter._build_conversion_rdkit_mol(model, atom_annotations=atom_annotations)
        if mol is None:
            return None
        AllChem.Compute2DCoords(mol)
        return Chem.MolToMolBlock(mol)


__all__ = ["RDKitConversionHelper"]
