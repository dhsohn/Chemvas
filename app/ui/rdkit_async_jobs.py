from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path

from core.document_io import atomic_write_text, atomic_write_via_temp
from PyQt6.QtCore import QCoreApplication, QObject, QThread, pyqtSignal, pyqtSlot

from ui.rdkit_export_job_state import (
    RDKitExportJob,
    rdkit_export_job_registry,
)

logger = logging.getLogger(__name__)


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
        self.result: tuple[bool, str] | None = None

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
                message = error or "Failed to export 3D XYZ."
                self.result = (False, message)
                self.failed.emit(message)
                return
            atomic_write_text(self._path, xyz_block)
            self.result = (True, self._path)
            self.succeeded.emit(self._path)
        except Exception as exc:
            message = str(exc) or "Failed to export 3D XYZ."
            self.result = (False, message)
            self.failed.emit(message)
        finally:
            self.finished.emit()


def _remove_staging_file(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


class XYZExportCoordinator(QObject):
    success_received = pyqtSignal(int, str)
    failure_received = pyqtSignal(int, str)
    thread_finished_received = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self.registry = rdkit_export_job_registry()
        self._application: QCoreApplication | None = None
        self._shutting_down = False
        self.success_received.connect(self._handle_success)
        self.failure_received.connect(self._handle_failure)
        self.thread_finished_received.connect(self._handle_thread_finished)

    def attach_to_application(self) -> None:
        application = QCoreApplication.instance()
        if application is None or application is self._application:
            return
        self._application = application
        application.aboutToQuit.connect(self.shutdown)

    def _invoke_callback(self, job: RDKitExportJob, callback, value: str) -> None:
        if callback is None or not job.owner_state.callbacks_enabled:
            return
        try:
            callback(value)
        except Exception:
            logger.debug("Ignoring an XYZ export callback failure.", exc_info=True)

    def _publish_staging_file(self, job: RDKitExportJob) -> None:
        atomic_write_via_temp(
            job.target_path,
            lambda final_tmp: os.replace(job.staging_path, final_tmp),
        )

    @pyqtSlot(int, str)
    def _handle_success(self, job_id: int, staging_path: str) -> None:
        job = self.registry.job(job_id)
        if job is None:
            _remove_staging_file(Path(staging_path))
            return
        if job.result_handled:
            return
        try:
            if self.registry.is_latest(job):
                self._publish_staging_file(job)
                self._invoke_callback(job, job.on_success, job.callback_path)
            else:
                _remove_staging_file(job.staging_path)
        except Exception as exc:
            _remove_staging_file(job.staging_path)
            if self.registry.is_latest(job):
                self._invoke_callback(job, job.on_error, str(exc) or "Failed to export 3D XYZ.")
        finally:
            job.result_handled = True
            self._release_if_complete(job)

    @pyqtSlot(int, str)
    def _handle_failure(self, job_id: int, message: str) -> None:
        job = self.registry.job(job_id)
        if job is None or job.result_handled:
            return
        _remove_staging_file(job.staging_path)
        if self.registry.is_latest(job):
            self._invoke_callback(job, job.on_error, message)
        job.result_handled = True
        self._release_if_complete(job)

    @pyqtSlot(int)
    def _handle_thread_finished(self, job_id: int) -> None:
        job = self.registry.job(job_id)
        if job is None:
            return
        job.thread_finished = True
        self._release_if_complete(job)

    def _release_if_complete(self, job: RDKitExportJob) -> None:
        released = self.registry.release_if_complete(job.job_id)
        if released is not None:
            _remove_staging_file(released.staging_path)

    @pyqtSlot()
    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        jobs = list(self.registry.active_jobs())
        for job in jobs:
            self.registry.disable_owner_callbacks(job.owner_state)
            thread = job.thread
            if thread is not None and thread.isRunning():
                thread.quit()
        for job in jobs:
            thread = job.thread
            if thread is not None and thread.isRunning():
                thread.wait()
            job.thread_finished = True
            if not job.result_handled:
                result = getattr(job.worker, "result", None)
                if result is not None:
                    succeeded, value = result
                    if succeeded:
                        self._handle_success(job.job_id, value)
                    else:
                        self._handle_failure(job.job_id, value)
                else:
                    _remove_staging_file(job.staging_path)
                    job.result_handled = True
            self._release_if_complete(job)


_EXPORT_COORDINATOR: XYZExportCoordinator | None = None


def xyz_export_coordinator() -> XYZExportCoordinator:
    global _EXPORT_COORDINATOR
    if _EXPORT_COORDINATOR is None:
        _EXPORT_COORDINATOR = XYZExportCoordinator()
    _EXPORT_COORDINATOR.attach_to_application()
    return _EXPORT_COORDINATOR


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
    coordinator = xyz_export_coordinator()
    job = coordinator.registry.reserve(
        owner,
        path,
        on_success=on_success,
        on_error=on_error,
    )
    try:
        thread = QThread()
        worker = XYZExportWorker(
            rdkit_adapter,
            model,
            atom_annotations,
            os.fspath(job.staging_path),
            rdkit_adapter_factory=rdkit_adapter_factory,
        )
        worker.moveToThread(thread)
        coordinator.registry.attach(job.job_id, thread=thread, worker=worker)

        thread.started.connect(worker.run)
        worker.succeeded.connect(
            lambda staging_path, job_id=job.job_id: coordinator.success_received.emit(job_id, staging_path)
        )
        worker.failed.connect(
            lambda message, job_id=job.job_id: coordinator.failure_received.emit(job_id, message)
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            lambda job_id=job.job_id: coordinator.thread_finished_received.emit(job_id)
        )
        thread.start()
    except Exception:
        coordinator.registry.discard(job.job_id)
        raise


__all__ = [
    "XYZExportCoordinator",
    "XYZExportWorker",
    "export_xyz_in_thread",
    "xyz_export_coordinator",
]
