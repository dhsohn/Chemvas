from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from chemvas.bootstrap import application

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
VALUE_OPTIONS = (
    "platform",
    "platformpluginpath",
    "platformtheme",
    "plugin",
    "qwindowgeometry",
    "qwindowicon",
    "qwindowtitle",
    "session",
    "display",
    "geometry",
    "title",
    "icon",
    "name",
    "visual",
    "style",
    "stylesheet",
    "qmljsdebugger",
)
FLAG_OPTIONS = (
    "reverse",
    "widgetcount",
    "nograb",
    "dograb",
    "testability",
    "qdevel",
    "qdebug",
)


@pytest.mark.parametrize("prefix", ["-", "--"])
@pytest.mark.parametrize("option", VALUE_OPTIONS)
@pytest.mark.parametrize("value", ["-draft", "--"])
def test_current_qt_value_options_preserve_the_next_argument(
    prefix: str, option: str, value: str
) -> None:
    # Qt consumes the next token even when it looks like an option or document.
    arguments = [prefix + option, value, "actual.svg"]
    original = list(arguments)
    application._validate_desktop_arguments(arguments)
    assert arguments == original


@pytest.mark.parametrize("prefix", ["-", "--"])
def test_qt_value_options_require_a_value(prefix: str) -> None:
    with pytest.raises(SystemExit) as error:
        application._validate_desktop_arguments([prefix + "platform"])
    assert error.value.code == 2


@pytest.mark.parametrize("prefix", ["-", "--"])
@pytest.mark.parametrize("option", FLAG_OPTIONS)
def test_current_qt_flag_options_are_forwarded(prefix: str, option: str) -> None:
    application._validate_desktop_arguments([prefix + option, "actual.chemvas"])


@pytest.mark.parametrize("prefix", ["-", "--"])
@pytest.mark.parametrize("option", ["style", "stylesheet", "qmljsdebugger"])
def test_qt_accepts_empty_equals_values(prefix: str, option: str) -> None:
    application._validate_desktop_arguments([prefix + option + "="])


def test_macos_finder_argument_is_only_forwarded_on_macos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for platform in ("linux", "win32"):
        monkeypatch.setattr(sys, "platform", platform)
        with pytest.raises(SystemExit) as error:
            application._validate_desktop_arguments(["-psn_0_12345"])
        assert error.value.code == 2
    monkeypatch.setattr(sys, "platform", "darwin")
    application._validate_desktop_arguments(["-psn_0_12345", "actual.mol"])


def _desktop_process(
    tmp_path: Path, arguments: list[str], expected_documents: list[str]
) -> subprocess.CompletedProcess[str]:
    script = textwrap.dedent("""
        import json, os, sys
        from types import SimpleNamespace
        from PyQt6.QtWidgets import QApplication
        from chemvas.bootstrap import application, file_open, window_registry
        from chemvas.ui.session import session_recovery_service
        expected = json.loads(os.environ['EXPECTED_DOCUMENTS'])
        opened = []
        def desktop_boundary(app):
            assert app.platformName() == 'offscreen'
            assert sys.argv[1:] == expected, (sys.argv[1:], expected)
            assert opened == expected[:1], (opened, expected)
            print('desktop reached with exact document arguments')
            raise SystemExit(7)
        def open_window():
            print('window requested')
            return object()
        QApplication.exec = desktop_boundary
        window_registry.open_new_window = open_window
        file_open.open_document = opened.append
        session_recovery_service.create_session_recovery_service = lambda **_: SimpleNamespace(
            restore_previous=lambda window: None, start=lambda app: None)
        application.main()
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_ROOT)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["EXPECTED_DOCUMENTS"] = json.dumps(expected_documents)
    for key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        env[key] = str(tmp_path / key)
    return subprocess.run(
        [sys.executable, "-c", script, "-platform", "offscreen", *arguments],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "option_groups",
    [
        pytest.param(
            [
                ["-qmljsdebugger", "port:0"],
                ["--qmljsdebugger", "-draft"],
                ["-stylesheet", "-missing.qss"],
                ["--style", "-missing"],
                ["-platformtheme", "-missing"],
                ["-plugin", "-missing"],
                ["-qwindowicon", "-missing.png"],
                ["-qwindowgeometry", "-10-20"],
                ["-qwindowtitle", "--"],
                ["-qwindowtitle", "not-the-document.chemvas"],
            ],
            id="value-options",
        ),
        pytest.param(
            [
                ["-qmljsdebugger="],
                ["-style="],
                ["--stylesheet="],
                ["-testability"],
                ["--qdevel", "-qdebug"],
                ["-reverse", "--widgetcount"],
            ],
            id="flags-and-empty-values",
        ),
    ],
)
def test_real_qt_consumes_supported_options_before_document_selection(
    tmp_path: Path, option_groups: list[list[str]]
) -> None:
    # Qt parses argv once, so one process checks a whole family of options: any
    # token Qt leaves behind is rejected or breaks the exact document arguments.
    options = [token for group in option_groups for token in group]
    documents = ["./-그림 & OH.chemvas", "./--style=Fusion.svg"]
    result = _desktop_process(tmp_path, [*options, *documents], documents)
    assert result.returncode == 7, result.stderr
    assert "desktop reached with exact document arguments" in result.stdout


@pytest.mark.parametrize(
    "options",
    [
        ["-nograb"],
        ["-title", "title.chemvas"],
        ["-display", ":0"],
    ],
)
def test_backend_specific_options_left_by_qt_cannot_become_documents(
    tmp_path: Path, options: list[str]
) -> None:
    # Xcb options are not consumed by offscreen. The second validation boundary
    # must reject them before any window/session or accidental document opening.
    result = _desktop_process(tmp_path, [*options, "actual.chemvas"], [])
    assert result.returncode == 2, result.stderr
    assert "unrecognized argument:" in result.stderr
    assert "window requested" not in result.stdout


@pytest.mark.parametrize(
    "arguments",
    [
        ["-font", "sans"],
        ["-fn", "sans"],
        ["-ncols", "256"],
        ["-cmap"],
        ["-im", "none"],
        ["-inputstyle", "onthespot"],
        ["--", "-style=Fusion.chemvas"],
        ["-name=title"],
        ["-bogus.chemvas"],
        ["-name", "title", "--bogus"],
    ],
)
def test_unsupported_options_and_sentinel_are_rejected_before_qt(
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Any Qt import during main() fails, so only rejection before Qt passes.
    for name in ["PyQt6", *(name for name in sys.modules if name.startswith("PyQt6."))]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(sys, "argv", ["chemvas", *arguments])
    with pytest.raises(SystemExit) as error:
        application.main()
    assert error.value.code == 2
    assert "unrecognized argument:" in capsys.readouterr().err


def test_rejected_option_never_loads_qt_in_a_fresh_process(tmp_path: Path) -> None:
    poison_package = tmp_path / "PyQt6"
    poison_package.mkdir()
    (poison_package / "__init__.py").write_text(
        "raise AssertionError('invalid argument imported Qt')\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(APP_ROOT)))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            "-name",
            "title",
            "--bogus",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, result.stderr
    assert "unrecognized argument:" in result.stderr
    assert "invalid argument imported Qt" not in result.stderr
