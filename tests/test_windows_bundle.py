"""Bundle construction contracts; native Windows build/GUI checks run separately."""

from __future__ import annotations

import json
import platform
import re
import struct
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "chemvas.spec"
BUILD = ROOT / "packaging" / "windows" / "build.ps1"


def _module(monkeypatch, name, **attributes):
    module = ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _spec(monkeypatch, target="win32", version="2.3.4"):
    calls = []
    metadata = []

    def constructor(kind):
        def record(*args, **kwargs):
            result = SimpleNamespace(kind=kind, args=args, kwargs=kwargs)
            if kind == "Analysis":
                for attr in (
                    "pure",
                    "zipped_data",
                    "scripts",
                    "binaries",
                    "zipfiles",
                    "datas",
                ):
                    setattr(result, attr, [attr])
            calls.append(result)
            return result

        return record

    def copy_metadata(name, *, recursive):
        metadata.append((name, recursive))
        return [(f"/{name}.dist-info", f"{name}.dist-info")]

    monkeypatch.setattr(sys, "platform", target)
    monkeypatch.setattr(sys, "path", list(sys.path))
    _module(monkeypatch, "chemvas", __version__=version)
    _module(monkeypatch, "PyInstaller.utils.hooks", copy_metadata=copy_metadata)
    _module(
        monkeypatch,
        "PyInstaller.utils.win32.versioninfo",
        **{
            name: constructor(name)
            for name in (
                "FixedFileInfo",
                "StringFileInfo",
                "StringStruct",
                "StringTable",
                "VarFileInfo",
                "VarStruct",
                "VSVersionInfo",
            )
        },
    )
    namespace = {
        "SPECPATH": str(SPEC.parent),
        **{
            name: constructor(name)
            for name in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE")
        },
    }
    exec(compile(SPEC.read_text(), str(SPEC), "exec"), namespace)
    return calls, metadata


def test_windows_executables_share_one_analysis_archive_and_dependency_tree(
    monkeypatch,
):
    calls, metadata = _spec(monkeypatch)
    analyses = [call for call in calls if call.kind == "Analysis"]
    archives = [call for call in calls if call.kind == "PYZ"]
    executables = [call for call in calls if call.kind == "EXE"]
    collections = [call for call in calls if call.kind == "COLLECT"]
    assert len(analyses) == len(archives) == len(collections) == 1
    assert [(item.kwargs["name"], item.kwargs["console"]) for item in executables] == [
        ("chemvas", False),
        ("chemvas-cli", True),
    ]
    assert all(item.args[0] is archives[0] for item in executables)
    assert all(item.args[1] is analyses[0].scripts for item in executables)
    assert all(item.args[2] == [("X utf8=1", None, "OPTION")] for item in executables)
    assert executables[0].args[2] is executables[1].args[2]
    assert collections[0].args[:2] == tuple(executables)
    assert collections[0].kwargs["name"] == "chemvas"
    assert all(item.kwargs["exclude_binaries"] for item in executables)
    assert all(item.kwargs["upx"] is False for item in executables)
    assert metadata == [("PyQt6", True), ("Pillow", True), ("rdkit", True)]
    data = analyses[0].kwargs["datas"]
    assert (str(ROOT / "LICENSE"), ".") in data
    assert (str(ROOT / "app/chemvas/assets/icon"), "chemvas/assets/icon") in data
    assert all(Path(item.kwargs["icon"]).is_file() for item in executables)


def test_windows_file_and_product_versions_come_from_source(monkeypatch):
    calls, _ = _spec(monkeypatch, version="31.47.59")
    info = next(call for call in calls if call.kind == "FixedFileInfo")
    assert info.kwargs["filevers"] == info.kwargs["prodvers"] == (31, 47, 59, 0)
    strings = [call.args for call in calls if call.kind == "StringStruct"]
    assert ("FileVersion", "31.47.59") in strings
    assert ("ProductVersion", "31.47.59") in strings
    version_info = next(call for call in calls if call.kind == "VSVersionInfo")
    assert all(
        call.kwargs["version"] is version_info for call in calls if call.kind == "EXE"
    )


@pytest.mark.parametrize(
    "version", ["1.2.3rc1", "1.2", "1.2.3.4", "1.2.-3", "65536.2.3"]
)
def test_unsupported_windows_version_fails_before_build(monkeypatch, version):
    with pytest.raises(ValueError, match="Windows"):
        _spec(monkeypatch, version=version)


