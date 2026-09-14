from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.subprocess_support import source_subprocess_env


@pytest.mark.parametrize("ambient", ["absent", "foreign"])
def test_python_child_imports_this_checkout_without_ambient_source_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ambient: str
) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    if ambient == "foreign":
        foreign = tmp_path / "foreign"
        package = foreign / "chemvas"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("IS_FOREIGN = True\n", encoding="utf-8")
        monkeypatch.setenv("PYTHONPATH", str(foreign))
    before = dict(os.environ)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, chemvas; print(json.dumps(chemvas.__file__))",
        ],
        env=source_subprocess_env(),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    imported = Path(json.loads(completed.stdout)).resolve()
    expected = Path(__file__).resolve().parents[1] / "app" / "chemvas" / "__init__.py"
    assert imported == expected
    assert dict(os.environ) == before


def test_source_environment_preserves_overrides_and_ambient_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient = os.pathsep.join((str(tmp_path / "first"), str(tmp_path / "second")))
    monkeypatch.setenv("PYTHONPATH", ambient)
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    monkeypatch.setenv("CHEMVAS_TEST_ENV", "preserved")
    before = dict(os.environ)
    overrides = {
        "QT_QPA_PLATFORM": "offscreen",
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }
    environment = source_subprocess_env(overrides)
    app_root = str(Path(__file__).resolve().parents[1] / "app")
    assert environment["PYTHONPATH"] == app_root + os.pathsep + ambient
    assert environment["QT_QPA_PLATFORM"] == "offscreen"
    assert environment["XDG_DATA_HOME"] == str(tmp_path / "data")
    assert environment["CHEMVAS_TEST_ENV"] == "preserved"
    assert dict(os.environ) == before
    assert overrides == {
        "QT_QPA_PLATFORM": "offscreen",
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }


def test_source_environment_keeps_explicit_path_override_after_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", "ambient-path")
    override = str(tmp_path / "override")
    environment = source_subprocess_env({"PYTHONPATH": override})
    app_root = str(Path(__file__).resolve().parents[1] / "app")
    assert environment["PYTHONPATH"] == app_root + os.pathsep + override
    assert os.environ["PYTHONPATH"] == "ambient-path"
