from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from PyQt6.QtCore import QObject, pyqtSignal

from chemvas.features.insertion import (
    Molecule3DScene,
    MoleculeIdentifiers,
    RDKitResult,
    model_with_atom_annotations,
)


class Preview3DAdapter(Protocol):
    last_error: str | None

    def is_loaded(self) -> bool: ...

    def preload(self) -> bool: ...

    def compute_identifiers(self, model: Any) -> MoleculeIdentifiers: ...

    def model_to_3d_scene_result(
        self,
        model: Any,
        atom_annotations: Any = None,
    ) -> RDKitResult[Molecule3DScene]: ...


class Preview3DWorker(QObject):
    finished = pyqtSignal(int, object, object, object, object, object, object, object)

    def __init__(
        self,
        request_id: int,
        rdkit_adapter: Preview3DAdapter | None,
        model: Any,
        atom_annotations: Any,
        *,
        rdkit_adapter_factory: Callable[[], Preview3DAdapter] | None = None,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._rdkit = rdkit_adapter
        self._model = model
        self._atom_annotations = atom_annotations
        self._rdkit_adapter_factory = rdkit_adapter_factory

    def run(self) -> None:
        formula = None
        mw = None
        smiles = None
        inchi = None
        inchikey = None
        scene = None
        error = None
        rdkit = (
            self._rdkit_adapter_factory()
            if self._rdkit_adapter_factory is not None
            else self._rdkit
        )
        try:
            assert rdkit is not None
            identifier_model = model_with_atom_annotations(
                self._model, self._atom_annotations
            )
            identifiers = rdkit.compute_identifiers(identifier_model)
            formula = identifiers.formula
            mw = identifiers.mw
            smiles = identifiers.smiles
            inchi = identifiers.inchi
            inchikey = identifiers.inchikey
            result = rdkit.model_to_3d_scene_result(
                self._model, atom_annotations=self._atom_annotations
            )
            scene = result.value
            error = result.error
        except Exception as exc:
            error = str(exc) or "Failed to build 3D preview."
        self.finished.emit(
            self._request_id, formula, mw, smiles, inchi, inchikey, scene, error
        )


__all__ = ["Preview3DAdapter", "Preview3DWorker"]
