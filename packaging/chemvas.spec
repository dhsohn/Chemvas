# PyInstaller spec for Chemvas — a one-folder GUI bundle with the app icon and,
# on macOS, a .app that claims the .chemvas document type.
#
#   python -m pip install pyinstaller
#   pyinstaller packaging/chemvas.spec
#
# Output: dist/Chemvas.app (macOS) or dist/chemvas/ (Windows/Linux).

import sys
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent
APP_DIR = REPO_ROOT / "app"
ICON_DIR = APP_DIR / "chemvas" / "assets" / "icon"
PACKAGING_ICONS = REPO_ROOT / "packaging" / "icons"

# Single-source the version from chemvas.__version__ (same value pyproject reads).
sys.path.insert(0, str(APP_DIR))
from chemvas import __version__ as CHEMVAS_VERSION

executable_icon = str(PACKAGING_ICONS / ("chemvas.ico" if sys.platform == "win32" else "chemvas.icns"))

a = Analysis(
    [str(APP_DIR / "main.py")],
    pathex=[str(APP_DIR)],
    binaries=[],
    datas=[(str(ICON_DIR), "chemvas/assets/icon")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chemvas",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=executable_icon,
)
coll = COLLECT(
    exe,
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
