from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal


class Preview3DWorker(QObject):
    finished = pyqtSignal(int, object, object, object, object)

    def __init__(
        self,
        request_id: int,
        rdkit_adapter: Any,
        model: Any,
        atom_annotations: Any,
    ) -> None:
        super().__init__()
        self._request_id = request_id
        self._rdkit = rdkit_adapter
        self._model = model
        self._atom_annotations = atom_annotations

    def run(self) -> None:
        formula = None
        mw = None
        scene = None
        error = None
        try:
            formula, mw, _ = self._rdkit.compute_props(self._model)
            scene = self._rdkit.model_to_3d_scene(
                self._model,
                atom_annotations=self._atom_annotations,
            )
            if scene is None:
                error = self._rdkit.last_error or "Failed to build 3D preview."
        except Exception as exc:
            error = str(exc) or "Failed to build 3D preview."
        self.finished.emit(self._request_id, formula, mw, scene, error)


__all__ = ["Preview3DWorker"]
