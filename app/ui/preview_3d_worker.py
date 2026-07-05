from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from ui.structure_payload_logic import model_with_atom_annotations


class Preview3DWorker(QObject):
    finished = pyqtSignal(int, object, object, object, object, object, object)

    def __init__(
        self,
        request_id: int,
        rdkit_adapter: Any,
        model: Any,
        atom_annotations: Any,
        *,
        rdkit_adapter_factory=None,
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
        inchikey = None
        scene = None
        error = None
        rdkit = self._rdkit_adapter_factory() if self._rdkit_adapter_factory is not None else self._rdkit
        try:
            identifier_model = model_with_atom_annotations(self._model, self._atom_annotations)
            identifiers = rdkit.compute_identifiers(identifier_model)
            formula = identifiers.formula
            mw = identifiers.mw
            smiles = identifiers.smiles
            inchikey = identifiers.inchikey
            result_method = getattr(rdkit, "model_to_3d_scene_result", None)
            if callable(result_method):
                result = result_method(self._model, atom_annotations=self._atom_annotations)
                scene = result.value
                error = result.error
            else:
                scene = rdkit.model_to_3d_scene(
                    self._model,
                    atom_annotations=self._atom_annotations,
                )
                if scene is None:
                    error = getattr(rdkit, "last_error", None) or "Failed to build 3D preview."
        except Exception as exc:
            error = str(exc) or "Failed to build 3D preview."
        self.finished.emit(self._request_id, formula, mw, smiles, inchikey, scene, error)


__all__ = ["Preview3DWorker"]
