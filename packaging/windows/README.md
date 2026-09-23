# Windows Distribution Preparation

[한국어](README.ko.md)

Instructions for building a standalone Windows installer using PyInstaller and Inno Setup on 64-bit Windows.

## Build Requirements

- 64-bit Windows with Python 3.12+
- [Inno Setup 6](https://jrsoftware.org/isdl.php)

From PowerShell in the repository root:

```powershell
py -3.13 -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install ".[rdkit]" -r packaging\windows\requirements-build.txt
.\packaging\windows\build.ps1 -Python .\.venv-windows\Scripts\python.exe -Iscc 'C:\Tools\Inno Setup 6\ISCC.exe'
```

### Build Outputs

- `chemvas.exe`: GUI desktop application (windowed).
- `chemvas-cli.exe`: Command-line executable for terminal usage and scripting.
- Output installer executable (`Output/Chemvas-Setup-*.exe`).

## Installation & File Association

The installer sets up Chemvas in `%LOCALAPPDATA%\Programs\Chemvas` for the current user (no administrator privileges required) and registers file associations for `.chemvas` documents.
