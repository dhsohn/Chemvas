# Windows distribution preparation

[한국어](README.ko.md)

This is a local, unsigned Windows build path, not a published desktop release.
The Python package remains the released distribution. Build on 64-bit Windows
with Python 3.12+; PyInstaller is not a Windows cross-compiler on Linux or macOS.

## Build

Use a fresh Windows checkout or copy of the source and a dedicated environment.
Do not build through a WSL UNC path or modify an existing application environment.
Install [Inno Setup 6](https://jrsoftware.org/isdl.php) and verify its publisher
signature. Its `/PORTABLE=1` mode can keep the compiler in a dedicated directory.
Keep the compiler directory intact, including DLLs and signature files.

From PowerShell in the source directory:

```powershell
py -3.13 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install ".[rdkit]" -r packaging\windows\requirements-build.txt
.\packaging\windows\build.ps1 -Python .\.venv-windows\Scripts\python.exe -Iscc 'C:\Tools\Inno Setup 6\ISCC.exe'
```

The script uses the supplied tools; it does not install packages or alter PATH.
It writes a new output directory for each build and prints its locations. The
application version comes from `chemvas.__version__`; making a local installer
does not create a release or change that version.

The outputs contain:

- `chemvas.exe`: desktop drawing and document opening, without a console window.
- `chemvas-cli.exe`: the same application with console output for document
  commands, `--help`, and `--version`.
- A setup `.exe` containing the application folder and its runtime dependencies.

Use the installer, or keep the **entire** application folder together. Copying
just `chemvas.exe` is not sufficient. This Windows installer build requires
the RDKit extra for SMILES and 3D features. Drawing-only installations without
RDKit remain available through the Python package, not this installer path.

## Install and open drawings

The installer installs for the current user, without requesting administrator
privileges, under `%LOCALAPPDATA%\Programs\Chemvas`, with a Start menu shortcut.
It registers Chemvas as an application for `.chemvas` drawings. It does not
replace an existing default application or edit Windows' protected `UserChoice`.

On the first double-click, Windows may ask which application to use. Choose
**Chemvas** and **Always**. Alternatively, use **Open with > Choose another app**
or Windows **Settings > Apps > Default apps**. This one-time selection is owned
by Windows, not forced by the installer.

Re-running setup updates that per-user installation. Close Chemvas before an
update. Uninstall through Windows' Installed apps or the installed uninstaller.
Uninstall removes installed program files and Chemvas' registrations, not saved
drawings or recovery data. It does not replace your drawing files with examples.

The application opens the first supported document argument. Reopening a file
in one process activates its existing window; launching another executable
creates a separate process. Cross-process single-instance routing is not part of
this first installer.

## Acceptance before a public release

Run `make check` for the source changes, then test the actual Windows artifacts:

1. Run `chemvas-cli.exe --version` and `--help`; inspect and render a public
   `.chemvas` example from outside the source directory.
2. Run the desktop and open a drawing whose path contains spaces and non-ASCII
   characters. Verify the canvas, icon, save, and reopening the saved copy.
3. Install, open the drawing using Windows' file association, then rerun setup.
   Check an existing alternative default is preserved.
4. Uninstall. Check that Chemvas registrations and installed executables are
   removed and the saved drawing remains unchanged.
5. For an RDKit-enabled build, insert SMILES and exercise 3D/export as well.

Source checks do not substitute for Windows installation or visual acceptance.
The executable is unsigned at this stage. Signing and testing on a clean
Windows machine remain release work; do not disable Windows security protections
to make an unsigned test pass.

Chemvas' source license remains MIT. Bundled dependencies have their own terms:
in particular, [PyQt is GPLv3 or commercially licensed](https://riverbankcomputing.com/commercial/pyqt).
Before distributing binaries, review the exact dependency versions, license
notices and corresponding-source obligations, and provide the required materials.
Bundling a license file alone is not a claim that those obligations are fulfilled.