@pytest.mark.parametrize("target", ["linux", "darwin"])
def test_other_platform_bundle_shape_is_preserved(monkeypatch, target):
    calls, metadata = _spec(monkeypatch, target=target)
    executables = [call for call in calls if call.kind == "EXE"]
    assert len(executables) == 1
    assert executables[0].kwargs["name"] == "chemvas"
    assert executables[0].args[2] == []
    assert "version" not in executables[0].kwargs
    assert metadata == []
    bundle = next(call for call in calls if call.kind == "BUNDLE")
    assert bundle.kwargs["info_plist"]["CFBundleDocumentTypes"][0][
        "CFBundleTypeExtensions"
    ] == ["chemvas"]


def _run_environment_probe(
    monkeypatch, capsys, *, target="win32", machine="AMD64", bits=8, builder="6.22.2"
):
    source = re.search(r"\$Probe = @'\n(.*?)\n'@", BUILD.read_text(), re.DOTALL).group(
        1
    )
    monkeypatch.setattr(sys, "platform", target)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(sys, "argv", ["-c", str(ROOT / "app")])
    monkeypatch.setattr(platform, "machine", lambda: machine)
    monkeypatch.setattr(struct, "calcsize", lambda _: bits)
    _module(monkeypatch, "PyInstaller", __version__=builder)
    _module(monkeypatch, "PIL", __version__="12.0.0")
    _module(monkeypatch, "rdkit", __version__="2026.03.1")
    _module(
        monkeypatch, "PyQt6.QtCore", PYQT_VERSION_STR="6.11.0", QT_VERSION_STR="6.11.2"
    )
    _module(
        monkeypatch,
        "chemvas",
        __version__="2.3.4",
        __file__=str(ROOT / "app/chemvas/__init__.py"),
    )
    exec(compile(source, "build.ps1 environment probe", "exec"), {})
    return json.loads(capsys.readouterr().out)


def test_prepared_environment_probe_reports_explicit_source_and_versions(
    monkeypatch, capsys
):
    result = _run_environment_probe(monkeypatch, capsys)
    assert result["version"] == "2.3.4"
    assert result["source"] == str(ROOT / "app/chemvas/__init__.py")
    assert result["pyinstaller"] == "6.22.2"


@pytest.mark.parametrize(
    "options",
    [
        {"target": "linux"},
        {"machine": "ARM64"},
        {"bits": 4},
        {"builder": "6.0"},
    ],
)
def test_environment_probe_rejects_unsupported_native_targets(
    monkeypatch, capsys, options
):
    with pytest.raises(SystemExit):
        _run_environment_probe(monkeypatch, capsys, **options)


def test_build_script_has_fresh_outputs_and_checks_before_installer():
    script = BUILD.read_text()
    assert "[Parameter(Mandatory = $true)][string]$Python" in script
    assert "[Parameter(Mandatory = $true)][string]$Iscc" in script
    assert "[Guid]::NewGuid()" in script
    assert "Remove-Item" not in script
    assert "pip install" not in script
    assert (
        "'-m', 'PyInstaller', '--workpath', $WorkDir, '--distpath', $DistDir, $Spec"
        in script
    )
    assert script.index("-LogStem (Join-Path $WorkDir 'version')") < script.index(
        "-LogStem (Join-Path $WorkDir 'installer')"
    )
    assert (
        '"/DAppVersion=$Version", "/DBundleDir=$BundleDir", "/DOutputDir=$InstallerDir"'
        in script
    )
    assert "Get-FileHash -LiteralPath $Artifact -Algorithm SHA256" in script
    assert (
        "PyInstaller==6.22.2" in (BUILD.parent / "requirements-build.txt").read_text()
    )


def test_native_steps_wait_for_real_exit_and_capture_both_streams():
    script = BUILD.read_text()
    assert "$LASTEXITCODE" not in script
    assert "$StartInfo.UseShellExecute = $false" in script
    assert "$StartInfo.RedirectStandardOutput = $true" in script
    assert "$StartInfo.RedirectStandardError = $true" in script
    assert script.index("$Process.StandardOutput.ReadToEndAsync()") < script.index(
        "$Process.WaitForExit("
    )
    assert script.index("$Process.StandardError.ReadToEndAsync()") < script.index(
        "$Process.WaitForExit("
    )
    assert "$Process.ExitCode -ne 0" in script
    assert "$Process.Kill()" in script
    assert "'environment-probe.py'" in script
    assert "@('-I', '-B', $ProbePath, $AppDir)" in script
    assert r"""[regex]::Replace($Value, '(\\*)"' """.strip() in script
