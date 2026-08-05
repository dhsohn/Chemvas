from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chemvas.bootstrap import document_render as cli
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    LEGACY_CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def application() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    app.setQuitOnLastWindowClosed(False)
    return app


def _state(*, far_x: float = 18.0) -> dict[str, object]:
    return {
        "model": serialize_model_state(
            MoleculeModel(
                atoms={0: Atom("C", 0.0, 0.0), 1: Atom("O", far_x, 0.0)},
                bonds=[Bond(0, 1)],
            )
        ),
        "ring_fills": [],
        "notes": [{"text": "render", "x": 3.0, "y": 18.0}],
        "marks": [],
        "arrows": [],
        "ts_brackets": [],
        "orbitals": [],
        "settings": serialize_settings(
            bond_length_px=18.0,
            arrow_line_width=1.5,
            arrow_head_scale=0.4,
            orbital_phase_enabled=True,
            text_font_size=13,
            text_font_weight=600,
            text_italic=False,
            sheet_size="A4",
            sheet_orientation="portrait",
        ),
        "last_smiles_input": None,
    }


def _write_source(
    path: Path,
    *,
    state: dict[str, object] | None = None,
    version: int = CANVAS_FILE_VERSION,
) -> bytes:
    write_document(path, state or _state(), version)
    return path.read_bytes()


@pytest.mark.parametrize("output_format", ["svg", "png"])
def test_render_is_byte_deterministic_and_reports_exact_hashes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    first = tmp_path / f"first.{output_format}"
    second = tmp_path / f"second.{output_format}"

    assert (
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(first),
                "--background",
                "transparent",
                "--dpi",
                "300",
            ]
        )
        == 0
    )
    first_report = json.loads(capsys.readouterr().out)
    assert (
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(second),
                "--background",
                "transparent",
                "--dpi",
                "300",
            ]
        )
        == 0
    )
    second_report = json.loads(capsys.readouterr().out)

    assert source.read_bytes() == source_bytes
    assert first.read_bytes() == second.read_bytes()
    output_hash = hashlib.sha256(first.read_bytes()).hexdigest()
    assert set(first_report) == {
        "background",
        "chemvas_document_version",
        "dpi",
        "format",
        "graphics_records",
        "height_pixels",
        "height_points",
        "output",
        "output_bytes",
        "output_format",
        "output_sha256",
        "source",
        "source_sha256",
        "version",
        "width_pixels",
        "width_points",
        "written",
    }
    assert first_report["format"] == "chemvas-document-render-report"
    assert first_report["version"] == 1
    assert first_report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert first_report["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert first_report["output_sha256"] == output_hash
    assert second_report["output_sha256"] == output_hash
    assert first_report["output_bytes"] == len(first.read_bytes())
    assert first_report["written"] is True
    assert first_report["background"] == "transparent"
    assert first_report["graphics_records"] == 4
    assert first_report["width_points"] > 0
    assert first_report["height_points"] > 0

    if output_format == "svg":
        assert b"<svg" in first.read_bytes()
        assert b"<path" in first.read_bytes()
        assert b">render</text>" in first.read_bytes()
        assert b"chemvas-svg-source" not in first.read_bytes()
        assert first_report["dpi"] is None
        assert first_report["width_pixels"] is None
        assert first_report["height_pixels"] is None
    else:
        image = QImage(str(first))
        assert not image.isNull()
        assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert image.width() == first_report["width_pixels"]
        assert image.height() == first_report["height_pixels"]
        assert first_report["dpi"] == 300


def test_default_white_png_and_legacy_document_render(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "legacy.chemvas"
    _write_source(source, version=LEGACY_CANVAS_FILE_VERSION)
    output = tmp_path / "legacy.png"

    assert cli.run(["render-document", str(source), "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)

    image = QImage(str(output))
    assert report["chemvas_document_version"] == LEGACY_CANVAS_FILE_VERSION
    assert report["background"] == "white"
    assert image.pixelColor(0, 0).alpha() == 255


def test_empty_document_and_extreme_geometry_publish_nothing(
    tmp_path: Path,
) -> None:
    empty_state = _state()
    empty_state["model"] = serialize_model_state(MoleculeModel())
    empty_state["notes"] = []
    empty = tmp_path / "empty.chemvas"
    _write_source(empty, state=empty_state)
    huge = tmp_path / "huge.chemvas"
    _write_source(huge, state=_state(far_x=1_000_000.0))

    for source, name in ((empty, "empty.svg"), (huge, "huge.png")):
        output = tmp_path / name
        with pytest.raises(SystemExit) as error:
            cli.run(["render-document", str(source), "--output", str(output)])
        assert error.value.code == 2
        assert not output.exists()
        assert not list(tmp_path.glob(f".{output.name}.staging-*"))


def test_source_and_graphics_limits_fail_before_render(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "limited.svg"

    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(source_bytes) - 1)
    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])
    assert error.value.code == 2
    assert not output.exists()

    monkeypatch.setattr(cli, "MAX_DOCUMENT_BYTES", len(source_bytes))
    monkeypatch.setattr(cli, "MAX_GRAPHICS_RECORDS", 1)
    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])
    assert error.value.code == 2
    assert not output.exists()


