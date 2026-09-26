"""Cancellable, isolated geometry check for the desktop pair editor."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal

import chemvas
from chemvas.core.document_io import write_document
from chemvas.domain.document import CANVAS_FILE_VERSION


class CalculationHandoffCheck(QObject):
    finished = pyqtSignal(object, bytes, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._directory: TemporaryDirectory[str] | None = None
        self._source = b""
        self._cancelled = False
        self._error = ""
        self.process = QProcess(self)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    def start(self, state: dict[str, object], step_id: str) -> None:
        if self._directory is not None:
            raise ValueError("A geometry check is already running.")
        self._directory = TemporaryDirectory(prefix="chemvas-pair-")
        directory = Path(self._directory.name)
        try:
            write_document(directory / "source.chemvas", state, CANVAS_FILE_VERSION)
            self._source = (directory / "source.chemvas").read_bytes()
        except (OSError, ValueError):
            self._cleanup()
            raise
        self._cancelled = False
        self._error = ""
        environment = QProcessEnvironment.systemEnvironment()
        package_parent = str(Path(chemvas.__file__).resolve().parent.parent)
        existing = environment.value("PYTHONPATH")
        environment.insert(
            "PYTHONPATH", os.pathsep.join(filter(None, (package_parent, existing)))
        )
        self.process.setStandardOutputFile(os.devnull)
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(directory))
        executable, prefix = _worker_command()
        self.timer.start(120_000)
        self.process.start(
            executable,
            prefix
            + [
                "pack-step",
                str(directory / "source.chemvas"),
                "--step",
                step_id,
                "--output",
                str(directory / "machine.json"),
            ],
        )

    def cancel(self) -> None:
        if self._directory is not None:
            self._cancelled = True
            self.process.kill()

    def shutdown(self) -> None:
        self.cancel()
        # The process is our own disposable worker, with no user output paths.
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.waitForFinished(3000)
        self._cleanup()

    def _timeout(self) -> None:
        self._error = "Geometry check timed out. Simplify the pair and try again."
        self.process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._error = self.process.errorString()
            self._finished(-1, QProcess.ExitStatus.CrashExit)

    def _finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._directory is None:
            return
        result = None
        error = self._error
        if self._cancelled:
            error = "Check cancelled. No handoff was exported."
        elif not error:
            if code != 0 or status != QProcess.ExitStatus.NormalExit:
                error = (
                    self.process.readAllStandardError()
                    .data()
                    .decode("utf-8", errors="replace")[-6000:]
                    or "Geometry check failed."
                )
            else:
                try:
                    result = json.loads(
                        (Path(self._directory.name) / "machine.json").read_bytes()
                    )
                except (OSError, ValueError) as exc:
                    error = str(exc)
        source = self._source
        self._cleanup()
        self.finished.emit(result, source, error)

    def _cleanup(self) -> None:
        self.timer.stop()
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None


def _worker_command() -> tuple[str, list[str]]:
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable)
        if sys.platform == "win32":
            # Windowed PyInstaller executables do not expose standard streams.
            executable = executable.with_name("chemvas-cli.exe")
        return str(executable), []
    return sys.executable, ["-m", "chemvas"]
