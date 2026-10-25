# Linux user installation

[한국어](README.ko.md)

Extract the tar.gz and run from the extracted directory:

```bash
bash install.sh
~/.local/bin/chemvas --version
```

No sudo or Python is needed to install the frozen application. Ubuntu requires
`shared-mime-info` and `desktop-file-utils` for its registration databases.
The target desktop is Ubuntu 24.04 x86_64 GNOME (Wayland and X11 are tested
separately). A WSL command-line check does not certify that desktop.

The installer owns `$XDG_DATA_HOME/chemvas` (default `~/.local/share/chemvas`),
a `~/.local/bin/chemvas` symlink, and user desktop, MIME and icon registrations.
It uses an absolute desktop launch path, so the application menu does not depend
on PATH. Add `~/.local/bin` to PATH if you want to type `chemvas` in a terminal.
It advertises CDXML support without changing your default application.
Spaces and Unicode in paths are supported; control characters and `=`/`%` in HOME
or XDG_DATA_HOME are rejected before installation.

The application directory is reserved for installed files. Save documents
elsewhere. To remove (use the same XDG_DATA_HOME as at installation):

```bash
bash "${XDG_DATA_HOME:-$HOME/.local/share}/chemvas/uninstall.sh" --uninstall
```

Removal preserves documents and Qt settings outside the application directory,
and preserves desktop/icon/MIME entries or launcher links replaced since install.
No existing files are overwritten. To update, close Chemvas, uninstall the owned
version and install the new package. An interrupted installation can be removed
using the same command before retrying. If a killed installer leaves
`$XDG_DATA_HOME/.chemvas-install.lock`, remove that empty directory only after
confirming no installer is running. Do not run installation or removal concurrently.

## Build

Use standalone CPython 3.13 (not Conda) on Linux x86_64:

```bash
python3 -m venv .venv-package
.venv-package/bin/python -m pip install . PyInstaller==6.22.2
PYTHON_BIN="$PWD/.venv-package/bin/python" bash packaging/linux/build.sh dist/linux-candidate
```

The output directory must be new. It contains the frozen bundle, an installable
package directory and a tar.gz. The build requires wheel-supplied PyQt6, Qt, sip
and Pillow license files in the bundle. Their presence does not replace release
licensing review. Run the release acceptance checklist before distributing.

If interruption occurs before the receipt is written, removal refuses the unowned
empty application directory. Use `rmdir` on that empty directory, then retry.
