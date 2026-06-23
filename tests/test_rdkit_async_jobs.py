import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QObject
except ModuleNotFoundError:
    QObject = None

if QObject is not None:
    from core.rdkit_types import MoleculeIdentifiers, RDKitResult
    from ui import rdkit_async_jobs
    from ui.preview_3d_worker import Preview3DWorker
    from ui.rdkit_async_jobs import XYZExportWorker, export_xyz_in_thread
    from ui.rdkit_export_job_state import rdkit_export_jobs_for


@unittest.skipUnless(QObject is not None, "PyQt6 is required for async RDKit export tests")
class XYZExportWorkerTest(unittest.TestCase):
    def test_run_writes_xyz_and_emits_success_and_finished(self) -> None:
        rdkit = SimpleNamespace(
            model_to_xyz_block=mock.Mock(return_value="1\nChemvas XYZ export\nC 0.0 0.0 0.0\n"),
            last_error=None,
        )
        signals = {"succeeded": [], "failed": [], "finished": 0}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            worker = XYZExportWorker(rdkit, "model", {"annotations": True}, str(path))
            worker.succeeded.connect(signals["succeeded"].append)
            worker.failed.connect(signals["failed"].append)
            worker.finished.connect(lambda: signals.__setitem__("finished", signals["finished"] + 1))

            worker.run()

            self.assertEqual(path.read_text(encoding="utf-8"), "1\nChemvas XYZ export\nC 0.0 0.0 0.0\n")

        rdkit.model_to_xyz_block.assert_called_once_with("model", atom_annotations={"annotations": True})
        self.assertEqual(signals["succeeded"], [str(path)])
        self.assertEqual(signals["failed"], [])
        self.assertEqual(signals["finished"], 1)

    def test_run_emits_rdkit_error_when_conversion_returns_none(self) -> None:
        rdkit = SimpleNamespace(
            model_to_xyz_block=mock.Mock(return_value=None),
            last_error="unsupported label",
        )
        signals = {"succeeded": [], "failed": [], "finished": 0}

        worker = XYZExportWorker(rdkit, "model", {}, "/tmp/not-written.xyz")
        worker.succeeded.connect(signals["succeeded"].append)
        worker.failed.connect(signals["failed"].append)
        worker.finished.connect(lambda: signals.__setitem__("finished", signals["finished"] + 1))

        worker.run()

        self.assertEqual(signals["succeeded"], [])
        self.assertEqual(signals["failed"], ["unsupported label"])
        self.assertEqual(signals["finished"], 1)

    def test_run_prefers_result_error_over_stale_adapter_error(self) -> None:
        rdkit = SimpleNamespace(
            model_to_xyz_block_result=mock.Mock(return_value=RDKitResult(None, "local error")),
            last_error="stale error",
        )
        signals = {"succeeded": [], "failed": [], "finished": 0}

        worker = XYZExportWorker(rdkit, "model", {}, "/tmp/not-written.xyz")
        worker.succeeded.connect(signals["succeeded"].append)
        worker.failed.connect(signals["failed"].append)
        worker.finished.connect(lambda: signals.__setitem__("finished", signals["finished"] + 1))

        worker.run()

        rdkit.model_to_xyz_block_result.assert_called_once_with("model", atom_annotations={})
        self.assertEqual(signals["succeeded"], [])
        self.assertEqual(signals["failed"], ["local error"])
        self.assertEqual(signals["finished"], 1)

    def test_run_emits_fallback_error_messages(self) -> None:
        cases = (
            (
                SimpleNamespace(model_to_xyz_block=mock.Mock(return_value=None), last_error=None),
                "Failed to export 3D XYZ.",
            ),
            (
                SimpleNamespace(model_to_xyz_block=mock.Mock(side_effect=RuntimeError()), last_error=None),
                "Failed to export 3D XYZ.",
            ),
            (
                SimpleNamespace(model_to_xyz_block=mock.Mock(side_effect=RuntimeError("boom")), last_error=None),
                "boom",
            ),
        )

        for rdkit, expected_message in cases:
            with self.subTest(expected_message=expected_message):
                failed = []
                finished = []
                worker = XYZExportWorker(rdkit, "model", {}, "/tmp/not-written.xyz")
                worker.failed.connect(failed.append)
                worker.finished.connect(lambda finished=finished: finished.append(True))

                worker.run()

                self.assertEqual(failed, [expected_message])
                self.assertEqual(finished, [True])


class _FakeSignal:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def emit(self, *args) -> None:
        for slot in list(self.slots):
            slot(*args)


class _FakeThread:
    instances = []

    def __init__(self, parent) -> None:
        self.parent = parent
        self.started = _FakeSignal()
        self.finished = _FakeSignal()
        self.quit_called = False
        self.delete_later_called = False
        self.start_called = False
        _FakeThread.instances.append(self)

    def quit(self) -> None:
        self.quit_called = True

    def deleteLater(self) -> None:
        self.delete_later_called = True

    def start(self) -> None:
        self.start_called = True


