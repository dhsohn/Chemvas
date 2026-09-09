from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from chemvas import __version__
from chemvas.bootstrap import application

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _help_commands(output: str) -> set[str]:
    _, commands = output.split("Headless commands:\n", maxsplit=1)
    return {line.split()[0] for line in commands.splitlines() if line.startswith("  ")}


@pytest.mark.parametrize(
    ("flag", "expected_output", "exact"),
    [
        ("--help", "Run with no arguments to launch the desktop app.", False),
        ("-h", "Run with no arguments to launch the desktop app.", False),
        ("--version", f"chemvas {__version__}\n", True),
    ],
)
def test_root_metadata_exits_zero_without_importing_qt(
    flag: str, expected_output: str, exact: bool, tmp_path: Path
) -> None:
    poison_package = tmp_path / "PyQt6"
    poison_package.mkdir()
    (poison_package / "__init__.py").write_text(
        "raise AssertionError('root metadata imported PyQt6')\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(APP_ROOT)))

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            flag,
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if exact:
        assert result.stdout == expected_output
    else:
        assert expected_output in result.stdout


def test_root_help_lists_compose_document(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["chemvas", "--help"])

    with pytest.raises(SystemExit) as error:
        application.main()

    assert error.value.code == 0
    assert "compose-document" in _help_commands(capsys.readouterr().out)


def test_root_help_lists_check_layout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["chemvas", "--help"])

    with pytest.raises(SystemExit) as error:
        application.main()

    assert error.value.code == 0
    assert "check-layout" in _help_commands(capsys.readouterr().out)


def test_root_help_inventory_matches_dispatched_headless_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["chemvas", "--help"])

    with pytest.raises(SystemExit) as error:
        application.main()

    assert error.value.code == 0
    dispatched_commands = {
        command for command, _description in application.HEADLESS_SUBCOMMAND_HELP
    }
    assert _help_commands(capsys.readouterr().out) == dispatched_commands
    assert dispatched_commands == (
        application.DOCUMENT_PATCH_COMMANDS
        | application.DOCUMENT_COMPOSITION_COMMANDS
        | application.DOCUMENT_LAYOUT_COMMANDS
        | application.SCHEME_LAYOUT_COMMANDS
        | application.DOCUMENT_TEMPLATE_COMMANDS
        | application.DOCUMENT_RENDER_COMMANDS
        | application.CALCULATION_BUNDLE_COMMANDS
    )


def test_template_command_dispatches_to_headless_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chemvas.bootstrap import document_template

    seen: list[list[str]] = []

    def run(argv: list[str]) -> int:
        seen.append(argv)
        return 7

    monkeypatch.setattr(document_template, "run", run)
    monkeypatch.setattr(sys, "argv", ["chemvas", "insert-template", "--help"])
    with pytest.raises(SystemExit) as error:
        application.main()
    assert error.value.code == 7
    assert seen == [["insert-template", "--help"]]


@pytest.mark.parametrize(
    ("argument", "expected"),
    [
        ("drawing.chemvas", "drawing.chemvas"),
        ("drawing.CHEMVAS", "drawing.CHEMVAS"),
        ("drawing.svg", "drawing.svg"),
        ("structure.mol", "structure.mol"),
        ("structure.MOL", "structure.MOL"),
        ("legacy.json", None),
        ("collection.sdf", None),
        ("coordinates.xyz", None),
        ("--structure.mol", None),
    ],
)
def test_startup_document_path_uses_only_public_document_suffixes(
    argument: str, expected: str | None
) -> None:
    assert (
        application._startup_document_path(["chemvas", "--platform", argument])
        == expected
    )


def test_startup_document_path_preserves_first_supported_path() -> None:
    assert (
        application._startup_document_path(
            [
                "chemvas",
                "--style",
                "Fusion",
                "legacy.json",
                "my structure.mol",
                "next.svg",
            ]
        )
        == "my structure.mol"
    )


