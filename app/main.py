import os
import sys
import threading
from contextlib import contextmanager
from typing import Iterator


IGNORED_STDERR_SUBSTRINGS = (
    "TSM AdjustCapsLockLEDForKeyTransitionHandling",
    "error messaging the mach port for IMKCFRunLoopWakeUpReliable",
    "qt.qpa.keymapper: Mismatch between Cocoa",
)


def _should_filter_stderr(platform: str | None = None) -> bool:
    return (platform or sys.platform) == "darwin"


def _stderr_filter_loop(
    read_fd: int,
    write_fd: int,
    ignored_substrings: tuple[str, ...] = IGNORED_STDERR_SUBSTRINGS,
) -> None:
    with os.fdopen(read_fd, "r", buffering=1) as reader, os.fdopen(write_fd, "w", buffering=1) as writer:
        for line in reader:
            if any(fragment in line for fragment in ignored_substrings):
                continue
            writer.write(line)
            writer.flush()


@contextmanager
def _filtered_stderr(stderr_fd: int = 2, platform: str | None = None) -> Iterator[None]:
    if not _should_filter_stderr(platform):
        yield
        return

    restore_stderr_fd = os.dup(stderr_fd)
    forward_stderr_fd = os.dup(stderr_fd)
    read_fd, write_fd = os.pipe()
    thread = threading.Thread(target=_stderr_filter_loop, args=(read_fd, forward_stderr_fd), daemon=True)
    os.dup2(write_fd, stderr_fd)
    os.close(write_fd)
    thread.start()
    try:
        yield
    finally:
        os.dup2(restore_stderr_fd, stderr_fd)
        os.close(restore_stderr_fd)
        thread.join(timeout=1.0)


def main() -> None:
    with _filtered_stderr():
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication([])
        window = MainWindow()
        window.show()
        app.exec()


if __name__ == "__main__":
    main()
