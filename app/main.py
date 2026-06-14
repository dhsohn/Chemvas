from chemvas import main as _chemvas_main

IGNORED_STDERR_SUBSTRINGS = _chemvas_main.IGNORED_STDERR_SUBSTRINGS
_filtered_stderr = _chemvas_main._filtered_stderr
_should_filter_stderr = _chemvas_main._should_filter_stderr
_stderr_filter_loop = _chemvas_main._stderr_filter_loop
main = _chemvas_main.main


if __name__ == "__main__":
    main()