@pytest.mark.parametrize(
    "argument",
    [
        "--help",
        "-h",
        "--version",
        "render",
        *dict(application.HEADLESS_SUBCOMMAND_HELP),
    ],
)
def test_windows_gui_rejects_console_commands_before_dispatch(
    argument: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PyQt6 import QtWidgets

    notices: list[str] = []
    monkeypatch.setattr(QtWidgets.QApplication, "instance", lambda: object())
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "information",
        lambda _parent, _title, message: notices.append(message),
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["chemvas.exe", argument])
    with monkeypatch.context() as no_console:
        no_console.setattr(sys, "stdout", None)
        with pytest.raises(SystemExit) as error:
            application.main()
    assert error.value.code == 2
    assert len(notices) == 1
    assert "chemvas-cli.exe" in notices[0]


def test_startup_path_keeps_windows_unicode_spaces_and_ampersand() -> None:
    path = "C:/그림 폴더/OH & OMe 구조.CHEMVAS"
    assert application._startup_document_path(["chemvas.exe", path]) == path


@pytest.mark.parametrize("arguments", [["render", "--help"], ["typo"], ["legacy.json"]])
def test_unknown_command_exits_without_importing_qt(
    arguments: list[str], tmp_path: Path
) -> None:
    poison_package = tmp_path / "PyQt6"
    poison_package.mkdir()
    (poison_package / "__init__.py").write_text(
        "raise AssertionError('invalid command imported PyQt6')\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(APP_ROOT)))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from chemvas.bootstrap.application import main; main()",
            *arguments,
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert f"unrecognized argument: {arguments[0]}" in result.stderr
    assert "chemvas --help" in result.stderr
    assert "imported PyQt6" not in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        ["--unknown"],
        ["drawing.chemvas", "--unknown"],
        ["-platform", "offscreen", "render", "--help"],
        ["--structure.mol"],
    ],
)
def test_unknown_arguments_do_not_create_windows_or_restore_sessions(
    arguments: list[str],
) -> None:
    script = textwrap.dedent("""
        from chemvas.bootstrap import application, window_registry
        from chemvas.ui import session_recovery_service
        def forbidden():
            raise AssertionError('invalid arguments reached desktop state')
        window_registry.open_new_window = forbidden
        session_recovery_service.create_session_recovery_service = forbidden
        application.main()
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_ROOT)
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script, *arguments],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, result.stderr
    assert "unrecognized argument:" in result.stderr
    assert "chemvas --help" in result.stderr
    assert "reached desktop state" not in result.stderr


@pytest.mark.parametrize(
    "document", [None, "그림 폴더/OH & OMe.MOL", "drawing.svg", "drawing.CHEMVAS"]
)
def test_qt_options_are_consumed_before_desktop_document_selection(
    document: str | None,
) -> None:
    script = textwrap.dedent("""
        import sys
        from types import SimpleNamespace
        from PyQt6.QtWidgets import QApplication
        from chemvas.bootstrap import application, file_open, window_registry
        from chemvas.core import rdkit_adapter
        from chemvas.ui import session_recovery_service
        expected = sys.argv[5:]
        opened = []
        def desktop_boundary(app):
            assert sys.argv[1:] == expected, (sys.argv[1:], expected)
            assert app.style().objectName() == 'fusion'
            assert opened == expected[:1], (opened, expected[:1])
            raise SystemExit(7)
        QApplication.exec = desktop_boundary
        window_registry.open_new_window = lambda: object()
        file_open.open_document = opened.append
        session_recovery_service.create_session_recovery_service = lambda: SimpleNamespace(
            restore_previous=lambda window: None, start=lambda app: None)
        rdkit_adapter.warm_rdkit_in_background = lambda: None
        application.main()
    """)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_ROOT)
    env["QT_QPA_PLATFORM"] = "offscreen"
    arguments = ["-platform", "offscreen", "-style", "Fusion"]
    if document is not None:
        arguments.append(document)
    result = subprocess.run(
        [sys.executable, "-c", script, *arguments],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )
    assert result.returncode == 7, result.stderr
