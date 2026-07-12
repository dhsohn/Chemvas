# Packaging assets

Platform icon files for desktop bundles, all generated from the single master
SVG at [`app/chemvas/assets/icon/chemvas.svg`](../app/chemvas/assets/icon/chemvas.svg).

| File | Use |
| --- | --- |
| `icons/chemvas.icns` | macOS `.app` bundle icon (`CFBundleIconFile`) |
| `icons/chemvas.ico` | Windows executable / installer icon |
| `icons/chemvas-1024.png` | Master raster for store listings and docs |

The runtime window/taskbar icon does **not** live here — it is the PNG set in
`app/chemvas/assets/icon/`, which ships inside the wheel and is loaded by
`chemvas.branding.app_icon()`.

## Regenerating

Edit the master SVG, then re-render everything (runtime PNGs, `.icns`, `.ico`):

```bash
QT_QPA_PLATFORM=offscreen python scripts/generate_icons.py
```

Rasterisation goes through Qt's own SVG renderer (the same one the app uses for
toolbar glyphs); `.icns` packing uses macOS `iconutil`, `.ico` packing uses
Pillow. The generated binaries are committed so building a bundle needs no extra
toolchain.

## Building a desktop bundle (PyInstaller)

[`chemvas.spec`](chemvas.spec) wires the icons and, on macOS, an `Info.plist`
that claims the `.chemvas` document type:

```bash
python -m pip install -e ".[rdkit]" pyinstaller   # rdkit optional
pyinstaller packaging/chemvas.spec
```

Output is `dist/Chemvas.app` (macOS) or `dist/chemvas/` (Windows/Linux). Opening
a `.chemvas` file is handled cross-platform: Windows/Linux pass the path in `argv`
(read by `_startup_document_path`), and macOS delivers a `QEvent.FileOpen` that
`chemvas.file_open.FileOpenEventFilter` routes to the loader.

## Linux desktop integration

[`linux/chemvas.desktop`](linux/chemvas.desktop) and
[`linux/chemvas.xml`](linux/chemvas.xml) (the `application/x-chemvas` MIME type)
register the app and its file type. After placing the bundle on `PATH`:

```bash
xdg-mime install --novendor packaging/linux/chemvas.xml
xdg-icon-resource install --context mimetypes --size 256 \
  app/chemvas/assets/icon/chemvas-256.png application-x-chemvas
install -Dm644 app/chemvas/assets/icon/chemvas-256.png \
  ~/.local/share/icons/hicolor/256x256/apps/chemvas.png
desktop-file-install --dir="$HOME/.local/share/applications" packaging/linux/chemvas.desktop
update-desktop-database ~/.local/share/applications
```
