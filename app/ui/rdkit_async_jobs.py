from __future__ import annotations

from core.document_io import atomic_write_text
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ui.rdkit_export_job_state import rdkit_export_jobs_for


class XYZExportWorker(QObject):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, rdkit_adapter, model, atom_annotations, path: str, *, rdkit_adapter_factory=None) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter
        self._model = model
        self._atom_annotations = atom_annotations
        self._path = path
        self._rdkit_adapter_factory = rdkit_adapter_factory

    def run(self) -> None:
        rdkit = self._rdkit_adapter_factory() if self._rdkit_adapter_factory is not None else self._rdkit
        try:
            result_method = getattr(rdkit, "model_to_xyz_block_result", None)
            if callable(result_method):
                result = result_method(self._model, atom_annotations=self._atom_annotations)
                xyz_block = result.value
                error = result.error
            else:
                xyz_block = rdkit.model_to_xyz_block(
                    self._model,
                    atom_annotations=self._atom_annotations,
                )
                error = getattr(rdkit, "last_error", None)
            if xyz_block is None:
                self.failed.emit(error or "Failed to export 3D XYZ.")
                return
            atomic_write_text(self._path, xyz_block)
            self.succeeded.emit(self._path)
        except Exception as exc:
            self.failed.emit(str(exc) or "Failed to export 3D XYZ.")
        finally:
            self.finished.emit()


def export_xyz_in_thread(
    owner: QObject,
    *,
    rdkit_adapter,
    model,
    atom_annotations,
    path: str,
    on_success,
    on_error,
    rdkit_adapter_factory=None,
) -> None:
    jobs = rdkit_export_jobs_for(owner)
    thread = QThread(owner)
    worker = XYZExportWorker(rdkit_adapter, model, atom_annotations, path, rdkit_adapter_factory=rdkit_adapter_factory)
    worker.moveToThread(thread)
    job = (thread, worker)
    jobs.append(job)

    thread.started.connect(worker.run)
    worker.succeeded.connect(on_success)
    worker.failed.connect(on_error)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda job=job: jobs.remove(job) if job in jobs else None)
    thread.start()


__all__ = ["XYZExportWorker", "export_xyz_in_thread"]
