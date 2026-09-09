from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from chemvas.bootstrap import document_render as cli
from chemvas.core.document_io import write_document
from chemvas.domain.document import (
    CANVAS_FILE_VERSION,
    Atom,
    Bond,
    MoleculeModel,
    serialize_model_state,
    serialize_settings,
)
from chemvas.ui.canvas_document_session_service import CanvasDocumentSessionService


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
        "shapes": [],
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
@pytest.mark.parametrize("null_graphics", [False, True])
def test_empty_graphics_measure_atoms_and_null_graphics_remain_invalid(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
    null_graphics: bool,
) -> None:
    state = _state()
    for key in (
        "notes",
        "marks",
        "arrows",
        "ts_brackets",
        "shapes",
        "orbitals",
        "ring_fills",
    ):
        state[key] = []
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source, state=state)
    output = tmp_path / f"native.{output_format}"
    if null_graphics:
        payload = json.loads(source_bytes)
        payload["state"]["notes"] = None
        source_bytes = json.dumps(payload).encode()
        source.write_bytes(source_bytes)
        with pytest.raises(SystemExit) as error:
            cli.run(
                [
                    "render-document",
                    str(source),
                    "--output",
                    str(output),
                    "--min-font-pt",
                    "1",
                ]
            )
        assert error.value.code == 2
        assert "Invalid Chemvas file" in capsys.readouterr().err
        assert not output.exists()
        assert source.read_bytes() == source_bytes
        return
    assert (
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--min-font-pt",
                "1",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["graphics_records"] == 3
    assert report["font_readability"]["coverage"]["atom"]["glyphs"] == 1
    assert "note" not in report["font_readability"]["coverage"]
    assert source.read_bytes() == source_bytes


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
        assert b"<text" not in first.read_bytes()
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


def test_default_white_png_and_current_document_render(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "current.chemvas"
    _write_source(source, version=CANVAS_FILE_VERSION)
    output = tmp_path / "current.png"

    assert cli.run(["render-document", str(source), "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)

    image = QImage(str(output))
    assert report["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert report["background"] == "white"
    assert image.pixelColor(0, 0).alpha() == 255


@pytest.mark.parametrize("output_format", ["svg", "png"])
def test_width_uses_shared_export_size_and_preserves_aspect_ratio(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    default_output = tmp_path / f"default.{output_format}"
    sized_output = tmp_path / f"sized.{output_format}"
    assert (
        cli.run(["render-document", str(source), "--output", str(default_output)]) == 0
    )
    default_report = json.loads(capsys.readouterr().out)
    assert (
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(sized_output),
                "--width-mm",
                "25.4",
                "--max-height-mm",
                "100",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert set(report) == set(default_report)
    assert report["width_points"] == 72.0
    assert report["height_points"] / report["width_points"] == pytest.approx(
        default_report["height_points"] / default_report["width_points"], abs=1e-6
    )
    assert source.read_bytes() == source_bytes
    if output_format == "svg":
        svg = ET.fromstring(sized_output.read_bytes())
        assert svg.attrib["width"] == "25.4mm"
        view_box = [float(value) for value in svg.attrib["viewBox"].split()]
        assert view_box[2] == 72.0
        assert view_box[3] == pytest.approx(report["height_points"], abs=1e-3)
    else:
        image = QImage(str(sized_output))
        assert image.width() == report["width_pixels"] == 300
        assert image.height() == report["height_pixels"]

    with cli.offscreen_canvas(_state(), command="test-render") as (_, service):
        gui_default = tmp_path / f"gui-default.{output_format}"
        gui_sized = tmp_path / f"gui-sized.{output_format}"
        service.export_figure(str(gui_default), fmt=output_format, background="white")
        service.export_figure(
            str(gui_sized), fmt=output_format, background="white", target_width_mm=25.4
        )
    assert default_output.read_bytes() == gui_default.read_bytes()
    assert sized_output.read_bytes() == gui_sized.read_bytes()


@pytest.mark.parametrize("option", ["--width-mm", "--max-height-mm", "--min-font-pt"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf", "1e309", "bad"])
def test_invalid_physical_options_fail_before_canvas_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    option: str,
    value: str,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / "invalid.svg"

    def unexpected_canvas(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid physical option reached canvas creation")

    monkeypatch.setattr(cli, "offscreen_canvas", unexpected_canvas)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                f"{option}={value}",
            ]
        )
    assert error.value.code == 2
    assert "positive finite number" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("width", [0.0, -1.0, float("nan"), float("inf")])
def test_direct_service_rejects_invalid_width_for_plan_and_export(
    tmp_path: Path, width: float
) -> None:
    output = tmp_path / "invalid.svg"
    with cli.offscreen_canvas(_state(), command="test-render") as (_, service):
        with pytest.raises(ValueError, match="target width must be a positive finite"):
            service.plan_figure_export(target_width_mm=width)
        with pytest.raises(ValueError, match="target width must be a positive finite"):
            service.export_figure(str(output), target_width_mm=width)
    assert not output.exists()


@pytest.mark.parametrize("output_format", ["svg", "png"])
def test_font_guard_reports_coverage_without_changing_output_bytes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    output_format: str,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    first = tmp_path / f"plain.{output_format}"
    checked = tmp_path / f"checked.{output_format}"
    cli.run(["render-document", str(source), "--output", str(first)])
    plain = json.loads(capsys.readouterr().out)
    cli.run(
        ["render-document", str(source), "--output", str(checked), "--min-font-pt", "1"]
    )
    report = json.loads(capsys.readouterr().out)
    assert "font_readability" not in plain
    assert set(report) == set(plain) | {"font_readability"}
    assert first.read_bytes() == checked.read_bytes()
    assert source.read_bytes() == source_bytes
    assert report["font_readability"]["status"] == "passed"
    assert report["font_readability"]["minimum_font_pt"] >= 1
    assert report["font_readability"]["coverage"]["atom"]["glyphs"] == 1
    assert report["font_readability"]["coverage"]["note"]["glyphs"] == 6


def test_font_guard_rejects_before_publication_and_reports_minimum_witness(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "too-small.svg"

    def unexpected_publication(*args: object, **kwargs: object) -> None:
        pytest.fail("undersized text reached output publication")

    monkeypatch.setattr(cli, "atomic_create_bytes", unexpected_publication)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--min-font-pt",
                "100",
            ]
        )
    message = capsys.readouterr().err
    assert error.value.code == 2
    assert "minimum visible font is" in message
    assert "below --min-font-pt 100" in message
    assert "'kind': 'atom', 'id': 1" in message
    assert source.read_bytes() == source_bytes
    assert not output.exists()


def test_default_export_does_not_invoke_font_measurement(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from chemvas.ui import export_readability_service

    def unexpected_measurement(*args: object, **kwargs: object) -> None:
        pytest.fail("default export reached optional font measurement")

    monkeypatch.setattr(
        export_readability_service, "assess_export_readability", unexpected_measurement
    )
    source = tmp_path / "source.chemvas"
    _write_source(source)
    assert (
        cli.run(
            ["render-document", str(source), "--output", str(tmp_path / "plain.svg")]
        )
        == 0
    )
    assert "font_readability" not in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("output_format", "options", "message"),
    [
        ("svg", ["--width-mm", "25.4", "--max-height-mm", "1"], "height exceeds"),
        ("png", ["--max-height-mm", "0.001"], "height exceeds"),
        ("svg", ["--width-mm", "6000"], "points per side"),
        ("png", ["--width-mm", "500", "--dpi", "1200"], "PNG render exceeds"),
    ],
)
def test_physical_size_limits_fail_before_painting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    output_format: str,
    options: list[str],
    message: str,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / f"limited.{output_format}"

    def unexpected_export(*args: object, **kwargs: object) -> None:
        pytest.fail("over-budget physical size reached painting")

    monkeypatch.setattr(
        CanvasDocumentSessionService, "export_figure", unexpected_export
    )
    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output), *options])
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert source.read_bytes() == source_bytes
    assert not output.exists()
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


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


@pytest.mark.parametrize("output_format", ["svg", "pdf"])
def test_existing_file_and_directory_outputs_are_preserved(
    tmp_path: Path, output_format: str
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    targets = [
        tmp_path / f"file.{output_format}",
        tmp_path / f"directory.{output_format}",
    ]
    targets[0].write_text("keep")
    targets[1].mkdir()

    for target in targets:
        with pytest.raises(SystemExit) as error:
            cli.run(["render-document", str(source), "--output", str(target)])
        assert error.value.code == 2
    assert targets[0].read_text(encoding="utf-8") == "keep"
    assert targets[1].is_dir()


@pytest.mark.parametrize("output_format", ["svg", "pdf"])
def test_existing_symlink_output_is_preserved(
    tmp_path: Path, output_format: str
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / f"link.{output_format}"
    try:
        output.symlink_to(tmp_path / "missing")
    except OSError as exc:
        if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows symlink creation requires developer privileges")
        raise

    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])

    assert error.value.code == 2
    assert output.is_symlink()


@pytest.mark.parametrize("output_format", ["svg", "pdf"])
def test_atomic_publish_rejects_target_created_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_format: str,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / f"raced.{output_format}"
    original_atomic_create = cli.atomic_create_bytes

    def race_create(path: Path, content: bytes) -> None:
        path.write_text("racer owns this path")
        original_atomic_create(path, content)

    monkeypatch.setattr(cli, "atomic_create_bytes", race_create)

    with pytest.raises(SystemExit) as error:
        cli.run(["render-document", str(source), "--output", str(output)])

    assert error.value.code == 2
    assert output.read_text(encoding="utf-8") == "racer owns this path"
    assert not list(tmp_path.glob(f".{output.name}.staging-*"))


@pytest.mark.parametrize(
    ("source_name", "output_name"),
    [
        ("source.json", "output.svg"),
        ("source.chemvas", "output.webp"),
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


@pytest.mark.parametrize("output_format", ["png", "pdf"])
def test_python_module_entrypoint_renders_without_desktop_startup(
    tmp_path: Path, output_format: str
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / f"entrypoint.{output_format}"
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
            "--background",
            "white",
            "--dpi",
            "300",
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
    if sys.platform == "win32":
        # Offscreen QPA rendered the note as square placeholders and expanded
        # this fixture to 95.74 points.
        assert report["width_points"] < 72.0


@pytest.mark.parametrize("output_format", ["svg", "pdf"])
def test_rendering_does_not_load_rdkit_or_leave_visible_windows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    application: QApplication,
    output_format: str,
) -> None:
    source = tmp_path / "source.chemvas"
    _write_source(source)
    output = tmp_path / f"output.{output_format}"
    rdkit_modules_before = {
        name for name in sys.modules if name == "rdkit" or name.startswith("rdkit.")
    }
    recovery_module_was_loaded = "chemvas.ui.session_recovery_service" in sys.modules

    assert cli.run(["render-document", str(source), "--output", str(output)]) == 0
    capsys.readouterr()
    application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents()

    assert not any(widget.isVisible() for widget in application.topLevelWidgets())
    rdkit_modules_after = {
        name for name in sys.modules if name == "rdkit" or name.startswith("rdkit.")
    }
    assert rdkit_modules_after == rdkit_modules_before
    assert (
        "chemvas.ui.session_recovery_service" in sys.modules
    ) is recovery_module_was_loaded


def _pdf_page_size(content: bytes) -> tuple[float, float]:
    media_box = re.search(rb"/MediaBox\s*\[0\s+0\s+([\d.]+)\s+([\d.]+)\]", content)
    assert media_box is not None
    return float(media_box[1]), float(media_box[2])


@pytest.mark.parametrize("background", ["white", "transparent"])
@pytest.mark.parametrize("dpi", [150, 600])
def test_pdf_is_one_vector_page_with_exact_report_and_requested_width(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    background: str,
    dpi: int,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "figure.pdf"
    assert (
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--background",
                background,
                "--dpi",
                str(dpi),
                "--width-mm",
                "25.4",
                "--max-height-mm",
                "100",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    content = output.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", content)) == 1
    assert not re.search(rb"/Subtype\s*/Image\b", content)
    assert b"/FlateDecode" in content
    streams = re.findall(
        rb"/Filter /FlateDecode\s*>>\s*stream\r?\n(.*?)\r?\nendstream",
        content,
        re.DOTALL,
    )
    decoded = [zlib.decompress(stream) for stream in streams]
    assert any(re.search(rb"[\d.]+ [\d.]+ m\s", stream) for stream in decoded)
    width, height = _pdf_page_size(content)
    assert width == pytest.approx(72.0, abs=0.01)
    assert height == pytest.approx(report["height_points"], abs=0.01)
    assert report["width_points"] == 72.0
    assert report["format"] == "chemvas-document-render-report"
    assert report["version"] == 1
    assert report["output_format"] == "pdf"
    assert report["background"] == background
    assert report["dpi"] == dpi
    assert report["width_pixels"] is None
    assert report["height_pixels"] is None
    assert report["output_bytes"] == len(content)
    assert report["output_sha256"] == hashlib.sha256(content).hexdigest()
    assert report["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert report["chemvas_document_version"] == CANVAS_FILE_VERSION
    assert report["written"] is True
    assert source.read_bytes() == source_bytes


def test_pdf_height_limit_rejects_before_export(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "too-tall.pdf"

    def unexpected_export(*args: object, **kwargs: object) -> None:
        pytest.fail("over-height PDF reached painting")

    monkeypatch.setattr(
        CanvasDocumentSessionService, "export_figure", unexpected_export
    )
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--width-mm",
                "25.4",
                "--max-height-mm",
                "0.1",
            ]
        )
    assert error.value.code == 2
    assert "height exceeds --max-height-mm" in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == source_bytes


def test_pdf_minimum_font_option_fails_before_canvas_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "unsupported-font-check.pdf"

    def unexpected_canvas(*args: object, **kwargs: object) -> None:
        pytest.fail("unsupported PDF font option reached canvas creation")

    monkeypatch.setattr(cli, "offscreen_canvas", unexpected_canvas)
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--min-font-pt",
                "6",
            ]
        )
    assert error.value.code == 2
    assert "--min-font-pt supports SVG and PNG" in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == source_bytes


def test_pdf_height_limit_includes_native_page_rounding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.chemvas"
    source_bytes = _write_source(source)
    output = tmp_path / "rounded-page.pdf"
    with cli.offscreen_canvas(_state(), command="test-pdf-rounding") as (_, service):
        plan = service.plan_figure_export(scope="sheet", sizing="bond")
    # Choose a width that makes the planned height 64.8 pt; Qt writes 65 pt.
    width_mm = plan.out_w_pt / plan.out_h_pt * 64.8 / 72 * 25.4
    height_limit_mm = 64.9 / 72 * 25.4

    def unexpected_export(*args: object, **kwargs: object) -> None:
        pytest.fail("rounded PDF page over the height limit reached painting")

    monkeypatch.setattr(
        CanvasDocumentSessionService, "export_figure", unexpected_export
    )
    with pytest.raises(SystemExit) as error:
        cli.run(
            [
                "render-document",
                str(source),
                "--output",
                str(output),
                "--width-mm",
                str(width_mm),
                "--max-height-mm",
                str(height_limit_mm),
            ]
        )
    assert error.value.code == 2
    assert "height exceeds --max-height-mm" in capsys.readouterr().err
    assert not output.exists()
    assert source.read_bytes() == source_bytes
