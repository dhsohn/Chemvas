"""Exercise the delivered shell installer against disposable user directories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux user installer")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def installation(tmp_path):
    package = tmp_path / "package space"
    package.mkdir()
    for name in ("install.sh", "chemvas.desktop", "chemvas.xml"):
        shutil.copy2(ROOT / "packaging/linux" / name, package / name)
    (package / "chemvas.png").write_bytes(b"icon")
    (package / "chemvas/_internal").mkdir(parents=True)
    binary = package / "chemvas/chemvas"
    binary.write_text('#!/bin/sh\nprintf "fixture executable\\n"\n')
    binary.chmod(0o755)
    home = tmp_path / "한글 home"
    home.mkdir()
    data = home / "custom data"
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("update-mime-database", "update-desktop-database"):
        tool = tools / name
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(data))
    env["PATH"] = f"{tools}:/usr/bin:/bin"
    return package, home, data, env


def run(installation, *args):
    package, _, _, env = installation
    return subprocess.run(
        ["bash", str(package / "install.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_launch_uninstall_preserves_documents_settings_and_default(
    installation,
):
    _, home, data, env = installation
    document = home / "문서.cdxml"
    document.write_text("user document")
    settings = home / ".config/Chemvas/settings.ini"
    settings.parent.mkdir(parents=True)
    settings.write_text("user settings")
    defaults = home / ".config/mimeapps.list"
    defaults.write_text("existing defaults")
    result = run(installation)
    assert result.returncode == 0, result.stderr
    launcher = home / ".local/bin/chemvas"
    assert (
        subprocess.check_output([str(launcher)], env=env, text=True).strip()
        == "fixture executable"
    )
    desktop = (data / "applications/chemvas.desktop").read_text()
    assert f'Exec="{data}/chemvas/app/chemvas" %f' in desktop
    # Exercise the retained removal entry point after the downloaded package is gone.
    shutil.rmtree(installation[0])
    result = subprocess.run(
        ["bash", str(data / "chemvas/uninstall.sh"), "--uninstall"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not (data / "chemvas").exists()
    assert not launcher.is_symlink()
    assert not (data / "applications/chemvas.desktop").exists()
    assert not (data / "mime/packages/chemvas.xml").exists()
    assert document.read_text() == "user document"
    assert settings.read_text() == "user settings"
    assert defaults.read_text() == "existing defaults"


@pytest.mark.parametrize("conflict", ["payload", "launcher", "desktop", "mime", "icon"])
def test_install_refuses_foreign_paths_before_mutation(installation, conflict):
    _, home, data, _ = installation
    target = {
        "payload": data / "chemvas",
        "launcher": home / ".local/bin/chemvas",
        "desktop": data / "applications/chemvas.desktop",
        "mime": data / "mime/packages/chemvas.xml",
        "icon": data / "icons/hicolor/256x256/apps/chemvas.png",
    }[conflict]
    target.parent.mkdir(parents=True)
    target.write_text("foreign file")
    assert run(installation).returncode != 0
    assert target.read_text() == "foreign file"
    assert not (data / "chemvas/.chemvas-install-v1").exists()


def test_uninstall_preserves_replaced_integration(installation):
    _, home, data, _ = installation
    assert run(installation).returncode == 0
    desktop = data / "applications/chemvas.desktop"
    desktop.write_text("another application")
    launcher = home / ".local/bin/chemvas"
    launcher.unlink()
    launcher.symlink_to("/some/other/program")
    assert run(installation, "--uninstall").returncode == 0
    assert desktop.read_text() == "another application"
    assert os.readlink(launcher) == "/some/other/program"


def test_uninstall_refuses_symlink_payload(installation):
    _, home, data, _ = installation
    data.mkdir()
    (data / "chemvas").symlink_to(home, target_is_directory=True)
    assert run(installation, "--uninstall").returncode != 0
    assert home.is_dir()


def test_reinstall_requires_removal_and_then_succeeds(installation):
    assert run(installation).returncode == 0
    assert run(installation).returncode != 0
    assert run(installation, "--uninstall").returncode == 0
    assert run(installation).returncode == 0


def test_desktop_escapes_exec_metacharacters(installation):
    _, _, _, env = installation
    data = Path(env["XDG_DATA_HOME"] + ' $cash`quote"slash\\semicolon;')
    env["XDG_DATA_HOME"] = str(data)
    result = run(installation)
    assert result.returncode == 0, result.stderr
    desktop = (data / "applications/chemvas.desktop").read_text()
    assert '\\\\$cash\\\\`quote\\\\"slash\\\\\\\\semicolon;' in desktop


@pytest.mark.parametrize(
    "bad",
    [
        "relative",
        "/tmp/equals=path",
        "/tmp/percent%path",
        "/tmp/new\nline",
        "/tmp/tab\tpath",
    ],
)
def test_rejects_unsupported_install_paths(installation, bad):
    installation[3]["XDG_DATA_HOME"] = bad
    result = run(installation)
    assert result.returncode != 0
    assert "absolute HOME/XDG_DATA_HOME" in result.stderr


def test_partial_payload_with_receipt_is_removable(installation):
    _, _, data, env = installation
    # Inject a copy failure after receipt creation, rather than synthesize state.
    tools = Path(env["PATH"].split(":")[0])
    cp = tools / "cp"
    cp.write_text(
        '#!/bin/sh\nif [ "$1" = "-a" ]; then exit 17; fi\nexec /bin/cp "$@"\n'
    )
    cp.chmod(0o755)
    assert run(installation).returncode == 17
    assert (data / "chemvas/.chemvas-install-v1").is_file()
    assert run(installation, "--uninstall").returncode == 0
    assert not (data / "chemvas").exists()
    cp.unlink()
    assert run(installation).returncode == 0


def test_orphan_empty_root_refused_with_safe_recovery_message(installation):
    _, _, data, _ = installation
    (data / "chemvas").mkdir(parents=True)
    result = run(installation, "--uninstall")
    assert result.returncode != 0
    assert "rmdir" in result.stderr
    assert (data / "chemvas").is_dir()


@pytest.mark.parametrize(
    "relative", ["mime/packages/chemvas.xml", "icons/hicolor/256x256/apps/chemvas.png"]
)
def test_uninstall_preserves_modified_mime_and_icon(installation, relative):
    _, _, data, _ = installation
    assert run(installation).returncode == 0
    f = data / relative
    f.write_bytes(b"replacement")
    assert run(installation, "--uninstall").returncode == 0
    assert f.read_bytes() == b"replacement"


@pytest.mark.parametrize("missing", [None, "pyqt6", "pyqt6_qt6", "pyqt6_sip", "pillow"])
def test_build_notice_gate_rejects_each_missing_distribution(tmp_path, missing):
    # A similarly named ancestor must not satisfy the dist-info basename match.
    fixture = tmp_path / "pyqt6-output" / "fixture"
    fixture.mkdir(parents=True)
    binary = fixture / "chemvas"
    binary.write_text('#!/bin/sh\necho "chemvas 9.9.9"\n')
    binary.chmod(0o755)
    for name in ("pyqt6", "pyqt6_qt6", "pyqt6_sip", "pillow"):
        if name == missing:
            continue
        metadata = fixture / "_internal" / f"{name.upper()}-1.0.dist-info/licenses"
        metadata.mkdir(parents=True)
        (metadata / "LICENSE").write_text("upstream notice")
    python = tmp_path / "python-stub"
    python.write_text(
        "#!/bin/bash\nset -eu\n"
        "if [[ $1 == -c ]]; then\n"
        '  if [[ $2 == *"from chemvas"* ]]; then echo 9.9.9; fi\n'
        "  exit 0\nfi\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  if [[ $1 == --distpath ]]; then target=$2; break; fi\n"
        "  shift\ndone\n"
        'mkdir -p "$target"\ncp -a "$NOTICE_FIXTURE" "$target/chemvas"\n'
    )
    python.chmod(0o755)
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "packaging/linux/build.sh"),
            str(tmp_path / "pyqt6-output/result"),
        ],
        env=dict(os.environ, PYTHON_BIN=str(python), NOTICE_FIXTURE=str(fixture)),
        text=True,
        capture_output=True,
        check=False,
    )
    if missing is None:
        assert result.returncode == 0, result.stderr
        assert (
            tmp_path / "pyqt6-output/result/Chemvas-9.9.9-linux-x86_64.tar.gz"
        ).is_file()
    else:
        assert result.returncode != 0
        assert f"Missing notice: {missing}" in result.stderr
        assert not list((tmp_path / "pyqt6-output/result").glob("*.tar.gz"))