def test_rendered_output_limit_leaves_no_final_or_staging_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "too-large.svg"
    monkeypatch.setattr(cli, "MAX_OUTPUT_BYTES", 1)

    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])

    assert error.value.code == 2
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


def test_existing_file_directory_and_symlink_outputs_are_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    targets = [
        tmp_path / "file.svg",
        tmp_path / "directory.svg",
        tmp_path / "link.svg",
    ]
    targets[0].write_text("keep")
    targets[1].mkdir()
    targets[2].symlink_to(tmp_path / "missing")

    for target in targets:
        with pytest.raises(SystemExit) as error:
            cli.run(["render-document", str(source), "--output", str(target)])
        assert error.value.code == 2
    assert targets[0].read_text() == "keep"
    assert targets[1].is_dir()
    assert targets[2].is_symlink()


def test_atomic_publish_rejects_target_created_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "raced.svg"
    original_atomic_create = cli.atomic_create_bytes

    def race_create(path: Path, content: bytes) -> None:
        path.write_text("racer owns this path")
        original_atomic_create(path, content)

    monkeypatch.setattr(cli, "atomic_create_bytes", race_create)

    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])

    assert error.value.code == 2
    assert output.read_text() == "racer owns this path"
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


@pytest.mark.parametrize(
    ("source_name", "output_name"),
    [
        ("source.json", "output.svg"),
        ("source.chemvas", "output.pdf"),
        ("source.chemvas", "missing/output.svg"),
    ],
)
def test_invalid_paths_are_rejected(
    tmp_path: Path,
    source_name: str,
    output_name: str,
) -> None:
    source = tmp_path / source_name
    source.write_text("{}")
    output = tmp_path / output_name

    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])

    assert error.value.code == 2
    assert not output.exists()


def test_module_import_is_qt_and_rdkit_free_until_rendering() -> None:
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    app_root = Path(__file__).resolve().parents[1] / "app"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(app_root), pythonpath) if value
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import chemvas.bootstrap.document_render; "
                "assert not any(name == 'PyQt6' or name.startswith('PyQt6.') "
                "for name in sys.modules); "
                "assert not any(name == 'rdkit' or name.startswith('rdkit.') "
                "for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_python_module_entrypoint_renders_without_desktop_startup(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "entrypoint.svg"
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH")
    app_root = Path(__file__).resolve().parents[1] / "app"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(app_root), pythonpath) if value
    )
    env["QT_QPA_PLATFORM"] = "deliberately-invalid-platform"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chemvas",
            "render-document",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert output.is_file()
    assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["output_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


def test_rendering_does_not_load_rdkit_or_leave_visible_windows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    application: QApplication,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "output.svg"
    rdkit_modules_before = {
        name for name in sys.modules if name == "rdkit" or name.startswith("rdkit.")
    }

    assert cli.run(["render-document", str(source), "--output", str(output)]) == 0
    capsys.readouterr()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()

    assert not any(widget.isVisible() for widget in application.topLevelWidgets())
    rdkit_modules_after = {
        name for name in sys.modules if name == "rdkit" or name.startswith("rdkit.")
    }
    assert rdkit_modules_after == rdkit_modules_before
    assert "chemvas.ui.session_recovery_service" not in sys.modules
