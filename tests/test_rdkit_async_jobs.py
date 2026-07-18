import os
import stat
import subprocess
import sys
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
    from chemvas.domain.document import MoleculeModel
    from chemvas.features.insertion import MoleculeIdentifiers, RDKitResult
    from chemvas.ui import rdkit_async_jobs
    from chemvas.ui.preview_3d_worker import Preview3DWorker
    from chemvas.ui.rdkit_async_jobs import XYZExportWorker, export_xyz_in_thread
    from chemvas.ui.rdkit_export_job_state import (
        normalized_export_target_path,
        rdkit_export_jobs_for,
        reset_rdkit_export_job_state_for_tests,
    )


@unittest.skipUnless(
    QObject is not None, "PyQt6 is required for async RDKit export tests"
)
class XYZExportWorkerTest(unittest.TestCase):
    def test_run_writes_xyz_and_emits_success_and_finished(self) -> None:
        rdkit = SimpleNamespace(
            model_to_xyz_block=mock.Mock(
                return_value="1\nChemvas XYZ export\nC 0.0 0.0 0.0\n"
            ),
            last_error=None,
        )
        signals = {"succeeded": [], "failed": [], "finished": 0}

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            worker = XYZExportWorker(rdkit, "model", {"annotations": True}, str(path))
            worker.succeeded.connect(signals["succeeded"].append)
            worker.failed.connect(signals["failed"].append)
            worker.finished.connect(
                lambda: signals.__setitem__("finished", signals["finished"] + 1)
            )

            worker.run()

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "1\nChemvas XYZ export\nC 0.0 0.0 0.0\n",
            )

        rdkit.model_to_xyz_block.assert_called_once_with(
            "model", atom_annotations={"annotations": True}
        )
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
        worker.finished.connect(
            lambda: signals.__setitem__("finished", signals["finished"] + 1)
        )

        worker.run()

        self.assertEqual(signals["succeeded"], [])
        self.assertEqual(signals["failed"], ["unsupported label"])
        self.assertEqual(signals["finished"], 1)

    def test_run_prefers_result_error_over_stale_adapter_error(self) -> None:
        rdkit = SimpleNamespace(
            model_to_xyz_block_result=mock.Mock(
                return_value=RDKitResult(None, "local error")
            ),
            last_error="stale error",
        )
        signals = {"succeeded": [], "failed": [], "finished": 0}

        worker = XYZExportWorker(rdkit, "model", {}, "/tmp/not-written.xyz")
        worker.succeeded.connect(signals["succeeded"].append)
        worker.failed.connect(signals["failed"].append)
        worker.finished.connect(
            lambda: signals.__setitem__("finished", signals["finished"] + 1)
        )

        worker.run()

        rdkit.model_to_xyz_block_result.assert_called_once_with(
            "model", atom_annotations={}
        )
        self.assertEqual(signals["succeeded"], [])
        self.assertEqual(signals["failed"], ["local error"])
        self.assertEqual(signals["finished"], 1)

    def test_run_emits_fallback_error_messages(self) -> None:
        cases = (
            (
                SimpleNamespace(
                    model_to_xyz_block=mock.Mock(return_value=None), last_error=None
                ),
                "Failed to export 3D XYZ.",
            ),
            (
                SimpleNamespace(
                    model_to_xyz_block=mock.Mock(side_effect=RuntimeError()),
                    last_error=None,
                ),
                "Failed to export 3D XYZ.",
            ),
            (
                SimpleNamespace(
                    model_to_xyz_block=mock.Mock(side_effect=RuntimeError("boom")),
                    last_error=None,
                ),
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

    def __init__(self, parent=None) -> None:
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

    def __init__(
        self,
        rdkit_adapter,
        model,
        atom_annotations,
        path: str,
        *,
        rdkit_adapter_factory=None,
    ) -> None:
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


@unittest.skipUnless(
    QObject is not None, "PyQt6 is required for async RDKit export tests"
)
class ExportXYZInThreadTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_rdkit_export_job_state_for_tests()
        _FakeThread.instances.clear()
        _FakeWorker.instances.clear()

    def tearDown(self) -> None:
        reset_rdkit_export_job_state_for_tests()

    def test_export_xyz_in_thread_wires_worker_and_cleans_finished_jobs(self) -> None:
        owner = QObject()
        succeeded = []
        failed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            path.write_text("previous xyz", encoding="utf-8")
            path.chmod(0o640)
            with (
                mock.patch.object(rdkit_async_jobs, "QThread", new=_FakeThread),
                mock.patch.object(rdkit_async_jobs, "XYZExportWorker", new=_FakeWorker),
            ):
                export_xyz_in_thread(
                    owner,
                    rdkit_adapter="rdkit",
                    model="model",
                    atom_annotations={"a": 1},
                    path=str(path),
                    on_success=succeeded.append,
                    on_error=failed.append,
                )

            thread = _FakeThread.instances[-1]
            worker = _FakeWorker.instances[-1]
            self.assertIsNone(thread.parent)
            self.assertEqual(worker.rdkit_adapter, "rdkit")
            self.assertIsNone(worker.rdkit_adapter_factory)
            self.assertEqual(worker.model, "model")
            self.assertEqual(worker.atom_annotations, {"a": 1})
            self.assertNotEqual(worker.path, str(path))
            self.assertEqual(Path(worker.path).parent, path.parent)
            self.assertIs(worker.moved_to, thread)
            self.assertEqual(rdkit_export_jobs_for(owner), [(thread, worker)])
            self.assertTrue(thread.start_called)

            thread.started.emit()
            self.assertTrue(worker.run_called)

            Path(worker.path).write_text("new xyz", encoding="utf-8")
            worker.succeeded.emit(worker.path)
            worker.failed.emit("ignored duplicate result")
            self.assertEqual(path.read_text(encoding="utf-8"), "new xyz")
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(succeeded, [str(path)])
            self.assertEqual(failed, [])

            worker.finished.emit()
            self.assertTrue(thread.quit_called)
            self.assertTrue(worker.delete_later_called)
            self.assertEqual(rdkit_export_jobs_for(owner), [(thread, worker)])

            thread.finished.emit()
            self.assertTrue(thread.delete_later_called)
            self.assertEqual(rdkit_export_jobs_for(owner), [])

    def test_overlapping_same_path_publishes_only_latest_generation_when_completion_reverses(
        self,
    ) -> None:
        owner = QObject()
        succeeded = []
        failed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            with (
                mock.patch.object(rdkit_async_jobs, "QThread", new=_FakeThread),
                mock.patch.object(rdkit_async_jobs, "XYZExportWorker", new=_FakeWorker),
            ):
                for model in ("older", "newer"):
                    export_xyz_in_thread(
                        owner,
                        rdkit_adapter="rdkit",
                        model=model,
                        atom_annotations={},
                        path=str(path),
                        on_success=succeeded.append,
                        on_error=failed.append,
                    )

            older_thread, newer_thread = _FakeThread.instances
            older_worker, newer_worker = _FakeWorker.instances
            Path(older_worker.path).write_text("older xyz", encoding="utf-8")
            Path(newer_worker.path).write_text("newer xyz", encoding="utf-8")

            newer_worker.succeeded.emit(newer_worker.path)
            newer_worker.finished.emit()
            newer_thread.finished.emit()
            older_worker.succeeded.emit(older_worker.path)
            older_worker.finished.emit()
            older_thread.finished.emit()

            self.assertEqual(path.read_text(encoding="utf-8"), "newer xyz")
            self.assertEqual(succeeded, [str(path)])
            self.assertEqual(failed, [])
            self.assertFalse(Path(older_worker.path).exists())
            self.assertFalse(Path(newer_worker.path).exists())
            self.assertEqual(rdkit_export_jobs_for(owner), [])

    def test_owner_destruction_suppresses_callbacks_but_keeps_latest_file_publication(
        self,
    ) -> None:
        owner = QObject()
        succeeded = []
        failed = []

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "export.xyz"
            with (
                mock.patch.object(rdkit_async_jobs, "QThread", new=_FakeThread),
                mock.patch.object(rdkit_async_jobs, "XYZExportWorker", new=_FakeWorker),
            ):
                export_xyz_in_thread(
                    owner,
                    rdkit_adapter="rdkit",
                    model="model",
                    atom_annotations={},
                    path=str(path),
                    on_success=succeeded.append,
                    on_error=failed.append,
                )

            thread = _FakeThread.instances[-1]
            worker = _FakeWorker.instances[-1]
            Path(worker.path).write_text("finished after close", encoding="utf-8")
            owner.destroyed.emit(owner)
            worker.succeeded.emit(worker.path)
            worker.finished.emit()
            thread.finished.emit()

            self.assertEqual(path.read_text(encoding="utf-8"), "finished after close")
            self.assertEqual(succeeded, [])
            self.assertEqual(failed, [])
            self.assertEqual(rdkit_export_jobs_for(owner), [])

    def test_normalized_target_collapses_relative_parent_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            child = directory / "child"
            child.mkdir()
            direct = directory / "export.xyz"
            aliased = child / ".." / "export.xyz"

            self.assertEqual(
                normalized_export_target_path(direct),
                normalized_export_target_path(aliased),
            )

    def test_owner_delete_keeps_running_qthread_until_event_loop_cleans_registry(
        self,
    ) -> None:
        app_root = Path(__file__).resolve().parents[1] / "app"
        script = r"""
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QObject, QTimer

from chemvas.ui.rdkit_async_jobs import export_xyz_in_thread
from chemvas.ui.rdkit_export_job_state import active_rdkit_export_jobs


class SlowAdapter:
    def model_to_xyz_block(self, model, atom_annotations=None):
        time.sleep(0.2)
        return "0\ncompleted after owner close\n"


app = QCoreApplication([])
owner = QObject()
target = Path(sys.argv[1])
successes = []
errors = []
export_xyz_in_thread(
    owner,
    rdkit_adapter=SlowAdapter(),
    model=None,
    atom_annotations={},
    path=str(target),
    on_success=successes.append,
    on_error=errors.append,
)
QTimer.singleShot(30, owner.deleteLater)


def quit_after_cleanup():
    if active_rdkit_export_jobs():
        QTimer.singleShot(10, quit_after_cleanup)
        return
    app.quit()


QTimer.singleShot(0, quit_after_cleanup)
QTimer.singleShot(3000, lambda: app.exit(2))
assert app.exec() == 0
assert target.read_text(encoding="utf-8") == "0\ncompleted after owner close\n"
assert successes == []
assert errors == []
assert active_rdkit_export_jobs() == ()
assert list(target.parent.glob(f".{target.name}.*.stage")) == []
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "shutdown.xyz"
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join(
                [str(app_root), env.get("PYTHONPATH", "")]
            ).rstrip(os.pathsep)
            completed = subprocess.run(
                [sys.executable, "-c", script, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)


@unittest.skipUnless(
    QObject is not None, "PyQt6 is required for async RDKit preview tests"
)
class Preview3DWorkerTest(unittest.TestCase):
    def test_run_prefers_result_error_over_stale_adapter_error(self) -> None:
        rdkit = SimpleNamespace(
            compute_identifiers=mock.Mock(
                return_value=MoleculeIdentifiers(
                    formula="C", mw=12.01, smiles="C", inchikey="KEY"
                )
            ),
            model_to_3d_scene_result=mock.Mock(
                return_value=RDKitResult(None, "local preview error")
            ),
            last_error="stale preview error",
        )
        model = MoleculeModel()
        atom_id = model.add_atom("C", 0.0, 0.0)
        atom_annotations = {atom_id: {"formal_charge": 1}}
        emitted = []
        worker = Preview3DWorker(7, rdkit, model, atom_annotations)
        worker.finished.connect(lambda *args: emitted.append(args))

        worker.run()

        rdkit.compute_identifiers.assert_called_once()
        identifier_model = rdkit.compute_identifiers.call_args.args[0]
        self.assertIsNot(identifier_model, model)
        self.assertEqual(identifier_model.atom_annotations, atom_annotations)
        self.assertEqual(model.atom_annotations, {})
        rdkit.model_to_3d_scene_result.assert_called_once_with(
            model, atom_annotations=atom_annotations
        )
        self.assertEqual(
            emitted, [(7, "C", 12.01, "C", "KEY", None, "local preview error")]
        )


if __name__ == "__main__":
    unittest.main()
