from __future__ import annotations

import os
import subprocess
import sys
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
    assert _help_commands(capsys.readouterr().out) == set(
        application.HEADLESS_SUBCOMMANDS
    )
    assert set(application.HEADLESS_SUBCOMMANDS) == (
        application.DOCUMENT_PATCH_COMMANDS
        | application.DOCUMENT_COMPOSITION_COMMANDS
        | application.DOCUMENT_LAYOUT_COMMANDS
        | application.DOCUMENT_RENDER_COMMANDS
        | application.CALCULATION_BUNDLE_COMMANDS
    )


@pytest.mark.parametrize(
    ("argument", "expected"),
    [
        ("drawing.chemvas", "drawing.chemvas"),
        ("drawing.CHEMVAS", "drawing.CHEMVAS"),
        ("drawing.svg", "drawing.svg"),
        ("legacy.json", None),
    ],
)
def test_startup_document_path_uses_only_public_document_suffixes(
    argument: str, expected: str | None
) -> None:
    assert (
        application._startup_document_path(["chemvas", "--platform", argument])
        == expected
    )