class _FakeWorker:
    instances = []

    def __init__(self, rdkit_adapter, model, atom_annotations, path: str, *, rdkit_adapter_factory=None) -> None:
        self.rdkit_adapter = rdkit_adapter
        self.rdkit_adapter_factory = rdkit_adapter_factory
        self.model = model
        self.atom_annotations = atom_annotations
        self.path = path
        self.succeeded = _FakeSignal()
        self.failed = _FakeSignal()
        self.finished = _FakeSignal()
        self.moved_to = None
        self.delete_later_called = False
        self.run_called = False
        _FakeWorker.instances.append(self)

    def moveToThread(self, thread) -> None:
        self.moved_to = thread

    def deleteLater(self) -> None:
        self.delete_later_called = True

    def run(self) -> None:
        self.run_called = True


@unittest.skipUnless(QObject is not None, "PyQt6 is required for async RDKit export tests")
class ExportXYZInThreadTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeThread.instances.clear()
        _FakeWorker.instances.clear()

    def test_export_xyz_in_thread_wires_worker_and_cleans_finished_jobs(self) -> None:
        owner = QObject()
        succeeded = []
        failed = []

        with (
            mock.patch.object(rdkit_async_jobs, "QThread", new=_FakeThread),
            mock.patch.object(rdkit_async_jobs, "XYZExportWorker", new=_FakeWorker),
        ):
            export_xyz_in_thread(
                owner,
                rdkit_adapter="rdkit",
                model="model",
                atom_annotations={"a": 1},
                path="/tmp/export.xyz",
                on_success=succeeded.append,
                on_error=failed.append,
            )

        thread = _FakeThread.instances[-1]
        worker = _FakeWorker.instances[-1]
        self.assertIs(thread.parent, owner)
        self.assertEqual(worker.rdkit_adapter, "rdkit")
        self.assertIsNone(worker.rdkit_adapter_factory)
        self.assertEqual(worker.model, "model")
        self.assertEqual(worker.atom_annotations, {"a": 1})
        self.assertEqual(worker.path, "/tmp/export.xyz")
        self.assertIs(worker.moved_to, thread)
        self.assertEqual(rdkit_export_jobs_for(owner), [(thread, worker)])
        self.assertTrue(thread.start_called)

        thread.started.emit()
        self.assertTrue(worker.run_called)

        worker.succeeded.emit("/tmp/export.xyz")
        worker.failed.emit("failure")
        self.assertEqual(succeeded, ["/tmp/export.xyz"])
        self.assertEqual(failed, ["failure"])

        worker.finished.emit()
        self.assertTrue(thread.quit_called)
        self.assertTrue(worker.delete_later_called)
        self.assertEqual(rdkit_export_jobs_for(owner), [(thread, worker)])

        thread.finished.emit()
        self.assertTrue(thread.delete_later_called)
        self.assertEqual(rdkit_export_jobs_for(owner), [])

    def test_export_xyz_in_thread_reuses_existing_job_list(self) -> None:
        existing_job = ("old-thread", "old-worker")
        owner = QObject()
        rdkit_export_jobs_for(owner).append(existing_job)

        with (
            mock.patch.object(rdkit_async_jobs, "QThread", new=_FakeThread),
            mock.patch.object(rdkit_async_jobs, "XYZExportWorker", new=_FakeWorker),
        ):
            export_xyz_in_thread(
                owner,
                rdkit_adapter="rdkit",
                model="model",
                atom_annotations={},
                path="/tmp/export.xyz",
                on_success=lambda _path: None,
                on_error=lambda _message: None,
            )

        thread = _FakeThread.instances[-1]
        worker = _FakeWorker.instances[-1]
        self.assertEqual(rdkit_export_jobs_for(owner), [existing_job, (thread, worker)])


@unittest.skipUnless(QObject is not None, "PyQt6 is required for async RDKit preview tests")
class Preview3DWorkerTest(unittest.TestCase):
    def test_run_prefers_result_error_over_stale_adapter_error(self) -> None:
        rdkit = SimpleNamespace(
            compute_identifiers=mock.Mock(
                return_value=MoleculeIdentifiers(formula="C", mw=12.01, smiles="C", inchikey="KEY")
            ),
            model_to_3d_scene_result=mock.Mock(return_value=RDKitResult(None, "local preview error")),
            last_error="stale preview error",
        )
        emitted = []
        worker = Preview3DWorker(7, rdkit, "model", {"annotations": True})
        worker.finished.connect(lambda *args: emitted.append(args))

        worker.run()

        rdkit.compute_identifiers.assert_called_once_with("model")
        rdkit.model_to_3d_scene_result.assert_called_once_with("model", atom_annotations={"annotations": True})
        self.assertEqual(emitted, [(7, "C", 12.01, "C", "KEY", None, "local preview error")])


if __name__ == "__main__":
    unittest.main()
