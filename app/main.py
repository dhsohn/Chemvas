from chemvas import main as _chemvas_main

IGNORED_STDERR_SUBSTRINGS = _chemvas_main.IGNORED_STDERR_SUBSTRINGS
sys = _chemvas_main.sys
_filtered_stderr = _chemvas_main._filtered_stderr
_should_filter_stderr = _chemvas_main._should_filter_stderr
_stderr_filter_loop = _chemvas_main._stderr_filter_loop


def main() -> None:
    with _filtered_stderr():
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow

        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        app.exec()


if __name__ == "__main__":
    main()
