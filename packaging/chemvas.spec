# PyInstaller spec for Chemvas — a one-folder GUI bundle with the app icon and,
# on macOS, a .app that claims the .chemvas document type.
#
#   python -m pip install pyinstaller
#   pyinstaller packaging/chemvas.spec
#
# Output: dist/Chemvas.app (macOS) or dist/chemvas/ (Windows/Linux).

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import copy_metadata

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_DIR = REPO_ROOT / "app"
ICON_DIR = APP_DIR / "chemvas" / "assets" / "icon"
PACKAGING_ICONS = REPO_ROOT / "packaging" / "icons"

# Single-source the version from chemvas.__version__ (same value pyproject reads).
sys.path.insert(0, str(APP_DIR))
from chemvas import __version__ as CHEMVAS_VERSION

executable_icon = str(PACKAGING_ICONS / ("chemvas.ico" if sys.platform == "win32" else "chemvas.icns"))

bundle_data = [(str(ICON_DIR), "chemvas/assets/icon"), (str(REPO_ROOT / "LICENSE"), ".")]
windows_version = {}
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo,
        VarStruct, VSVersionInfo,
    )

    if not re.fullmatch(r"\d+\.\d+\.\d+", CHEMVAS_VERSION):
        raise ValueError("Windows bundles require a numeric major.minor.patch source version")
    version_tuple = (*map(int, CHEMVAS_VERSION.split(".")), 0)
    if any(part > 65535 for part in version_tuple):
        raise ValueError("Windows version components must not exceed 65535")
    windows_version["version"] = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=version_tuple, prodvers=version_tuple,
            mask=0x3F, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0),
        ),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Chemvas contributors"),
                StringStruct("FileDescription", "Chemvas chemical drawing editor"),
                StringStruct("FileVersion", CHEMVAS_VERSION),
                StringStruct("ProductName", "Chemvas"),
                StringStruct("ProductVersion", CHEMVAS_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )
    # Preserve notices provided by the installed distributions; this is not a
    # substitute for reviewing the redistribution terms of the resulting bundle.
    for distribution in ("PyQt6", "Pillow", "rdkit"):
        bundle_data.extend(copy_metadata(distribution, recursive=True))

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=bundle_data,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

# Frozen interpreters ignore PYTHONUTF8. Persist UTF-8 mode so redirected CLI
# output containing Unicode document paths is independent of the Windows locale.
interpreter_options = [("X utf8=1", None, "OPTION")] if sys.platform == "win32" else []
exe = EXE(
    pyz,
    a.scripts,
    interpreter_options,
    exclude_binaries=True,
    name="chemvas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=executable_icon,
    **windows_version,
)
executables = [exe]
if sys.platform == "win32":
    # The console companion retains the existing JSON/help/agent CLI. Both
    # executables share one analysis and dependency directory.
    cli = EXE(
        pyz, a.scripts, interpreter_options, exclude_binaries=True, name="chemvas-cli",
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
        console=True, icon=executable_icon, **windows_version,
    )
    executables.append(cli)
coll = COLLECT(
    *executables,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="chemvas",
)

app = BUNDLE(
    coll,
    name="Chemvas.app",
    icon=str(PACKAGING_ICONS / "chemvas.icns"),
    bundle_identifier="com.dhsohn.chemvas",
    version=CHEMVAS_VERSION,
    info_plist={
        "CFBundleName": "Chemvas",
        "CFBundleDisplayName": "Chemvas",
        "CFBundleShortVersionString": CHEMVAS_VERSION,
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Chemvas Drawing",
                "CFBundleTypeExtensions": ["chemvas"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
                "CFBundleTypeIconFile": "chemvas.icns",
            }
        ],
    },
)
