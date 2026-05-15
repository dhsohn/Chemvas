from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class XYZExportWorker(QObject):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, rdkit_adapter, model, atom_annotations, path: str) -> None:
        super().__init__()
        self._rdkit = rdkit_adapter
        self._model = model
        self._atom_annotations = atom_annotations
        self._path = path

    def run(self) -> None:
        try:
            xyz_block = self._rdkit.model_to_xyz_block(
                self._model,
                atom_annotations=self._atom_annotations,
            )
            if xyz_block is None:
                self.failed.emit(self._rdkit.last_error or "Failed to export 3D XYZ.")
                return
            Path(self._path).write_text(xyz_block, encoding="utf-8")
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
) -> None:
    jobs = getattr(owner, "_rdkit_export_jobs", None)
    if jobs is None:
        jobs = []
        setattr(owner, "_rdkit_export_jobs", jobs)

    thread = QThread(owner)
    worker = XYZExportWorker(rdkit_adapter, model, atom_annotations, path)
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
