import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import main as app_main


class MainStderrFilterTest(unittest.TestCase):
    def _capture_stderr_output(self, platform: str, lines: list[str]) -> str:
        original_stderr_fd = os.dup(2)
        capture_read_fd, capture_write_fd = os.pipe()
        capture_read_closed = False
        try:
            os.dup2(capture_write_fd, 2)
            os.close(capture_write_fd)
            with app_main._filtered_stderr(platform=platform):
                for line in lines:
                    os.write(2, line.encode("utf-8"))
            os.dup2(original_stderr_fd, 2)
            with os.fdopen(capture_read_fd, "r", encoding="utf-8") as capture_reader:
                output = capture_reader.read()
            capture_read_closed = True
            return output
        finally:
            os.dup2(original_stderr_fd, 2)
            os.close(original_stderr_fd)
            if not capture_read_closed:
                os.close(capture_read_fd)

    def test_filtered_stderr_suppresses_known_macos_noise(self) -> None:
        output = self._capture_stderr_output(
            platform="darwin",
            lines=[
                "visible line\n",
                "TSM AdjustCapsLockLEDForKeyTransitionHandling noise\n",
                "second visible line\n",
            ],
        )

        self.assertIn("visible line", output)
        self.assertIn("second visible line", output)
        self.assertNotIn("TSM AdjustCapsLockLEDForKeyTransitionHandling", output)

    def test_filtered_stderr_is_noop_outside_macos(self) -> None:
        output = self._capture_stderr_output(
            platform="linux",
            lines=["qt.qpa.keymapper: Mismatch between Cocoa should remain visible\n"],
        )

        self.assertIn("qt.qpa.keymapper: Mismatch between Cocoa should remain visible", output)


if __name__ == "__main__":
    unittest.main()
