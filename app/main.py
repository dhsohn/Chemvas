import os
import threading

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main() -> None:
    def _stderr_filter_loop(read_fd: int, write_fd: int) -> None:
        with os.fdopen(read_fd, "r", buffering=1) as reader, os.fdopen(write_fd, "w", buffering=1) as writer:
            for line in reader:
                if "TSM AdjustCapsLockLEDForKeyTransitionHandling" in line:
                    continue
                if "error messaging the mach port for IMKCFRunLoopWakeUpReliable" in line:
                    continue
                writer.write(line)

    original_stderr_fd = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)
    thread = threading.Thread(target=_stderr_filter_loop, args=(read_fd, original_stderr_fd), daemon=True)
    thread.start()

    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
