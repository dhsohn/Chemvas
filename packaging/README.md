# Packaging Assets

[한국어](README.ko.md)

Platform icons and desktop bundling configurations generated from [`app/chemvas/assets/icon/chemvas.svg`](../app/chemvas/assets/icon/chemvas.svg).

| File | Target |
| --- | --- |
| `icons/chemvas.icns` | macOS `.app` bundle icon |
| `icons/chemvas.ico` | Windows executable / installer icon |
| `icons/chemvas-1024.png` | High-resolution master raster |

## Regenerating Icons

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_icons.py
```

## Desktop Bundle (PyInstaller)

Build a standalone desktop executable using [`chemvas.spec`](chemvas.spec):

```bash
python -m pip install -e ".[rdkit]" pyinstaller   # rdkit optional
pyinstaller packaging/chemvas.spec
```

Output is placed in `dist/Chemvas.app` (macOS) or `dist/chemvas/` (Windows/Linux).

## Windows Installer

See the [Windows build guide](windows/README.md) for building the standalone Inno Setup installer.

## Linux Desktop Integration

Register desktop icons and `.chemvas` MIME associations:

```bash
xdg-mime install --novendor packaging/linux/chemvas.xml
xdg-icon-resource install --context mimetypes --size 256 \
  app/chemvas/assets/icon/chemvas-256.png application-x-chemvas
install -Dm644 app/chemvas/assets/icon/chemvas-256.png \
  ~/.local/share/icons/hicolor/256x256/apps/chemvas.png
desktop-file-install --dir="$HOME/.local/share/applications" packaging/linux/chemvas.desktop
update-desktop-database ~/.local/share/applications
```
